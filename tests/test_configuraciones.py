"""Configuraciones de indicadores con nombre (máx. 5), «default» de solo lectura y guardado automático."""
import streamlit as st

from core import profiles, user_menu as U


def _reset(mp, settings=None):
    st.session_state.clear()
    st.session_state.trader_profile = "swing"
    st.session_state.technical_settings = settings
    st.session_state.profile = {"email": "owner@local"}
    saved = {}

    def fake_save(tf=None, rango=None, settings=None, trader_profile=None):
        saved["S"] = settings
        st.session_state.technical_settings = settings
    mp.setattr(profiles, "save_user_view", fake_save)
    return saved


def test_default_modificada_pide_nombre_y_guardar_activa(monkeypatch):
    saved = _reset(monkeypatch)
    U.init_work("swing", force=True)
    assert U.active() == U.DEFAULT and not U.needs_name()
    U.work()["bb"]["on"] = False
    assert U.needs_name()
    assert U.save_as("default")  # nombre reservado
    assert U.save_as("Cripto 1h") is None
    assert U.active() == "Cripto 1h" and not U.dirty()
    assert saved["S"]["ind_sets"]["activo"] == "Cripto 1h" and "Cripto 1h" in saved["S"]["ind_sets"]["sets"]


def test_autosave_y_maximo_cinco(monkeypatch):
    saved = _reset(monkeypatch)
    U.init_work("swing", force=True)
    for i in range(5):
        assert U.save_as(f"S{i}") is None
    assert U.save_as("S5")  # sexta: error
    assert U.save_as("S1") is None  # sobrescribir una existente sí
    U.work()["rsi"]["in"]["len"] = 21
    U.autosave()
    assert saved["S"]["ind_sets"]["sets"]["S1"]["rsi"]["in"]["len"] == 21 and not U.dirty()


def test_cambiar_y_eliminar(monkeypatch):
    _reset(monkeypatch)
    U.init_work("swing", force=True)
    U.work()["rsi"]["in"]["len"] = 9
    U.save_as("A")
    U.load_set(U.DEFAULT)
    assert U.work()["rsi"]["in"]["len"] != 9
    U.load_set("A")
    assert U.work()["rsi"]["in"]["len"] == 9
    U.delete_set("A")
    assert U.active() == U.DEFAULT and "A" not in U.sets()


def test_migra_configuracion_anterior_una_sola_vez(monkeypatch):
    _reset(monkeypatch, {"indicadores": {"rsi": {"on": True, "conf": True, "in": {"len": 7}}}})
    U.init_work("swing", force=True)
    assert U.active() == U.MIGRADA and U.work()["rsi"]["in"]["len"] == 7
    _reset(monkeypatch, {"indicadores": {"rsi": {"on": True, "conf": True, "in": {"len": 7}}},
            "ind_sets": {"activo": "default", "sets": {}}})
    U.init_work("swing", force=True)
    assert U.active() == U.DEFAULT


def test_renombrar_exportar_importar(monkeypatch):
    _reset(monkeypatch)
    U.init_work("swing", force=True)
    U.work()["rsi"]["in"]["len"] = 9
    U.save_as("A")
    U.save_as("B")
    assert U.rename_set("A", "B")  # ya existe
    assert U.rename_set("A", "default")  # reservado
    assert U.rename_set("A", "Alfa") is None and list(U.sets()) == ["Alfa", "B"]
    data = U.export_json("Alfa").encode()
    nombre, cfg = U.parse_import(data)
    assert nombre == "Alfa" and cfg["rsi"]["in"]["len"] == 9
    assert isinstance(U.parse_import(b"{}"), str) and isinstance(U.parse_import(b"no json"), str)
    assert U.import_into(U.DEFAULT, nombre, cfg) is None  # desde default: crea «Alfa (2)»
    assert U.active() == "Alfa (2)" and len(U.sets()) == 3
    cfg["rsi"]["in"]["len"] = 30
    assert U.import_into("B", nombre, cfg) is None and U.sets()["B"]["rsi"]["in"]["len"] == 30
