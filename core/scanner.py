"""
Escáner de mercado: calcula para cada acción el puntaje técnico, la probabilidad
histórica de ganancia (triple barrera, calibrada con el universo completo),
el valor esperado en R y un plan de operación rápido. Devuelve un ranking.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from . import probability as P
from .levels import trade_plan
from .technical import compute_all, score_series


def _label(score: float, p: float, ev: float) -> str:
    if ev >= 0.30 and score >= 20:
        return "COMPRA FUERTE"
    if ev >= 0.10 and score >= 0:
        return "COMPRA"
    if ev >= 0.10 and score < 0:
        return "REBOTE (contratendencia)"
    if score <= -30 and ev < 0:
        return "EVITAR / VENTA"
    return "NEUTRAL"


def scan(prices: dict[str, pd.DataFrame], min_price=5.0, min_dollar_vol=20e6, tp=3.0, sl=1.5, horizon=20,
         band=15.0, strength=25, progress: Callable[[float, str], None] | None = None) -> pd.DataFrame:
    prepared = {}
    pool_s, pool_w = [], []
    items = list(prices.items())
    for i, (t, df) in enumerate(items):
        if progress and i % 10 == 0:
            progress(i / max(1, len(items)), f"Calculando indicadores · {t}")
        if df is None or len(df) < 260:
            continue
        px = float(df["Close"].iloc[-1])
        dvol = float((df["Close"] * df["Volume"]).tail(20).mean())
        if px < min_price or dvol < min_dollar_vol:
            continue
        try:
            d = compute_all(df)
            s = score_series(d)
            o = P.barrier_outcomes(d, tp, sl, horizon, "long")
        except Exception:
            continue
        prepared[t] = (d, s, o, dvol)
        j = pd.concat([s, o["win"]], axis=1).dropna()
        pool_s.append(j.iloc[:, 0].values)
        pool_w.append(j.iloc[:, 1].values)

    if not prepared:
        return pd.DataFrame()

    # ---- Calibración del universo: tasa de acierto por nivel de puntaje ----
    S = np.concatenate(pool_s)
    W = np.concatenate(pool_w)
    order = np.argsort(S)
    S, W = S[order], W[order]
    cumW = np.r_[0, np.cumsum(W)]

    def pooled(cur):
        lo, hi = np.searchsorted(S, cur - band), np.searchsorted(S, cur + band, side="right")
        n = hi - lo
        return (cumW[hi] - cumW[lo]) / n if n > 30 else float(W.mean())

    rets_3m = {t: float(v[0]["Close"].iloc[-1] / v[0]["Close"].iloc[-64] - 1) for t, v in prepared.items()}
    rs_rank = pd.Series(rets_3m).rank(pct=True)

    rows = []
    for k, (t, (d, s, o, dvol)) in enumerate(prepared.items()):
        if progress and k % 10 == 0:
            progress(k / len(prepared), f"Evaluando probabilidad · {t}")
        cur = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 0.0
        st = P.conditional_stats(s, o, cur, band)
        prior = pooled(cur)
        p = P.shrunk_probability(st["wins"], st["n"], prior, strength)
        ev = P.expected_R(p, tp, sl)
        r = d.iloc[-1]
        try:
            plan = trade_plan(d, "long", sl, tp)
        except Exception:
            plan = {}
        hi52 = float(d["High"].tail(252).max())
        rows.append({
            "Ticker": t,
            "Señal": _label(cur, p, ev),
            "Prob. ganancia": p,
            "Valor esperado (R)": ev,
            "Score técnico": cur,
            "Fuerza relativa 3m": float(rs_rank[t]) * 100,
            "Precio": float(r["Close"]),
            "Var. 1d %": float(r["Close"] / d["Close"].iloc[-2] - 1) * 100,
            "Ret. 3m %": rets_3m[t] * 100,
            "Dist. máx 52s %": (float(r["Close"]) / hi52 - 1) * 100,
            "RSI": float(r["RSI"]),
            "ADX": float(r["ADX"]),
            "Vol. relativo": float(r["Volume"] / r["VOL_SMA20"]) if r["VOL_SMA20"] else np.nan,
            "ATR %": float(r["ATR"] / r["Close"] * 100),
            "Sobre SMA200": bool(r["Close"] > r["SMA200"]),
            "Entrada": plan.get("entrada"),
            "Stop": plan.get("stop"),
            "Objetivo 1": plan.get("objetivo_1"),
            "Objetivo 2": plan.get("objetivo_2"),
            "Casos similares": st["n"],
            "Vol. $ prom (M)": dvol / 1e6,
        })
    if progress:
        progress(1.0, "Escaneo completo")
    out = pd.DataFrame(rows)
    # Ranking: valor esperado, desempate por fuerza relativa
    out["Ranking score"] = out["Valor esperado (R)"] * 100 + 0.15 * out["Score técnico"] + 0.1 * out["Fuerza relativa 3m"]
    out = out.sort_values("Ranking score", ascending=False).reset_index(drop=True)
    out.insert(0, "#", range(1, len(out) + 1))
    return out
