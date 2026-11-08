"""
Perfiles de trader y ajustes técnicos.

Cada perfil define sus temporalidades, la temporalidad por defecto, los ajustes técnicos
pre-seteados (medias, RSI, MACD, ADX, Bollinger, Fibonacci) y qué métricas prioriza el
Resumen Ejecutivo. El motor calcula todo siempre; el perfil solo decide qué se destaca.

Las cuatro medias móviles ocupan "ranuras" fijas en el DataFrame (EMA9, EMA21, SMA50, SMA200)
para no romper el resto del motor; su tipo, periodo, color y etiqueta salen de los ajustes.
"""
from __future__ import annotations

import copy
import json

MA_SLOTS = ["EMA9", "EMA21", "SMA50", "SMA200"]  # rápida, media, lenta, larga
MA_ROLES = ["Rápida", "Media", "Lenta", "Larga"]
MA_TYPES = ["EMA", "SMA", "WMA"]

BASE_SETTINGS = {
    "mas": [
        {"tipo": "EMA", "periodo": 9, "color": "#FFEB3B"},
        {"tipo": "EMA", "periodo": 21, "color": "#FF9800"},
        {"tipo": "SMA", "periodo": 50, "color": "#E91E63"},
        {"tipo": "SMA", "periodo": 200, "color": "#B2B5BE"},
    ],
    "rsi": {"periodo": 14, "sobrecompra": 70, "sobreventa": 30},
    "macd": {"rapida": 12, "lenta": 26, "senal": 9},
    "adx": {"periodo": 14, "umbral": 25},
    "bollinger": {"periodo": 20, "desv": 2.0},
    "fibonacci": {"velas": 126},
    # Vista del gráfico: temporalidad de velas y rango visible elegidos por el usuario (uno por temporalidad).
    # No interviene en los cálculos: se guarda junto a los ajustes para recordarlo entre sesiones.
    "vista": {"rangos": {}},
    # Panel de indicadores (menú USER › Indicadores): ver core/indicators.py
    "indicadores": {},
}


def _s(**over) -> dict:
    s = copy.deepcopy(BASE_SETTINGS)
    for k, v in over.items():
        if k == "mas":
            s["mas"] = v
        else:
            s[k].update(v)
    return s


PERFILES: dict[str, dict] = {
    "day": {
        "nombre": "Day Trader", "icono": "⚡", "tfs": ["10m", "1h"], "tf": "10m",
        "descripcion": "Operaciones de horas a 2–3 días. Prioriza VWAP, la media rápida, RSI y volumen relativo.",
        "settings": _s(mas=[{"tipo": "EMA", "periodo": 9, "color": "#FFEB3B"},
                            {"tipo": "EMA", "periodo": 20, "color": "#FF9800"},
                            {"tipo": "EMA", "periodo": 50, "color": "#E91E63"},
                            {"tipo": "SMA", "periodo": 200, "color": "#B2B5BE"}],
                       rsi={"periodo": 9}, bollinger={"periodo": 20}, fibonacci={"velas": 78}),
        "prioridad": ["estado", "vwap", "ma_rapida", "rsi", "vol_rel", "atr", "entrada", "stop", "tp1"],
    },
    "swing": {
        "nombre": "Swing Trader", "icono": "🌊", "tfs": ["1h", "4h", "1D"], "tf": "1D",
        "descripcion": "Operaciones de días a semanas. Prioriza entrada, TP1/TP2 con tiempo estimado y el perfil de volumen (VRVP).",
        "settings": _s(),
        "prioridad": ["estado", "entrada", "tp1", "tp2", "rr", "prob", "poc", "vah_val"],
    },
    "position": {
        "nombre": "Position Trader", "icono": "🏔️", "tfs": ["1D", "1W"], "tf": "1W",
        "descripcion": "Posiciones de meses. Prioriza la tendencia de largo plazo, el puntaje combinado y la probabilidad.",
        "settings": _s(mas=[{"tipo": "EMA", "periodo": 10, "color": "#FFEB3B"},
                            {"tipo": "EMA", "periodo": 20, "color": "#FF9800"},
                            {"tipo": "SMA", "periodo": 50, "color": "#E91E63"},
                            {"tipo": "SMA", "periodo": 100, "color": "#B2B5BE"}],
                       fibonacci={"velas": 104}),
        "prioridad": ["estado", "tendencia", "combinado", "prob", "entrada", "tp2", "objetivo_analistas", "piotroski"],
    },
    "fundamental": {
        "nombre": "Fundamental", "icono": "📊", "tfs": ["1D", "1M"], "tf": "1D",
        "descripcion": "Inversión por valor y calidad. Prioriza Piotroski, PEG, P/E, ROE, flujo de caja y el objetivo de analistas.",
        "settings": _s(),
        "prioridad": ["fundamental", "piotroski", "peg", "pe_fwd", "roe", "fcf", "objetivo_analistas", "tendencia"],
    },
    "crypto": {
        "nombre": "Crypto", "icono": "₿", "tfs": ["30m", "4h", "1D"], "tf": "4h",
        "descripcion": "Criptomonedas (p. ej. BTC-USD), mercado 24/7. Prioriza volatilidad, RSI, VWAP y niveles del plan.",
        "settings": _s(rsi={"sobrecompra": 75, "sobreventa": 25}, bollinger={"desv": 2.5}),
        "prioridad": ["estado", "rsi", "atr", "vwap", "entrada", "tp1", "tp2", "stop"],
    },
}
DEFAULT_PERFIL = "swing"


def get(key: str | None) -> dict:
    return PERFILES.get(key or DEFAULT_PERFIL, PERFILES[DEFAULT_PERFIL])


def default_settings(key: str | None) -> dict:
    return copy.deepcopy(get(key)["settings"])


def merge_settings(saved) -> dict:
    """Ajustes guardados (dict o JSON) completados con los valores base."""
    if isinstance(saved, str):
        try:
            saved = json.loads(saved)
        except Exception:
            saved = None
    s = copy.deepcopy(BASE_SETTINGS)
    if isinstance(saved, dict):
        for k, v in saved.items():
            if k == "mas" and isinstance(v, list) and len(v) == 4:
                s["mas"] = [{**BASE_SETTINGS["mas"][i], **(v[i] or {})} for i in range(4)]
            elif k in s and isinstance(v, dict):
                s[k].update(v)
    return s


def ma_label(settings: dict | None, slot: str) -> str:
    """Etiqueta visible de una ranura de media (p. ej. 'EMA9' → 'EMA20' si el usuario la cambió)."""
    if not settings:
        return slot
    m = settings["mas"][MA_SLOTS.index(slot)]
    return f"{m['tipo']}{int(m['periodo'])}"


def ma_color(settings: dict | None, slot: str) -> str:
    base = {"EMA9": "#FFEB3B", "EMA21": "#FF9800", "SMA50": "#E91E63", "SMA200": "#B2B5BE"}
    if not settings:
        return base[slot]
    return settings["mas"][MA_SLOTS.index(slot)].get("color") or base[slot]


def engine_settings(settings: dict) -> dict:
    """Ajustes que usa el motor de cálculo (sin la vista del gráfico, que no cambia los indicadores)."""
    return {k: v for k, v in settings.items() if k not in ("vista", "indicadores")}


def save_user_view(tf: str | None = None, rango: str | None = None, settings: dict | None = None,
                   trader_profile: str | None = None) -> None:
    """Guarda temporalidad, rango visible y/o ajustes técnicos del usuario actual (Supabase o config local)
    y actualiza la sesión, para que análisis y configuración de indicadores muestren lo mismo."""
    import streamlit as st

    from . import db, store
    ss = st.session_state
    S = copy.deepcopy(settings if settings is not None else merge_settings(ss.get("technical_settings")))
    tf = tf or ss.get("default_tf") or get(trader_profile or ss.get("trader_profile"))["tf"]
    if rango:
        S.setdefault("vista", {}).setdefault("rangos", {})[tf] = rango
    tp = trader_profile or ss.get("trader_profile") or DEFAULT_PERFIL
    email = (ss.get("profile") or {}).get("email")
    if email and email != "owner@local":
        db.save_trader_profile(email, tp, S, tf)
    else:  # modo personal sin base de datos
        cfg = ss.get("cfg") or store.config()
        cfg.update({"trader_profile": tp, "technical_settings": copy.deepcopy(S), "default_tf": tf})
        store.save_config(cfg)
    ss.trader_profile, ss.technical_settings, ss.default_tf = tp, S, tf


def saved_range(settings: dict | None, tf: str) -> str | None:
    return ((settings or {}).get("vista") or {}).get("rangos", {}).get(tf)
