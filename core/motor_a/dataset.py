"""Panel de entrenamiento del Motor A: todas las acciones del universo × todos los días desde 2016.

Fila = (fecha, ticker). Columnas = variables (en σ de la acción), contexto de mercado y la etiqueta de triple barrera.
Limitación conocida (sesgo de supervivencia): el universo es el de HOY (acciones líquidas actuales); las que quebraron
o salieron del índice desde 2016 no están. Eso tiende a inflar un poco los resultados históricos.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import etiquetas as ET, variables as VA

H_DEF, K_DEF = 10, 1.0
NO_VARIABLES = {"sigma_d", "y", "barrera", "dias", "ret_h_sigma", "ticker"}
CACHE_DIR = Path(os.environ.get("MOTOR_A_DIR", "datos/motor_a"))
MIN_SESIONES = 300


def columnas_variables(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c not in NO_VARIABLES]


def construir(barras: dict[str, pd.DataFrame], spy: pd.DataFrame, H: int = H_DEF, k: float = K_DEF) -> pd.DataFrame:
    """barras: {ticker: OHLCV diario}. Devuelve el panel apilado e indexado por (fecha, ticker)."""
    M = VA.de_mercado(spy)
    partes = []
    for t, df in barras.items():
        df = df.dropna(subset=["Close"])
        if len(df) < MIN_SESIONES:
            continue
        X = VA.relativas(VA.por_accion(df), M)
        Y = ET.triple_barrera(df, X["sigma_d"], H, k)
        Z = X.join(Y)
        Z["ticker"] = t
        partes.append(Z)
    if not partes:
        return pd.DataFrame()
    P = pd.concat(partes)
    P.index.name = "fecha"
    P = P.reset_index().set_index(["fecha", "ticker"]).sort_index()
    num = P.select_dtypes("number").columns
    P[num] = P[num].astype("float32")
    return P


def descargar(tickers: list[str], desde_anios: float = 11.0, log=print) -> dict[str, pd.DataFrame]:
    """Barras diarias desde Alpaca (SIP histórico, ajustadas por splits y dividendos) en bloques de 100 símbolos."""
    from .. import alpaca
    out = {}
    for i in range(0, len(tickers), 100):
        bloque = tickers[i:i + 100]
        out.update(alpaca.batch_bars(bloque, "1D", desde_anios))
        log(f"  barras {min(i + 100, len(tickers))}/{len(tickers)}")
    return out


def universo(nombre: str = "Finviz · Todo el mercado líquido (cap > $2B)", maximo: int = 800, log=print) -> list[str]:
    """Acciones líquidas actuales (ordenadas por capitalización). Si Finviz falla, S&P 500 + Nasdaq 100."""
    try:
        from .. import finviz
        t = finviz.universe(nombre)
        if len(t) >= 100:
            return t[:maximo]
    except Exception as e:
        log(f"  Finviz no respondió ({str(e)[:60]}); uso S&P 500 + Nasdaq 100")
    from .. import data
    return data.get_universe("S&P 500 + Nasdaq 100")[:maximo]


def guardar(panel: pd.DataFrame, nombre: str = "panel.parquet") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / nombre
    panel.to_parquet(p)
    return p


def cargar(nombre: str = "panel.parquet") -> pd.DataFrame | None:
    p = CACHE_DIR / nombre
    return pd.read_parquet(p) if p.exists() else None


def sintetico(n_acciones: int = 40, n_dias: int = 1500, senal: float = 0.0, semilla: int = 7):
    """Mercado sintético para pruebas. Con `senal` > 0 hay momentum real (el retorno de mañana depende del de los
    últimos 20 días), de modo que un modelo correcto DEBE encontrar ventaja; con 0 es ruido puro y no debe hallarla."""
    rng = np.random.default_rng(semilla)
    fechas = pd.bdate_range("2016-01-04", periods=n_dias)
    m = rng.normal(0, 0.009, n_dias)
    spy = _ohlcv(100 * np.exp(np.cumsum(m)), rng, fechas)
    barras = {}
    for j in range(n_acciones):
        vol = rng.uniform(0.012, 0.04)
        e = rng.normal(0, vol, n_dias)
        r = np.zeros(n_dias)
        for i in range(n_dias):
            mom = r[max(0, i - 20):i].sum() if i else 0.0
            r[i] = 0.8 * m[i] + e[i] + senal * vol * np.tanh(mom / (vol * np.sqrt(20)))
        barras[f"S{j:03d}"] = _ohlcv(50 * np.exp(np.cumsum(r)), rng, fechas, vol)
    return barras, spy


def _ohlcv(c, rng, fechas, vol=0.01):
    o = c * np.exp(rng.normal(0, vol * 0.3, len(c)))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, vol * 0.5, len(c))))
    lo = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, vol * 0.5, len(c))))
    v = rng.lognormal(14, 0.4, len(c))
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v}, index=fechas)
