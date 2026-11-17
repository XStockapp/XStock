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


def test_clase_por_strike():
    ks = PO.strikes_atm([e["strike"] for e in EVS], S)
    assert [PO.clase(e["strike"], S, "CALL", ks) for e in EVS] == ["ITM", "ATM", "OTM", "OTM"]
    assert PO.clase(520, S, "PUT", ks) == "OTM" and PO.clase(550, S, "PUT", ks) == "ITM"


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
