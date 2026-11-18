"""Archivo diario de la cadena de opciones (después del cierre).

Por qué: Alpaca solo guarda barras de opciones desde feb-2024 y sin bid/ask históricos; sin IV, skew ni spreads
históricos no se puede entrenar ni validar el Motor B. Este archivo construye esa historia día a día.

Se guarda en Supabase Storage (bucket privado «opciones»):
  diario/AAAA-MM-DD/resumen.parquet  → una fila por acción (todas las del universo)
  diario/AAAA-MM-DD/cadenas.parquet  → contratos completos (tus acciones + las 50 más líquidas)
"""
from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd

PLAZOS = (7, 14, 30, 45)  # días de calendario para la estructura temporal de la IV ATM
COLS_CADENA = ["symbol", "type", "exp", "dte", "strike", "bid", "ask", "last", "mid", "volume", "oi", "iv", "delta",
               "gamma", "theta", "vega"]


def _iv_atm_por_venc(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """IV ATM de cada vencimiento: media de call y put del strike más cercano al precio."""
    filas = []
    for (exp, dte), g in df.groupby(["exp", "dte"]):
        g = g.dropna(subset=["iv"])
        if g.empty:
            continue
        k = g["strike"].iloc[(g["strike"] - spot).abs().argmin()]
        ivs = g[g["strike"] == k]["iv"]
        filas.append({"exp": exp, "dte": int(dte), "iv": float(ivs.mean())})
    return pd.DataFrame(filas).sort_values("dte") if filas else pd.DataFrame(columns=["exp", "dte", "iv"])


def _interpolar(t: pd.DataFrame, dias: int) -> float:
    """IV ATM a `dias` interpolando en varianza total (σ²·T), como hace el mercado. NaN si queda fuera del rango."""
    t = t[t["dte"] > 0]
    if len(t) == 0 or dias < t["dte"].min() * 0.5 or dias > t["dte"].max() * 1.5:
        return float("nan")
    w = (t["iv"] ** 2) * t["dte"]
    v = float(np.interp(dias, t["dte"], w))
    return math.sqrt(max(v, 0) / dias)


def _iv_delta(g: pd.DataFrame, tipo: str, objetivo: float) -> float:
    g = g[(g["type"] == tipo)].dropna(subset=["delta", "iv"])
    if g.empty:
        return float("nan")
    i = (g["delta"] - objetivo).abs().argmin()
    return float(g["iv"].iloc[i]) if abs(g["delta"].iloc[i] - objetivo) <= 0.12 else float("nan")


def resumir(df: pd.DataFrame, spot: float, vol_real: float | None) -> dict:
    """Una fila de resumen para una acción y un día. IV en decimal."""
    out = {"spot": spot, "vol_real_20": vol_real, "contratos": int(len(df))}
    if df.empty:
        return out
    d = df.copy()
    d["iv"] = pd.to_numeric(d["iv"], errors="coerce")
    if d["iv"].median() > 3:  # viene en %
        d["iv"] = d["iv"] / 100
    t = _iv_atm_por_venc(d, spot)
    for p in PLAZOS:
        out[f"iv_atm_{p}d"] = _interpolar(t, p)
    if vol_real:
        out["iv_vs_real_30d"] = out["iv_atm_30d"] / vol_real if np.isfinite(out["iv_atm_30d"]) else float("nan")
    # skew 25Δ en el vencimiento más cercano a 30 días: IV put −0.25 menos IV call +0.25
    if len(t):
        e30 = t.iloc[(t["dte"] - 30).abs().argmin()]["exp"]
        g = d[d["exp"] == e30]
        p25, c25 = _iv_delta(g, "put", -0.25), _iv_delta(g, "call", 0.25)
        out["skew_25d"] = p25 - c25
        out["iv_put_25d"], out["iv_call_25d"] = p25, c25
    # actividad y costo
    oi_c, oi_p = d.loc[d["type"] == "call", "oi"].sum(), d.loc[d["type"] == "put", "oi"].sum()
    v_c, v_p = d.loc[d["type"] == "call", "volume"].sum(), d.loc[d["type"] == "put", "volume"].sum()
    out.update({"oi_call": float(oi_c), "oi_put": float(oi_p), "vol_call": float(v_c), "vol_put": float(v_p),
                "put_call_oi": float(oi_p / oi_c) if oi_c else float("nan"),
                "put_call_vol": float(v_p / v_c) if v_c else float("nan")})
    cerca = d[(d["dte"] >= 5) & ((d["strike"] / spot - 1).abs() <= 0.03) & (d["bid"] > 0) & (d["ask"] > 0)]
    if len(cerca):
        sp = (cerca["ask"] - cerca["bid"]) / ((cerca["ask"] + cerca["bid"]) / 2)
        out["spread_atm_pct"] = float(sp.median() * 100)
    return out


def a_parquet(df: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    df.to_parquet(b, index=False)
    return b.getvalue()
