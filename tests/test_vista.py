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
