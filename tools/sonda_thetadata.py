"""Sonda del plan gratuito de ThetaData con su librería oficial (sin Theta Terminal): qué endpoints responden,
qué columnas traen (¿interés abierto?) y desde cuándo. Autenticación: THETADATA_API_KEY o THETADATA_EMAIL +
THETADATA_PASSWORD. Solo imprime."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pandas as pd
from thetadata import ThetaClient

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

clave = os.environ.get("THETADATA_API_KEY", "").strip()
try:
    if clave:
        c = ThetaClient(api_key=clave, dataframe_type="pandas")
        print("Autenticado con clave API.")
    else:
        c = ThetaClient(email=os.environ.get("THETADATA_EMAIL", "").strip(),
                        password=os.environ.get("THETADATA_PASSWORD", "").strip(), dataframe_type="pandas")
        print("Autenticado con correo y contraseña.")
except Exception as e:
    print("No se pudo autenticar:", str(e)[:300])
    sys.exit(1)


def probar(nombre, f, **p):
    print(f"\n--- {nombre} {p}")
    try:
        d = f(**p)
        d = d.to_pandas() if hasattr(d, "to_pandas") else d
        print(f"{len(d)} filas · columnas: {list(d.columns)}")
        print(d.head(6).to_string())
        return d
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:300])
        return pd.DataFrame()


hoy = date.today()
exps = probar("Vencimientos AMD", c.option_list_expirations, symbol="AMD")
venc = None
if len(exps):
    vals = pd.to_datetime(exps.iloc[:, -1].astype(str), errors="coerce").dropna()
    fut = sorted(v.date() for v in vals if v.date() >= hoy)
    venc = fut[1] if len(fut) > 1 else (fut[0] if fut else None)
ayer, sem = hoy - timedelta(days=1), hoy - timedelta(days=8)
if venc:
    probar("EOD de un vencimiento, última semana", c.option_history_eod, start_date=sem, end_date=ayer, symbol="AMD",
           expiration=venc)
    probar("Interés abierto histórico", c.option_history_open_interest, symbol="AMD", expiration=venc, date=ayer)
    probar("IV histórica EOD", c.option_history_greeks_eod, start_date=sem, end_date=ayer, symbol="AMD",
           expiration=venc) if hasattr(c, "option_history_greeks_eod") else None
for dias in (200, 420, 700, 1200):
    f = hoy - timedelta(days=dias)
    probar(f"EOD hace {dias} días (todos los vencimientos)", c.option_history_eod, start_date=f,
           end_date=f + timedelta(days=4), symbol="AMD", expiration="*")
