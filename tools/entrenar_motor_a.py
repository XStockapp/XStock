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

from core.motor_a import artefactos as AR, dataset as DS, iv_historica as IV, macro as MC, modelo as MO  # noqa: E402
from core.motor_a import sec as SE  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=500, help="máximo de acciones del universo")
    ap.add_argument("--mis", default="", help="tus acciones separadas por coma (por defecto: watchlists de la app)")
    ap.add_argument("--experimentos", default="direccion:10",
                    help="lista objetivo:H separada por coma, p. ej. direccion:3,direccion:20,movimiento:10")
    ap.add_argument("--iv-max", type=int, default=200, help="acciones para reconstruir la IV (vs_iv)")
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
    resumen = []
    orden = list(barras) if a.sintetico is not None else tickers  # orden de liquidez del universo
    for exp in [e.strip() for e in a.experimentos.split(",") if e.strip()]:
        obj, H = exp.split(":")
        if obj == "vs_iv":
            R, wf, panel = experimento(barras, spy, sec_datos, macro, "movimiento", int(H), a, fuente, mis, t0)
            resumen.append(("movimiento", int(H), R))
            comparar_iv(barras, wf, panel, int(H), a, orden[:a.iv_max] + [t for t in mis if t not in orden[:a.iv_max]])
            continue
        R, _, _ = experimento(barras, spy, sec_datos, macro, obj, int(H), a, fuente, mis, t0)
        resumen.append((obj, int(H), R))
    print("\n==================== RESUMEN ====================")
    for obj, H, R in resumen:
        print(f"{obj:<10} H={H:<3} AUC {R['auc']:.4f} (referencia {R['auc_momentum']:.4f}) · BSS {R['bss']:+.4f} · "
              f"IC {R['ic_medio']:+.3f} (t={R['ic_t']:.1f}) · {R['veredicto']}")
    return resumen


def experimento(barras, spy, sec_datos, macro, obj, H, a, fuente, mis, t0):
    ref, ref_nombre = MO.REFERENCIAS[obj]
    print(f"\n========== {obj.upper()} · H = {H} sesiones · {DS.OBJETIVOS[obj]} ==========")
    panel = DS.construir(barras, spy, H, a.k, sec_datos, macro, obj)
    print(f"Panel: {len(panel):,} filas · {panel.index.get_level_values('ticker').nunique()} acciones · "
          f"tasa real {panel['y'].mean():.1%}")
    # ---- medición por bloques: un bloque entra solo si mejora fuera de muestra
    bloques, aceptadas, wf, mejor = [], None, None, None
    for nombre, cols in DS.columnas_por_bloque(panel):
        prueba = cols if aceptadas is None else aceptadas + [c for c in cols if c not in aceptadas]
        print(f"Validación walk-forward · {nombre} ({len(prueba)} variables):")
        w = MO.walk_forward(panel, H, cols=prueba, ref=ref)
        R0 = w["resumen"]
        entra = mejor is None or (R0["auc"] > mejor["auc"] + 0.001 and R0["bss"] >= mejor["bss"])
        bloques.append({"bloque": nombre, "variables": len(prueba), "auc": R0["auc"], "bss": R0["bss"],
                        "ic_t": R0["ic_t"], "entra": bool(entra)})
        if entra:
            aceptadas, wf, mejor = prueba, w, R0
        print(f"  → {'entra' if entra else 'NO entra (no mejora fuera de muestra)'}")
    R = wf["resumen"]
    arboles = int(sorted(d["arboles"] for d in wf["pliegues"])[len(wf["pliegues"]) // 2])
    principal = (obj, H) == ("direccion", 10)
    final = MO.modelo_final(panel, wf["columnas"], arboles)
    fechas = panel.index.get_level_values("fecha")
    reporte = {
        "generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "fuente": fuente, "objetivo": obj, "pregunta": DS.OBJETIVOS[obj], "referencia": ref_nombre, "H": H, "k": a.k,
        "acciones": int(panel.index.get_level_values("ticker").nunique()), "filas": int(len(panel)),
        "desde": str(fechas.min().date()), "hasta": str(fechas.max().date()),
        "variables": wf["columnas"], "arboles_final": arboles, "arboles_por_anio": [d["arboles"] for d in wf["pliegues"]],
        "resumen": R, "pliegues": wf["pliegues"], "bloques": bloques,
        "mis_acciones": MO.resumir_subconjunto(wf["oos"], mis, H), "mis_acciones_lista": mis,
        "importancia": MO.importancia(final, wf["columnas"]),
        "calibracion": MO.calibrador(wf["oos"]),
        "segundos": round(time.time() - t0, 1),
        "limitaciones": ["Universo actual (sesgo de supervivencia): faltan acciones que salieron del mercado desde 2016.",
                         "Sin variables de opciones (historia insuficiente en Alpaca). Sin CPI ni empleo todavía.",
                         "Movimiento: la referencia es la volatilidad realizada reciente, no la IV (no hay IV histórica "
                         "gratuita desde 2016); superar a la volatilidad realizada no implica superar a la IV.",
                         "Los bloques se eligen con los mismos datos fuera de muestra con que se miden (5 decisiones): "
                         "pequeño sesgo optimista; por eso un bloque solo entra si mejora AUC y Brier a la vez.",
                         "Fundamentales: primera cifra publicada en la SEC, usable desde el día hábil siguiente.",
                         "Etiquetas con máximos/mínimos diarios: si ambas barreras se tocan el mismo día decide el cierre."],
    }
    nombre = AR.nombre_reporte(obj, H)
    modelo_txt = final.model_to_string() if principal else None
    AR.guardar_local(reporte, modelo_txt, nombre)
    subido = False if (a.sin_subir or a.sintetico is not None) else AR.subir(reporte, modelo_txt, nombre)
    print(f"\nVeredicto: {R['veredicto']}  ·  AUC {R['auc']:.3f} ({ref_nombre} {R['auc_momentum']:.3f}, azar 0.500)"
          f"  ·  Brier skill {R['bss']:+.4f}  ·  IC {R['ic_medio']:+.3f} (t={R['ic_t']:.1f})")
    print(f"Árboles por año: {reporte['arboles_por_anio']}")
    for b in bloques:
        print(f"  {b['bloque']:<38} AUC {b['auc']:.4f} · BSS {b['bss']:+.4f} · {'entra' if b['entra'] else 'no entra'}")
    if reporte["mis_acciones"]:
        m = reporte["mis_acciones"]
        print(f"Tus acciones ({m['acciones']}): AUC {m['auc']:.3f} · BSS {m['bss']:+.4f} · {m['veredicto']}")
    print(f"Decil alto: acierto {R['decil_alto']['real']:.1%} · decil bajo {R['decil_bajo']['real']:.1%}"
          f" · tasa real {R['tasa_real']:.1%}")
    for i in reporte["importancia"][:6]:
        print(f"    {i['variable']:<28}{i['peso'] * 100:5.1f}%")
    print(f"{nombre} subido a Supabase Storage." if subido else f"{nombre} guardado en {DS.CACHE_DIR}/.")
    return R, wf, panel


def comparar_iv(barras, wf, panel, H, a, tickers):
    print(f"\n========== MOVIMIENTO vs IV · H = {H} · {len(tickers)} acciones · desde feb-2024 ==========")
    if a.sintetico is not None:
        print("  (omitido en modo sintético: no hay opciones)")
        return None
    ivdf = IV.descargar_iv(barras, tickers)
    print(f"  IV reconstruida: {len(ivdf):,} observaciones")
    C = IV.comparar(wf["oos"], ivdf, panel, H, a.k)
    if not C:
        print("  Datos insuficientes para comparar.")
        return None
    rep = {"generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "objetivo": "vs_iv", "H": H,
           "k": a.k, **C}
    nombre = f"reporte_vs_iv_H{H}.json"
    AR.guardar_local(rep, None, nombre)
    if not a.sin_subir:
        AR.subir(rep, None, nombre)
    print(f"Filas comparables: {C['filas']:,} ({C['acciones']} acciones) · prueba desde {C['corte']}: {C['filas_prueba']:,}")
    print(f"IV mediana {C['iv_mediana']:.1%} · IV/vol. real mediana {C['iv_vs_rv_mediana']:.2f}")
    print(f"AUC  IV {C['auc_iv']:.4f} · modelo {C['auc_modelo']:.4f} · combinado {C['auc_combinado']:.4f}")
    print(f"Brier IV calibrada {C['brier_iv_cal']:.4f} · modelo {C['brier_modelo']:.4f} · "
          f"combinado {C['brier_combinado']:.4f}")
    print(f"Pesos de la combinación: IV {C['coef_iv']:+.2f} · modelo {C['coef_modelo']:+.2f}")
    print("Quintiles de (modelo − IV): ¿el modelo ve más movimiento del que cobra la IV?")
    for t in C["tramos"]:
        print(f"   dif {t['dif']:+.2f} · IV dice {t['p_iv']:.1%} · modelo {t['p_modelo']:.1%} · real {t['real']:.1%} · n={t['n']:,}")
    print(f"{nombre} guardado.")
    return C


if __name__ == "__main__":
    main()
