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

from core.motor_a import artefactos as AR, dataset as DS, modelo as MO  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=800, help="máximo de acciones del universo")
    ap.add_argument("--H", type=int, default=DS.H_DEF, help="horizonte en sesiones")
    ap.add_argument("--k", type=float, default=DS.K_DEF, help="barreras a ±k·σ·√H")
    ap.add_argument("--sintetico", type=float, default=None, help="usar mercado sintético con esta señal")
    ap.add_argument("--sin-subir", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.sintetico is not None:
        barras, spy = DS.sintetico(senal=a.sintetico)
        fuente = f"sintético (señal {a.sintetico})"
    else:
        tickers = DS.universo(maximo=a.max)
        print(f"Universo: {len(tickers)} acciones")
        barras = DS.descargar(tickers + ["SPY"])
        spy = barras.pop("SPY")
        fuente = "Alpaca SIP diario ajustado"
    print("Construyendo variables y etiquetas…")
    panel = DS.construir(barras, spy, a.H, a.k)
    if a.sintetico is None:
        DS.guardar(panel)
    print(f"Panel: {len(panel):,} filas · {panel.index.get_level_values('ticker').nunique()} acciones")
    print("Validación walk-forward:")
    wf = MO.walk_forward(panel, a.H)
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
        "resumen": R, "pliegues": wf["pliegues"],
        "importancia": MO.importancia(final, wf["columnas"]),
        "calibracion": MO.calibrador(wf["oos"]),
        "segundos": round(time.time() - t0, 1),
        "limitaciones": ["Universo actual (sesgo de supervivencia): faltan acciones que salieron del mercado desde 2016.",
                         "Solo precio y volumen diarios; sin variables de opciones (historia insuficiente en Alpaca).",
                         "Etiquetas con máximos/mínimos diarios: si ambas barreras se tocan el mismo día decide el cierre."],
    }
    AR.guardar_local(reporte, final.model_to_string())
    subido = False if (a.sin_subir or a.sintetico is not None) else AR.subir(reporte, final.model_to_string())
    print(f"\nVeredicto: {R['veredicto']}  ·  AUC {R['auc']:.3f} (momentum {R['auc_momentum']:.3f}, azar 0.500)"
          f"  ·  Brier skill {R['bss']:+.4f}  ·  IC {R['ic_medio']:+.3f} (t={R['ic_t']:.1f})")
    print(f"Decil alto: acierto {R['decil_alto']['real']:.1%} · decil bajo {R['decil_bajo']['real']:.1%}"
          f" · tasa real {R['tasa_real']:.1%}")
    print("Reporte subido a Supabase Storage." if subido else f"Reporte guardado en {DS.CACHE_DIR}/.")
    return R


if __name__ == "__main__":
    main()
