"""Descarga de datos gratuitos para el Motor B (DoltHub, post-no-preference) con caché en disco.

volatility_history: IV y volatilidad histórica por acción y día (semanal 2019-2020, diaria después).
earnings_calendar:  fechas de resultados con hora (antes de la apertura / después del cierre).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd

from ..fuentes import dolthub as D

DIR = Path(os.environ.get("MOTOR_B_DIR", "datos/motor_b"))
COLS_VOL = "date, act_symbol, iv_current, hv_current, iv_year_high, iv_year_low"


def _num(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _bajar_iv(t: str) -> pd.DataFrame:
    d = D.paginado("options", f"SELECT {COLS_VOL} FROM volatility_history WHERE act_symbol='{t}' ORDER BY date",
                   por_pagina=1000, max_paginas=5)
    if d.empty:
        return d
    d = _num(d, ["iv_current", "hv_current", "iv_year_high", "iv_year_low"])
    d["date"] = pd.to_datetime(d["date"])
    return d


def historia_iv(tickers: list[str], log=print, hilos: int = 6) -> pd.DataFrame:
    """IV / HV diarias de cada acción (una consulta por acción, en paralelo; caché por acción en disco)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    (DIR / "iv").mkdir(parents=True, exist_ok=True)
    partes, faltan = [], []
    for t in tickers:
        f = DIR / "iv" / f"{t}.parquet"
        fresco = f.exists() and time.time() - f.stat().st_mtime < 6 * 86400  # se renueva cada semana
        (partes.append(pd.read_parquet(f)) if fresco else faltan.append(t))
    log(f"  IV en caché: {len(partes)} · por descargar: {len(faltan)}")
    with ThreadPoolExecutor(hilos) as ex:
        fut = {ex.submit(_bajar_iv, t): t for t in faltan}
        for n, fu in enumerate(as_completed(fut)):
            t = fut[fu]
            try:
                d = fu.result()
            except Exception as e:
                log(f"  IV {t}: {str(e)[:80]}")
                continue
            if len(d):
                d.to_parquet(DIR / "iv" / f"{t}.parquet", index=False)
                partes.append(d)
            if (n + 1) % 50 == 0:
                log(f"  IV DoltHub {n + 1}/{len(faltan)}")
    if not partes:
        return pd.DataFrame()
    H = pd.concat(partes, ignore_index=True).rename(columns={"act_symbol": "ticker", "date": "fecha"})
    return H.dropna(subset=["iv_current"]).sort_values(["ticker", "fecha"])


def calendario_resultados(tickers: list[str], log=print) -> pd.DataFrame:
    f = DIR / "resultados.parquet"
    if f.exists() and set(tickers) <= set(pd.read_parquet(f)["ticker"]):
        return pd.read_parquet(f)
    partes = []
    for i in range(0, len(tickers), 40):
        lista = ",".join(f"'{t}'" for t in tickers[i:i + 40])
        try:
            partes.append(D.paginado("earnings", f"SELECT act_symbol, date, `when` FROM earnings_calendar "
                                                 f"WHERE act_symbol IN ({lista}) ORDER BY act_symbol, date"))
        except Exception as e:
            log(f"  calendario {i}: {str(e)[:80]}")
    if not partes:
        return pd.DataFrame(columns=["ticker", "fecha", "hora"])
    C = pd.concat(partes, ignore_index=True).rename(columns={"act_symbol": "ticker", "date": "fecha", "when": "hora"})
    C["fecha"] = pd.to_datetime(C["fecha"])
    DIR.mkdir(parents=True, exist_ok=True)
    C.to_parquet(f, index=False)
    return C
