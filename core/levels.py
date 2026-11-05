"""
Plan de operación: entrada, stop-loss, objetivos y tamaño de posición.
Basado en ATR (volatilidad), soportes/resistencias y relación riesgo/beneficio.
"""
from __future__ import annotations

import pandas as pd

from .technical import fibonacci, pivot_levels


def trade_plan(df: pd.DataFrame, direction: str = "long", sl_atr: float = 1.5, tp_atr: float = 3.0,
               account: float = 10_000, risk_pct: float = 1.0) -> dict:
    r = df.iloc[-1]
    px, a = float(r["Close"]), float(r["ATR"])
    supports, resist = pivot_levels(df)
    fib = fibonacci(df)
    long = direction == "long"
    sgn = 1 if long else -1

    # --- Entrada ---------------------------------------------------------
    ema21 = float(r["EMA21"])
    extended = (px - ema21) * sgn > 1.0 * a
    if extended:
        # esperar retroceso: EMA21 o soporte/resistencia más cercano en esa zona
        cands = [ema21]
        near = supports if long else resist
        cands += [lv for lv, _ in near[:3] if abs(lv - px) <= 2 * a]
        entry = max(cands) if long else min(cands)
        entry_type = "Límite en retroceso (precio extendido > 1 ATR de la EMA21)"
    else:
        entry = px
        entry_type = "A mercado / cierre actual"

    # --- Stop ------------------------------------------------------------
    base_stop = entry - sgn * sl_atr * a
    struct = None
    if long and supports:
        below = [lv for lv, _ in supports if lv < entry]
        if below:
            struct = below[0] - 0.25 * a
    if not long and resist:
        above = [lv for lv, _ in resist if lv > entry]
        if above:
            struct = above[0] + 0.25 * a
    stop = base_stop
    stop_type = f"{sl_atr} × ATR"
    if struct is not None:
        dist = abs(entry - struct)
        if 1.0 * a <= dist <= 3.0 * a:
            stop, stop_type = struct, "Bajo soporte estructural − 0.25 ATR" if long else "Sobre resistencia + 0.25 ATR"
    risk = abs(entry - stop)

    # --- Objetivos -------------------------------------------------------
    t1 = entry + sgn * 2 * risk
    t2 = entry + sgn * max(3 * risk, tp_atr * a)
    obstacles = [lv for lv, _ in (resist if long else supports)]
    obstacles = [lv for lv in obstacles if (lv - entry) * sgn > 1.2 * risk]
    t1_type = "2R"
    if obstacles and abs(obstacles[0] - entry) < abs(t1 - entry) * 1.25:
        t1 = obstacles[0] - sgn * 0.1 * a
        t1_type = "Resistencia más cercana" if long else "Soporte más cercano"
    if (t2 - t1) * sgn <= 0:
        t2 = t1 + sgn * risk

    # --- Tamaño ----------------------------------------------------------
    risk_money = account * risk_pct / 100
    shares = int(risk_money // risk) if risk > 0 else 0
    shares = min(shares, int(account // entry)) if entry > 0 else 0

    return {
        "direccion": "COMPRA (largo)" if long else "VENTA (corto)",
        "precio": px,
        "atr": a,
        "entrada": entry,
        "tipo_entrada": entry_type,
        "stop": stop,
        "tipo_stop": stop_type,
        "objetivo_1": t1,
        "tipo_obj1": t1_type,
        "objetivo_2": t2,
        "riesgo_por_accion": risk,
        "rr_1": abs(t1 - entry) / risk if risk else None,
        "rr_2": abs(t2 - entry) / risk if risk else None,
        "acciones": shares,
        "capital_requerido": shares * entry,
        "riesgo_monetario": shares * risk,
        "soportes": supports[:4],
        "resistencias": resist[:4],
        "fibonacci": fib,
    }
