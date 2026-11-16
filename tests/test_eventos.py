import numpy as np
import pandas as pd

from core import eventos as EV
from core import technical as T


def _serie(n=200, salto=150, pct=0.12):
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, n)
    r[salto] = pct
    c = 100 * np.exp(np.cumsum(r))
    idx = pd.bdate_range("2025-01-01", periods=n)
    o = np.r_[c[0], c[:-1]]
    o[salto] = c[salto] * 0.99  # abre con gap
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.004, "Low": np.minimum(o, c) * 0.996, "Close": c,
                         "Volume": np.where(np.arange(n) == salto, 5e6, 1e6)}, index=idx)


def test_detecta_vela_de_evento():
    d = _serie()
    det = EV.detectar(d)
    assert det["anomala"].iloc[150]
    assert det["anomala"].sum() <= 4  # sin falsos positivos masivos en ruido normal


def test_atr_robusto_no_se_infla():
    d = _serie()
    a_rob = T.atr(d).iloc[155]
    a_raw = T.wilder(T.true_range(d), 14).iloc[155]
    assert a_rob < a_raw


def test_marcadores_y_avisos():
    d = _serie(salto=198)
    evs = [{"fecha": d.index[198].date().isoformat(), "ret": 0.12, "causa": "Noticia", "tipo": "noticia"}]
    mk = EV.marcadores(evs, d)
    assert mk and mk[0]["x"] == d.index[198]
    av = EV.avisos(evs, d, None, hoy=d.index[-1].date())
    assert av and "reciente" in av[0]
