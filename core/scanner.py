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
from .market import rendimientos, spark
from .levels import trade_plan
from .technical import compute_all, score_series
from . import patterns as PT


def _patron(d: pd.DataFrame) -> dict:
    """Patrón chartista vigente (movimiento actual, velas diarias) para la tabla del escáner."""
    try:
        f = PT.patterns(d, tf="1D")
    except Exception:
        f = []
    if not f:
        return {"Patrón": None, "Patrón sesgo": None, "Patrón estado": None, "Patrón activación": None,
                "Patrón objetivo": None}
    f = f[0]
    return {"Patrón": f["nombre"], "Patrón sesgo": f["sesgo"], "Patrón estado": f["estado_meta"],
            "Patrón activación": f.get("activacion"), "Patrón objetivo": f.get("objetivo")}


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


def _label_short(score: float, ev: float) -> str:
    if ev >= 0.30 and score <= -20:
        return "VENTA FUERTE"
    if ev >= 0.10 and score <= 0:
        return "VENTA"
    return "NEUTRAL"


def _pool(pairs):
    S = np.concatenate([a for a, _ in pairs]) if pairs else np.array([0.0])
    W = np.concatenate([b for _, b in pairs]) if pairs else np.array([0.35])
    order = np.argsort(S)
    S, W = S[order], W[order]
    cumW = np.r_[0, np.cumsum(W)]

    def pooled(cur, band):
        lo, hi = np.searchsorted(S, cur - band), np.searchsorted(S, cur + band, side="right")
        n = hi - lo
        return (cumW[hi] - cumW[lo]) / n if n > 30 else float(W.mean())
    return pooled


def scan(prices: dict[str, pd.DataFrame], min_price=5.0, min_dollar_vol=20e6, tp=3.0, sl=1.5, horizon=20,
         band=15.0, strength=25, progress: Callable[[float, str], None] | None = None,
         meta: dict | None = None) -> pd.DataFrame:
    """Evalúa cada acción en ambos sentidos: compra (long) y venta en corto (short)."""
    meta = meta or {}
    prepared = {}
    pairs_l, pairs_s = [], []
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
            ol = P.barrier_outcomes(d, tp, sl, horizon, "long")
            osh = P.barrier_outcomes(d, tp, sl, horizon, "short")
        except Exception:
            continue
        prepared[t] = (d, s, ol, osh, dvol)
        jl = pd.concat([s, ol["win"]], axis=1).dropna()
        pairs_l.append((jl.iloc[:, 0].values, jl.iloc[:, 1].values))
        js = pd.concat([-s, osh["win"]], axis=1).dropna()
        pairs_s.append((js.iloc[:, 0].values, js.iloc[:, 1].values))

    if not prepared:
        return pd.DataFrame()
    pooled_l, pooled_s = _pool(pairs_l), _pool(pairs_s)

    rets_3m = {t: float(v[0]["Close"].iloc[-1] / v[0]["Close"].iloc[-64] - 1) for t, v in prepared.items()}
    rs_rank = pd.Series(rets_3m).rank(pct=True)

    rows = []
    for k, (t, (d, s, ol, osh, dvol)) in enumerate(prepared.items()):
        if progress and k % 10 == 0:
            progress(k / len(prepared), f"Evaluando probabilidad · {t}")
        cur = float(s.iloc[-1]) if pd.notna(s.iloc[-1]) else 0.0
        stl = P.conditional_stats(s, ol, cur, band)
        p = P.shrunk_probability(stl["wins"], stl["n"], pooled_l(cur, band), strength)
        ev = P.expected_R(p, tp, sl)
        sts = P.conditional_stats(-s, osh, -cur, band)
        ps = P.shrunk_probability(sts["wins"], sts["n"], pooled_s(-cur, band), strength)
        evs = P.expected_R(ps, tp, sl)
        r = d.iloc[-1]
        try:
            plan = trade_plan(d, "long", sl, tp)
        except Exception:
            plan = {}
        try:
            plan_s = trade_plan(d, "short", sl, tp)
        except Exception:
            plan_s = {}
        hi52 = float(d["High"].tail(252).max())
        side = "LONG" if (ev > evs or (ev == evs and cur >= 0)) else "SHORT"
        mt = meta.get(t, {})
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
            "Casos similares": stl["n"],
            "Vol. $ prom (M)": dvol / 1e6,
            # --- lado corto ---
            "Señal corto": _label_short(cur, evs),
            "Prob. corto": ps,
            "EV corto (R)": evs,
            "Entrada corto": plan_s.get("entrada"),
            "Stop corto": plan_s.get("stop"),
            "Obj. corto 1": plan_s.get("objetivo_1"),
            "Obj. corto 2": plan_s.get("objetivo_2"),
            "Casos similares corto": sts["n"],
            "Lado": side,
            "Sector": mt.get("sector") or "Sin sector",
            "Market cap": mt.get("cap"),
            "Nombre": mt.get("nombre"),
            **{f"Ret {k}": v for k, v in rendimientos(d, t).items()},
            "Spark": spark(d),
            **_patron(d),
        })
    if progress:
        progress(1.0, "Escaneo completo")
    out = pd.DataFrame(rows)
    out["Ranking score"] = out["Valor esperado (R)"] * 100 + 0.15 * out["Score técnico"] + 0.1 * out["Fuerza relativa 3m"]
    out["Ranking corto"] = out["EV corto (R)"] * 100 - 0.15 * out["Score técnico"] + 0.1 * (100 - out["Fuerza relativa 3m"])
    out = out.sort_values("Ranking score", ascending=False).reset_index(drop=True)
    out.insert(0, "#", range(1, len(out) + 1))
    return out
