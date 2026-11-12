import numpy as np
import pandas as pd

from core import confirmacion as CF
from core.technical import adx_regimen, compute_all, score_series


def _df(n=400, seed=1, drift=0.05):
    r = np.random.default_rng(seed)
    c = 100 + np.cumsum(r.normal(drift, 1.2, n))
    o = c + r.normal(0, 0.4, n)
    h = np.maximum(c, o) + r.uniform(0.1, 1.0, n)
    lo = np.minimum(c, o) - r.uniform(0.1, 1.0, n)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": r.integers(1e6, 2e6, n).astype(float)}, index=idx)


def test_peso_acotado_y_cuantitativo_domina():
    d = compute_all(_df())
    cal = CF.calibrar(d, score_series(d))
    assert CF.W_MIN <= cal["peso_patrones"] <= CF.W_MAX
    assert cal["peso_cuantitativo"] >= 0.70


def test_mezcla_lineal():
    cal = {"peso_patrones": 0.3}
    adx = {"regimen": "tendencia"}
    a = [{"nombre": "Doble suelo", "categoria": "Reversión", "sesgo": "alcista", "estado": "Confirmado",
          "volumen": True, "confluencia": True}]
    r = CF.consolidar(0.55, 1, a, cal, 40, adx)
    assert abs(r["confianza_global"] - (0.7 * 55 + 0.3 * 100)) < 0.06
    assert r["aporte_patrones"] > 0
    # en contra: peso a la mitad y alerta
    r2 = CF.consolidar(0.55, -1, a, cal, -40, adx)
    assert abs(r2["confianza_global"] - (0.85 * 55 + 0.15 * 0)) < 0.06
    assert r2["alertas"]
    # sin patrones: la confianza es la cuantitativa salvo el peso hacia 50
    r3 = CF.consolidar(0.55, 1, [], cal, 40, adx)
    assert abs(r3["confianza_global"] - (0.7 * 55 + 0.3 * 50)) < 0.06


def test_adx_nivel_clave_23():
    d = compute_all(_df())
    reg = adx_regimen(d)
    assert reg["nivel_clave"] == 23
    assert reg["regimen"] == ("tendencia" if reg["adx"] >= 23 else "rango")


def test_envolvente_en_nivel():
    d = _df(120)
    d = compute_all(d)
    i = len(d) - 1
    lo = float(d["Low"].tail(20).min())
    d.iloc[i - 1, d.columns.get_loc("Open")] = lo + 2
    d.iloc[i - 1, d.columns.get_loc("Close")] = lo + 0.5
    d.iloc[i - 1, d.columns.get_loc("Low")] = lo
    d.iloc[i, d.columns.get_loc("Open")] = lo + 0.3
    d.iloc[i, d.columns.get_loc("Close")] = lo + 2.6
    d.iloc[i, d.columns.get_loc("Low")] = lo + 0.2
    d.iloc[i, d.columns.get_loc("High")] = lo + 2.8
    v = CF._velas(d, [lo], 1.0)
    assert v and v[0]["nombre"] == "Envolvente alcista" and v[0]["estado"] == "Pendiente de confirmación"


def test_veredictos_homologados():
    from core import ai
    assert ai.normalizar_veredicto("COMPRAR") == "COMPRA"
    assert ai.normalizar_veredicto("ESPERAR", {"estado_tipo": "esperar"}) == "REBOTE"
    assert ai.normalizar_veredicto("ESPERAR", {}) == "NEUTRAL"
    assert ai.normalizar_veredicto("VENDER EN CORTO") == "EVITAR / VENTA"
