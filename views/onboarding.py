"""Onboarding: paso 1 elegir perfil de trader, paso 2 ajustar los indicadores técnicos."""
import streamlit as st

from core import profiles, user_menu
from core.timeframes import RANGOS, rango_valido

prof = st.session_state.get("profile") or {}
saved_key = st.session_state.get("trader_profile")
step = st.session_state.setdefault("ob_step", 1)

st.markdown("<div class='sec'>Configura tu espacio de trabajo</div>", unsafe_allow_html=True)
st.progress(0.5 if step == 1 else 1.0, text=f"Paso {step} de 2 · " + ("Perfil de trader" if step == 1 else "Indicadores"))

# ---------------------------------------------------------------- PASO 1
if step == 1:
    st.markdown("### ¿Cómo operas?")
    st.caption("El perfil define tus temporalidades y qué se destaca en el resumen. El motor siempre calcula todo, "
               "y puedes cambiar de perfil cuando quieras desde la barra lateral.")
    keys = list(profiles.PERFILES)
    cols = st.columns(len(keys))
    for c, k in zip(cols, keys):
        P = profiles.PERFILES[k]
        with c.container(border=True):
            st.markdown(f"<div style='font-size:28px'>{P['icono']}</div><b>{P['nombre']}</b>", unsafe_allow_html=True)
            st.caption(" · ".join(P["tfs"]))
            st.markdown(f"<div class='small muted'>{P['descripcion']}</div>", unsafe_allow_html=True)
            if st.button("Elegir", key=f"ob_{k}", type="primary" if k == saved_key else "secondary",
                         width="stretch"):
                st.session_state.ob_profile = k
                st.session_state.onboarding = True
                st.session_state.ind_saved_once = False
                st.session_state.ob_step = 2
                user_menu.init_work(k, force=True)
                st.rerun()
    st.caption("Temporalidad mínima de la plataforma: 10 minutos.")
    st.stop()

# ---------------------------------------------------------------- PASO 2: configuración inicial
import pandas as pd  # noqa: E402

from core import data, user_menu  # noqa: E402
from core import indicators as IND  # noqa: E402
from core.technical import volume_profile  # noqa: E402
from core.timeframes import is_crypto, rango_velas  # noqa: E402
from core.ui import price_chart  # noqa: E402

k = st.session_state.get("ob_profile") or saved_key or profiles.DEFAULT_PERFIL
P = profiles.get(k)
user_menu.init_work(k)
st.markdown(f"### {P['icono']} {P['nombre']} · configura tus indicadores")
st.caption("Activa y ajusta tus indicadores en el panel de la izquierda (**USER › Indicadores**). El gráfico de ejemplo "
           "muestra cada cambio al instante. Pulsa **Guardar** en el panel y luego **Entrar a la plataforma**.")

SAMPLE = "BTC-USD" if k == "crypto" else "SPY"
_tf_saved = st.session_state.get("default_tf") if k == saved_key else None
_tf0 = _tf_saved if _tf_saved in P["tfs"] else P["tf"]
c1, c2, _ = st.columns([1.3, 2.2, 2], vertical_alignment="bottom")
tf = c1.segmented_control("Velas", P["tfs"], default=_tf0, key="ob_tf_sel",
                          help="Temporalidad por defecto de tus análisis. Se guarda al pulsar Guardar.") or _tf0
st.session_state.ob_tf = tf
_vista = (profiles.merge_settings(st.session_state.get("technical_settings")).get("vista") if k == saved_key else None) or {}
_r0 = rango_valido(tf, (_vista.get("rangos") or {}).get(tf))
rango = c2.segmented_control("Rango visible", RANGOS[tf], default=_r0, key=f"ob_rng_{tf}") or _r0


@st.cache_data(ttl=900, show_spinner=False)
def _sample(sym: str, tf_: str) -> pd.DataFrame:
    try:
        df = data.history_tf(sym, tf_)
        if len(df) >= 60:
            return df
    except Exception:
        pass
    return data._synthetic_tf(sym, tf_)


raw = _sample(SAMPLE, tf)
cfg_ind = user_menu.work()
bars = rango_velas(tf, rango, is_crypto(SAMPLE), len(raw))
vpi = cfg_ind["vrvp"]["in"]
vp = (volume_profile(raw.tail(bars), bins=max(4, min(300, int(IND._num(vpi.get("rows"), 24)))),
                     value_area=IND._num(vpi.get("va"), 70) / 100) if cfg_ind["vrvp"]["on"] else None)
with st.container(border=True):
    st.markdown(f"<div class='muted small'><b>{SAMPLE}</b> · gráfico de ejemplo · velas {tf} · "
                f"{len(IND.activos(cfg_ind, tf))} indicadores activos · fuente {raw.attrs.get('fuente', '')}</div>",
                unsafe_allow_html=True)
    fig = price_chart(raw, None, vp, None, bars=bars, tf=tf, crypto=is_crypto(SAMPLE),
                      settings=profiles.default_settings(k), ind=cfg_ind)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True})

ok = st.session_state.get("ind_saved_once") and not user_menu.dirty()
h1, h2 = st.columns([3, 1.2], vertical_alignment="center")
h1.caption("Configuración guardada. Ya puedes analizar con todas las herramientas de la plataforma." if ok else
           "Guarda tu configuración de indicadores (botón Guardar del panel izquierdo) para continuar.")
if h2.button("Entrar a la plataforma", type="primary", width="stretch", disabled=not ok):
    st.session_state.onboarding = False
    st.session_state.ob_step = 1
    st.session_state.pop("ob_tf", None)
    st.rerun()
