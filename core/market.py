"""
Métricas de mercado para las tablas de la watchlist y del escáner: rendimiento por periodo,
mini gráficos, logos y datos de CoinGecko para cripto, y preferencias de columnas del usuario.

Acciones: los periodos se cuentan en sesiones bursátiles (7D = 5 sesiones, 1M = 21, 6M = 126).
Cripto: el mercado es 24/7, los periodos se cuentan en días corridos y los datos (1h, 24h, 7d,
30d, 200d, 1a, volumen, market cap, FDV, ranking y gráfico de 7 días) vienen de CoinGecko.
"""
from __future__ import annotations

import copy
import math

import pandas as pd

from .timeframes import is_crypto

LOGO_ACCION = "https://financialmodelingprep.com/image-stock/{}.png"

# ---------------------------------------------------------------- rendimiento por periodo
PERIODOS_ACCION = {"1D": 1, "7D": 5, "1M": 21, "3M": 63, "6M": 126, "1A": 252}
PERIODOS_CRIPTO_DIAS = {"1D": 1, "7D": 7, "1M": 30, "3M": 91, "6M": 182, "1A": 365}
SPARK_MAX = 182  # velas diarias guardadas para el mini gráfico


def rendimientos(df: pd.DataFrame, ticker: str) -> dict[str, float | None]:
    """Variación % del cierre en cada periodo (None si no hay historial suficiente)."""
    per = PERIODOS_CRIPTO_DIAS if is_crypto(ticker) else PERIODOS_ACCION
    c = df["Close"].dropna()
    out = {}
    for k, n in per.items():
        out[k] = float(c.iloc[-1] / c.iloc[-1 - n] - 1) * 100 if len(c) > n and c.iloc[-1 - n] else None
    return out


def spark(df: pd.DataFrame, n: int = SPARK_MAX) -> list[float]:
    """Cierres recientes para el mini gráfico (redondeados para ocupar poco espacio)."""
    c = df["Close"].dropna().tail(n)
    return [float(f"{v:.6g}") for v in c]


def spark_tail(lista, periodo: str, ticker: str = "") -> list[float]:
    if not isinstance(lista, (list, tuple)) and not hasattr(lista, "__len__"):
        return []
    lista = list(lista)
    per = PERIODOS_CRIPTO_DIAS if is_crypto(ticker) else PERIODOS_ACCION
    n = per.get(periodo, len(lista))
    return lista[-(n + 1):]


def logo(ticker: str) -> str | None:
    return None if is_crypto(ticker) else LOGO_ACCION.format(ticker.replace("-", "."))


# ---------------------------------------------------------------- cripto (CoinGecko)
def cripto_mercado(tickers: list[str]) -> dict[str, dict]:
    """Datos de mercado de CoinGecko para tickers SÍMBOLO-USD. Si varias monedas comparten
    símbolo, se toma la de mayor capitalización."""
    from .crypto import _get as cg
    syms = sorted({t.split("-")[0].lower() for t in tickers if is_crypto(t)})
    out: dict[str, dict] = {}
    for i in range(0, len(syms), 100):
        rows = cg("/coins/markets", {"vs_currency": "usd", "symbols": ",".join(syms[i:i + 100]), "per_page": 250,
                                     "order": "market_cap_desc", "sparkline": "true",
                                     "price_change_percentage": "1h,24h,7d,30d,200d,1y"})
        for r in rows:
            t = f"{(r.get('symbol') or '').upper()}-USD"
            if t in out:
                continue  # ya está la de mayor capitalización
            cap, fdv = r.get("market_cap"), r.get("fully_diluted_valuation")
            out[t] = {
                "nombre": r.get("name"), "logo": r.get("image"), "ranking": r.get("market_cap_rank"),
                "precio": r.get("current_price"),
                "1h": r.get("price_change_percentage_1h_in_currency"),
                "24h": r.get("price_change_percentage_24h_in_currency", r.get("price_change_percentage_24h")),
                "7d": r.get("price_change_percentage_7d_in_currency"),
                "30d": r.get("price_change_percentage_30d_in_currency"),
                "200d": r.get("price_change_percentage_200d_in_currency"),
                "1a": r.get("price_change_percentage_1y_in_currency"),
                "volumen": r.get("total_volume"), "cap": cap, "fdv": fdv,
                "cap_fdv": (cap / fdv) if cap and fdv else None,
                "spark": [float(f"{v:.6g}") for v in ((r.get("sparkline_in_7d") or {}).get("price") or [])
                          if v is not None and not math.isnan(v)],
            }
    return out


# ---------------------------------------------------------------- preferencias de columnas
OPCIONES = {
    "acciones": {
        "perf": ["1D", "7D", "1M", "3M", "6M", "1A"],
        "metricas": ["Volumen $", "Market cap", "Sector"],
        "tecnicas": ["Score técnico", "Fuerza relativa", "RSI", "ADX", "Vol. relativo", "ATR %", "Objetivo 2",
                     "Casos similares"],
        "grafico": ["Ninguno", "1M", "3M", "6M"],
    },
    "cripto": {
        "perf": ["1h", "24h", "7d", "30d", "200d", "1a"],
        "metricas": ["Volumen 24h", "Market cap", "FDV", "Market cap / FDV", "Ranking"],
        "tecnicas": ["Score técnico", "RSI", "ADX", "ATR %", "Objetivo 2", "Casos similares"],
        "grafico": ["Ninguno", "7 días"],
    },
}
PREFS_DEFAULT = {
    "acciones": {"perf": ["1D", "7D", "1M", "6M"], "metricas": ["Volumen $", "Market cap"], "tecnicas": [],
                 "grafico": "3M", "filas": 50},
    "cripto": {"perf": ["1h", "24h", "7d", "30d"], "metricas": ["Volumen 24h", "Market cap"], "tecnicas": [],
               "grafico": "7 días", "filas": 50},
}
FILAS = [25, 50, 100, 250]


def prefs(settings: dict | None, kind: str) -> dict:
    """Preferencias guardadas del usuario completadas con los valores por defecto."""
    base = copy.deepcopy(PREFS_DEFAULT[kind])
    saved = (((settings or {}).get("vista") or {}).get("tablas") or {}).get(kind) or {}
    for k, v in saved.items():
        if k in base:
            base[k] = v
    op = OPCIONES[kind]
    for k in ("perf", "metricas", "tecnicas"):
        base[k] = [x for x in op[k] if x in (base[k] or [])]  # orden fijo y sin opciones inválidas
    if base["grafico"] not in op["grafico"]:
        base["grafico"] = PREFS_DEFAULT[kind]["grafico"]
    if base["filas"] not in FILAS:
        base["filas"] = 50
    return base


def with_prefs(settings: dict, kind: str, p: dict) -> dict:
    S = copy.deepcopy(settings)
    S.setdefault("vista", {}).setdefault("tablas", {})[kind] = p
    return S
