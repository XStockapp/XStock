"""B2: entrena y valida el modelo de IV futura con la historia gratuita de DoltHub (2019-2026).

Uso: python tools/entrenar_motor_b.py [--max 500] [--sintetico]
Sube el reporte a Supabase Storage (modelos/motor_b/reporte_iv.json) si hay credenciales.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from core.motor_a import artefactos as AR, dataset as DS  # noqa: E402
from core.motor_b import datos as DB, iv_modelo as IM  # noqa: E402


def sintetico(n=60, semilla=3):
    """IV sintética con reversión a la media y subidas antes de resultados que se desploman después."""
    rng = np.random.default_rng(semilla)
    fechas = pd.bdate_range("2019-02-11", "2026-11-13")
    H, C = [], []
    for j in range(n + 1):
        t = "SPY" if j == n else f"S{j:03d}"
        base = rng.uniform(0.2, 0.7) if t != "SPY" else 0.16
        res = fechas[rng.integers(20, 80)::63]
        x, iv = 0.0, []
        for f in fechas:
            x = 0.93 * x + rng.normal(0, 0.06)
            k = np.searchsorted(res, f)
            dias = (res[k] - f).days if k < len(res) else 99
            bump = 0.35 * np.exp(-dias / 6) if 0 <= dias <= 25 else 0.0
            iv.append(base * np.exp(x + bump))
        iv = np.array(iv)
        H.append(pd.DataFrame({"fecha": fechas, "ticker": t, "iv_current": iv, "hv_current": iv * rng.uniform(0.7, 1.0),
                               "iv_year_high": pd.Series(iv).rolling(252, 1).max(),
                               "iv_year_low": pd.Series(iv).rolling(252, 1).min()}))
        C.append(pd.DataFrame({"ticker": t, "fecha": res, "hora": "After market close"}))
    return pd.concat(H, ignore_index=True), pd.concat(C, ignore_index=True)


def subir(rep: dict) -> bool:
    url, h = AR._sb()
    if not url:
        return False
    r = requests.post(f"{url}/storage/v1/object/{AR.BUCKET}/motor_b/reporte_iv.json", timeout=60,
                      data=json.dumps(rep, ensure_ascii=False, default=float).encode(),
                      headers={**h, "Content-Type": "application/json", "x-upsert": "true"})
    return r.status_code < 300


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=500)
    ap.add_argument("--sintetico", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.sintetico:
        H, C = sintetico()
        fuente = "sintético"
    else:
        tickers = DS.universo(maximo=a.max)
        tickers = [t for t in tickers if "-" not in t] + ["SPY"]
        print(f"Universo: {len(tickers)} símbolos · descargando IV de DoltHub…")
        H = DB.historia_iv(tickers)
        C = DB.calendario_resultados(tickers)
        fuente = "DoltHub post-no-preference (volatility_history, earnings_calendar)"
    print(f"IV: {len(H):,} filas · {H['ticker'].nunique()} acciones · {H['fecha'].min().date()} → "
          f"{H['fecha'].max().date()} · resultados: {len(C):,}")
    P = IM.construir(H, C)
    print(f"Panel: {len(P):,} filas · con objetivo: {P['y'].notna().sum():,}")
    W = IM.walk_forward(P)
    R = W["resumen"]
    import lightgbm as lgb
    D = P.dropna(subset=["y"])
    D = D[D["y"].abs() < 2]
    arb = int(np.median([d["arboles"] for d in W["pliegues"]]))
    final = lgb.train(IM.PARAMS, lgb.Dataset(D[W["columnas"]], D["y"]), max(arb, 50))
    g = final.feature_importance("gain")
    imp = [{"variable": W["columnas"][i], "peso": float(g[i] / g.sum())} for i in np.argsort(-g)[:15]]
    rep = {"generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "fuente": fuente,
           "objetivo": "iv_futura", "pregunta": "ln(IV dentro de ~1 semana / IV hoy)",
           "acciones": int(P.index.get_level_values("ticker").nunique()),
           "desde": str(P.index.get_level_values("fecha").min().date()),
           "hasta": str(P.index.get_level_values("fecha").max().date()),
           "resumen": R, "pliegues": W["pliegues"], "importancia": imp, "segundos": round(time.time() - t0, 1)}
    out = DB.DIR / "reporte_iv.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=float))
    subido = False if a.sintetico else subir(rep)
    print(f"\nVeredicto: {R['veredicto']}")
    print(f"R² fuera de muestra: modelo {R['r2']:+.3f} · reversión simple {R['r2_ref']:+.3f} · sin cambio 0")
    print(f"IC por fecha: modelo {R['ic']:+.3f} (t={R['ic_t']:.1f}) · reversión {R['ic_ref']:+.3f} (t={R['ic_ref_t']:.1f})")
    print(f"Acierto del signo: {R['acierto_signo']:.1%}")
    print(f"Con resultados en la semana: R² {R['con_resultados']['r2']:+.3f} (ref {R['con_resultados']['r2_ref']:+.3f}, "
          f"n={R['con_resultados']['n']:,}) · sin resultados: R² {R['sin_resultados']['r2']:+.3f} "
          f"(ref {R['sin_resultados']['r2_ref']:+.3f})")
    print("Deciles de la predicción (cambio de IV predicho → real):")
    for d in R["deciles"]:
        print(f"   {d['pred']:+.3f} → {d['real']:+.3f}  (n={d['n']:,})")
    for i in imp[:10]:
        print(f"    {i['variable']:<26}{i['peso'] * 100:5.1f}%")
    print("Reporte subido a Supabase." if subido else f"Reporte guardado en {out}.")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
