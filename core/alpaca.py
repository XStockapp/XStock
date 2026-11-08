"""
Precios desde Alpaca Market Data (plan gratuito).

* Acciones y ETF: barras históricas SIP (100 % del mercado) hasta hace 16 minutos; el plan
  gratuito no permite consultar SIP más reciente. La vela en curso se completa con el feed IEX
  (tiempo real, solo la bolsa IEX) mediante `latest_bar`.
* Cripto: barras de Alpaca Crypto (24/7, no requieren clave).
* Límite del plan gratuito: 200 llamadas por minuto. Las barras se guardan en una caché en
  memoria con vencimiento (TTL) para no repetir descargas.

Las claves se leen de los secrets ALPACA_API_KEY y ALPACA_SECRET_KEY. Sin claves, `available()`
devuelve False y la capa de datos usa Yahoo Finance.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from .store import secret

BASE = "https://data.alpaca.markets"
NY = "America/New_York"
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}

# Años de historial que se piden por temporalidad (Alpaca tiene datos desde 2016)
YEARS = {"30m": 2, "1h": 3, "4h": 4, "1D": 10, "1W": 11, "1M": 11}
# Vencimiento de la caché en segundos
TTL = {"30m": 120, "1h": 300, "4h": 600, "1D": 900, "1W": 3600, "1M": 3600}


class AlpacaError(Exception):
    pass


def _keys() -> tuple[str, str]:
    return secret("ALPACA_API_KEY"), secret("ALPACA_SECRET_KEY")


def available() -> bool:
    k, s = _keys()
    return bool(k and s)


def _headers() -> dict:
    k, s = _keys()
    h = {"Accept": "application/json"}
    if k and s:
        h.update({"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s})
    return h


def is_crypto(ticker: str) -> bool:
    return ticker.upper().endswith(("-USD", "-USDT", "-EUR"))


def crypto_symbol(ticker: str) -> str:
    """BTC-USD → BTC/USD (formato de Alpaca)."""
    base, _, quote = ticker.upper().partition("-")
    return f"{base}/{quote or 'USD'}"


def stock_symbol(ticker: str) -> str:
    """BRK-B → BRK.B (Alpaca usa punto en las clases de acciones)."""
    return ticker.upper().replace("-", ".")


# ---------------------------------------------------------------- caché en memoria
class _TTLCache:
    def __init__(self, maxsize: int = 96):
        self.maxsize, self._d, self._lock = maxsize, OrderedDict(), threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._d.get(key)
            if not hit or hit[0] < time.time():
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return hit[1]

    def put(self, key, value, ttl: float):
        with self._lock:
            self._d[key] = (time.time() + ttl, value)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()


CACHE = _TTLCache()


# ---------------------------------------------------------------- HTTP
def _get(path: str, params: dict, session: requests.Session | None = None) -> dict:
    s = session or requests
    for attempt in range(3):
        r = s.get(BASE + path, params=params, headers=_headers(), timeout=20)
        if r.status_code == 429:  # límite de 200/min: espera y reintenta
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except Exception:
                msg = r.text
            raise AlpacaError(f"{r.status_code}: {msg}")
        return r.json()
    raise AlpacaError("429: límite de llamadas de Alpaca alcanzado")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _paged(path: str, params: dict) -> dict[str, list]:
    """Descarga todas las páginas de un endpoint de barras multi-símbolo."""
    out: dict[str, list] = {}
    params = dict(params)
    with requests.Session() as s:
        for _ in range(200):
            js = _get(path, params, s)
            for sym, rows in (js.get("bars") or {}).items():
                out.setdefault(sym, []).extend(rows or [])
            tok = js.get("next_page_token")
            if not tok:
                break
            params["page_token"] = tok
    return out


def _frame(rows: list, daily: bool) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=OHLCV)
    df = pd.DataFrame(rows).rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    idx = pd.to_datetime(df["t"], utc=True).dt.tz_convert(NY).dt.tz_localize(None)
    df.index = idx.dt.normalize() if daily else idx
    df = df[OHLCV].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def _regular_session(df: pd.DataFrame) -> pd.DataFrame:
    """Solo la sesión regular 9:30–16:00 (Alpaca también entrega pre y post mercado)."""
    if df.empty:
        return df
    t = df.index.hour * 60 + df.index.minute
    return df[(t >= 570) & (t < 960) & (df.index.dayofweek < 5)]


def resample(df: pd.DataFrame, tf: str, crypto: bool) -> pd.DataFrame:
    if df.empty or tf in ("30m", "1D"):
        return df
    if tf == "1h":
        rule, kw = "1h", ({} if crypto else {"origin": "start_day", "offset": "30min"})
    elif tf == "4h":
        rule, kw = "4h", ({} if crypto else {"origin": "start_day", "offset": "9h30min"})
    elif tf == "1W":
        rule, kw = "W-FRI", {}
    else:  # 1M
        rule, kw = "ME", {}
    out = df.resample(rule, **kw).agg(_AGG).dropna(subset=["Close"])
    if not crypto and tf in ("1h", "4h"):
        out = _regular_session(out)
    return out


def _base_tf(tf: str, crypto: bool) -> str:
    """Temporalidad que se pide a Alpaca; el resto se agrega localmente para alinear las velas
    a la apertura de las 9:30 (Alpaca alinea las horas al reloj)."""
    if tf in ("1D", "1W", "1M"):
        return "1Day"
    if crypto and tf in ("1h", "4h"):
        return "1Hour"
    return "30Min"


# ---------------------------------------------------------------- API pública
def bars(ticker: str, tf: str = "1D", years: float | None = None) -> pd.DataFrame:
    """Historial OHLCV en la temporalidad pedida (30m, 1h, 4h, 1D, 1W, 1M). Lanza AlpacaError."""
    df = batch_bars([ticker], tf, years).get(ticker)
    if df is None or df.empty:
        raise AlpacaError(f"Alpaca no devolvió barras {tf} para {ticker}")
    return df


def batch_bars(tickers: list[str], tf: str = "1D", years: float | None = None) -> dict[str, pd.DataFrame]:
    """Barras de varios símbolos con la menor cantidad de llamadas posible (multi-símbolo + paginación)."""
    years = years or YEARS.get(tf, 5)
    out: dict[str, pd.DataFrame] = {}
    todo = []
    for t in tickers:
        hit = CACHE.get((t, tf, years))
        if hit is not None:
            out[t] = hit
        else:
            todo.append(t)
    stocks = [t for t in todo if not is_crypto(t)]
    cryptos = [t for t in todo if is_crypto(t)]
    now = datetime.now(timezone.utc)
    start = _iso(now - timedelta(days=int(365 * years) + 7))

    if stocks:
        if not available():
            raise AlpacaError("Faltan ALPACA_API_KEY y ALPACA_SECRET_KEY")
        base = _base_tf(tf, False)
        symmap = {stock_symbol(t): t for t in stocks}
        syms = list(symmap)
        for i in range(0, len(syms), 100):  # bloques de 100 símbolos por consulta
            part = syms[i:i + 100]
            params = {"symbols": ",".join(part), "timeframe": base, "start": start, "limit": 10000,
                      "adjustment": "all", "sort": "asc"}
            try:  # SIP (todo el mercado) hasta hace 16 minutos
                raw = _paged("/v2/stocks/bars", {**params, "feed": "sip", "end": _iso(now - timedelta(minutes=16))})
            except AlpacaError as e:
                if "subscription" not in str(e).lower() and not str(e).startswith("403"):
                    raise
                raw = _paged("/v2/stocks/bars", {**params, "feed": "iex"})
            for sym, rows in raw.items():
                t = symmap.get(sym, sym)
                df = _frame(rows, base == "1Day")
                if base == "30Min":
                    df = _regular_session(df)
                df = resample(df, tf, False)
                if len(df):
                    out[t] = df
                    CACHE.put((t, tf, years), df, TTL.get(tf, 600))

    if cryptos:
        base = _base_tf(tf, True)
        symmap = {crypto_symbol(t): t for t in cryptos}
        raw = _paged("/v1beta3/crypto/us/bars", {"symbols": ",".join(symmap), "timeframe": base, "start": start,
                                                 "limit": 10000, "sort": "asc"})
        for sym, rows in raw.items():
            t = symmap.get(sym, sym)
            df = resample(_frame(rows, base == "1Day"), tf, True)
            if len(df):
                out[t] = df
                CACHE.put((t, tf, years), df, TTL.get(tf, 600))
    return out


def latest_bar(ticker: str) -> dict | None:
    """Última barra de 1 minuto en tiempo real (IEX para acciones). Base del gráfico en vivo."""
    if is_crypto(ticker):
        sym = crypto_symbol(ticker)
        js = _get("/v1beta3/crypto/us/latest/bars", {"symbols": sym})
    else:
        sym = stock_symbol(ticker)
        js = _get("/v2/stocks/bars/latest", {"symbols": sym, "feed": "iex"})
    b = (js.get("bars") or {}).get(sym)
    if not b:
        return None
    t = pd.Timestamp(b["t"]).tz_convert(NY).tz_localize(None)
    return {"t": t, "Open": b["o"], "High": b["h"], "Low": b["l"], "Close": b["c"], "Volume": b["v"]}
