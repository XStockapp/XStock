"""IV histórica reconstruida y comparación «modelo de movimiento vs IV».

Alpaca solo tiene barras de opciones desde febrero de 2024. Para cada acción y cada lunes de muestra:
  1. vencimiento objetivo: el primer viernes ≥ 11 días después (≈ 9-10 sesiones, como el horizonte H = 10);
  2. símbolos OCC de los strikes más cercanos al precio (call y put), con la rejilla de strikes según el precio;
  3. cierre de ese lunes de cada opción → IV por Black-Scholes; IV ATM = media de call y put del strike más cercano
     (promediar call y put reduce el error de precios desfasados).
Con esa IV se calcula la probabilidad «implícita» de que el precio toque ±k·σ20·√H en H sesiones (doble barrera para
un movimiento browniano sin deriva) y se compara con la del modelo sobre las mismas filas.
"""
from __future__ import annotations

import math
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import alpaca
from ..options import implied_vol

TASA = 0.045
_ULT = [0.0]


def _throttle(seg: float = 0.32):  # ≈ 190 llamadas/min, bajo el límite de 200 del plan Basic
    e = seg - (time.time() - _ULT[0])
    if e > 0:
        time.sleep(e)
    _ULT[0] = time.time()


def viernes_objetivo(f: date, min_dias: int = 11) -> date:
    d = f + timedelta(days=min_dias)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _pasos(s: float) -> list[float]:
    if s < 25:
        return [0.5, 1.0, 2.5]
    if s < 100:
        return [1.0, 2.5, 5.0]
    if s < 250:
        return [2.5, 5.0, 10.0]
    if s < 1000:
        return [5.0, 10.0, 25.0]
    return [10.0, 25.0, 50.0]


def strikes_candidatos(s: float, n: int = 6) -> list[float]:
    ks = set()
    for p in _pasos(s):
        base = math.floor(s / p) * p
        for j in (-1, 0, 1, 2):
            k = round(base + j * p, 2)
            if k > 0 and abs(k / s - 1) <= 0.06:
                ks.add(k)
    return sorted(ks, key=lambda k: abs(k - s))[:n]


def occ(root: str, venc: date, call: bool, k: float) -> str:
    return f"{root}{venc:%y%m%d}{'C' if call else 'P'}{int(round(k * 1000)):08d}"


def _barras_opciones(simbolos: list[str], f: date) -> dict[str, dict]:
    if not simbolos:
        return {}
    _throttle()
    ini = f"{f.isoformat()}T00:00:00Z"
    fin = f"{(f + timedelta(days=1)).isoformat()}T00:00:00Z"
    try:
        js = alpaca._get("/v1beta1/options/bars", {"symbols": ",".join(simbolos), "timeframe": "1Day",
                                                   "start": ini, "end": fin, "limit": 1000})
    except Exception:
        return {}
    return {s: rows[0] for s, rows in (js.get("bars") or {}).items() if rows}


def descargar_iv(barras: dict[str, pd.DataFrame], tickers: list[str], desde: str = "2024-02-12",
                 log=print) -> pd.DataFrame:
    """IV ATM reconstruida por (fecha, ticker) para los lunes desde `desde`. Acciones con guion (BRK-B) se omiten."""
    lunes = [d for d in pd.bdate_range(desde, pd.Timestamp.today()) if d.weekday() == 0]
    tickers = [t for t in tickers if t in barras and "-" not in t]
    filas = []
    for n, f in enumerate(lunes):
        fd = f.date()
        venc = viernes_objetivo(fd)
        dte = (venc - fd).days
        for i in range(0, len(tickers), 5):  # 5 acciones × 12 símbolos por consulta
            plan = {}
            for t in tickers[i:i + 5]:
                df = barras[t]
                if f not in df.index:
                    continue
                s = float(df.loc[f, "Close"])
                for k in strikes_candidatos(s):
                    plan[occ(t, venc, True, k)] = (t, s, k, True)
                    plan[occ(t, venc, False, k)] = (t, s, k, False)
            got = _barras_opciones(list(plan), fd)
            mejor: dict[str, tuple] = {}
            for sym, b in got.items():
                t, s, k, call = plan[sym]
                iv = implied_vol(float(b["c"]), s, k, dte / 365, call, TASA)
                if np.isfinite(iv) and 0.03 < iv < 4:
                    mejor.setdefault((t, k), {})[call] = (iv, s)
            por_t: dict[str, list] = {}
            for (t, k), d in mejor.items():
                if True in d and False in d:  # call y put del mismo strike
                    s = d[True][1]
                    por_t.setdefault(t, []).append((abs(k / s - 1), (d[True][0] + d[False][0]) / 2, k))
            for t, lst in por_t.items():
                dist, iv, k = min(lst)
                filas.append({"fecha": f, "ticker": t, "iv": iv, "dist_strike": dist, "dte": dte})
        if n % 10 == 9:
            log(f"  IV: {n + 1}/{len(lunes)} lunes · {len(filas):,} observaciones")
    if not filas:
        return pd.DataFrame(columns=["iv", "dist_strike", "dte"])
    return pd.DataFrame(filas).set_index(["fecha", "ticker"]).sort_index()


def prob_toque(sigma_h: np.ndarray, a: np.ndarray, terminos: int = 60) -> np.ndarray:
    """P(un movimiento browniano sin deriva con desviación sigma_h al final del horizonte toca ±a antes del final).
    1 − P(permanecer en (−a, a)); serie clásica de la doble barrera."""
    sigma_h, a = np.asarray(sigma_h, float), np.asarray(a, float)
    z = (sigma_h / a) ** 2
    acc = np.zeros_like(z)
    for j in range(terminos):
        n = 2 * j + 1
        acc += ((-1) ** j) / n * np.exp(-(n * n) * math.pi ** 2 * z / 8)
    return np.clip(1 - 4 / math.pi * acc, 1e-4, 1 - 1e-4)


def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")


def combinar(p_modelo, iv, sigma_d, H: int, k: float, rep: dict) -> dict:
    """En vivo: con el reporte vs-IV, probabilidad que cobra la IV, probabilidad combinada y señal IV barata/cara.
    p_modelo: probabilidad SIN calibrar del modelo de movimiento (la misma escala usada al ajustar la combinación)."""
    p_modelo, iv, sigma_d = (np.atleast_1d(np.asarray(x, float)) for x in (p_modelo, iv, sigma_d))
    a = k * sigma_d * math.sqrt(H)
    p_iv = prob_toque(iv * math.sqrt(H / 252), a)
    p_iv_cal = np.interp(p_iv, rep["cal_iv"]["x"], rep["cal_iv"]["y"])
    z = rep["intercepto"] + rep["coef_iv"] * _logit(p_iv) + rep["coef_modelo"] * _logit(p_modelo)
    p_comb = 1 / (1 + np.exp(-z))
    dif = _logit(p_modelo) - _logit(p_iv_cal)
    q = np.searchsorted(rep["cortes_dif"], dif) + 1  # 1..5
    senal = np.where(q >= 5, "barata", np.where(q <= 1, "cara", "justa"))
    return {"p_iv": p_iv_cal, "p_comb": p_comb, "dif": dif, "quintil": q, "senal": senal}


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def comparar(O: pd.DataFrame, ivdf: pd.DataFrame, panel: pd.DataFrame, H: int, k: float,
             corte: str = "2025-07-01") -> dict | None:
    """O: predicciones fuera de muestra del modelo de movimiento (p, y). Compara contra la IV sobre las mismas filas.
    Se calibra la IV y se ajusta la combinación con las fechas < `corte` y se mide con las posteriores."""
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    D = O[["p", "y"]].join(ivdf, how="inner").join(panel[["sigma_d"]], how="left").dropna()
    if len(D) < 500:
        return None
    a = k * D["sigma_d"].to_numpy() * math.sqrt(H)
    D["p_iv"] = prob_toque(D["iv"].to_numpy() * math.sqrt(H / 252), a)
    D["iv_vs_rv"] = D["iv"] / (D["sigma_d"] * math.sqrt(252))
    f = D.index.get_level_values("fecha")
    tr, te = D[f < pd.Timestamp(corte)], D[f >= pd.Timestamp(corte)]
    if len(tr) < 300 or len(te) < 300:
        return None
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99).fit(tr["p_iv"], tr["y"])
    lr = LogisticRegression(max_iter=300).fit(np.c_[_logit(tr["p_iv"]), _logit(tr["p"])], tr["y"])
    te = te.copy()
    te["p_iv_cal"] = iso.predict(te["p_iv"])
    te["p_comb"] = lr.predict_proba(np.c_[_logit(te["p_iv"]), _logit(te["p"])])[:, 1]
    y = te["y"].to_numpy()

    def brier(p):
        return float(np.mean((np.asarray(p) - y) ** 2))
    # ¿cuándo el modelo ve MÁS movimiento del que cobra la IV? quintiles de la diferencia de logits
    te["dif"] = _logit(te["p"]) - _logit(te["p_iv_cal"])
    q = pd.qcut(te["dif"], 5, labels=False, duplicates="drop")
    tramos = te.groupby(q).agg(dif=("dif", "mean"), p_iv=("p_iv_cal", "mean"), p_modelo=("p", "mean"),
                               real=("y", "mean"), n=("y", "size")).reset_index(drop=True)
    return {
        "filas": int(len(D)), "filas_prueba": int(len(te)), "acciones": int(D.index.get_level_values("ticker").nunique()),
        "desde": str(f.min().date()), "hasta": str(f.max().date()), "corte": corte,
        "iv_mediana": float(D["iv"].median()), "iv_vs_rv_mediana": float(D["iv_vs_rv"].median()),
        "auc_iv": _auc(y, te["p_iv"]), "auc_modelo": _auc(y, te["p"]), "auc_combinado": _auc(y, te["p_comb"]),
        "brier_iv_cal": brier(te["p_iv_cal"]), "brier_modelo": brier(te["p"]), "brier_combinado": brier(te["p_comb"]),
        "coef_iv": float(lr.coef_[0][0]), "coef_modelo": float(lr.coef_[0][1]), "intercepto": float(lr.intercept_[0]),
        # para usar en vivo: calibración de la probabilidad de la IV y cortes de quintil de la diferencia de logits
        "cal_iv": {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_]},
        "cortes_dif": [float(v) for v in te["dif"].quantile([0.2, 0.4, 0.6, 0.8])],
        "tasa_real": float(y.mean()), "tramos": tramos.to_dict("records"),
    }
