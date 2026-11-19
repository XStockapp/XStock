"""Sonda del plan gratuito de ThetaData: qué endpoints responden, qué columnas traen (¿interés abierto?) y desde
cuándo. Requiere el Theta Terminal v3 ya iniciado (lo arranca el flujo de GitHub). Solo imprime."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.fuentes import thetadata as T  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

if not T.esperar(180):
    print("El Theta Terminal no respondió en 3 minutos (¿credenciales?).")
    sys.exit(1)


def probar(nombre, ruta, **p):
    cod, d, err = T.get(ruta, **p)
    print(f"\n--- {nombre}: {ruta} {p}\nHTTP {cod} · {len(d)} filas · columnas: {list(d.columns)}")
    if err:
        print("   ", err.replace("\n", " ")[:300])
    if len(d):
        print(d.head(6).to_string())
    return d


exps = probar("Vencimientos AMD", "option/list/expirations", symbol="AMD")
hoy = date.today()
ult = (hoy - timedelta(days=1)).strftime("%Y%m%d")
sem = (hoy - timedelta(days=8)).strftime("%Y%m%d")
venc = None
if len(exps):
    col = exps.columns[-1]
    fut = [str(x).replace("-", "") for x in exps[col] if str(x).replace("-", "") >= hoy.strftime("%Y%m%d")]
    venc = fut[1] if len(fut) > 1 else (fut[0] if fut else None)
if venc:
    probar("EOD 1 vencimiento, última semana", "option/history/eod", symbol="AMD", expiration=venc, start_date=sem, end_date=ult)
    probar("Interés abierto histórico (ayer)", "option/history/open_interest", symbol="AMD", expiration=venc, date=ult)
    probar("Interés abierto, instantánea", "option/snapshot/open_interest", symbol="AMD", expiration=venc)
    probar("Cotización histórica (bid/ask) ayer", "option/history/quote", symbol="AMD", expiration=venc, date=ult,
           interval="1h")
    probar("IV histórica (griegas EOD)", "option/history/greeks/eod", symbol="AMD", expiration=venc, start_date=sem,
           end_date=ult)
for dias in (300, 400, 800):
    f = (hoy - timedelta(days=dias)).strftime("%Y%m%d")
    f2 = (hoy - timedelta(days=dias - 3)).strftime("%Y%m%d")
    probar(f"EOD hace {dias} días (todos los vencimientos)", "option/history/eod", symbol="AMD", expiration="*",
           start_date=f, end_date=f2)
    probar(f"Interés abierto hace {dias} días", "option/history/open_interest", symbol="AMD", expiration="*", date=f2)
