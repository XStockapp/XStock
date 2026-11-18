"""Sonda: qué hay realmente en las bases de DoltHub (cobertura, columnas, fechas) y si su IV coincide con la de
Alpaca/Black-Scholes. Solo imprime; no guarda nada."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.fuentes import dolthub as D  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def q(repo, sql, n=12):
    print(f"\n--- [{repo}] {sql}")
    try:
        d = D.consulta(repo, sql)
        print(d.head(n).to_string() if len(d) else "(sin filas)", f"\n({len(d)} filas · {d.attrs.get('estado')})")
        return d
    except Exception as e:
        print("ERROR:", str(e)[:300])
        return pd.DataFrame()


q("options", "SHOW TABLES")
q("options", "DESCRIBE option_chain", 30)
q("options", "DESCRIBE volatility_history", 30)
for t in ("AMD", "AAPL", "SPY"):
    q("options", f"SELECT MIN(date) AS desde, MAX(date) AS hasta, COUNT(*) AS filas FROM volatility_history WHERE act_symbol='{t}'")
q("options", "SELECT * FROM volatility_history WHERE act_symbol='AMD' ORDER BY date DESC LIMIT 5")
q("options", "SELECT date, COUNT(*) AS contratos FROM option_chain WHERE act_symbol='AMD' AND date >= '2019-01-01' "
             "AND date < '2019-03-01' GROUP BY date")
q("options", "SELECT date, COUNT(*) AS contratos FROM option_chain WHERE act_symbol='AMD' AND date >= '2026-11-01' GROUP BY date")
q("options", "SELECT * FROM option_chain WHERE act_symbol='AMD' AND date = (SELECT MAX(date) FROM option_chain "
             "WHERE act_symbol='AMD') ORDER BY expiration, strike LIMIT 12")
q("options", "SELECT MIN(date) AS desde FROM option_chain WHERE act_symbol='AMD'")
q("options", "SELECT COUNT(DISTINCT act_symbol) AS acciones FROM volatility_history WHERE date = "
             "(SELECT MAX(date) FROM volatility_history WHERE act_symbol='SPY')")
q("earnings", "SHOW TABLES", 30)
for t in ("earnings_calendar", "eps_estimate", "eps_history"):
    q("earnings", f"DESCRIBE {t}", 20)
    q("earnings", f"SELECT * FROM {t} WHERE act_symbol='AMD' ORDER BY date ASC LIMIT 5")
    q("earnings", f"SELECT MIN(date), MAX(date), COUNT(*) FROM {t} WHERE act_symbol='AMD'")
