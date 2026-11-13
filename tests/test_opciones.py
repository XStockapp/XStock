import math
from datetime import date

import pandas as pd

from core import ai, options as OP


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


def test_destacado_y_validacion():
    df, spot = _cadena(), 267.73
    cands = {s: OP.candidatos(df, spot, s) for s in ("alcista", "bajista")}
    assert cands["alcista"] and all(c["option_type"] == "CALL" for c in cands["alcista"])
    h = OP.destacar(cands, "Alcista", {"adx": 29, "regimen": "tendencia"}, OP.muros(df), [], spot)
    assert h["action_trigger"] == "pulse_glow_animation" and h["option_type"] == "CALL"
    assert OP.destacar(cands, "Neutral", {}, {}, [], spot) is None
    todos = cands["alcista"] + cands["bajista"]
    ok = ai.validar_destacado({"target_expiration_tab": h["target_expiration_tab"], "option_type": "CALL",
                               "strike": h["strike"], "rationale": "x"}, todos)
    assert ok and ok["strike"] == h["strike"]
    assert ai.validar_destacado({"target_expiration_tab": "ENE 1 '30", "option_type": "CALL", "strike": 1}, todos) is None


def test_simulador_escenarios():
    df, spot = _cadena(), 267.73
    w, gx = OP.muros(df), OP.gex_por_strike(df, spot)
    exps = sorted(df["exp"].unique())
    a = OP.mejor_strike(df, spot, exps[2], "CALL", w, gx)
    assert a and a["exp"] == exps[2] and a["tipo"] == "CALL"
    # el elegido tiene el mayor valor esperado de su vencimiento
    d = df[(df.exp == exps[2]) & (df.type == "call")]
    otros = [OP.evaluar(r, spot, df, w, gx) for _, r in d.iterrows()]
    assert all(a["ve"] >= o["ve"] - 1e-9 for o in otros if o and o["delta"] and 0.15 <= abs(o["delta"]) <= 0.75)
    b = OP.mejor_vencimiento(df, spot, a["strike"], "CALL", w, gx)
    assert b and b["strike"] == a["strike"]
    e = OP.evaluar(OP.contrato(df, exps[2], a["strike"], "CALL"), spot, df, w, gx)
    assert abs(e["breakeven"] - (a["strike"] + e["prima"])) < 1e-9 and 0 <= e["p_toque"] <= 100
    assert isinstance(OP.riesgos(e, "Bajista", {"regimen": "rango"}, -1, None, spot), list)


def test_pnl_trayectoria():
    # llegar antes al objetivo deja más valor temporal: utilidad decreciente con los días
    r1 = OP.pnl_trayectoria(270, "CALL", 0.3, 6.0, 30, 265, 280, 2)
    r2 = OP.pnl_trayectoria(270, "CALL", 0.3, 6.0, 30, 265, 280, 25)
    assert r1["utilidad_usd"] > r2["utilidad_usd"] and r2["quema_theta_usd"] > r1["quema_theta_usd"] > 0
    # al vencimiento: valor intrínseco
    r3 = OP.pnl_trayectoria(270, "CALL", 0.3, 6.0, 30, 265, 280, 30)
    assert abs(r3["valor_objetivo"] - 10) < 1e-9 and abs(r3["utilidad_usd"] - 400) < 1e-6
    p = OP.pnl_trayectoria(260, "PUT", 0.3, 5.0, 20, 265, 250, 30)  # días > DTE se acota
    assert abs(p["valor_objetivo"] - 10) < 1e-9
