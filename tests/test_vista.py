from core import profiles
from core.timeframes import RANGO_DEFAULT, RANGOS, rango_valido, rango_velas


def test_rangos_por_temporalidad():
    assert rango_velas("1D", "6M") == 126
    assert rango_velas("1h", "1M") == 147          # 21 sesiones × 7 velas
    assert rango_velas("30m", "1S") == 65           # 5 sesiones × 13 velas
    assert rango_velas("1D", "1A", crypto=True) == 365
    assert rango_velas("1M", "Máx", disponibles=180) == 180
    assert rango_velas("1D", "5A", disponibles=300) == 300
    for tf, opts in RANGOS.items():
        assert RANGO_DEFAULT[tf] in opts


def test_rango_invalido_vuelve_al_defecto():
    assert rango_valido("1h", "5A") == "1M"
    assert rango_valido("1D", None) == "6M"


def test_vista_se_conserva_y_no_entra_al_motor():
    s = profiles.merge_settings({"rsi": {"periodo": 9}, "vista": {"rangos": {"4h": "6M"}}})
    assert profiles.saved_range(s, "4h") == "6M" and s["rsi"]["periodo"] == 9
    assert "vista" not in profiles.engine_settings(s)
    assert profiles.saved_range(profiles.default_settings("swing"), "1D") is None


def test_10m():
    from core.timeframes import validate
    assert validate("10m") == "10m"
    assert rango_velas("10m", "3D") == 117 and rango_velas("10m", "Hoy") == 39
    assert profiles.get("day")["tfs"][0] == "10m"
    import pytest
    for bad in ("1m", "5m", "15m"):
        with pytest.raises(ValueError):
            validate(bad)


def test_future_index_respeta_la_sesion():
    import pandas as pd
    from core.timeframes import future_index
    fri = pd.Timestamp("2026-11-06 15:50")
    assert future_index(fri, 1, "10m") == pd.Timestamp("2026-11-09 09:30")   # lunes a la apertura
    assert future_index(fri, 39, "10m") == pd.Timestamp("2026-11-09 15:50")  # 39 velas = 1 sesión
    assert future_index(fri, 45, "10m") == pd.Timestamp("2026-11-10 10:20")
    assert future_index(pd.Timestamp("2026-11-05 09:30"), 13, "30m") == pd.Timestamp("2026-11-06 09:30")
    assert future_index(fri, 6, "10m", crypto=True) == pd.Timestamp("2026-11-06 16:50")
