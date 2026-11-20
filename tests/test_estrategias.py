import numpy as np
import pandas as pd

from core import comparativa_widget as CW, estrategias as E
from core import options as OP


def _df(n=500, seed=0):
    c = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 0.01, n)))
    return pd.DataFrame({"Open": c, "High": c * 1.004, "Low": c * 0.996, "Close": c, "Volume": 1e6},
                        index=pd.date_range("2026-01-01", periods=n, freq="h"))


def test_senal_tradinglatino_forma():
    s = E.senal_tradinglatino(_df())
    assert s and set(s) >= {"direccion", "confirmada", "velas", "detalle"}
    assert E.senal_tradinglatino(_df(50)) is None


def test_catalogo_solo_validadas_activables():
    assert E.CATALOGO["tradinglatino"]["validada"]
    assert not any(c["validada"] for k, c in E.CATALOGO.items() if k != "tradinglatino")


def test_mas_alla_objetivo():
    assert OP.mas_alla_objetivo({"tipo": "PUT", "strike": 44, "objetivo": 51.5})
    assert not OP.mas_alla_objetivo({"tipo": "PUT", "strike": 53, "objetivo": 51.5})
    assert OP.mas_alla_objetivo({"tipo": "CALL", "strike": 60, "objetivo": 58})


def test_comparativa_html():
    o = {"strike": 44.0, "tipo": "PUT", "vencimiento": "DIC 11 '26", "exp_iso": "2026-12-11", "dte": 22,
         "breakeven": 43.25, "ve": -46.9, "pop": 15, "prima": 0.75, "costo": 79, "delta": -0.12}
    h = CW.html(55.65, 51.5, {1: o, 2: None, 3: None}, 1, "2026-11-20")
    assert "Comparativa de las 3 opciones" in h and '"k": 44.0' in h
