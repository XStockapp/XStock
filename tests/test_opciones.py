import math
from datetime import date

import pandas as pd

from core import options as OP


def test_bs_y_iv_inversa():
    p = OP.bs_price(100, 105, 30 / 365, 0.3, True)
    assert abs(OP.implied_vol(p, 100, 105, 30 / 365, True) - 0.3) < 1e-3
    g = OP.bs_greeks(100, 100, 30 / 365, 0.3, True)
    assert 0.5 < g["delta"] < 0.56 and g["gamma"] > 0 and g["theta"] < 0


def test_occ():
    assert OP.parse_occ("AAPL261120C00270000") == ("AAPL", date(2026, 11, 20), "call", 270.0)


def _cadena():
    return OP._demo_chain("AMZN", 267.73, date(2026, 11, 13)).assign(
        dte=lambda x: [(e - date(2026, 11, 13)).days for e in x["exp"]],
        mid=lambda x: (x["bid"] + x["ask"]) / 2)


def test_metricas():
    df, spot = _cadena(), 267.73
    sm = OP.resumen(df, spot)
    assert sm["pcr_volumen"] > 0 and sm["pcr_open_interest"] > 0
    near = df[df["dte"] == sm["dte"]]
    atm = near["strike"].iloc[(near["strike"] - spot).abs().argmin()]
    c = near[(near.strike == atm) & (near.type == "call")]["mid"].iloc[0]
    p = near[(near.strike == atm) & (near.type == "put")]["mid"].iloc[0]
    assert abs(sm["expected_move_usd"] - round((c + p) * 0.85, 2)) < 0.011
    w = OP.muros(df)
    assert len(w["call_walls"]) == 2 and w["call_walls"][0]["strike"] > spot  # muro sintético de calls sobre el spot
    assert w["put_walls"][0]["strike"] < spot
    gx = OP.gex_por_strike(df, spot)
    k = gx.index[0]
    sub = df[(df.strike == k)]
    esp = sum((1 if r.type == "call" else -1) * r.gamma * r.oi * 100 * spot ** 2 * 0.01 for r in sub.itertuples())
    assert math.isclose(gx.iloc[0], esp, rel_tol=1e-9)


def test_max_pain_simple():
    df = pd.DataFrame({"strike": [90, 100, 110, 90, 100, 110], "type": ["call"] * 3 + ["put"] * 3,
                       "oi": [10, 100, 10, 10, 100, 10]})
    assert OP.max_pain(df) == 100


def test_niveles_opt123_y_presupuesto():
    df, spot = _cadena(), 267.73
    w, gx = OP.muros(df), OP.gex_por_strike(df, spot)
    evs = OP.evaluar_todos(df, spot, "CALL", w, gx)
    niv = OP.niveles(evs, spot, "OTM", 31, presupuesto=50.0)
    assert niv[1] and niv[1]["dte"] >= 11 and niv[1]["strike"] > spot
    if niv[2]:
        assert 4 <= niv[2]["dte"] <= 10
    if niv[3]:
        assert niv[3]["dte"] <= 3
    aj = niv[1].get("ajuste")
    assert niv[1]["contratos"] == 0 and aj and aj["capital_optimo"] >= niv[1]["costo"]
    rico = OP.niveles(evs, spot, "OTM", 31, presupuesto=1e6)
    assert rico[1]["contratos"] > 0 and "ajuste" not in rico[1]
    itm = OP.niveles(evs, spot, "ITM", 31)
    assert itm[1] is None or itm[1]["strike"] < spot


def test_mtf_por_vencimiento_de_cada_contrato():
    from core import mtf as MTF
    df, spot = _cadena(), 267.73
    w, gx = OP.muros(df), OP.gex_por_strike(df, spot)
    vistos = []

    def fn(dte):
        vistos.append(dte)
        p = MTF.pesos(max(dte, 0.5), ["1h", "4h", "1D"])
        # 1h alcista, 1D bajista: a corto plazo manda 1h, a largo plazo 1D
        return {"puntaje": p["1h"] * 60 + p["4h"] * 0 + p["1D"] * -60, "niveles": [], "objetivo": None, "pesos": p}
    evs = OP.evaluar_todos(df, spot, "CALL", w, gx, None, fn)
    assert sorted(set(vistos)) == sorted(set(e["dte"] for e in evs)) and len(vistos) == len(set(vistos))
    corto = [e for e in evs if e["dte"] <= 3]
    largo = [e for e in evs if e["dte"] >= 25]
    assert corto and all(not e["mtf_contra"] for e in corto)      # a corto plazo el CALL va a favor
    assert largo and all(e["mtf_contra"] for e in largo)          # a largo plazo el diario lo contradice


def test_iv_coherente_con_la_prima():
    """La IV del feed (sesgada) se reemplaza por la implícita en el precio medio: calls y puts del mismo strike
    quedan coherentes (paridad put-call) y el precio Black-Scholes reproduce la prima."""
    import numpy as np
    import pandas as pd
    from datetime import date
    rows = [("call", 535, 37.98, 41.89, .818), ("call", 550, 31.80, 34.63, .802),
            ("put", 535, 38.00, 39.86, .578), ("put", 550, 45.30, 49.39, .56)]
    df = pd.DataFrame([{"type": t, "exp": date(2026, 12, 11), "strike": k, "bid": b, "ask": a, "iv": iv,
                        "delta": np.nan, "gamma": np.nan, "theta": np.nan, "vega": np.nan, "dte": 26}
                       for t, k, b, a, iv in rows])
    df["mid"] = (df.bid + df.ask) / 2
    out = OP.recalcular_iv(df, 534.06)
    c550, p550 = out[(out.strike == 550) & (out.type == "call")].iloc[0], out[(out.strike == 550) & (out.type == "put")].iloc[0]
    assert abs(c550.iv - p550.iv) < 0.02  # antes: 0.80 vs 0.56
    assert abs(OP.bs_price(534.06, 550, 26 / 365, c550.iv, True) - c550.mid) < 1.0
    assert c550.iv_feed == .802
