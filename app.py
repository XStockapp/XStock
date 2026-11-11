"""
XStock — Plataforma de análisis de acciones de EE.UU.
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

st.set_page_config(page_title="XStock · Trading · Data · Analytics", page_icon="assets/favicon.png", layout="wide",
                   initial_sidebar_state="auto")
inject_css()

# ---- Acceso: invitaciones + Auth0 (Google o correo con código) / modo personal ----
from core import auth, brand  # noqa: E402

profile = auth.gate()
ADMIN = profile.get("role") == "admin"

if "cfg" not in st.session_state:
    st.session_state.cfg = store.config()
cfg = st.session_state.cfg

# ---- Perfil de trader y ajustes técnicos (onboarding) ----
from core import profiles as _profiles  # noqa: E402

if "trader_profile" not in st.session_state:
    _src = cfg if profile.get("email") == "owner@local" else profile
    st.session_state.trader_profile = _src.get("trader_profile")
    st.session_state.technical_settings = _profiles.merge_settings(_src.get("technical_settings"))
    st.session_state.default_tf = _src.get("default_tf") or _profiles.get(_src.get("trader_profile"))["tf"]
NEEDS_ONBOARDING = not st.session_state.trader_profile or st.session_state.get("onboarding")

st.logo("assets/xstock_wordmark.png", size="large", icon_image="assets/xstock_icon.png")

with st.sidebar:
    if os.environ.get("TRADING_DEMO") == "1":
        st.warning("MODO DEMO: datos sintéticos")

_main = [
    st.Page("views/scanner.py", title="Escáner de mercado", icon=":material/radar:", default=True),
    st.Page("views/analisis.py", title="Análisis de acción", icon=":material/candlestick_chart:"),
    st.Page("views/watchlist.py", title="Watchlist", icon=":material/visibility:"),
    st.Page("views/portafolio.py", title="Portafolio", icon=":material/account_balance_wallet:"),
]
_admin = [
    st.Page("views/admin_invitaciones.py", title="Invitaciones", icon=":material/person_add:"),
    st.Page("views/admin_usuarios.py", title="Usuarios y uso", icon=":material/group:"),
]
_onb = [st.Page("views/onboarding.py", title="Configurar perfil", icon=":material/tune:", default=True)]
if NEEDS_ONBOARDING:
    pages = st.navigation(_onb)
else:
    pages = st.navigation({"Módulos de mercado": _main, "Sistema & cuenta": _admin} if ADMIN
                          else {"Módulos de mercado": _main})

def _admin_ia():
    provs = ["Alpaca con respaldo de Yahoo (gratis)", "Alpha Vantage (premium)"]
    cfg["proveedor"] = st.selectbox("Proveedor de precios del análisis", provs,
                                    index=1 if str(cfg.get("proveedor", "")).startswith("Alpha ") else 0,
                                    help="Alpaca entrega todo el mercado (SIP) con 15 minutos de retraso e historial desde 2016; "
                                         "si falla o faltan sus claves se usa Yahoo. El escáner también usa Alpaca. "
                                         "Con Alpha Vantage premium el análisis usa su historial diario.")
    from core import alpaca as _alp
    st.caption("✅ Claves de Alpaca cargadas desde los secrets" if _alp.available()
               else "⚠️ Faltan ALPACA_API_KEY y ALPACA_SECRET_KEY: se usará Yahoo")
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
    if st.button("Guardar configuración", width="stretch"):
        store.save_config(cfg)
        st.success("Guardado en datos/config.json")


from core import user_menu  # noqa: E402

with st.sidebar:
    if NEEDS_ONBOARDING and st.session_state.get("ob_step", 1) == 1:
        pass  # en el paso 1 (elegir perfil) el menú todavía no aplica
    else:
        user_menu.render(profile, ADMIN, cfg, onboarding=NEEDS_ONBOARDING, extra_admin=_admin_ia)
    # barra de estado: mercado y fuente de datos (valores reales, sin métricas inventadas)
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _Z
    from core import alpaca as _alp
    _ny = _dt.now(_Z("America/New_York"))
    _mins = _ny.hour * 60 + _ny.minute
    _open = _ny.weekday() < 5 and 570 <= _mins < 960
    _src = ("DEMO" if os.environ.get("TRADING_DEMO") == "1" else
            "ALPHA VANTAGE" if str(cfg.get("proveedor", "")).startswith("Alpha") else
            "ALPACA SIP −15m" if _alp.available() else "YAHOO")
    st.markdown(f"<div class='x-status'><span><i style='background:{'#26A69A' if _open else '#8B949E'}'></i>"
                f"NYSE {'ABIERTO' if _open else 'CERRADO'}</span><span>{_ny:%H:%M} NY</span>"
                f"<span>DATOS {_src}</span></div>", unsafe_allow_html=True)

pages.run()
