"""Backtest por cortes ficticios: en cada vela del pasado se «corta» la serie como si fuera la última, se calcula la
señal multi-temporalidad con lo que se sabía en ese instante (velas cerradas de las mayores) y se mide qué hizo el
precio DESPUÉS del corte: si tocó primero el objetivo (tp × ATR) o el stop (sl × ATR) dentro del horizonte.

Operaciones sin solapamiento (tras una entrada se espera a su salida, como haría un trader) y separación temporal:
los parámetros se eligen en el primer 60 % de la historia de cada activo (entrenamiento) y se reportan en el 40 %
final (prueba), que el ajuste no vio. Así se puede ajustar la fórmula sin sobreajustarla.

Parámetros que se buscan:
* sigma: suavidad de la curva de pesos (core/mtf.py).
* escala: factor sobre los plazos naturales de cada temporalidad (mueve la curva hacia mayores o menores).
* umbral: |puntaje MTF| mínimo para operar.
* filtro: «ninguno» o «sin contra la mayor» (no operar si la temporalidad mayor apunta en contra).
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from . import mtf as MTF
from .timeframes import TIMEFRAMES
from .validacion import tabla_mtf

GRID = {"sigma": (0.7, 1.0, 1.4), "escala": (0.5, 1.0, 2.0), "umbral": (10, 20, 30),
        "filtro": ("ninguno", "sin contra la mayor")}
ACTUAL = {"sigma": MTF.SIGMA, "escala": 1.0, "umbral": 15, "filtro": "ninguno"}


def pesos_param(hd: float, tfs: list[str], sigma: float, escala: float) -> np.ndarray:
    h = max(hd, 0.1)
    raw = np.array([math.exp(-(math.log(h / (MTF.PLAZO[t] * escala)) ** 2) / (2 * sigma ** 2)) for t in tfs])
    return raw / raw.sum()


def simular(T: pd.DataFrame, tfs: list[str], hd: float, h: int, p: dict, tp: float, sl: float,
            desde: int = 0, hasta: int | None = None) -> dict:
    """Operaciones no solapadas entre las velas [desde, hasta). Resultado en R (múltiplos del riesgo)."""
    S = T[tfs].to_numpy(float)
    c, hi, lo, atr = (T[k].to_numpy(float) for k in ("close", "high", "low", "atr"))
    w = pesos_param(hd, tfs, p["sigma"], p["escala"])
    sc = S @ w
    n = len(c)
    hasta = n - 1 if hasta is None else min(hasta, n - 1)
    rr = tp / sl
    res, dir_ok = [], []
    i = desde
    while i < hasta:
        s = sc[i]
        if abs(s) < p["umbral"] or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        d = 1 if s > 0 else -1
        if p["filtro"] == "sin contra la mayor" and S[i, -1] * d <= -15:
            i += 1
            continue
        e = c[i]
        tgt, stp = e + d * tp * atr[i], e - d * sl * atr[i]
        fin = min(n - 1, i + h)
        r, salida = None, fin
        for j in range(i + 1, fin + 1):
            toca_t = hi[j] >= tgt if d > 0 else lo[j] <= tgt
            toca_s = lo[j] <= stp if d > 0 else hi[j] >= stp
            if toca_s:  # si ambos en la misma vela, se asume el stop (conservador)
                r, salida = -1.0, j
                break
            if toca_t:
                r, salida = rr, j
                break
        if r is None:
            r = d * (c[fin] - e) / (sl * atr[i])
        res.append(r)
        dir_ok.append(np.sign(c[min(n - 1, i + h)] - e) == d)
        i = salida + 1
    res = np.array(res)
    return {"ops": len(res), "r": res, "dir_ok": np.array(dir_ok, dtype=bool)}


def resumen(res: np.ndarray, dir_ok: np.ndarray) -> dict:
    n = len(res)
    if n == 0:
        return {"ops": 0, "ganadoras": float("nan"), "esperanza_r": float("nan"), "ic_lo": float("nan"),
                "ic_hi": float("nan"), "profit_factor": float("nan"), "acierto_dir": float("nan"), "r_total": 0.0}
    m = float(res.mean())
    se = float(res.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    gan, per = res[res > 0].sum(), -res[res < 0].sum()
    return {"ops": n, "ganadoras": float((res > 0).mean()), "esperanza_r": m, "ic_lo": m - 1.96 * se,
            "ic_hi": m + 1.96 * se, "profit_factor": float(gan / per) if per > 0 else float("inf"),
            "acierto_dir": float(dir_ok.mean()), "r_total": float(res.sum())}


def ejecutar(tickers, tf: str = "1h", horizontes_dias=(1, 3, 7), tp: float = 3.0, sl: float = 1.5,
             provider: str = "yahoo", av_key: str = "", settings: dict | None = None, corte: float = 0.6,
             progreso=None) -> dict:
    """Corre la búsqueda de parámetros en entrenamiento y reporta en prueba, por horizonte y agregado."""
    tablas, err = {}, {}
    for t in tickers:
        try:
            tablas[t] = tabla_mtf(t, tf, provider, av_key, settings)
        except Exception as e:
            err[t] = str(e)
    if not tablas:
        raise RuntimeError("Sin datos: " + "; ".join(f"{k}: {v}" for k, v in err.items()))
    tfs = MTF.triada(tf)
    tablas = {k: v for k, v in tablas.items() if all(t in v.columns for t in tfs)}
    bpd = TIMEFRAMES[tf]["bars_day"]
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    salida = []
    total = len(horizontes_dias) * (len(combos) + 1)
    k_ = 0
    for hd in horizontes_dias:
        h = max(1, int(round(hd * bpd * 7 / 5)))

        def correr(p, fase):
            rs, ds, por = [], [], {}
            for tk, T in tablas.items():
                cut = int(len(T) * corte)
                a, b = (0, cut) if fase == "train" else (cut, len(T) - h)
                r = simular(T, tfs, hd, h, p, tp, sl, a, b)
                rs.append(r["r"])
                ds.append(r["dir_ok"])
                por[tk] = resumen(r["r"], r["dir_ok"])
            return resumen(np.concatenate(rs) if rs else np.array([]),
                           np.concatenate(ds) if ds else np.array([], dtype=bool)), por

        mejor, mejor_p, ranking = None, None, []
        for p in combos:
            k_ += 1
            if progreso:
                progreso(k_ / total)
            tr, _ = correr(p, "train")
            # criterio: esperanza en R con mínimo de operaciones; desempate por profit factor
            if tr["ops"] < 20 or not np.isfinite(tr["esperanza_r"]):
                continue
            puntaje = tr["esperanza_r"] - 0.5 * (tr["esperanza_r"] - tr["ic_lo"])  # castiga la incertidumbre
            ranking.append((puntaje, p, tr))
            if mejor is None or puntaje > mejor:
                mejor, mejor_p = puntaje, p
        k_ += 1
        act_tr, _ = correr(ACTUAL, "train")
        act_te, act_por = correr(ACTUAL, "test")
        fila = {"horizonte_dias": hd, "velas": h, "actual": {"param": ACTUAL, "train": act_tr, "test": act_te,
                                                             "por_activo": act_por}}
        if mejor_p:
            b_tr = next(r[2] for r in ranking if r[1] == mejor_p)
            b_te, b_por = correr(mejor_p, "test")
            fila["ajustado"] = {"param": mejor_p, "train": b_tr, "test": b_te, "por_activo": b_por}
            fila["top"] = [{"param": r[1], "train": r[2]} for r in sorted(ranking, key=lambda x: -x[0])[:5]]
        salida.append(fila)
    return {"tickers": list(tablas), "errores": err, "tf": tf, "tfs": tfs, "tp": tp, "sl": sl,
            "corte": corte, "horizontes": salida,
            "periodo": {k: (str(v.index[0])[:10], str(v.index[int(len(v) * corte)])[:10], str(v.index[-1])[:10])
                        for k, v in tablas.items()}}
