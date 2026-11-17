from datetime import date

from core import options as OP
from core import perfil_opciones as PO

S = 534.06


def _e(K, prima, iv, tipo="CALL", dte=26, delta=0.45, spread=8.0):
    return {"contrato": f"{tipo} {K}", "tipo": tipo, "strike": float(K), "prima": prima, "iv": iv * 100, "dte": dte,
            "delta": delta if tipo == "CALL" else -delta, "spread_pct": spread, "ve": 0.0, "breakeven": K + prima,
            "pop": 30.0, "exp_iso": "2026-12-11", "costo": prima * 100}


EVS = [_e(520, 49.09, .730, delta=.60), _e(535, 39.94, .699, delta=.54), _e(550, 33.22, .695, delta=.48),
       _e(575, 23.19, .676, delta=.38, spread=7.2)]


def test_clase_por_strike_en_sigma():
    # AMD (IV ~70 %, 26 días): ±1/8σ ≈ ±2.6 % → 535 ATM, 550 (+3 %) ya OTM
    assert [e["clase"] for e in PO.marcar_clases(EVS, S)] == ["ITM", "ATM", "OTM", "OTM"]
    assert PO.clase({**EVS[0], "tipo": "PUT"}, S) == "OTM" and PO.clase({**EVS[2], "tipo": "PUT"}, S) == "ITM"


def test_misma_distancia_en_sigma_misma_clase():
    # 2 % OTM en SPY (IV 15 %) vs 2 % en AMD (IV 68 %): en SPY es OTM, en AMD sigue siendo ATM
    assert OP.clase_contrato(612, 600, "CALL", 0.15, 26) == "OTM"
    assert OP.clase_contrato(204, 200, "CALL", 0.68, 26) == "ATM"
    # misma distancia en σ → misma z
    z1 = OP.moneyness_z(600 * 1.02, 600, 0.15, 26)
    z2 = OP.moneyness_z(200 * (1.02 ** (0.68 / 0.15)), 200, 0.68, 26)
    assert abs(z1 - z2) < 0.1


def test_rango_y_riesgo_prima():
    assert OP.rango_strikes(None, 30) == OP.RANGO_STRIKE
    assert OP.rango_strikes(0.15, 30) < OP.rango_strikes(0.70, 30) <= 0.45
    e = {"iv": 60.0, "delta": 0.30, "prima": 1.0}
    r = OP.riesgo_prima(e, 100, False)  # 0.30·100·0.6/√252 /1 = 113 % → extremo
    assert r["nivel"] == "Extremo"
    lento = {"iv": 20.0, "delta": 0.55, "prima": 8.0}
    assert OP.riesgo_prima(lento, 100)["nivel"] == "Moderado"
    assert OP.riesgo_prima(lento, 100, crush=True)["nivel"] == "Alto"


def test_iv_relativa_a_vol_real():
    e = {"iv": 45.0, "delta": .5, "prima": 2, "exp_iso": "2026-12-11", "strike": 100, "tipo": "CALL", "dte": 20,
         "spread_pct": 3, "dentro_mov_esperado": True, "bajo_muro_puts": False, "sobre_muro_calls": False, "feriados": 0, "objetivo": 104, "obstaculos": [], "oi": 500, "theta_dia_pct": 1.0}
    from collections import defaultdict
    e = defaultdict(int, e)
    caro = OP.riesgos(e, "Alcista", {}, 0, None, 100, None, vol_real=0.30)
    assert any("IV cara" in x for x in caro)
    assert not any("IV" in x and "cara" in x for x in OP.riesgos(e, "Alcista", {}, 0, None, 100, None, vol_real=0.44))


def test_regla_maestra_solo_otm():
    p = PO.normalizar({"clases": ["OTM"]})
    an = PO.anotar(EVS, S, p)
    assert {e["clase"] for e in an if e["tac_estado"] == "fuera"} == {"ITM", "ATM"}
    niv = OP.niveles(an, S, p["clases"], 31, None, filtro=lambda e: e["tac_estado"] == "ok", clave=PO.orden)
    assert niv[1]["clase"] == "OTM"  # nunca otra clase
    t = niv[1]["tac"]
    assert 30 <= t["meta_antes"] <= 48 and t["ruido_corte"] >= 45  # el corte −35 % se toca por ruido


def test_meta_imposible_bloquea_y_espera():
    p = PO.normalizar({"clases": ["OTM"], "meta": 100, "dias": 1})
    an = PO.anotar(EVS, S, p)
    assert all(e["tac_estado"] in ("fuera", "bloqueado") for e in an)
    niv = OP.niveles(an, S, p["clases"], 31, None, filtro=lambda e: e["tac_estado"] == "ok", clave=PO.orden)
    assert niv[1] is None  # ESPERAR, no un contrato de otra clase


def test_resultados_excluye():
    p = PO.normalizar({"resultados": "evitar"})
    an = PO.anotar(EVS, S, p, res_prox=date(2026, 12, 1))
    assert all(e["tac_estado"] == "resultados" for e in an)


def test_guardar_por_accion_y_global():
    s = PO.guardar({}, "AMD", {"clases": ["OTM"]}, todas=False)
    assert PO.leer(s, "AMD")[1] == "ticker" and PO.leer(s, "NVDA") == (None, None)
    s = PO.guardar(s, "NVDA", {"clases": ["ITM"]}, todas=True)
    assert PO.leer(s, "TSLA")[0]["clases"] == ["ITM"] and PO.leer(s, "AMD")[0]["clases"] == ["OTM"]
