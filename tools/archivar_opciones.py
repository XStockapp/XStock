"""Archivo diario de la cadena de opciones (Motor B). Corre en GitHub Actions después del cierre.

Uso: python tools/archivar_opciones.py [--max 200] [--completas 50]
Necesita ALPACA_API_KEY / ALPACA_SECRET_KEY; si hay SUPABASE_URL / SUPABASE_SERVICE_KEY sube los archivos al bucket
privado «opciones». Si el mercado no abrió hoy (feriado), no guarda nada.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from core import alpaca, options as OP  # noqa: E402
from core.motor_a import artefactos as AR, dataset as DS  # noqa: E402
from core.motor_b import archivo as ARC  # noqa: E402

BUCKET = "opciones"


def subir(nombre: str, cuerpo: bytes) -> bool:
    url, h = AR._sb()
    if not url:
        return False
    requests.post(f"{url}/storage/v1/bucket", headers=h, json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=30)
    r = requests.post(f"{url}/storage/v1/object/{BUCKET}/{nombre}", data=cuerpo, timeout=120,
                      headers={**h, "Content-Type": "application/octet-stream", "x-upsert": "true"})
    return r.status_code < 300


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--completas", type=int, default=50, help="acciones con la cadena completa (además de las tuyas)")
    ap.add_argument("--dias", type=int, default=60, help="vencimientos hasta N días")
    a = ap.parse_args()
    hoy = datetime.now(ZoneInfo("America/New_York")).date()
    spy = alpaca.batch_bars(["SPY"], "1D", 0.05).get("SPY")
    if spy is None or spy.index[-1].date() != hoy:
        print(f"El mercado no abrió hoy ({hoy}): no se archiva.")
        return
    tickers = DS.universo(maximo=a.max)
    mis = DS.mis_acciones(tickers)
    todos = tickers + [t for t in mis if t not in tickers]
    completas = set(mis) | set(tickers[:a.completas])
    barras = alpaca.batch_bars(todos, "1D", 0.15)
    resumen, cadenas = [], []
    t0 = time.time()
    for i, t in enumerate(todos):
        b = barras.get(t)
        if b is None or b.empty or b.index[-1].date() != hoy:
            continue
        spot = float(b["Close"].iloc[-1])
        rv = OP.vol_realizada(b["Close"])
        try:
            time.sleep(1.2)  # ~4 consultas por acción → bajo el límite de 200/min
            df, info = OP.chain(t, spot, a.dias, rv)
        except Exception as e:
            print(f"  {t}: {str(e)[:80]}")
            continue
        fila = {"fecha": hoy.isoformat(), "ticker": t, "feed": info.get("feed"), **ARC.resumir(df, spot, rv)}
        resumen.append(fila)
        if t in completas and not df.empty:
            c = df[[c for c in ARC.COLS_CADENA if c in df.columns]].copy()
            c.insert(0, "ticker", t)
            c["exp"] = c["exp"].astype(str)
            cadenas.append(c)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(todos)} · {time.time() - t0:.0f} s")
    R = pd.DataFrame(resumen)
    C = pd.concat(cadenas, ignore_index=True) if cadenas else pd.DataFrame()
    out = Path("datos/opciones/diario") / hoy.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    R.to_parquet(out / "resumen.parquet", index=False)
    if len(C):
        C.to_parquet(out / "cadenas.parquet", index=False)
    ok = subir(f"diario/{hoy}/resumen.parquet", ARC.a_parquet(R))
    if len(C):
        ok = subir(f"diario/{hoy}/cadenas.parquet", ARC.a_parquet(C)) and ok
    print(f"Archivado {hoy}: {len(R)} acciones en el resumen · {len(C):,} contratos completos "
          f"({C['ticker'].nunique() if len(C) else 0} acciones) · feed {R['feed'].mode().iat[0] if len(R) else '—'} · "
          f"{'subido a Supabase' if ok else 'solo local'}")
    if len(R):
        print(R[["ticker", "iv_atm_30d", "iv_vs_real_30d", "skew_25d", "spread_atm_pct"]].head(8).round(3).to_string())
    return R


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
