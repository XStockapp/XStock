import numpy as np
import pandas as pd

from core import backtest_cortes as BC


def _T(path, score_1h=50, score_4h=50, score_1d=50):
    c = np.array(path, float)
    idx = pd.date_range("2026-01-01", periods=len(c), freq="h")
    return pd.DataFrame({"close": c, "high": c + 0.1, "low": c - 0.1, "atr": np.full(len(c), 1.0),
                         "1h": score_1h, "4h": score_4h, "1D": score_1d}, index=idx)


def test_objetivo_antes_que_stop():
    T = _T([100, 100.5, 101, 101.5, 102, 102.5, 103.2] + [103] * 5)
    r = BC.simular(T, ["1h", "4h", "1D"], 1, 8, BC.ACTUAL, 3.0, 1.5, 0, 1)
    assert r["ops"] == 1 and abs(r["r"][0] - 2.0) < 1e-9  # tp/sl = 3/1.5


def test_stop_y_filtro_contra_mayor():
    T = _T([100, 99.5, 99, 98.4, 98] + [98] * 5)
    r = BC.simular(T, ["1h", "4h", "1D"], 1, 8, BC.ACTUAL, 3.0, 1.5, 0, 1)
    assert r["r"][0] == -1.0
    T2 = _T([100] * 10, 50, 50, -60)
    p = dict(BC.ACTUAL, filtro="sin contra la mayor", sigma=1.0, escala=1.0)
    assert BC.simular(T2, ["1h", "4h", "1D"], 0.3, 5, p, 3.0, 1.5)["ops"] == 0


def test_sin_solapamiento():
    T = _T(list(np.linspace(100, 130, 200)))
    r = BC.simular(T, ["1h", "4h", "1D"], 1, 10, BC.ACTUAL, 3.0, 1.5)
    assert r["ops"] <= 200 // 2
