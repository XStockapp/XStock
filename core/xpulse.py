"""X-Pulse (nombre comercial del Motor A) en la app: lee las predicciones diarias que calcula GitHub Actions
(modelos/motor_a/predicciones.json) y las muestra como un panel compacto. La app no entrena ni descarga barras.

Qué dice X-Pulse: la probabilidad de que la acción se mueva con fuerza (±k·σ·√H, en cualquier dirección) en las
próximas H sesiones, comparada con lo que ya cobra la IV de las opciones → señal «IV barata / justa / cara».
No predice la dirección: en las pruebas fuera de muestra la dirección no tuvo ventaja sobre el azar.
"""
from __future__ import annotations

import html
import json
import math

import streamlit as st

from core.ui import AMBER, GREEN, MUTED, RED

NOMBRE = "X-Pulse"
SENALES = {
    "barata": ("IV BARATA", GREEN, "X-Pulse espera más movimiento del que cobran las opciones: comprar opciones "
                                   "tiene el viento a favor."),
    "cara": ("IV CARA", RED, "Las opciones cobran más movimiento del que espera X-Pulse: la prima está cara para "
                             "comprar; cuidado con la caída de la IV."),
    "justa": ("IV JUSTA", AMBER, "La IV cobra aproximadamente el movimiento que espera X-Pulse."),
}


@st.cache_data(ttl=1800, show_spinner=False)
def predicciones() -> dict | None:
    from core.motor_a import artefactos as AR
    try:
        crudo = AR.bajar("predicciones.json")
        return json.loads(crudo) if crudo else None
    except Exception:
        return None


def de(ticker: str) -> tuple[dict | None, dict | None]:
    P = predicciones()
    if not P:
        return None, None
    return (P.get("acciones") or {}).get(str(ticker).upper()), P


def _pct(v) -> str:
    return "—" if v is None or not math.isfinite(v) else f"{v * 100:.0f}%"


def panel_html(ticker: str, spot: float | None = None) -> str | None:
    """HTML del panel; None si X-Pulse no cubre esta acción (crypto, poco líquida o sin predicción hoy)."""
    x, P = de(ticker)
    if not x or x.get("p") is None:
        return None
    H, k = P.get("H", 10), P.get("k", 1.0)
    mov = k * (x.get("sigma_d") or 0) * math.sqrt(H)  # tamaño del movimiento en fracción del precio
    mov_txt = f"±{mov * 100:.1f}%" + (f" (±${spot * mov:,.2f})" if spot else "")
    base = P.get("tasa_base")
    s = SENALES.get(x.get("senal") or "")
    rv_iv = (x.get("sigma_d") or 0) * math.sqrt(252) / x["iv"] if x.get("iv") else None
    inflada = rv_iv is not None and rv_iv > 1.5  # la vol. real de 20 sesiones viene de un salto puntual
    if inflada and s:
        s = (s[0], MUTED, s[2])
    chip = (f"<span class='x-chip' style='border-color:{s[1]}66;color:{s[1]}'>{s[0]}</span>" if s else
            f"<span class='x-chip' style='color:{MUTED}'>SIN IV HOY</span>")
    filas = [("Probabilidad de movimiento fuerte", _pct(x["p"])),
             ("Lo que cobra la IV", _pct(x.get("p_iv"))),
             ("Promedio histórico", _pct(base)),
             ("IV ATM ~14 días", _pct(x.get("iv")))]
    celdas = "".join(f"<div class='xp-c'><div class='xp-l'>{html.escape(a)}</div><div class='xp-v num'>{b}</div></div>"
                     for a, b in filas)
    nota = s[2] if s else "Sin cadena de opciones archivada hoy para esta acción: solo la probabilidad del modelo."
    if inflada:
        nota = (f"Volatilidad inflada por un salto reciente: la real de 20 sesiones es {rv_iv:.1f}× la IV, así que el "
                "movimiento de referencia es exagerado y la señal es menos confiable.")
    return (
        "<style>.xp{background:#161B22;border:1px solid #30363D;border-radius:6px;padding:10px 12px;margin:6px 0 10px}"
        ".xp-h{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:13px}"
        ".xp-h b{letter-spacing:.06em}.xp-g{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;"
        "margin-top:8px}.xp-c{border:1px solid #30363D;border-radius:4px;padding:6px 8px}"
        ".xp-l{font-size:11px;color:#8B949E}.xp-v{font-size:14px;font-variant-numeric:tabular-nums;"
        "font-family:'JetBrains Mono','Fira Code',monospace}.xp-n{font-size:12px;color:#8B949E;margin-top:6px}"
        "@media(max-width:640px){.xp-g{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>"
        f"<div class='xp'><div class='xp-h'><b>{NOMBRE}</b>"
        f"<span class='muted'>fuerza esperada en {H} sesiones · movimiento de referencia {html.escape(mov_txt)}</span>"
        f"{chip}<span class='muted num' style='margin-left:auto;font-size:11px'>al cierre {html.escape(P.get('fecha', ''))}</span>"
        f"</div><div class='xp-g'>{celdas}</div>"
        f"<div class='xp-n'>{html.escape(nota)} La dirección la marca el análisis técnico y tus estrategias; X-Pulse "
        "indica si el movimiento tendrá recorrido y si las opciones lo cobran barato.</div></div>")


def mostrar(ticker: str, spot: float | None = None) -> bool:
    h = panel_html(ticker, spot)
    if h:
        st.markdown(h, unsafe_allow_html=True)
    return bool(h)
