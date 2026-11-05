"""
QuantDesk — Plataforma de análisis de acciones de EE.UU.
Ejecutar:  streamlit run app.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from core import store
from core.ai import MODELOS
from core.ui import inject_css

st.set_page_config(page_title="QuantDesk · Análisis de acciones", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()

# ---- Acceso protegido con contraseña (APP_PASSWORD en los secrets de Streamlit Cloud) ----
_pwd = store.secret("APP_PASSWORD")
if _pwd and not st.session_state.get("auth_ok"):
    st.markdown("<div style='max-width:380px;margin:12vh auto 0'><div class='brand' style='font-size:1.8rem'>"
                "Quant<span>Desk</span></div><div class='muted'>Acceso privado</div></div>", unsafe_allow_html=True)
    _c = st.columns([1, 1.2, 1])[1]
    with _c.form("login"):
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            if p == _pwd:
                st.session_state.auth_ok = True
                st.rerun()
            st.error("Contraseña incorrecta")
    st.stop()

if "cfg" not in st.session_state:
    st.session_state.cfg = store.config()
cfg = st.session_state.cfg

with st.sidebar:
    st.markdown("<div class='brand'>Quant<span>Desk</span></div>"
                "<div class='muted'>Escáner · Análisis · IA</div>", unsafe_allow_html=True)
    if os.environ.get("TRADING_DEMO") == "1":
        st.warning("MODO DEMO: datos sintéticos")

pages = st.navigation([
    st.Page("views/scanner.py", title="Escáner de mercado", icon=":material/radar:", default=True),
    st.Page("views/analisis.py", title="Análisis de acción", icon=":material/candlestick_chart:"),
    st.Page("views/watchlist.py", title="Watchlist", icon=":material/visibility:"),
])

with st.sidebar:
    st.divider()
    with st.expander("⚙️ Configuración", expanded=False):
        cfg["capital"] = st.number_input("Capital de la cuenta (USD)", 100.0, 1e8, float(cfg["capital"]), 500.0)
        cfg["riesgo_pct"] = st.number_input("Riesgo por operación (%)", 0.1, 5.0, float(cfg["riesgo_pct"]), 0.1)
        c1, c2 = st.columns(2)
        cfg["tp_atr"] = c1.number_input("Objetivo (×ATR)", 1.0, 8.0, float(cfg["tp_atr"]), 0.5)
        cfg["sl_atr"] = c2.number_input("Stop (×ATR)", 0.5, 5.0, float(cfg["sl_atr"]), 0.25)
        cfg["horizonte"] = st.slider("Horizonte (sesiones)", 5, 60, int(cfg["horizonte"]))
        st.caption("IA y datos")
        provs = ["Yahoo Finance (gratis)", "Alpha Vantage (premium)"]
        cfg["proveedor"] = st.selectbox("Proveedor de datos del análisis", provs,
                                        index=provs.index(cfg.get("proveedor", provs[0])) if cfg.get("proveedor") in provs else 0,
                                        help="El escáner masivo siempre usa Yahoo (Alpha Vantage gratis permite ~25 consultas/día). "
                                             "Con Alpha Vantage premium el análisis usa su historial y fundamentales.")
        cfg["modelo"] = st.selectbox("Modelo de IA", list(MODELOS), index=list(MODELOS).index(cfg["modelo"])
                                     if cfg["modelo"] in MODELOS else 0)
        if store.secret("ANTHROPIC_API_KEY"):
            st.caption("✅ Anthropic API key cargada desde los secrets")
        else:
            cfg["anthropic_key"] = st.text_input("Anthropic API key", cfg["anthropic_key"], type="password",
                                                 help="console.anthropic.com → API Keys. Sin clave se usa síntesis por reglas.")
        if store.secret("ALPHAVANTAGE_API_KEY"):
            st.caption("✅ Alpha Vantage key cargada desde los secrets")
        else:
            cfg["alphavantage_key"] = st.text_input("Alpha Vantage API key (gratis)", cfg["alphavantage_key"], type="password",
                                                    help="alphavantage.co/support/#api-key — respaldo de fundamentales.")
        if st.button("Guardar configuración", use_container_width=True):
            store.save_config(cfg)
            st.success("Guardado en datos/config.json")
    wl = store.watchlist()
    st.caption(f"Watchlist: **{len(wl)}** acciones" + (" · ☁️ sincronizada" if store.cloud_enabled() else ""))

pages.run()
