import json

import pandas as pd
import pytest

from core import indicators as I
from core import profiles
from core.data import _synthetic, _synthetic_tf


def test_catalogo_completo():
    assert len(I.CATALOGO) == 35
    ids = {c["id"] for c in I.CATALOGO}
    assert {"ma", "vrvp", "rsi", "macd", "wt", "konc", "fvg", "ob"} <= ids
    for c in I.CATALOGO:
        assert c["inputs"] and c["plots"] and all(c["info"].get(k) for k, _ in I.FICHA), c["id"]
    vrvp = [f["l"] for f in I.BYID["vrvp"]["inputs"]]
    assert vrvp == ["Diseño de las filas", "Tamaño de la fila", "Volumen", "Volumen del área de valor"]


def test_config_por_perfil_y_merge():
    sw = I.default_config("swing", profiles.default_settings("swing"))
    assert I.activos(sw) == ["ma", "rsi", "macd", "bb", "vol", "vrvp"]
    day = I.default_config("day", profiles.default_settings("day"))
    assert "vwap" in I.activos(day) and day["vwap"]["in"]["anchor"] == "Sesión"
    saved = {"ma": {"in": {"l1": 12}, "st": {"m1": {"w": 3}}}, "ichi": {"on": True, "conf": True}, "zzz": {}}
    m = I.merge_config(saved, "swing", profiles.default_settings("swing"))
    assert m["ma"]["in"]["l1"] == 12 and m["ma"]["st"]["m1"]["w"] == 3 and m["ma"]["st"]["m1"]["c"]
    assert m["ichi"]["on"] and "zzz" not in m


def test_sincroniza_motor():
    S = profiles.default_settings("swing")
    cfg = I.default_config("swing", S)
    cfg["ma"]["in"].update(l1=8, t1="HMA")
    cfg["rsi"]["in"].update(len=9, ob=75)
    out = I.to_engine(cfg, S)
    assert out["mas"][0]["periodo"] == 8 and out["mas"][0]["tipo"] == "EMA"  # HMA no existe en el motor: conserva EMA
    assert out["rsi"] == {"periodo": 9, "sobrecompra": 75, "sobreventa": 30}
    assert out["indicadores"]["ma"]["in"]["t1"] == "HMA"
    assert "indicadores" not in profiles.engine_settings(out)
    cfg["macd"]["in"].update(fast=30, slow=26)
    assert I.validar(cfg)


@pytest.mark.parametrize("tf", ["10m", "1h", "1D", "1W"])
def test_calculos_dibujables(tf):
    df = _synthetic_tf("AAPL", tf) if tf != "1D" else _synthetic("AAPL")
    cfg = I.default_config("swing")
    for c in I.CATALOGO:
        p = cfg[c["id"]]["in"]
        if c["draw"] == "ov" and c["id"] not in ("fib", "vrvp"):
            els = I.overlay(df, c["id"], p, tf)
            assert els, c["id"]
            for e in els:
                for k in ("y", "up", "a"):
                    if isinstance(e.get(k), pd.Series):
                        assert e[k].notna().any(), (c["id"], e["plot"])
        if c["draw"] == "pane" and c["id"] != "vol":
            pn = I.pane(df, c["id"], p)
            assert pn and (pn["lines"] or pn.get("hist")), c["id"]


def test_todas_las_medias():
    s = _synthetic("AAPL")["Close"]
    for t in ["SMA", "EMA", "WMA", "HMA", "RMA", "DEMA", "TEMA", "VWMA", "ALMA", "KAMA", "LSMA"]:
        r = I.ma(t, s, 20, _synthetic("AAPL")["Volume"])
        assert r.notna().sum() > len(s) - 60, t
        assert abs(r.iloc[-1] / s.iloc[-1] - 1) < 0.15, t


def test_grafico_con_todo_activo():
    from core.ui import price_chart
    df = _synthetic("AAPL")
    cfg = I.default_config("swing")
    for c in I.CATALOGO:
        cfg[c["id"]]["on"] = True
    fig = price_chart(df, None, None, None, bars=120, tf="1D", ind=cfg)
    assert len(fig.data) > 30
    cfg["ma"]["st"]["m1"]["v"] = False
    assert len(price_chart(df, None, None, None, bars=120, tf="1D", ind=cfg).data) == len(fig.data) - 1
