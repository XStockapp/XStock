from core import mtf


def test_pesos_flexibles_por_horizonte():
    tfs = ["1h", "4h", "1D"]
    corto, medio, largo = mtf.pesos(1, tfs), mtf.pesos(10, tfs), mtf.pesos(30, tfs)
    for p in (corto, medio, largo):
        assert abs(sum(p.values()) - 1) < 1e-9
    assert corto["1h"] > corto["4h"] > corto["1D"]       # intradía: domina la menor
    assert largo["1D"] > largo["4h"] > largo["1h"]       # largo plazo: domina la mayor
    assert medio["4h"] >= max(medio["1h"], medio["1D"]) * 0.8
    # el peso de la mayor crece de forma monótona con el horizonte
    ws = [mtf.pesos(h, tfs)["1D"] for h in (0.5, 1, 3, 7, 14, 30, 60)]
    assert ws == sorted(ws)


def _A(score, soportes, resist, regimen="tendencia", close=100.0, atr=2.0):
    import pandas as pd
    df = pd.DataFrame({"Close": [close], "ATR": [atr]})
    return {"combinado": score, "df": df, "plan": {"atr": atr, "soportes": soportes, "resistencias": resist},
            "vprofile": {}, "metodo": {"adx": {"adx": 30, "regimen": regimen}, "consolidado": {}}}


def test_combinar_alineado_y_limites():
    an = {"1h": _A(40, [(98, 2)], [(103, 2)]), "4h": _A(35, [(96, 3)], [(103.4, 2)]), "1D": _A(50, [(92, 4)], [(110, 3)])}
    r = mtf.combinar(an, 5, "1h")
    assert r["estado"] == "Alineado" and r["puntaje"] > 0 and r["alineacion"] == 1
    obj = r["limites"]["objetivo"]
    assert obj and obj["tipo"] == "R" and abs(obj["precio"] - 103.2) < 0.5  # 1h y 4h se agrupan
    assert r["limites"]["segundo_nivel"]["precio"] == 110


def test_conflicto_con_la_mayor():
    an = {"1h": _A(40, [(98, 2)], [(103, 2)]), "4h": _A(30, [(96, 3)], [(104, 2)]), "1D": _A(-50, [(92, 4)], [(110, 3)])}
    assert mtf.combinar(an, 2, "1h")["estado"] == "Rebote contra la tendencia mayor"
    an_l = {k: _A(5, [(98, 1)], [(103, 1)], regimen="rango") for k in ("1h", "4h", "1D")}
    assert mtf.combinar(an_l, 5, "1h")["estado"] == "Lateral"
