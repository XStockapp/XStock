import numpy as np
import pandas as pd
import pytest

from core.motor_a import dataset as DS, etiquetas as ET, modelo as MO, variables as VA

pytest.importorskip("lightgbm")


def test_triple_barrera_casos():
    f = pd.bdate_range("2024-01-01", periods=6)
    c = np.full(6, 100.0)
    df = pd.DataFrame({"Open": c, "High": c + [0, 0, 5, 0, 0, 0], "Low": c - [0, 1, 0, 5, 0, 0], "Close": c}, index=f)
    y = ET.triple_barrera(df, pd.Series(0.01, index=f), H=2, k=1.0)  # barreras ±1.41 %
    assert (y["y"].iloc[0], y["barrera"].iloc[0], y["dias"].iloc[0]) == (1, 1, 2)  # el −1 % no llega; +5 % sí
    assert (y["y"].iloc[2], y["barrera"].iloc[2]) == (0, -1)  # −5 % al día siguiente
    assert (y["y"].iloc[3], y["barrera"].iloc[3]) == (0, 0)  # nada en 2 sesiones → vertical (sin subida)
    assert y["y"].iloc[-1] != y["y"].iloc[-1]  # sin futuro suficiente → NaN


def test_variables_sin_futuro():
    barras, spy = DS.sintetico(n_acciones=1, n_dias=400)
    df = next(iter(barras.values()))
    X1 = VA.por_accion(df)
    X2 = VA.por_accion(df.iloc[:300])  # cortar el futuro no cambia el pasado
    pd.testing.assert_frame_equal(X1.iloc[:300], X2, check_freq=False)


def test_ruido_no_da_ventaja_y_senal_si():
    for senal, esperado in ((0.0, "SIN VENTAJA DEMOSTRADA"), (0.15, None)):
        barras, spy = DS.sintetico(n_acciones=25, n_dias=1300, senal=senal)
        R = MO.walk_forward(DS.construir(barras, spy), log=lambda *_: None)["resumen"]
        if esperado:
            assert R["veredicto"] == esperado and R["auc"] < 0.52
        else:
            assert R["auc"] > 0.55 and R["ic_t"] > 3 and R["veredicto"] != "SIN VENTAJA DEMOSTRADA"
