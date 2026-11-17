"""Entrena y valida el Motor A (fases 1 y 2). Pensado para correr fuera de Render (GitHub Actions o un PC).

Uso:
  python tools/entrenar_motor_a.py                    # universo líquido Finviz (máx. 800), datos de Alpaca
  python tools/entrenar_motor_a.py --max 300 --H 10 --k 1.0
  python tools/entrenar_motor_a.py --sintetico 0.15   # prueba sin claves: mercado sintético con señal 0.15

Necesita ALPACA_API_KEY / ALPACA_SECRET_KEY (variables de entorno). Si además hay SUPABASE_URL /
SUPABASE_SERVICE_KEY, sube el modelo y el reporte a Supabase Storage para que la app los muestre.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402

from core.motor_a import artefactos as AR, dataset as DS, macro as MC, modelo as MO, sec as SE  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=500, help="máximo de acciones del universo")
    ap.add_argument("--mis", default="", help="tus acciones separadas por coma (por defecto: watchlists de la app)")
    ap.add_argument("--H", type=int, default=DS.H_DEF, help="horizonte en sesiones")
    ap.add_argument("--k", type=float, default=DS.K_DEF, help="barreras a ±k·σ·√H")
    ap.add_argument("--sintetico", type=float, default=None, help="usar mercado sintético con esta señal")
    ap.add_argument("--sin-subir", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    sec_datos, dgs2, mis = None, None, []
    if a.sintetico is not None:
        barras, spy = DS.sintetico(senal=a.sintetico)
        fuente = f"sintético (señal {a.sintetico})"
        mis = list(barras)[:10]
    else:
        tickers = DS.universo(maximo=a.max)
        mis = [t.strip().upper() for t in a.mis.split(",") if t.strip()] or DS.mis_acciones(tickers)
        extra = [t for t in mis if t not in tickers]  # tus acciones se descargan siempre
        print(f"Universo: {len(tickers)} acciones líquidas + {len(extra)} tuyas fuera de él")
        barras = DS.descargar(tickers + extra + ["SPY"])
        spy = barras.pop("SPY")
        fuente = "Alpaca SIP diario ajustado"
        if os.environ.get(SE.UA_ENV):
            print("SEC EDGAR (tamaño, resultados, adquisiciones, fundamentales)…")
            sec_datos = SE.descargar(list(barras))
            fuente += f" + SEC EDGAR ({len(sec_datos)} empresas)"
        else:
            print("Sin SEC_USER_AGENT: se omiten tamaño, resultados y fundamentales.")
        dgs2 = MC.descargar_dgs2()
        if dgs2 is not None:
            fuente += " + FRED (tasa a 2 años)"
    macro = MC.variables(spy, dgs2)
    print("Construyendo variables y etiquetas…")
    panel = DS.construir(barras, spy, a.H, a.k, sec_datos, macro)
    if a.sintetico is None:
        DS.guardar(panel)
    print(f"Panel: {len(panel):,} filas · {panel.index.get_level_values('ticker').nunique()} acciones")
    # ---- medición por bloques: un bloque entra solo si mejora fuera de muestra
    bloques, aceptadas, wf, mejor = [], None, None, None
    for nombre, cols in DS.columnas_por_bloque(panel):
        prueba = cols if aceptadas is None else aceptadas + [c for c in cols if c not in aceptadas]
        print(f"Validación walk-forward · {nombre} ({len(prueba)} variables):")
        w = MO.walk_forward(panel, a.H, cols=prueba)
        R0 = w["resumen"]
        entra = mejor is None or (R0["auc"] > mejor["auc"] + 0.001 and R0["bss"] >= mejor["bss"])
        bloques.append({"bloque": nombre, "variables": len(prueba), "auc": R0["auc"], "bss": R0["bss"],
                        "ic_t": R0["ic_t"], "entra": bool(entra)})
        if entra:
            aceptadas, wf, mejor = prueba, w, R0
        print(f"  → {'entra' if entra else 'NO entra (no mejora fuera de muestra)'}")
    R = wf["resumen"]
    arboles = int(sorted(d["arboles"] for d in wf["pliegues"])[len(wf["pliegues"]) // 2])
    final = MO.modelo_final(panel, wf["columnas"], arboles)
    fechas = panel.index.get_level_values("fecha")
    reporte = {
        "generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "fuente": fuente, "H": a.H, "k": a.k,
        "acciones": int(panel.index.get_level_values("ticker").nunique()), "filas": int(len(panel)),
        "desde": str(fechas.min().date()), "hasta": str(fechas.max().date()),
        "variables": wf["columnas"], "arboles_final": arboles,
        "resumen": R, "pliegues": wf["pliegues"], "bloques": bloques,
        "mis_acciones": MO.resumir_subconjunto(wf["oos"], mis, a.H), "mis_acciones_lista": mis,
        "importancia": MO.importancia(final, wf["columnas"]),
        "calibracion": MO.calibrador(wf["oos"]),
        "segundos": round(time.time() - t0, 1),
        "limitaciones": ["Universo actual (sesgo de supervivencia): faltan acciones que salieron del mercado desde 2016.",
                         "Sin variables de opciones (historia insuficiente en Alpaca). Sin CPI ni empleo todavía.",
                         "Los bloques se eligen con los mismos datos fuera de muestra con que se miden (5 decisiones): "
                         "pequeño sesgo optimista; por eso un bloque solo entra si mejora AUC y Brier a la vez.",
                         "Fundamentales: primera cifra publicada en la SEC, usable desde el día hábil siguiente.",
                         "Etiquetas con máximos/mínimos diarios: si ambas barreras se tocan el mismo día decide el cierre."],
    }
    AR.guardar_local(reporte, final.model_to_string())
    subido = False if (a.sin_subir or a.sintetico is not None) else AR.subir(reporte, final.model_to_string())
    print(f"\nVeredicto: {R['veredicto']}  ·  AUC {R['auc']:.3f} (momentum {R['auc_momentum']:.3f}, azar 0.500)"
          f"  ·  Brier skill {R['bss']:+.4f}  ·  IC {R['ic_medio']:+.3f} (t={R['ic_t']:.1f})")
    for b in bloques:
        print(f"  {b['bloque']:<38} AUC {b['auc']:.4f} · BSS {b['bss']:+.4f} · {'entra' if b['entra'] else 'no entra'}")
    if reporte["mis_acciones"]:
        m = reporte["mis_acciones"]
        print(f"Tus acciones ({m['acciones']}): AUC {m['auc']:.3f} · BSS {m['bss']:+.4f} · {m['veredicto']}")
    print(f"Decil alto: acierto {R['decil_alto']['real']:.1%} · decil bajo {R['decil_bajo']['real']:.1%}"
          f" · tasa real {R['tasa_real']:.1%}")
    print("Reporte subido a Supabase Storage." if subido else f"Reporte guardado en {DS.CACHE_DIR}/.")
    return R


if __name__ == "__main__":
    main()
