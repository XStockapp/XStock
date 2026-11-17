"""Modelo base del Motor A (LightGBM) y su validación walk-forward con purga.

Validación (lo único que cuenta son predicciones FUERA de muestra):
  · Por años: para probar el año Y se entrena con todo lo anterior a Y, quitando las últimas H+2 sesiones
    (purga: sus etiquetas miran días que ya están dentro del año de prueba).
  · Se compara contra dos referencias: la tasa base (predecir siempre la frecuencia histórica) y un momentum simple
    (regresión logística con 3 retornos). El modelo solo «tiene ventaja» si supera a ambas fuera de muestra.
  · Métricas: AUC, Brier y Brier skill score (mejora sobre la tasa base), curva de fiabilidad, IC de rango por fecha
    (submuestreado cada H días para no contar muestras solapadas) y la ventaja económica por deciles.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .dataset import columnas_variables

PARAMS = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 31, "min_child_samples": 400,
          "subsample": 0.7, "subsample_freq": 1, "colsample_bytree": 0.7, "reg_lambda": 1.0,
          "verbose": -1, "n_jobs": -1}
N_ARBOLES = 600
MOMENTUM = ["ret_5", "ret_20", "ret_60"]
UMBRALES = {"auc": 0.52, "bss": 0.0, "ic_t": 2.0}


def _lgb():
    import lightgbm as lgb
    return lgb


def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")


def _brier(y, p):
    return float(np.mean((p - y) ** 2))


def _entrenar(Xtr, ytr, Xva=None, yva=None):
    lgb = _lgb()
    dtr = lgb.Dataset(Xtr, ytr, free_raw_data=False)
    kw = {}
    if Xva is not None and len(Xva):
        dva = lgb.Dataset(Xva, yva, reference=dtr)
        kw = {"valid_sets": [dva], "callbacks": [lgb.early_stopping(50, verbose=False)]}
    return lgb.train(PARAMS, dtr, num_boost_round=N_ARBOLES, **kw)


def _momentum(Xtr, ytr, Xte):
    from sklearn.linear_model import LogisticRegression
    a, b = Xtr[MOMENTUM].fillna(0).clip(-6, 6), Xte[MOMENTUM].fillna(0).clip(-6, 6)
    return LogisticRegression(max_iter=300).fit(a, ytr).predict_proba(b)[:, 1]


def _purga(fechas: pd.DatetimeIndex, inicio: pd.Timestamp, H: int) -> pd.Timestamp:
    previas = fechas[fechas < inicio].unique().sort_values()
    return previas[-(H + 2)] if len(previas) > H + 2 else previas[0]


def walk_forward(panel: pd.DataFrame, H: int = 10, primer_anio: int | None = None, log=print) -> dict:
    P = panel.dropna(subset=["y"])
    cols = columnas_variables(P)
    fechas = P.index.get_level_values("fecha")
    anios = sorted(set(fechas.year))
    primer_anio = primer_anio or anios[min(3, len(anios) - 1)]  # al menos 3 años de entrenamiento
    oos, pliegues = [], []
    for Y in [a for a in anios if a >= primer_anio]:
        ini = pd.Timestamp(Y, 1, 1)
        fin = pd.Timestamp(Y + 1, 1, 1)
        corte = _purga(fechas, ini, H)
        tr, te = P[fechas < corte], P[(fechas >= ini) & (fechas < fin)]
        if len(te) < 200 or len(tr) < 2000:
            continue
        # validación interna para early stopping: el último 15 % (en el tiempo) del entrenamiento, también purgado
        ft = tr.index.get_level_values("fecha")
        cva = ft.unique().sort_values()[int(0.85 * ft.nunique())]
        cva_p = _purga(ft, cva, H)
        a, v = tr[ft < cva_p], tr[ft >= cva]
        m = _entrenar(a[cols], a["y"], v[cols], v["y"])
        p = m.predict(te[cols], num_iteration=m.best_iteration or None)
        base = float(tr["y"].mean())
        pm = _momentum(tr[cols], tr["y"], te[cols])
        y = te["y"].to_numpy()
        d = {"anio": Y, "n_test": int(len(te)), "n_train": int(len(tr)), "arboles": int(m.best_iteration or N_ARBOLES),
             "tasa_base": base, "auc": _auc(y, p), "auc_momentum": _auc(y, pm),
             "brier": _brier(y, p), "brier_base": _brier(y, np.full(len(y), base)), "brier_momentum": _brier(y, pm)}
        d["bss"] = 1 - d["brier"] / d["brier_base"]
        pliegues.append(d)
        oos.append(pd.DataFrame({"p": p, "p_mom": pm, "p_base": base, "y": y, "ret": te["ret_h_sigma"].to_numpy()},
                                index=te.index))
        log(f"  {Y}: AUC {d['auc']:.3f} (momentum {d['auc_momentum']:.3f}) · BSS {d['bss']:+.4f} · n={len(te):,}")
    if not oos:
        raise ValueError("No hay suficientes datos para la validación walk-forward.")
    O = pd.concat(oos)
    return {"pliegues": pliegues, "oos": O, "columnas": cols, "resumen": resumir(O, pliegues, H)}


def resumir(O: pd.DataFrame, pliegues: list[dict], H: int) -> dict:
    y, p = O["y"].to_numpy(), O["p"].to_numpy()
    r = {"n_oos": int(len(O)), "auc": _auc(y, p), "auc_momentum": _auc(y, O["p_mom"].to_numpy()),
         "brier": _brier(y, p), "brier_base": _brier(y, O["p_base"].to_numpy()),
         "brier_momentum": _brier(y, O["p_mom"].to_numpy()), "tasa_real": float(y.mean())}
    r["bss"] = 1 - r["brier"] / r["brier_base"]
    r["bss_momentum"] = 1 - r["brier_momentum"] / r["brier_base"]
    # IC de rango por fecha (correlación de Spearman entre probabilidad y retorno a H en σ), cada H fechas
    fechas = O.index.get_level_values("fecha").unique().sort_values()[::H]
    ics = []
    for f in fechas:
        g = O.xs(f, level="fecha")
        if len(g) >= 10:
            ics.append(g["p"].rank().corr(g["ret"].rank()))
    ics = np.array([x for x in ics if np.isfinite(x)])
    r["ic_medio"] = float(ics.mean()) if len(ics) else float("nan")
    r["ic_t"] = float(ics.mean() / ics.std(ddof=1) * math.sqrt(len(ics))) if len(ics) > 2 and ics.std() > 0 else float("nan")
    r["ic_n"] = int(len(ics))
    # fiabilidad: 10 tramos de probabilidad predicha → frecuencia real
    q = pd.qcut(O["p"], 10, labels=False, duplicates="drop")
    fia = O.groupby(q).agg(p_media=("p", "mean"), real=("y", "mean"), n=("y", "size"), ret_sigma=("ret", "mean"))
    r["fiabilidad"] = fia.reset_index(drop=True).to_dict("records")
    r["decil_alto"] = fia.iloc[-1].to_dict()
    r["decil_bajo"] = fia.iloc[0].to_dict()
    r["pliegues_auc_sobre_05"] = int(sum(1 for d in pliegues if d["auc"] > 0.5))
    r["pliegues_supera_momentum"] = int(sum(1 for d in pliegues if d["auc"] > d["auc_momentum"]))
    r["pliegues"] = len(pliegues)
    senal = (r["auc"] >= UMBRALES["auc"] and r["bss"] > UMBRALES["bss"] and (r["ic_t"] or 0) >= UMBRALES["ic_t"]
             and r["pliegues_auc_sobre_05"] >= math.ceil(0.75 * len(pliegues)))
    supera = r["auc"] > r["auc_momentum"] + 0.002 and r["bss"] > r["bss_momentum"]
    r["veredicto"] = ("VENTAJA DEMOSTRADA" if senal and supera else
                      "SEÑAL REAL, PERO NO SUPERA AL MOMENTUM SIMPLE" if senal else "SIN VENTAJA DEMOSTRADA")
    r["criterio"] = (f"Señal: AUC ≥ {UMBRALES['auc']}, Brier skill > 0, IC t ≥ {UMBRALES['ic_t']} y AUC > 0.5 en al "
                     "menos el 75 % de los años. Ventaja: además supera al momentum simple en AUC y en Brier.")
    return r


def calibrador(O: pd.DataFrame) -> dict:
    """Calibración isotónica ajustada SOLO con predicciones fuera de muestra (honesta)."""
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99).fit(O["p"], O["y"])
    return {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_]}


def calibrar(p, cal: dict | None):
    if not cal:
        return p
    return np.interp(p, cal["x"], cal["y"])


def importancia(modelo, cols: list[str], n: int = 20) -> list[dict]:
    g = modelo.feature_importance("gain")
    tot = g.sum() or 1
    orden = np.argsort(-g)[:n]
    return [{"variable": cols[i], "peso": float(g[i] / tot)} for i in orden]


def modelo_final(panel: pd.DataFrame, cols: list[str], arboles: int):
    P = panel.dropna(subset=["y"])
    lgb = _lgb()
    return lgb.train(PARAMS, lgb.Dataset(P[cols], P["y"]), num_boost_round=max(arboles, 50))
