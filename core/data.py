"""
Capa de datos (gratuita):
  * Yahoo Finance vía yfinance  → precios diarios, fundamentales y estados financieros (sin clave)
  * Alpha Vantage (clave gratuita) → respaldo de fundamentales (OVERVIEW) y cotización
  * Universos: S&P 500 / Nasdaq 100 (Wikipedia), todo NYSE+NASDAQ (nasdaqtrader.com), Dow 30
  * Modo DEMO con datos sintéticos para probar sin internet
"""
from __future__ import annotations

import io
import os
import time
import zlib
from typing import Callable

import numpy as np
import pandas as pd
import requests
import streamlit as st

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

DOW30 = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "GS", "HD", "HON", "IBM",
         "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT"]

FALLBACK_LARGE_CAPS = sorted(set(DOW30 + [
    "GOOGL", "META", "TSLA", "AVGO", "BRK-B", "LLY", "XOM", "MA", "COST", "ORCL", "NFLX", "AMD", "ADBE", "PEP",
    "TMO", "ABT", "LIN", "ACN", "QCOM", "TXN", "INTU", "AMAT", "PM", "NOW", "ISRG", "BKNG", "UBER", "GE", "RTX",
    "SPGI", "PLD", "LOW", "BLK", "SYK", "ELV", "MDT", "ADI", "LRCX", "MU", "PANW", "KLAC", "SNPS", "CDNS", "ANET",
    "C", "BAC", "WFC", "MS", "SCHW", "DE", "UPS", "LMT", "T", "TMUS", "CMCSA", "PFE", "ABBV", "BMY", "GILD",
    "MO", "SBUX", "ADP", "MDLZ", "CI", "CB", "PGR", "MMC", "ZTS", "REGN", "VRTX", "SO", "DUK", "NEE", "COP",
    "SLB", "EOG", "FCX", "NEM", "PLTR", "CRWD", "SHOP", "MELI", "ABNB", "PYPL", "INTC", "F", "GM"]))

from .finviz import UNIVERSOS_FINVIZ

CRIPTO_UNIVERSO = "Cripto (ranking CoinGecko)"
UNIVERSOS = (["S&P 500", "Nasdaq 100", "Dow 30", "S&P 500 + Nasdaq 100"] + list(UNIVERSOS_FINVIZ)
             + ["Todo NYSE + NASDAQ (filtrado por liquidez)", "Movers del día (Alpha Vantage)", "Lista personalizada",
                CRIPTO_UNIVERSO])


def _demo() -> bool:
    return os.environ.get("TRADING_DEMO", "0") == "1"


# --------------------------------------------------------------------------
# Universos
# --------------------------------------------------------------------------
SECTOR_ES = {"Information Technology": "Tecnología", "Technology": "Tecnología", "Health Care": "Salud",
             "Healthcare": "Salud", "Financials": "Finanzas", "Financial": "Finanzas", "Consumer Discretionary": "Consumo discrecional",
             "Consumer Cyclical": "Consumo discrecional", "Consumer Staples": "Consumo básico", "Consumer Defensive": "Consumo básico",
             "Communication Services": "Comunicaciones", "Industrials": "Industria", "Energy": "Energía",
             "Utilities": "Servicios públicos", "Real Estate": "Inmobiliario", "Materials": "Materiales",
             "Basic Materials": "Materiales"}


def _wiki_table(url: str, col_candidates: list[str]):
    """(tickers, meta) de una tabla de Wikipedia con columna de sector GICS."""
    html = requests.get(url, headers=UA, timeout=20).text
    for t in pd.read_html(io.StringIO(html)):
        for c in col_candidates:
            if c in t.columns:
                tick = [str(s).strip().replace(".", "-") for s in t[c]]
                sec = t["GICS Sector"].tolist() if "GICS Sector" in t.columns else [None] * len(tick)
                meta = {k: {"sector": SECTOR_ES.get(v, v)} for k, v in zip(tick, sec) if k and k != "nan"}
                return list(meta), meta
    raise ValueError("tabla no encontrada")


def sp500() -> list[str]:
    return _wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"])[0]


def nasdaq100() -> list[str]:
    return _wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"])[0]


def all_us_listed() -> list[str]:
    """Todas las acciones comunes listadas en NASDAQ, NYSE y NYSE American (sin ETFs ni test issues)."""
    out = []
    t1 = pd.read_csv(io.StringIO(requests.get(
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", headers=UA, timeout=20).text), sep="|")
    t1 = t1[(t1["Test Issue"] == "N") & (t1["ETF"] == "N")]
    out += t1["Symbol"].dropna().tolist()
    t2 = pd.read_csv(io.StringIO(requests.get(
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", headers=UA, timeout=20).text), sep="|")
    t2 = t2[(t2["Test Issue"] == "N") & (t2["ETF"] == "N") & (t2["Exchange"].isin(["N", "A"]))]
    out += t2["ACT Symbol"].dropna().tolist()
    clean = []
    for s in out:
        s = str(s)
        if any(ch in s for ch in "$^") or s.startswith("File"):
            continue
        # excluir warrants, units, rights, preferentes
        if len(s) >= 5 and s[-1] in "WURQ" and s not in ("GOOGL",):
            continue
        clean.append(s.replace(".", "-"))
    return sorted(set(clean))


def universe_with_meta(name: str, custom: str = "", av_key: str = ""):
    """Devuelve (tickers, {ticker: {sector, cap}}). El sector alimenta el mapa de calor."""
    if _demo():
        secs = list(SECTOR_ES.values())
        return FALLBACK_LARGE_CAPS, {t: {"sector": secs[zlib.crc32(t.encode()) % 11]} for t in FALLBACK_LARGE_CAPS}
    try:
        if name == "S&P 500":
            return _wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"])
        if name == "Nasdaq 100":
            return _wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"])
        if name == "S&P 500 + Nasdaq 100":
            t1, m1 = _wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"])
            t2, m2 = _wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"])
            m = {**m2, **m1}
            return list(m), m
        if name.startswith("Finviz"):
            from .finviz import universe_meta
            for k, v in (mm := universe_meta(name)[1]).items():
                v["sector"] = SECTOR_ES.get(v.get("sector"), v.get("sector"))
            if mm:
                return list(mm), mm
    except Exception:
        pass
    return get_universe(name, custom, av_key), {}


def get_universe(name: str, custom: str = "", av_key: str = "") -> list[str]:
    if _demo():
        return FALLBACK_LARGE_CAPS
    try:
        if name == "S&P 500":
            return sp500()
        if name == "Nasdaq 100":
            return nasdaq100()
        if name == "Dow 30":
            return DOW30
        if name == "S&P 500 + Nasdaq 100":
            return sorted(set(sp500()) | set(nasdaq100()))
        if name.startswith("Todo"):
            return all_us_listed()
        if name.startswith("Finviz"):
            from .finviz import universe as fv_universe
            tick = fv_universe(name)
            if tick:
                return tick
        if name.startswith("Movers"):
            return av_movers(av_key)
        if name == "Lista personalizada":
            return sorted({t.strip().upper() for t in custom.replace(";", ",").replace("\n", ",").split(",") if t.strip()})
    except Exception:
        pass
    return FALLBACK_LARGE_CAPS


# --------------------------------------------------------------------------
# Precios
# --------------------------------------------------------------------------
def _synthetic(ticker: str, n: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(ticker.encode()))
    drift = rng.normal(0.0004, 0.0008)
    vol = rng.uniform(0.012, 0.035)
    # régimen cambiante para que haya tendencias
    regime = np.repeat(rng.normal(0, 0.0015, n // 60 + 1), 60)[:n]
    ret = rng.normal(drift + regime, vol, n)
    close = 50 * np.exp(np.cumsum(ret)) * rng.uniform(0.5, 8)
    hi = close * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = close * (1 - np.abs(rng.normal(0, vol / 2, n)))
    op = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, vol / 4, n))
    hi = np.maximum.reduce([hi, op, close])
    lo = np.minimum.reduce([lo, op, close])
    volu = rng.lognormal(15, 0.5, n) * (1 + 3 * np.abs(ret) / vol / 10)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": volu}, index=idx)


def _years(period: str) -> float:
    try:
        return float(period.rstrip("y")) if period.endswith("y") else 5.0
    except ValueError:
        return 5.0


def _use_alpaca(ticker: str, provider: str) -> bool:
    from . import alpaca
    return provider != "alphavantage" and (alpaca.available() or alpaca.is_crypto(ticker))


def _tag(df: pd.DataFrame, fuente: str) -> pd.DataFrame:
    df.attrs["fuente"] = fuente
    return df


ALPACA_FUENTE = "Alpaca (SIP, 15 min de retraso)"


def history(ticker: str, period: str = "3y", provider: str = "yahoo", av_key: str = "") -> pd.DataFrame:
    if _demo():
        return _tag(_synthetic(ticker), "Datos de ejemplo")
    if _use_alpaca(ticker, provider):
        from . import alpaca
        try:
            df = alpaca.bars(ticker, "1D", max(_years(period), 5))
            if len(df) >= 60:
                return _tag(df, ALPACA_FUENTE if not alpaca.is_crypto(ticker) else "Alpaca Crypto")
        except Exception:
            pass  # cae a Yahoo
    if provider == "alphavantage" and av_key:
        try:
            df = av_daily(ticker, av_key, full=True)
            if len(df) >= 260:
                return _tag(df.tail(1300), "Alpha Vantage")
        except Exception:
            pass  # cae a Yahoo
    import yfinance as yf
    df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if df.empty:
        raise ValueError(f"Sin datos para {ticker}")
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return _tag(df[["Open", "High", "Low", "Close", "Volume"]].dropna(), "Yahoo Finance")


def _synthetic_tf(ticker: str, tf: str, n: int = 600) -> pd.DataFrame:
    """Datos sintéticos (modo demo) con el índice de tiempo de la temporalidad pedida."""
    from .timeframes import is_crypto
    df = _synthetic(ticker + tf, n)
    end = pd.Timestamp.today().normalize() + pd.Timedelta(hours=15, minutes=30)
    if tf in ("10m", "30m", "1h", "4h"):
        step = {"10m": "10min", "30m": "30min", "1h": "60min", "4h": "240min"}[tf]
        if is_crypto(ticker):
            idx = pd.date_range(end=end, periods=n, freq=step)
        else:
            per_day = {"10m": 39, "30m": 13, "1h": 7, "4h": 2}[tf]
            days = pd.bdate_range(end=end.normalize(), periods=n // per_day + 2)
            stamps = [d + pd.Timedelta(hours=9, minutes=30) + i * pd.Timedelta(step) for d in days for i in range(per_day)]
            idx = pd.DatetimeIndex(stamps[-n:])
    elif tf == "1W":
        idx = pd.date_range(end=end.normalize(), periods=n, freq="W-FRI")
    elif tf == "1M":
        idx = pd.date_range(end=end.normalize(), periods=min(n, 240), freq="ME")
        df = df.tail(len(idx))
    else:
        idx = (pd.date_range(end=end.normalize(), periods=n, freq="D") if is_crypto(ticker)
               else pd.bdate_range(end=end.normalize(), periods=n))
    df.index = idx
    return df


def history_tf(ticker: str, tf: str = "1D", provider: str = "yahoo", av_key: str = "") -> pd.DataFrame:
    """Historial OHLCV en la temporalidad pedida. Mínimo 10m: nunca se ofrecen velas de 1m/5m/15m (10m con Yahoo se arma desde 5m)."""
    from .timeframes import TIMEFRAMES, is_crypto, validate
    tf = validate(tf)
    if tf == "1D":
        return history(ticker, "10y" if _use_alpaca(ticker, provider) else "5y", provider, av_key)
    if _demo():
        return _tag(_synthetic_tf(ticker, tf), "Datos de ejemplo")
    if _use_alpaca(ticker, provider):
        from . import alpaca
        try:
            df = alpaca.bars(ticker, tf)
            if len(df) >= 60:
                return _tag(df, ALPACA_FUENTE if not alpaca.is_crypto(ticker) else "Alpaca Crypto")
        except Exception:
            pass  # cae a Yahoo
    spec = TIMEFRAMES[tf]
    import yfinance as yf
    df = yf.Ticker(ticker).history(period=spec["period"], interval=spec["yf"], auto_adjust=True)
    if df.empty:
        raise ValueError(f"Sin datos {tf} para {ticker}")
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    df.index = idx
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if spec["resample"]:
        df = df.resample(spec["resample"], origin="start_day", offset="9h30min").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        if not is_crypto(ticker):
            _t = df.index.hour * 60 + df.index.minute
            df = df[(_t >= 570) & (_t < 960)]
    return _tag(df, "Yahoo Finance")


def batch_history(tickers: list[str], period: str = "2y", chunk: int = 100,
                  progress: Callable[[float, str], None] | None = None) -> dict[str, pd.DataFrame]:
    """Descarga masiva en bloques. Devuelve {ticker: DataFrame OHLCV}."""
    out: dict[str, pd.DataFrame] = {}
    if _demo():
        for i, t in enumerate(tickers):
            out[t] = _synthetic(t)
            if progress:
                progress((i + 1) / len(tickers), t)
        return out
    from . import alpaca
    if alpaca.available():  # Alpaca: 100 símbolos por consulta, mucho más rápido y sin bloqueos
        try:
            if progress:
                progress(0.05, f"Descargando {len(tickers)} símbolos desde Alpaca")
            got = alpaca.batch_bars(list(tickers), "1D", _years(period))
            out.update({t: d for t, d in got.items() if len(d) >= 30})
        except Exception:
            pass
        tickers = [t for t in tickers if t not in out]  # los que falten van a Yahoo
        if not tickers:
            if progress:
                progress(1.0, "Descarga completa")
            return out
    import yfinance as yf
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        if progress:
            progress(i / len(tickers), f"Descargando {i + 1}–{i + len(part)} de {len(tickers)}")
        for attempt in range(3):
            try:
                raw = yf.download(part, period=period, auto_adjust=True, group_by="ticker",
                                  threads=True, progress=False)
                break
            except Exception:
                time.sleep(2 * (attempt + 1))
                raw = None
        if raw is None or raw.empty:
            continue
        for t in part:
            try:
                d = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                d = d[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(d) > 0:
                    d.index = pd.to_datetime(d.index).tz_localize(None)
                    out[t] = d
            except Exception:
                continue
    if progress:
        progress(1.0, "Descarga completa")
    return out


# --------------------------------------------------------------------------
# Fundamentales
# --------------------------------------------------------------------------
def _demo_info(ticker: str) -> dict:
    rng = np.random.default_rng(zlib.crc32((ticker + "f").encode()))
    px = float(_synthetic(ticker)["Close"].iloc[-1])
    return {
        "longName": f"{ticker} Corp (DEMO)", "sector": rng.choice(["Technology", "Healthcare", "Financials", "Energy"]),
        "industry": "Demo", "marketCap": rng.uniform(5e9, 2e12), "trailingPE": rng.uniform(8, 60),
        "forwardPE": rng.uniform(8, 45), "pegRatio": rng.uniform(0.6, 3.5), "priceToBook": rng.uniform(1, 15),
        "enterpriseToEbitda": rng.uniform(6, 35), "freeCashflow": rng.uniform(-1e9, 2e10),
        "returnOnEquity": rng.uniform(-0.05, 0.45), "returnOnAssets": rng.uniform(-0.02, 0.2),
        "grossMargins": rng.uniform(0.2, 0.8), "operatingMargins": rng.uniform(-0.05, 0.4),
        "profitMargins": rng.uniform(-0.05, 0.3), "revenueGrowth": rng.uniform(-0.1, 0.4),
        "earningsGrowth": rng.uniform(-0.3, 0.6), "debtToEquity": rng.uniform(10, 250),
        "currentRatio": rng.uniform(0.7, 3), "beta": rng.uniform(0.6, 1.8),
        "targetMeanPrice": px * rng.uniform(0.85, 1.35), "recommendationMean": rng.uniform(1.4, 3.2),
        "numberOfAnalystOpinions": int(rng.integers(5, 45)), "currentPrice": px,
    }


def info(ticker: str, av_key: str | None = None, provider: str = "yahoo") -> dict:
    if _demo():
        return _demo_info(ticker)
    data = {}
    if provider == "alphavantage" and av_key:
        try:
            av = av_overview(ticker, av_key)
            if av.get("longName"):
                data = av
        except Exception:
            pass
    try:
        import yfinance as yf
        yinfo = yf.Ticker(ticker).info or {}
        data = {**yinfo, **{k: v for k, v in data.items() if v is not None}}
    except Exception:
        pass
    if (not data or data.get("trailingPE") is None) and av_key:
        try:
            from .fundamental import alpha_vantage_overview_to_info
            ov = requests.get("https://www.alphavantage.co/query",
                              params={"function": "OVERVIEW", "symbol": ticker, "apikey": av_key}, timeout=20).json()
            if ov.get("Symbol"):
                av = alpha_vantage_overview_to_info(ov)
                data = {**av, **{k: v for k, v in data.items() if v is not None}}
        except Exception:
            pass
    return data


def statements(ticker: str):
    if _demo():
        return None, None, None
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        return t.financials, t.balance_sheet, t.cashflow
    except Exception:
        return None, None, None


def news(ticker: str, n: int = 8, av_key: str = "") -> list[dict]:
    if _demo():
        return []
    if av_key:
        try:
            items = av_news(ticker, av_key, n)
            if items:
                return items
        except Exception:
            pass
    try:
        import yfinance as yf
        items = yf.Ticker(ticker).news or []
        out = []
        for it in items[:n]:
            c = it.get("content", it)
            out.append({"titulo": c.get("title"), "fuente": (c.get("provider") or {}).get("displayName", c.get("publisher")),
                        "link": ((c.get("canonicalUrl") or {}).get("url") or c.get("link"))})
        return [o for o in out if o["titulo"]]
    except Exception:
        return []


# --------------------------------------------------------------------------
# Alpha Vantage (REST — la misma fuente que el conector MCP de Claude)
#   Gratis: TIME_SERIES_DAILY compacto (100 días), TOP_GAINERS_LOSERS, NEWS_SENTIMENT, ~25 llamadas/día
#   Premium: historial completo (outputsize=full), OVERVIEW, estados financieros, sin límite diario
# --------------------------------------------------------------------------
AV_URL = "https://www.alphavantage.co/query"


class AlphaVantageError(RuntimeError):
    pass


def _av(params: dict, key: str) -> dict:
    if not key:
        raise AlphaVantageError("Falta la API key de Alpha Vantage")
    j = requests.get(AV_URL, params={**params, "apikey": key}, timeout=30).json()
    msg = j.get("Information") or j.get("Note") or j.get("Error Message")
    if msg and len(j) <= 2:
        raise AlphaVantageError(msg)
    return j


def av_daily(ticker: str, key: str, full: bool = True) -> pd.DataFrame:
    """OHLCV diario. full=True requiere plan premium; si falla, cae a 'compact' (100 días)."""
    try:
        j = _av({"function": "TIME_SERIES_DAILY_ADJUSTED" if full else "TIME_SERIES_DAILY", "symbol": ticker,
                 "outputsize": "full" if full else "compact"}, key)
    except AlphaVantageError:
        if not full:
            raise
        j = _av({"function": "TIME_SERIES_DAILY", "symbol": ticker, "outputsize": "compact"}, key)
    ts = next(v for k, v in j.items() if "Time Series" in k)
    df = pd.DataFrame(ts).T.astype(float)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    ren = {"1. open": "Open", "2. high": "High", "3. low": "Low", "4. close": "Close"}
    if "5. adjusted close" in df.columns:  # ajustar por splits/dividendos
        f = df["5. adjusted close"] / df["4. close"]
        for c in ("1. open", "2. high", "3. low", "4. close"):
            df[c] = df[c] * f
        df = df.rename(columns={"6. volume": "Volume"})
    else:
        df = df.rename(columns={"5. volume": "Volume"})
    return df.rename(columns=ren)[["Open", "High", "Low", "Close", "Volume"]]


def av_overview(ticker: str, key: str) -> dict:
    from .fundamental import alpha_vantage_overview_to_info
    return alpha_vantage_overview_to_info(_av({"function": "OVERVIEW", "symbol": ticker}, key))


def av_movers(key: str) -> list[str]:
    """Más activas + mayores alzas/bajas del día (endpoint gratuito). Excluye warrants/units/rights."""
    j = _av({"function": "TOP_GAINERS_LOSERS"}, key)
    out = []
    for grp in ("most_actively_traded", "top_gainers", "top_losers"):
        for it in j.get(grp, []):
            t = it["ticker"]
            if any(ch in t for ch in "+^.") or (len(t) >= 5 and t[-1] in "WUR"):
                continue
            out.append(t)
    return list(dict.fromkeys(out))


def av_news(ticker: str, key: str, n: int = 8) -> list[dict]:
    j = _av({"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": 50}, key)
    out = []
    for it in j.get("feed", [])[:n]:
        sent = next((s for s in it.get("ticker_sentiment", []) if s.get("ticker") == ticker), {})
        out.append({"titulo": it.get("title"), "fuente": it.get("source"), "link": it.get("url"),
                    "sentimiento": sent.get("ticker_sentiment_label")})
    return out


# --------------------------------------------------------------------------
# Premercado y postmercado
# --------------------------------------------------------------------------
def session_ny(now=None) -> str:
    """Sesión del mercado de EE. UU. por la hora de Nueva York: 'pre' (4:00–9:30), 'regular' (9:30–16:00),
    'post' (16:00–20:00) o 'cerrado' (noches y fines de semana; no considera feriados)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return "cerrado"
    m = now.hour * 60 + now.minute
    return "pre" if 240 <= m < 570 else "regular" if m < 960 and m >= 570 else "post" if 960 <= m < 1200 else "cerrado"


@st.cache_data(ttl=60, show_spinner=False)
def extended_quote(ticker: str) -> dict | None:
    """Último precio fuera del horario regular (premercado o postmercado) y su variación frente al último cierre
    regular. None en horario regular, con el mercado cerrado, para cripto o si no hay datos."""
    from .timeframes import is_crypto
    ses = session_ny()
    if _demo() and os.environ.get("TRADING_DEMO_SESION") in ("pre", "post"):  # solo para capturas en modo demo
        ses = os.environ["TRADING_DEMO_SESION"]
    if ses not in ("pre", "post") or is_crypto(ticker):
        return None
    if _demo():
        h = history(ticker, "1y")
        ref = float(h["Close"].iloc[-1])
        return {"sesion": ses, "precio": round(ref * 1.0035, 2), "ref": ref, "var": 0.35, "hora": "07:45",
                "fuente": "demo"}
    from . import alpaca
    try:
        if alpaca.available():
            sym = alpaca.stock_symbol(ticker)
            sn = (alpaca._get("/v2/stocks/snapshots", {"symbols": sym, "feed": "iex"}) or {}).get(sym) or {}
            tr = sn.get("latestTrade") or {}
            ref = (sn.get("dailyBar") or {}).get("c") if ses == "post" else (sn.get("prevDailyBar") or {}).get("c")
            if tr.get("p") and ref:
                t = pd.Timestamp(tr["t"]).tz_convert("America/New_York")
                if session_ny(t.to_pydatetime()) == ses:
                    return {"sesion": ses, "precio": float(tr["p"]), "ref": float(ref),
                            "var": (float(tr["p"]) / float(ref) - 1) * 100, "hora": f"{t:%H:%M}", "fuente": "Alpaca IEX"}
    except Exception:
        pass
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="2d", interval="5m", prepost=True)
        if h is not None and len(h):
            ix = h.index.tz_convert("America/New_York")
            last_t = ix[-1]
            reg = h[[(570 <= t.hour * 60 + t.minute < 960) for t in ix]]
            if session_ny(last_t.to_pydatetime()) == ses and len(reg):
                ref = float(reg["Close"].iloc[-1])
                px = float(h["Close"].iloc[-1])
                return {"sesion": ses, "precio": px, "ref": ref, "var": (px / ref - 1) * 100, "hora": f"{last_t:%H:%M}",
                        "fuente": "Yahoo"}
    except Exception:
        pass
    return None


@st.cache_data(ttl=60, show_spinner=False)
def extended_quotes(tickers: tuple) -> dict:
    """Premercado / postmercado para varias acciones a la vez (Alpaca, snapshots por lotes de 100).
    {ticker: {sesion, precio, ref, var, hora}}; vacío en horario regular, con el mercado cerrado o sin Alpaca."""
    from .timeframes import is_crypto
    ses = session_ny()
    if _demo() and os.environ.get("TRADING_DEMO_SESION") in ("pre", "post"):
        ses = os.environ["TRADING_DEMO_SESION"]
    tks = [t for t in tickers if not is_crypto(t)]
    if ses not in ("pre", "post") or not tks:
        return {}
    if _demo():
        out = {}
        for t in tks:
            h = history(t, "1y")
            ref = float(h["Close"].iloc[-1])
            v = ((sum(map(ord, t)) * 37) % 900 - 450) / 100  # variación determinista ±4.5 %
            out[t] = {"sesion": ses, "precio": round(ref * (1 + v / 100), 2), "ref": ref, "var": v, "hora": "07:45"}
        return out
    from . import alpaca
    out = {}
    try:
        if not alpaca.available():
            return {}
        sym = {alpaca.stock_symbol(t): t for t in tks}
        keys = list(sym)
        for i in range(0, len(keys), 100):
            js = alpaca._get("/v2/stocks/snapshots", {"symbols": ",".join(keys[i:i + 100]), "feed": "iex"}) or {}
            for k, sn in js.items():
                sn = sn or {}
                tr = sn.get("latestTrade") or {}
                ref = (sn.get("dailyBar") or {}).get("c") if ses == "post" else (sn.get("prevDailyBar") or {}).get("c")
                if not (tr.get("p") and ref and k in sym):
                    continue
                t = pd.Timestamp(tr["t"]).tz_convert("America/New_York")
                if session_ny(t.to_pydatetime()) != ses:
                    continue
                out[sym[k]] = {"sesion": ses, "precio": float(tr["p"]), "ref": float(ref),
                               "var": (float(tr["p"]) / float(ref) - 1) * 100, "hora": f"{t:%H:%M}"}
    except Exception:
        pass
    return out
