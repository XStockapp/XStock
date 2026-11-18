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


def _serie(iv, fechas, t="AAA"):
    return pd.DataFrame({"fecha": fechas, "ticker": t, "iv_current": iv, "hv_current": np.full(len(iv), 0.3),
                         "iv_year_high": np.full(len(iv), 0.9), "iv_year_low": np.full(len(iv), 0.1)})


def test_objetivo_una_semana_y_sin_futuro():
    from core.motor_b import iv_modelo as IM
    f = pd.bdate_range("2024-01-01", periods=200)
    iv = np.linspace(0.3, 0.6, 200)
    g = _serie(iv, f)
    y = IM._objetivo(g)
    # lunes 2024-01-01 → lunes siguiente (7 días): ln(iv[5]/iv[0])
    assert np.isclose(y.iloc[0], np.log(iv[5] / iv[0]))
    assert y.iloc[-1] != y.iloc[-1]  # sin futuro → NaN
    # cambiar el futuro no altera las variables del pasado
    P1 = IM.construir(pd.concat([_serie(iv, f), _serie(np.full(200, 0.2), f, "SPY")]), pd.DataFrame(columns=["ticker", "fecha"]))
    iv2 = iv.copy()
    iv2[150:] = 2.0
    P2 = IM.construir(pd.concat([_serie(iv2, f), _serie(np.full(200, 0.2), f, "SPY")]), pd.DataFrame(columns=["ticker", "fecha"]))
    X = [c for c in IM.variables(P1)]
    a = P1.xs("AAA", level="ticker").iloc[:140][X]
    b = P2.xs("AAA", level="ticker").iloc[:140][X]
    pd.testing.assert_frame_equal(a, b)


def test_resultados_dias_y_horizonte():
    from core.motor_b import iv_modelo as IM
    f = pd.bdate_range("2024-03-01", periods=30)
    cal = pd.DataFrame({"ticker": "AAA", "fecha": [pd.Timestamp("2024-03-12")], "hora": ["After market close"]})
    R = IM._resultados(_serie(np.full(30, 0.4), f), cal)
    i = list(f).index(pd.Timestamp("2024-03-05"))
    assert R["res_dias_hasta"].iloc[i] == 7 and R["res_en_horizonte"].iloc[i] == 1
    assert R["res_despues_cierre"].iloc[i] == 1
    j = list(f).index(pd.Timestamp("2024-03-14"))
    assert R["res_dias_desde"].iloc[j] == 2
