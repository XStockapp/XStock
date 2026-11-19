"""Predicciones diarias del Motor A para la app (corre en GitHub Actions después del archivo de opciones).

Para cada acción (tus watchlists + las más líquidas):
  · probabilidad de que el precio se mueva ±k·σ·√H en las próximas H sesiones (modelo de movimiento, calibrada);
  · probabilidad que «cobra» la IV de hoy (IV ATM a ~14 días del archivo diario) para ese mismo movimiento;
  · señal IV barata / justa / cara: quintil de la diferencia modelo − IV, con los cortes medidos fuera de muestra.
Sube modelos/motor_a/predicciones.json; la app solo lee ese archivo (no entrena ni descarga nada pesado).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.motor_a import artefactos as AR, dataset as DS, iv_historica as IV, macro as MC, modelo as MO  # noqa: E402
from core.motor_a import sec as SE  # noqa: E402

H = 10
NOMBRE = "predicciones.json"


def _json(nombre: str) -> dict | None:
    crudo = AR.bajar(nombre)
    return json.loads(crudo) if crudo else None


def resumen_iv(hoy: str) -> pd.DataFrame:
    p = Path("datos/opciones/diario") / hoy / "resumen.parquet"
    if p.exists():
        return pd.read_parquet(p).set_index("ticker")
    return pd.DataFrame()


def predecir(panel: pd.DataFrame, modelo, rep: dict, rep_iv: dict | None, R: pd.DataFrame) -> pd.DataFrame:
    ultima = panel.index.get_level_values("fecha").max()
    X = panel.xs(ultima, level="fecha")
    cols = rep["variables"]
    p = modelo.predict(X[cols])
    D = pd.DataFrame({"p_raw": p, "p": MO.calibrar(p, rep.get("calibracion")),
                      "sigma_d": X["sigma_d"].astype(float)}, index=X.index)
    D["fecha"] = str(pd.Timestamp(ultima).date())
    if rep_iv and len(R) and "iv_atm_14d" in R:
        D = D.join(R[["iv_atm_14d", "iv_atm_30d"]], how="left")
        ok = D["iv_atm_14d"].notna() & (D["iv_atm_14d"] > 0)
        if ok.any():
            c = IV.combinar(D.loc[ok, "p_raw"], D.loc[ok, "iv_atm_14d"], D.loc[ok, "sigma_d"], H, rep["k"], rep_iv)
            for k_, v in c.items():
                D.loc[ok, k_] = v
    return D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=200)
    a = ap.parse_args()
    rep = _json(f"reporte_movimiento_H{H}.json")
    txt = AR.bajar(AR.nombre_modelo("movimiento", H))
    if not rep or not txt:
        print("Falta el modelo de movimiento entrenado (corre Motor A con experimentos vs_iv:10).")
        return
    rep_iv = _json(f"reporte_vs_iv_H{H}.json")
    if rep_iv and "cal_iv" not in rep_iv:
        print("El reporte vs-IV es anterior a esta versión (sin calibración guardada): se omite la señal de IV.")
        rep_iv = None
    modelo = MO._lgb().Booster(model_str=txt.decode())
    hoy = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    tickers = DS.universo(maximo=a.max)
    mis = DS.mis_acciones(tickers)
    todos = tickers + [t for t in mis if t not in tickers]
    barras = DS.descargar(todos + ["SPY"], desde_anios=3)
    spy = barras.pop("SPY")
    sec_datos = SE.descargar(list(barras)) if os.environ.get(SE.UA_ENV) else None
    macro = MC.variables(spy, MC.descargar_dgs2())
    panel = DS.construir(barras, spy, H, rep["k"], sec_datos, macro, "movimiento")
    faltan = [c for c in rep["variables"] if c not in panel.columns]
    for c in faltan:  # p. ej. sin SEC: LightGBM trata NaN como «sin dato»
        panel[c] = np.nan
    D = predecir(panel, modelo, rep, rep_iv, resumen_iv(hoy))

    def num(v):
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), 4)
    por = {}
    for t, f in D.iterrows():
        por[t] = {"p": num(f["p"]), "p_iv": num(f.get("p_iv")), "p_comb": num(f.get("p_comb")),
                  "iv": num(f.get("iv_atm_14d")), "sigma_d": num(f["sigma_d"]),
                  "senal": f.get("senal") if isinstance(f.get("senal"), str) else None,
                  "quintil": int(f["quintil"]) if pd.notna(f.get("quintil")) else None}
    out = {"generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "fecha": D["fecha"].iat[0],
           "H": H, "k": rep["k"], "tasa_base": rep["resumen"].get("tasa_real"),
           "modelo_generado": rep.get("generado_utc"), "variables_faltantes": faltan,
           "acciones": por}
    AR.guardar_local(out, None, NOMBRE)
    subido = AR.subir(out, None, NOMBRE)
    con_iv = sum(1 for v in por.values() if v["senal"])
    print(f"Predicciones {out['fecha']}: {len(por)} acciones ({con_iv} con señal de IV) · "
          f"{'subidas a Supabase' if subido else 'solo local'}" + (f" · faltan {faltan}" if faltan else ""))
    top = D.sort_values("p", ascending=False).head(8)
    print(top[[c for c in ("p", "p_iv", "senal", "iv_atm_14d") if c in top]].round(3).to_string())


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
