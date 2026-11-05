"""
Finviz (gratuito, vía finvizfinance): screener de todo el mercado de EE.UU., ficha de
~80 métricas por acción, señales técnicas, cambios de rating de analistas, insiders y noticias.
Los datos gratuitos de Finviz tienen ~15-20 min de retraso. Uso personal y moderado.
"""
from __future__ import annotations

import re

import pandas as pd

# Universos basados en el screener de Finviz: (señal, filtros)
LIQ = {"Average Volume": "Over 500K", "Price": "Over $5", "Country": "USA"}
UNIVERSOS_FINVIZ = {
    "Finviz · Todo el mercado líquido (cap > $2B)": ("", {**LIQ, "Market Cap.": "+Mid (over $2bln)"}),
    "Finviz · Nuevos máximos": ("New High", LIQ),
    "Finviz · Volumen inusual": ("Unusual Volume", LIQ),
    "Finviz · Top gainers del día": ("Top Gainers", LIQ),
    "Finviz · Sobreventa (RSI<30)": ("Oversold", LIQ),
    "Finviz · Compras recientes de insiders": ("Recent Insider Buying", LIQ),
    "Finviz · Upgrades de analistas": ("Upgrades", LIQ),
    "Finviz · Canal ascendente": ("Channel Up", LIQ),
    "Finviz · Doble suelo": ("Double Bottom", LIQ),
}


def screener(signal: str = "", filters: dict | None = None, limit: int = 2000) -> list[str]:
    from finvizfinance.screener.overview import Overview
    ov = Overview()
    ov.set_filter(signal=signal, filters_dict=filters or {})
    df = ov.screener_view(order="Market Cap.", ascend=False, limit=limit, verbose=0, sleep_sec=1)
    if df is None or df.empty:
        return []
    return [str(t).replace(".", "-") for t in df["Ticker"].dropna()]


def universe(name: str) -> list[str]:
    signal, filters = UNIVERSOS_FINVIZ[name]
    return screener(signal, filters)


# ---------------------------------------------------------------------------
# Ficha de la acción
# ---------------------------------------------------------------------------
_MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "N/A"):
        return None
    m = re.match(r"^(-?\d+(?:\.\d+)?)([KMBT%]?)", s)
    if not m:
        return None
    x = float(m.group(1))
    suf = m.group(2)
    if suf == "%":
        return x / 100
    return x * _MULT.get(suf, 1)


def snapshot(ticker: str) -> dict:
    """Ficha completa de Finviz (valores originales en texto)."""
    from finvizfinance.quote import finvizfinance as FV
    q = FV(ticker.replace("-", "."))
    return q.ticker_fundament(raw=True)


def _div_yield(v):
    m = re.search(r"\(([\d.]+)%\)", str(v or ""))
    return float(m.group(1)) / 100 if m else None


def to_info(f: dict) -> dict:
    """Mapea la ficha de Finviz al formato de yfinance (para el puntaje fundamental)."""
    g = lambda k: _num(f.get(k))
    de = g("Debt/Eq")
    return {
        "longName": f.get("Company"), "sector": f.get("Sector"), "industry": f.get("Industry"),
        "marketCap": g("Market Cap"), "trailingPE": g("P/E"), "forwardPE": g("Forward P/E"), "pegRatio": g("PEG"),
        "priceToBook": g("P/B"), "priceToSalesTrailing12Months": g("P/S"), "enterpriseToEbitda": g("EV/EBITDA"),
        "returnOnEquity": g("ROE"), "returnOnAssets": g("ROA"), "grossMargins": g("Gross Margin"),
        "operatingMargins": g("Oper. Margin"), "profitMargins": g("Profit Margin"),
        "revenueGrowth": g("Sales Q/Q"), "earningsGrowth": g("EPS Q/Q"),
        "debtToEquity": de * 100 if de is not None else None,  # mismo formato que yfinance (%)
        "currentRatio": g("Current Ratio"), "beta": g("Beta"), "dividendYield": _div_yield(f.get("Dividend TTM")),
        "targetMeanPrice": g("Target Price"), "recommendationMean": g("Recom"), "currentPrice": g("Price"),
    }


EXTRA_KEYS = [
    ("Short Float", "pct"), ("Short Ratio", "num"), ("Insider Own", "pct"), ("Insider Trans", "pct"),
    ("Inst Own", "pct"), ("Inst Trans", "pct"), ("EPS next Y Percentage", "pct"), ("EPS next 5Y", "pct"),
    ("Perf Week", "pct"), ("Perf Month", "pct"), ("Perf Quarter", "pct"), ("Perf YTD", "pct"),
    ("Rel Volume", "num"), ("RSI (14)", "num"), ("SMA20", "pct"), ("SMA50", "pct"), ("SMA200", "pct"),
    ("Earnings", "txt"), ("Optionable", "txt"), ("Shortable", "txt"),
]


def extras(f: dict) -> dict:
    out = {}
    for k, kind in EXTRA_KEYS:
        v = f.get(k)
        if v in (None, "", "-"):
            continue
        out[k] = v if kind == "txt" else _num(v)
    return out


def ratings(ticker: str, n: int = 8) -> list[dict]:
    """Últimos cambios de rating de analistas (upgrades/downgrades)."""
    try:
        from finvizfinance.quote import finvizfinance as FV
        df = FV(ticker.replace("-", ".")).ticker_outer_ratings()
        if df is None or df.empty:
            return []
        df = df.head(n)
        return [{k: (str(v.date()) if hasattr(v, "date") else v) for k, v in r.items()} for r in df.to_dict("records")]
    except Exception:
        return []


def news(ticker: str, n: int = 8) -> list[dict]:
    try:
        from finvizfinance.quote import finvizfinance as FV
        df = FV(ticker.replace("-", ".")).ticker_news()
        if df is None or df.empty:
            return []
        return [{"titulo": r["Title"], "fuente": r.get("Source") or "Finviz", "link": r["Link"]}
                for r in df.head(n).to_dict("records")]
    except Exception:
        return []


def signal(ticker: str) -> list[str]:
    try:
        from finvizfinance.quote import finvizfinance as FV
        return FV(ticker.replace("-", ".")).ticker_signal() or []
    except Exception:
        return []


def bundle(ticker: str) -> dict:
    """Una sola descarga de la página de Finviz → ficha, extras, ratings, noticias y señales."""
    from finvizfinance.quote import finvizfinance as FV
    q = FV(ticker.replace("-", "."))
    out = {"snapshot": {}, "info": {}, "extras": {}, "ratings": [], "news": [], "signals": []}
    try:
        out["snapshot"] = q.ticker_fundament(raw=True)
        out["info"] = to_info(out["snapshot"])
        out["extras"] = extras(out["snapshot"])
    except Exception:
        pass
    try:
        df = q.ticker_outer_ratings()
        if df is not None and not df.empty:
            out["ratings"] = [{k: (str(v.date()) if hasattr(v, "date") else v) for k, v in r.items()}
                              for r in df.head(8).to_dict("records")]
    except Exception:
        pass
    try:
        df = q.ticker_news()
        if df is not None and not df.empty:
            out["news"] = [{"titulo": r["Title"], "fuente": r.get("Source") or "Finviz", "link": r["Link"]}
                           for r in df.head(8).to_dict("records")]
    except Exception:
        pass
    try:
        out["signals"] = q.ticker_signal() or []
    except Exception:
        pass
    return out
