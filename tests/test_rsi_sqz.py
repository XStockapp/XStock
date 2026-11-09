import numpy as np
import pandas as pd

from core import indicators as I


def _df(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    return pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1e6}, index=idx)


def test_rsi_una_linea_fondo_y_divergencias():
    cfg = I.default_config("swing")
    pn = I.pane(_df(), "rsi", cfg["rsi"]["in"])
    assert [k for k, _ in pn["lines"]] == ["rsi"]  # sin MA por defecto, como TradingView
    assert pn["fill"] == "bg" and len(pn["refs"]) == 3
    for t1, v1, t2, v2, kind in pn["divs"]:
        assert t1 < t2 and kind in ("bull", "bear")
        assert (v2 > v1) if kind == "bull" else (v2 < v1)


def test_divergencia_alcista_detectada():
    # precio hace mínimo más bajo y el oscilador mínimo más alto
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    low = np.full(n, 100.0); low[15] = 90; low[40] = 85
    osc = pd.Series(np.full(n, 50.0), index=idx); osc.iloc[15] = 20; osc.iloc[40] = 30
    df = pd.DataFrame({"Low": low, "High": low + 5}, index=idx)
    d = I.divergencias(df, osc, lb=5)
    assert any(k == "bull" and t1 == idx[15] and t2 == idx[40] for t1, _, t2, _, k in d)


def test_squeeze_cuatro_colores_y_puntos():
    cfg = I.default_config("swing")
    pn = I.pane(_df(), "sqz", cfg["sqz"]["in"])
    assert set(pn["hcols"].dropna().unique()) <= {"up1", "up2", "dn1", "dn2"}
    assert set(pn["dots"].unique()) <= {"sqon", "sqoff"}
    assert "mom" in I.BYID and I.pane(_df(), "mom", cfg["mom"]["in"])["lines"]


def test_desactivado_pasa_a_otros_al_cargar():
    saved = {"bb": {"on": False, "conf": True}}
    m = I.merge_config(saved, "swing")
    assert m["bb"]["conf"] is False and m["bb"]["on"] is False
