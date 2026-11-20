import numpy as np

from core import xpulse
from core.motor_a import iv_historica as IV

REP = {"cal_iv": {"x": [0.0, 1.0], "y": [0.0, 1.0]}, "intercepto": 0.0, "coef_iv": 0.5, "coef_modelo": 0.5,
       "cortes_dif": [-0.4, -0.1, 0.1, 0.4]}


def test_combinar_senal():
    # misma IV y σ: el modelo con más probabilidad que la IV → barata; con menos → cara
    sig = 0.02
    p_iv = float(IV.prob_toque(np.array([0.32 * np.sqrt(10 / 252)]), np.array([1.0 * sig * np.sqrt(10)]))[0])
    c = IV.combinar([min(0.99, p_iv + 0.3), max(0.01, p_iv - 0.3), p_iv], [0.32] * 3, [sig] * 3, 10, 1.0, REP)
    assert list(c["senal"]) == ["barata", "cara", "justa"]
    assert np.all((c["p_comb"] > 0) & (c["p_comb"] < 1))


def test_panel(monkeypatch):
    P = {"fecha": "2026-11-18", "H": 10, "k": 1.0, "tasa_base": 0.42,
         "acciones": {"AAPL": {"p": 0.61, "p_iv": 0.48, "iv": 0.27, "sigma_d": 0.015, "senal": "barata"},
                      "XYZ": {"p": 0.3, "p_iv": None, "iv": None, "sigma_d": 0.02, "senal": None}}}
    monkeypatch.setattr(xpulse, "predicciones", lambda: P)
    h = xpulse.panel_html("aapl", 200.0)
    assert "X-Pulse" in h and "IV BARATA" in h and "61%" in h and "±4.7%" in h
    assert "SIN IV HOY" in xpulse.panel_html("XYZ")
    assert xpulse.panel_html("NOPE") is None
