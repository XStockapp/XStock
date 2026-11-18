"""Sonda: qué hay realmente en las bases de DoltHub (cobertura, columnas, fechas). Solo imprime; no guarda nada.
La tabla option_chain es enorme: las consultas deben fijar fecha exacta y símbolo (clave primaria)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.fuentes import dolthub as D  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)


def q(repo, sql, n=40):
    print(f"\n--- [{repo}] {sql}")
    try:
        d = D.consulta(repo, sql)
        print(d.head(n).to_string() if len(d) else "(sin filas)", f"\n({len(d)} filas · {d.attrs.get('estado')})")
        return d
    except Exception as e:
        print("ERROR:", str(e)[:300])
        return pd.DataFrame()


for f in ("2019-02-09", "2021-06-02", "2024-06-03", "2026-11-17"):
    q("options", f"SELECT COUNT(*) AS contratos, COUNT(DISTINCT expiration) AS vencimientos, MIN(strike), MAX(strike) "
                 f"FROM option_chain WHERE date='{f}' AND act_symbol='AMD'")
q("options", "SELECT expiration, strike, call_put, bid, ask, vol, delta FROM option_chain WHERE date='2026-11-17' "
             "AND act_symbol='AMD' ORDER BY expiration, strike, call_put", 60)
q("options", "SELECT date FROM volatility_history WHERE act_symbol='AMD' AND date < '2021-01-01' ORDER BY date LIMIT 40")
q("earnings", "SELECT * FROM eps_history WHERE act_symbol='AMD' ORDER BY period_end_date DESC LIMIT 6")
q("earnings", "SELECT * FROM earnings_calendar WHERE act_symbol='AMD' ORDER BY date DESC LIMIT 3")
