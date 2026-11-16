from datetime import date

from core import calendario as CAL


def test_feriados_2026_conocidos():
    f = CAL.feriados(2026)
    esperado = {date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
                date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)}
    assert set(f) == esperado  # el 4-jul-2026 cae sábado: se observa el viernes 3


def test_cierres_y_sesiones():
    assert CAL.cierre_anticipado(date(2026, 11, 27))
    assert CAL.cierre_anticipado(date(2026, 12, 24))
    assert not CAL.es_habil(date(2026, 11, 26))
    # del lunes 23-nov al viernes 27-nov: 4 sesiones (jueves feriado)
    assert CAL.sesiones(date(2026, 11, 20), date(2026, 11, 27)) == 4
    assert CAL.feriados_entre(date(2026, 11, 20), date(2026, 12, 31)) == [(date(2026, 11, 26), "Acción de Gracias"),
                                                                         (date(2026, 12, 25), "Navidad")]


def test_pascua():
    assert CAL._pascua(2025) == date(2025, 4, 20) and CAL._pascua(2027) == date(2027, 3, 28)
