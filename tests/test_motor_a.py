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


def _facts():
    q = []
    for i, (fin, filed, ing, bpa) in enumerate([("2023-03-31", "2023-05-02", 100, 1.0), ("2023-06-30", "2023-08-01", 110, 1.1),
                                                 ("2023-09-30", "2023-10-31", 120, 1.2), ("2024-03-31", "2024-05-02", 150, 1.6),
                                                 ("2024-06-30", "2024-08-01", 160, 1.4)]):
        ini = str((pd.Timestamp(fin) - pd.Timedelta(days=90)).date())
        q.append((ini, fin, filed, ing, bpa))
    rev = [{"start": a, "end": b, "filed": f, "val": r, "form": "10-Q"} for a, b, f, r, _ in q]
    eps = [{"start": a, "end": b, "filed": f, "val": e, "form": "10-Q"} for a, b, f, _, e in q]
    sh = [{"end": "2023-04-20", "filed": "2023-05-02", "val": 1e6, "form": "10-Q"},
          {"end": "2024-04-20", "filed": "2024-05-02", "val": 9e5, "form": "10-Q"}]
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "EarningsPerShareDiluted": {"units": {"USD/shares": eps}}},
                      "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": sh}}}}}


def test_sec_point_in_time():
    from core.motor_a import sec as SE
    f = pd.bdate_range("2023-01-02", "2024-12-31")
    df = pd.DataFrame({"Open": 10.0, "High": 10.5, "Low": 9.5, "Close": 10.0, "Volume": 1e6}, index=f)
    pres = SE.tabla_presentaciones([{"form": ["8-K", "8-K", "10-Q"], "filingDate": ["2024-05-02", "2024-06-10", "2024-05-02"],
                                     "items": ["2.02,9.01", "2.01", ""]}])
    V = SE.variables(df, pd.Series(0.01, index=f), pres, _facts())
    # la capitalización usa las acciones publicadas el 2-may-2023 solo desde el día hábil siguiente
    assert np.isnan(V.loc["2023-05-02", "tam_log_cap"]) and np.isclose(V.loc["2023-05-03", "tam_log_cap"], np.log(1e7))
    # el crecimiento de ingresos del 1T-2024 (150 vs 100) aparece solo después de su presentación
    assert np.isnan(V.loc["2024-05-02", "fund_crec_ingresos"]) or V.loc["2024-05-02", "fund_crec_ingresos"] != np.log(1.5)
    assert np.isclose(V.loc["2024-05-03", "fund_crec_ingresos"], np.log(1.5))
    # resultados (8-K 2.02) y adquisición (2.01): días desde el evento, contados desde el día hábil siguiente
    assert V.loc["2024-05-03", "res_dias_desde"] == 0 and V.loc["2024-05-10", "res_dias_desde"] == 5
    assert V.loc["2024-06-10", "corp_dias_desde_adquisicion"] == 250 and V.loc["2024-06-11", "corp_dias_desde_adquisicion"] == 0


def test_macro_fomc():
    from core.motor_a import macro as MC
    f = pd.bdate_range("2024-01-02", "2024-03-29")
    spy = pd.DataFrame({"Close": np.linspace(470, 520, len(f))}, index=f)
    M = MC.variables(spy)
    assert M.loc["2024-01-31", "mac_dias_hasta_fomc"] == 0 and M.loc["2024-01-30", "mac_dias_hasta_fomc"] == 1
    assert M.loc["2024-02-01", "mac_fomc_con_proyecciones"] == 1  # la próxima (20-mar) tiene proyecciones
    assert M.loc["2024-01-31", "mac_dias_desde_fomc"] == 0
    assert len(MC.PROGRAMADAS) == 96 and all(a < b for (a, _), (b, _) in zip(MC.PROGRAMADAS, MC.PROGRAMADAS[1:]))
