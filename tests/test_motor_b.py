import math

import numpy as np
import pandas as pd

from core.motor_b import archivo as ARC


def test_interpolacion_en_varianza():
    t = pd.DataFrame({"dte": [10, 40], "iv": [0.30, 0.50]})
    v = ARC._interpolar(t, 25)
    esperado = math.sqrt(np.interp(25, [10, 40], [0.09 * 10, 0.25 * 40]) / 25)
    assert abs(v - esperado) < 1e-9 and 0.30 < v < 0.50
    assert np.isnan(ARC._interpolar(t, 90))  # fuera del rango de vencimientos


def test_resumen_de_cadena(monkeypatch):
    monkeypatch.setenv("TRADING_DEMO", "1")
    from core import options as OP
    df, _ = OP.chain("AMD", 171.3, 60, 0.55)
    r = ARC.resumir(df, 171.3, 0.55)
    for c in ("iv_atm_7d", "iv_atm_30d", "skew_25d", "spread_atm_pct", "put_call_oi"):
        assert np.isfinite(r[c]), c
    assert 0.05 < r["iv_atm_30d"] < 2 and abs(r["iv_vs_real_30d"] - r["iv_atm_30d"] / 0.55) < 1e-9
    assert ARC.resumir(pd.DataFrame(), 100, None)["contratos"] == 0
