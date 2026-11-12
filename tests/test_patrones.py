import numpy as np
import pandas as pd

from core import patterns as PT


def _df(path, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    c = np.asarray(path, float) + rng.normal(0, noise, len(path))
    idx = pd.bdate_range("2025-01-01", periods=len(c))
    return pd.DataFrame({"Open": c, "High": c + 0.6, "Low": c - 0.6, "Close": c, "Volume": 1e6}, index=idx)


def _seg(*pts, n=12):
    out = []
    for a, b in zip(pts, pts[1:]):
        out += list(np.linspace(a, b, n, endpoint=False))
    return out + [pts[-1]]


def test_canal_alcista_y_bajista():
    t = np.arange(120)
    up = _df(100 + 0.4 * t + 3 * np.sin(t / 4), noise=0.2)
    ch = PT.channel(up)
    assert ch["tipo"] == "alcista" and ch["confirmado"]
    dn = _df(200 - 0.4 * t + 3 * np.sin(t / 4), noise=0.2)
    assert PT.channel(dn)["tipo"] == "bajista"
    flat = _df(100 + 4 * np.sin(t / 4), noise=0.2)
    assert PT.channel(flat)["tipo"] == "lateral"


def test_senal_canal():
    assert PT.channel_signal({"tipo": "alcista", "posicion": 0.1}) > 0.5  # cerca del soporte: comprar
    assert PT.channel_signal({"tipo": "alcista", "posicion": -0.2}) < 0  # ruptura bajista
    assert PT.channel_signal({"tipo": "bajista", "posicion": 0.9}) < -0.5
    assert PT.channel_signal({"tipo": "lateral", "posicion": 0.9}) < 0
    assert PT.channel_signal(None) is None


def test_hombro_cabeza_hombro():
    path = [90] * 10 + _seg(90, 104, 96, 112, 96, 104, 88, 86)
    f = PT.patterns(_df(path))
    assert any(p["nombre"] == "Hombro-cabeza-hombro" and p["estado"] == "confirmada" for p in f), f


def test_doble_suelo():
    path = [110] * 10 + _seg(110, 95, 105, 95.2, 108)
    f = PT.patterns(_df(path))
    assert any(p["nombre"] == "Doble suelo" for p in f), f
