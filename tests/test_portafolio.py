import pandas as pd

from core import portfolio as P


def _df(rows, start="2026-11-02"):
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame([{"Open": c, "High": h, "Low": l, "Close": c} for h, l, c in rows], index=idx)


def _op(**kw):
    o = {"id": "x", "ticker": "T", "fecha": "2026-11-02T15:00:00Z", "tf": "1D", "largo": True, "modo": "limit",
         "entrada": 100.0, "precio_registro": 103.0, "stop": 95.0, "tp1": 105.0, "tp2": 110.0, "acciones": 10,
         "riesgo": 50.0, "cierre": None, "fecha_cierre": None}
    o.update(kw)
    return o


def test_limit_pendiente_hasta_tocar_entrada():
    e = P.evaluar(_op(), _df([(104, 101, 103), (105, 100.5, 104)]))
    assert e["estado"] == "Pendiente" and e["resultado"] is None and e["abierta"]


def test_llenada_y_tp2():
    e = P.evaluar(_op(), _df([(103, 99, 101), (106, 101, 105), (111, 104, 110)]))
    assert e["estado"] == "Cerrada (TP2)" and e["resultado"] == 100 and e["resultado_R"] == 2


def test_stop_tras_tp1_y_corto():
    e = P.evaluar(_op(), _df([(103, 99, 101), (106, 101, 105), (104, 94, 95)]))
    assert e["estado"] == "Stop tras TP1" and e["resultado"] == -50
    c = P.evaluar(_op(largo=False, modo="market", entrada=100, stop=105, tp1=95, tp2=90),
                  _df([(101, 97, 98), (99, 96, 97)]))
    assert c["estado"] == "Abierta" and c["resultado"] == 30


def test_cierre_manual():
    e = P.evaluar(_op(modo="market", cierre=102.0), _df([(103, 99, 101)]))
    assert e["estado"] == "Cerrada (manual)" and e["resultado"] == 20 and not e["abierta"]
