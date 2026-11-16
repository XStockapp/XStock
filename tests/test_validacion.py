import numpy as np

from core import validacion as V


def test_wilson_y_fisher():
    lo, hi = V.wilson(60, 100)
    assert 0.49 < lo < 0.51 and 0.69 < hi < 0.71
    a, b = V.fisher_ci(0.1, 400)
    assert a < 0.1 < b and a > 0


def test_logit_recupera_coeficiente():
    rng = np.random.default_rng(0)
    x = rng.normal(size=4000)
    y = (rng.random(4000) < 1 / (1 + np.exp(-(0.2 + 1.5 * x)))).astype(float)
    w = V.logit_fit(np.column_stack([np.ones_like(x), x]), y, l2=0.0)
    assert abs(w[1] - 1.5) < 0.2 and abs(w[0] - 0.2) < 0.15


def test_walk_forward_no_mira_el_futuro():
    rng = np.random.default_rng(1)
    n = 1000
    x = rng.normal(size=n)
    y = np.zeros(n)
    y[600:] = (x[600:] > 0)  # la relación solo existe en el futuro
    p = V.walk_forward_prob(np.column_stack([np.ones(n), x]), y, 600, 100, 5)
    # el primer bloque se ajustó solo con el pasado (sin relación): no puede predecir bien
    first = p[600:700]
    assert np.isfinite(first).all() and np.mean((first > 0.5) == (x[600:700] > 0)) < 0.75


def test_metricas_ruido_sin_ventaja():
    rng = np.random.default_rng(2)
    s = rng.normal(0, 40, 3000)
    f = rng.normal(0, 0.01, 3000)
    m = V._metricas(s, f, np.full(3000, 0.5), 1)
    assert m["acierto_lo"] < 0.5 < m["acierto_hi"] and m["ic_lo"] < 0 < m["ic_hi"]
