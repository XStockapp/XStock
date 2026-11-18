"""B2: ¿hacia dónde irá la IV de cada acción la próxima semana?

Objetivo: y = ln(IV en t+~1 semana / IV en t), con la IV de DoltHub (volatility_history.iv_current).
Para quien compra opciones, saber si la IV va a caer (después de resultados, tras la Fed, al volver a su nivel
normal) o a subir (antes de resultados) cambia el valor esperado tanto como acertar el movimiento.

Validación: walk-forward por años, con purga de una semana. Se compara contra dos referencias:
  · «sin cambio» (y = 0)
  · «reversión simple»: regresión lineal con IV/HV, rango de IV del año y resultados dentro del horizonte.
El modelo solo cuenta si supera a la reversión simple fuera de muestra (R² y correlación de rango por fecha).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..motor_a import macro as MC

DIAS_OBJ = (6, 10)  # el «t + 1 semana» debe caer entre 6 y 10 días de calendario
REF = ["iv_hv", "iv_rango", "res_en_horizonte", "iv_cambio_1s"]
PARAMS = {"objective": "huber", "alpha": 0.9, "learning_rate": 0.03, "num_leaves": 31, "min_child_samples": 300,
          "subsample": 0.7, "subsample_freq": 1, "colsample_bytree": 0.8, "reg_lambda": 1.0, "verbose": -1}


def _cambio_previo(g: pd.DataFrame, dias: int) -> pd.Series:
    """ln(IV hoy / IV de hace ~`dias` días de calendario) usando la observación más cercana anterior."""
    s = g.set_index("fecha")["iv_current"]
    prev = s.reindex(s.index - pd.Timedelta(days=dias), method="ffill", tolerance=pd.Timedelta(days=4))
    return pd.Series(np.log(s.to_numpy() / prev.to_numpy()), index=g.index)


def _objetivo(g: pd.DataFrame) -> pd.Series:
    f = g["fecha"].to_numpy()
    iv = g["iv_current"].to_numpy()
    y = np.full(len(g), np.nan)
    j = 0
    for i in range(len(g)):
        j = max(j, i + 1)
        while j < len(g) and (f[j] - f[i]) < np.timedelta64(DIAS_OBJ[0], "D"):
            j += 1
        if j < len(g) and (f[j] - f[i]) <= np.timedelta64(DIAS_OBJ[1], "D"):
            y[i] = math.log(iv[j] / iv[i])
    return pd.Series(y, index=g.index)


def _resultados(g: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    fechas = np.sort(cal["fecha"].to_numpy())
    out = pd.DataFrame(index=g.index)
    if len(fechas) == 0:
        out["res_dias_hasta"], out["res_dias_desde"], out["res_en_horizonte"] = 45.0, 90.0, 0.0
        return out
    f = g["fecha"].to_numpy()
    k = np.searchsorted(fechas, f, side="left")  # próximo resultado (incluye hoy)
    hasta = np.where(k < len(fechas), (fechas[np.minimum(k, len(fechas) - 1)] - f) / np.timedelta64(1, "D"), np.nan)
    kd = np.searchsorted(fechas, f, side="right") - 1
    desde = np.where(kd >= 0, (f - fechas[np.maximum(kd, 0)]) / np.timedelta64(1, "D"), np.nan)
    # el calendario se conoce con ~4 semanas de antelación: más allá se trata como «sin fecha»
    out["res_dias_hasta"] = np.where(np.isnan(hasta) | (hasta > 30), 45.0, hasta)
    out["res_dias_desde"] = np.where(np.isnan(desde), 90.0, np.minimum(desde, 90))
    out["res_en_horizonte"] = ((out["res_dias_hasta"] >= 0) & (out["res_dias_hasta"] <= 8)).astype(float)
    if "hora" in cal and len(cal):
        amc = cal.set_index("fecha")["hora"].astype(str).str.contains("After", case=False)
        prox = pd.Series(fechas[np.minimum(k, len(fechas) - 1)]).map(amc).to_numpy()
        out["res_despues_cierre"] = np.where(out["res_dias_hasta"] <= 30, prox.astype(float), np.nan)
    return out


def construir(H: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Panel (fecha, ticker) con variables y objetivo."""
    spy = H[H["ticker"] == "SPY"].set_index("fecha")["iv_current"]
    partes = []
    for t, g in H.groupby("ticker"):
        g = g.sort_values("fecha").reset_index(drop=True)
        if len(g) < 120:
            continue
        Z = pd.DataFrame({"fecha": g["fecha"], "ticker": t})
        Z["iv"] = g["iv_current"]
        Z["hv"] = g["hv_current"]
        Z["iv_hv"] = np.log(g["iv_current"] / g["hv_current"])
        rango = (g["iv_year_high"] - g["iv_year_low"]).replace(0, np.nan)
        Z["iv_rango"] = (g["iv_current"] - g["iv_year_low"]) / rango
        Z["iv_cambio_1s"] = _cambio_previo(g, 7)
        Z["iv_cambio_1m"] = _cambio_previo(g, 30)
        Z["hv_cambio_1m"] = np.log(g["hv_current"] / g.set_index("fecha")["hv_current"].reindex(
            g["fecha"] - pd.Timedelta(days=30), method="ffill", tolerance=pd.Timedelta(days=4)).to_numpy())
        Z = Z.join(_resultados(g, cal[cal["ticker"] == t] if len(cal) else cal))
        Z["y"] = _objetivo(g)
        partes.append(Z)
    P = pd.concat(partes, ignore_index=True)
    # mercado y Reserva Federal
    s = spy.reindex(P["fecha"]).to_numpy()
    P["mkt_iv"] = s
    P["iv_vs_mkt"] = np.log(P["iv"] / P["mkt_iv"])
    P["mkt_iv_cambio_1s"] = P["fecha"].map(np.log(spy / spy.reindex(spy.index - pd.Timedelta(days=7), method="ffill",
                                                                     tolerance=pd.Timedelta(days=4)).to_numpy()))
    fechas = pd.DatetimeIndex(sorted(P["fecha"].unique()))
    M = MC.variables(pd.DataFrame({"Close": np.ones(len(fechas))}, index=fechas))[
        ["mac_dias_hasta_fomc", "mac_dias_desde_fomc", "mac_fomc_con_proyecciones"]]
    P = P.join(M, on="fecha")
    P = P.replace([np.inf, -np.inf], np.nan).set_index(["fecha", "ticker"]).sort_index()
    num = P.select_dtypes("number").columns
    P[num] = P[num].astype("float32")
    return P


def variables(P: pd.DataFrame) -> list[str]:
    return [c for c in P.columns if c not in ("y", "iv", "hv")]


def _ic_por_fecha(O: pd.DataFrame, col: str, cada: int = 5) -> tuple[float, float, int]:
    ics = []
    for f, g in list(O.groupby(level="fecha"))[::cada]:
        if len(g) >= 20:
            ics.append(g[col].rank().corr(g["y"].rank()))
    ics = np.array([x for x in ics if np.isfinite(x)])
    if len(ics) < 3:
        return float("nan"), float("nan"), len(ics)
    return float(ics.mean()), float(ics.mean() / ics.std(ddof=1) * math.sqrt(len(ics))), len(ics)


def _r2(y, p):
    return float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)) if len(y) > 1 else float("nan")


def walk_forward(P: pd.DataFrame, primer_anio: int = 2021, log=print) -> dict:
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    D = P.dropna(subset=["y"])
    D = D[D["y"].abs() < 2]  # descarta errores de datos (IV que se multiplica por 7 en una semana)
    cols = variables(D)
    f = D.index.get_level_values("fecha")
    oos, pl = [], []
    for Y in sorted(set(f.year)):
        if Y < primer_anio:
            continue
        ini, fin = pd.Timestamp(Y, 1, 1), pd.Timestamp(Y + 1, 1, 1)
        tr, te = D[f < ini - pd.Timedelta(days=12)], D[(f >= ini) & (f < fin)]
        if len(te) < 1000 or len(tr) < 5000:
            continue
        ft = tr.index.get_level_values("fecha")
        cva = ft.max() - pd.Timedelta(days=150)
        a, v = tr[ft < cva - pd.Timedelta(days=12)], tr[ft >= cva]
        m = lgb.train(PARAMS, lgb.Dataset(a[cols], a["y"]), 800, valid_sets=[lgb.Dataset(v[cols], v["y"])],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        ref = LinearRegression().fit(tr[REF].fillna(0), tr["y"]).predict(te[REF].fillna(0))
        y = te["y"].to_numpy()
        d = {"anio": Y, "n": int(len(te)), "arboles": int(m.best_iteration), "r2": _r2(y, p), "r2_ref": _r2(y, ref),
             "r2_cero": _r2(y, np.zeros_like(y)), "acierto_signo": float(np.mean(np.sign(p) == np.sign(y)))}
        pl.append(d)
        oos.append(pd.DataFrame({"p": p, "ref": ref, "y": y, "res_en_horizonte": te["res_en_horizonte"].to_numpy()},
                                index=te.index))
        log(f"  {Y}: R² modelo {d['r2']:+.3f} · reversión simple {d['r2_ref']:+.3f} · n={len(te):,}")
    O = pd.concat(oos)
    y, p, r = O["y"].to_numpy(), O["p"].to_numpy(), O["ref"].to_numpy()
    ic, ic_t, ic_n = _ic_por_fecha(O, "p")
    icr, icr_t, _ = _ic_por_fecha(O, "ref")
    R = {"n_oos": int(len(O)), "r2": _r2(y, p), "r2_ref": _r2(y, r), "ic": ic, "ic_t": ic_t, "ic_n": ic_n,
         "ic_ref": icr, "ic_ref_t": icr_t, "acierto_signo": float(np.mean(np.sign(p) == np.sign(y)))}
    # ¿acierta las caídas grandes de IV (lo que más daña al comprador)?
    q = pd.qcut(O["p"], 10, labels=False, duplicates="drop")
    dec = O.groupby(q).agg(pred=("p", "mean"), real=("y", "mean"), n=("y", "size")).reset_index(drop=True)
    R["deciles"] = dec.to_dict("records")
    con = O[O["res_en_horizonte"] > 0]
    sin = O[O["res_en_horizonte"] == 0]
    R["con_resultados"] = {"n": int(len(con)), "r2": _r2(con["y"].to_numpy(), con["p"].to_numpy()),
                           "r2_ref": _r2(con["y"].to_numpy(), con["ref"].to_numpy())}
    R["sin_resultados"] = {"n": int(len(sin)), "r2": _r2(sin["y"].to_numpy(), sin["p"].to_numpy()),
                           "r2_ref": _r2(sin["y"].to_numpy(), sin["ref"].to_numpy())}
    supera = (R["r2"] > R["r2_ref"] + 0.005 and (R["ic"] or 0) > (R["ic_ref"] or 0) and
              sum(d["r2"] > d["r2_ref"] for d in pl) >= math.ceil(0.75 * len(pl)))
    R["veredicto"] = "SUPERA A LA REVERSIÓN SIMPLE" if supera else (
        "PREDICE, PERO NO SUPERA A LA REVERSIÓN SIMPLE" if R["r2"] > 0.01 else "SIN CAPACIDAD PREDICTIVA")
    return {"resumen": R, "pliegues": pl, "oos": O, "columnas": cols}
