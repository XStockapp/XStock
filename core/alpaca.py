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
YEARS = {"10m": 1, "30m": 2, "1h": 3, "4h": 4, "1D": 10, "1W": 11, "1M": 11}
# Vencimiento de la caché en segundos
TTL = {"10m": 60, "30m": 120, "1h": 300, "4h": 600, "1D": 900, "1W": 3600, "1M": 3600}


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
    if df.empty or tf in ("10m", "30m", "1D"):
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
    if tf == "10m":
        return "10Min"  # las 9:30 caen en múltiplo de 10 min: velas ya alineadas a la apertura
    return "30Min"


# ---------------------------------------------------------------- API pública
def bars(ticker: str, tf: str = "1D", years: float | None = None) -> pd.DataFrame:
    """Historial OHLCV en la temporalidad pedida (10m, 30m, 1h, 4h, 1D, 1W, 1M). Lanza AlpacaError."""
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
                if base in ("10Min", "30Min"):
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



# ---------------------------------------------------------------- diagnóstico del plan
def diagnostico() -> list[dict]:
    """Prueba en vivo qué permite la cuenta de Alpaca (sin exponer claves). Cada prueba:
    {prueba, ok (True/False/None), detalle}. ok=None = informativo."""
    out = []

    def add(prueba, ok, detalle):
        out.append({"prueba": prueba, "ok": ok, "detalle": detalle})

    if not available():
        add("Claves configuradas", False, "Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY en el servidor.")
        return out
    add("Claves configuradas", True, "Presentes en el servidor (no se muestran).")
    now = datetime.now(timezone.utc)

    def _try(path, params):
        try:
            r = requests.get(BASE + path, params=params, headers=_headers(), timeout=20)
            return r.status_code, r.headers, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
        except Exception as e:  # red
            return 0, {}, {"message": str(e)[:120]}

    # 1) SIP reciente (prueba la restricción de 15 minutos del plan Basic)
    st, hd, js = _try("/v2/stocks/bars", {"symbols": "SPY", "timeframe": "1Min", "feed": "sip",
                                          "start": _iso(now - timedelta(minutes=10)), "limit": 5})
    lim = hd.get("X-RateLimit-Limit") if hd else None
    if st == 200:
        add("SIP en tiempo real (últimos 15 min)", True, "Permitido: la cuenta tiene el plan Algo Trader Plus.")
    else:
        add("SIP en tiempo real (últimos 15 min)", False,
            f"No permitido (HTTP {st}): plan Basic. El histórico SIP sí funciona hasta hace 15 minutos.")
    # 2) histórico SIP más antiguo
    st, _, js = _try("/v2/stocks/bars", {"symbols": "SPY", "timeframe": "1Day", "feed": "sip",
                                         "start": "2015-01-01T00:00:00Z", "limit": 1, "sort": "asc"})
    rows = (js.get("bars") or {}).get("SPY") or []
    add("Histórico diario más antiguo (SIP)", bool(rows),
        f"Desde {rows[0]['t'][:10]}" if rows else f"Sin datos (HTTP {st}).")
    # 3) límite de llamadas por minuto
    add("Límite de llamadas por minuto", None, f"{lim} llamadas/min" if lim else "Alpaca no informó el límite.")
    # 4) opciones: feed OPRA vs indicative
    st, _, js = _try("/v1beta1/options/snapshots/SPY", {"feed": "opra", "limit": 1})
    if st == 200:
        add("Opciones · feed OPRA", True, "Permitido: cotizaciones reales del mercado de opciones.")
    else:
        st2, _, _ = _try("/v1beta1/options/snapshots/SPY", {"feed": "indicative", "limit": 1})
        add("Opciones · feed OPRA", False,
            "No permitido: se usa el feed indicative (precios derivados, operaciones con 15 min de retraso)."
            if st2 == 200 else f"Ni OPRA ni indicative respondieron (HTTP {st}/{st2}).")
    # 5) historia de opciones: barras diarias de un contrato SPY vencido
    sym = "SPY240315C00510000"
    st, _, js = _try("/v1beta1/options/bars", {"symbols": sym, "timeframe": "1Day", "start": "2024-01-01T00:00:00Z",
                                               "limit": 1, "sort": "asc"})
    rows = (js.get("bars") or {}).get(sym) or []
    add("Histórico de opciones", bool(rows),
        f"Disponible desde {rows[0]['t'][:10]} (contrato de prueba {sym})." if rows
        else f"Sin barras históricas (HTTP {st}). Alpaca documenta historia solo desde feb-2024.")
    return out
