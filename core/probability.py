"""
Probabilidad objetiva de ganancia basada en evidencia histórica.

Método "triple barrera" (López de Prado): para cada día t se simula una operación
con entrada al cierre, objetivo = entrada + TP·ATR, stop = entrada − SL·ATR y un
horizonte máximo de H días. Se registra cuál barrera se toca primero.

La probabilidad de hoy = frecuencia con la que, en el pasado, días con un puntaje
técnico SIMILAR al actual terminaron tocando el objetivo antes que el stop.
Se ajusta con un prior bayesiano (encogimiento) hacia la tasa del universo
para no sobre-confiar en muestras pequeñas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

DEFAULTS = dict(tp=3.0, sl=1.5, horizon=20, band=15.0, prior_strength=25)


def barrier_outcomes(df: pd.DataFrame, tp=2.0, sl=1.0, horizon=20, direction="long") -> pd.DataFrame:
    """Devuelve por barra: win (1/0/NaN si no resuelve aún), R obtenido y días hasta salida."""
    c = df["Close"].values
    h = df["High"].values
    l = df["Low"].values
    a = df["ATR"].values
    n = len(df)
    win = np.full(n, np.nan)
    rr = np.full(n, np.nan)
    days = np.full(n, np.nan)
    if n <= horizon + 1:
        return pd.DataFrame({"win": win, "R": rr, "dias": days}, index=df.index)

    H = sliding_window_view(h[1:], horizon)  # filas: t+1 .. t+horizon
    L = sliding_window_view(l[1:], horizon)
    C_end = c[horizon:]
    m = H.shape[0]  # = n - horizon
    entry = c[:m]
    atr_ = a[:m]
    sgn = 1 if direction == "long" else -1
    tp_px = entry + sgn * tp * atr_
    sl_px = entry - sgn * sl * atr_
    if direction == "long":
        hit_tp = H >= tp_px[:, None]
        hit_sl = L <= sl_px[:, None]
    else:
        hit_tp = L <= tp_px[:, None]
        hit_sl = H >= sl_px[:, None]
    big = horizon + 10
    i_tp = np.where(hit_tp.any(1), hit_tp.argmax(1), big)
    i_sl = np.where(hit_sl.any(1), hit_sl.argmax(1), big)
    # Si ambas en la misma vela: asumimos stop primero (conservador)
    w = np.where(i_tp < i_sl, 1.0, 0.0)
    r = np.where(i_tp < i_sl, tp / sl, -1.0)
    d = np.minimum(i_tp, i_sl) + 1.0
    timeout = (i_tp == big) & (i_sl == big)
    r_to = sgn * (C_end - entry) / (sl * atr_)
    r = np.where(timeout, np.clip(r_to, -1, tp / sl), r)
    w = np.where(timeout, (r_to > 0).astype(float), w)
    d = np.where(timeout, horizon, d)
    valid = np.isfinite(atr_) & (atr_ > 0)
    win[:m] = np.where(valid, w, np.nan)
    rr[:m] = np.where(valid, r, np.nan)
    days[:m] = np.where(valid, d, np.nan)
    return pd.DataFrame({"win": win, "R": rr, "dias": days}, index=df.index)


def conditional_stats(score: pd.Series, out: pd.DataFrame, current: float, band: float = 15.0) -> dict:
    """Estadística de días históricos con puntaje dentro de ±band del actual."""
    j = pd.concat([score.rename("s"), out], axis=1).dropna()
    sim = j[(j["s"] - current).abs() <= band]
    allr = j
    return {
        "n": int(len(sim)),
        "wins": float(sim["win"].sum()),
        "avg_R": float(sim["R"].mean()) if len(sim) else np.nan,
        "base_rate": float(allr["win"].mean()) if len(allr) else np.nan,
        "base_R": float(allr["R"].mean()) if len(allr) else np.nan,
        "dias_prom": float(sim["dias"].mean()) if len(sim) else np.nan,
    }


def shrunk_probability(wins: float, n: int, prior_p: float, strength: int = 25) -> float:
    if not np.isfinite(prior_p):
        prior_p = 0.35
    return float((wins + strength * prior_p) / (n + strength))


def expected_R(p: float, tp=2.0, sl=1.0) -> float:
    return p * (tp / sl) - (1 - p) * 1.0


def backtest_signal(df: pd.DataFrame, score: pd.Series, threshold=40.0, tp=2.0, sl=1.0,
                    horizon=20, direction="long") -> dict:
    """Backtest sin solapamiento: entra cuando el puntaje cruza el umbral."""
    out = barrier_outcomes(df, tp, sl, horizon, direction)
    s = score if direction == "long" else -score
    cross = (s >= threshold) & (s.shift() < threshold)
    trades, next_free = [], -1
    idx = list(df.index)
    for i, t in enumerate(idx):
        if i <= next_free or not cross.get(t, False):
            continue
        o = out.loc[t]
        if pd.isna(o["R"]):
            continue
        trades.append({"fecha": t, "R": o["R"], "win": o["win"], "dias": o["dias"]})
        next_free = i + int(o["dias"])
    if not trades:
        return {"n": 0}
    T = pd.DataFrame(trades)
    gains = T.loc[T["R"] > 0, "R"].sum()
    losses = -T.loc[T["R"] < 0, "R"].sum()
    eq = T["R"].cumsum()
    return {
        "n": len(T),
        "win_rate": float(T["win"].mean()),
        "avg_R": float(T["R"].mean()),
        "profit_factor": float(gains / losses) if losses > 0 else float("inf"),
        "max_dd_R": float((eq - eq.cummax()).min()),
        "total_R": float(T["R"].sum()),
        "trades": T,
    }
