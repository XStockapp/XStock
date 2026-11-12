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


def test_hombro_cabeza_hombro_vigencia():
    base = [90] * 10 + _seg(90, 104, 96, 112, 96, 104)
    # pendiente de ruptura: el precio baja desde el hombro derecho pero sigue sobre la clavicular (96)
    f = PT.patterns(_df(base + list(np.linspace(104, 98.5, 8))))
    h = [p for p in f if p["nombre"] == "Hombro-cabeza-hombro"]
    assert h and h[0]["estado_meta"] == "PENDING_BREAKOUT" and abs(h[0]["activacion"] - 96) < 1.5, f
    assert "Si el precio pierde" in h[0]["condicion"]
    # recién confirmada: cierre bajo la clavicular en las últimas velas
    f = PT.patterns(_df(base + list(np.linspace(104, 94.5, 10))))
    assert any(p["nombre"] == "Hombro-cabeza-hombro" and p["estado_meta"] == "CONFIRMED" for p in f), f
    # ruptura antigua (movimiento ya en curso): se descarta
    f = PT.patterns(_df(base + _seg(104, 88, 86)))
    assert not any(p["nombre"] == "Hombro-cabeza-hombro" for p in f), f


def test_patron_pasado_se_descarta():
    # HCH completo hace mucho y luego 60 velas de tendencia: nada vigente del HCH
    path = [90] * 10 + _seg(90, 104, 96, 112, 96, 104, 88) + list(np.linspace(88, 120, 60))
    assert not any(p["nombre"].startswith("Hombro") for p in PT.patterns(_df(path)))


def test_temporalidad_baja_sin_patrones():
    base = [90] * 10 + _seg(90, 104, 96, 112, 96, 104) + list(np.linspace(104, 98.5, 8))
    assert PT.patterns(_df(base), tf="10m") == [] and PT.patterns(_df(base), tf="30m") == []
    assert PT.patterns(_df(base), tf="1h")


def test_doble_suelo():
    path = [110] * 10 + _seg(110, 95, 105, 95.2, 108)
    f = PT.patterns(_df(path))
    assert any(p["nombre"] == "Doble suelo" for p in f), f
