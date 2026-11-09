"""
Barra izquierda: menú USER (Indicadores, Estrategias, Watchlist, Portafolio, Alertas, Configuración, Perfil).

* Cada sección se despliega en su lugar y empuja a las demás hacia abajo (acordeón).
* Indicadores: lista de los indicadores configurados. Cada uno lleva una casilla para activarlo, su nombre
  (despliega la configuración con las pestañas de TradingView), y la ficha "i". Los que nunca se configuraron
  quedan dentro de "Otros indicadores". Guardar guarda todo; Cancelar vuelve a lo último guardado.
* Modo enfoque: con más de 10 indicadores activos y cambios sin guardar, las demás secciones se ocultan
  hasta pulsar Guardar.
* Los cambios se ven al instante en el gráfico (la pantalla lee la copia de trabajo `ind_work`).
"""
from __future__ import annotations

import json

import streamlit as st

from . import indicators as I
from . import profiles

W = "iw_"  # prefijo de las claves de los controles del panel (para poder restablecerlos)
SECCIONES = [("ind", "Indicadores", ":material/stacked_line_chart:"), ("est", "Estrategias", ":material/strategy:"),
             ("wl", "Watchlist", ":material/visibility:"), ("pf", "Portafolio", ":material/account_balance_wallet:"),
             ("al", "Alertas", ":material/notifications:"), ("cf", "Configuración", ":material/settings:"),
             ("pr", "Perfil", ":material/person:")]
_DASHES = [("solid", "───"), ("dashed", "‒ ‒ ‒"), ("dotted", "·····")]

CSS = """<style>
/* Barra lateral: barra de desplazamiento siempre visible */
[data-testid="stSidebarContent"] { scrollbar-width: thin; scrollbar-color: #484F58 transparent; }
[data-testid="stSidebarContent"]::-webkit-scrollbar { width: 8px; }
[data-testid="stSidebarContent"]::-webkit-scrollbar-thumb { background: #484F58; border-radius: 4px; }
/* Indicadores abierto: ocupa toda la columna izquierda (oculta navegación y las demás secciones de USER) */
section[data-testid="stSidebar"]:has([class*="st-key-usr_sec_ind"] > div > details[open]) [data-testid="stSidebarNav"],
section[data-testid="stSidebar"]:has([class*="st-key-usr_sec_ind"] > div > details[open]) [data-testid="stSidebarNavSeparator"],
section[data-testid="stSidebar"]:has([class*="st-key-usr_sec_ind"] > div > details[open]) [class*="st-key-usr_sec_"]:not([class*="st-key-usr_sec_ind"]) { display: none !important; }
/* …y su lista se desplaza dentro del panel, con Guardar siempre a la vista */
[class*="st-key-usr_sec_ind"] > div > details > [data-testid="stExpanderDetails"] {
  max-height: calc(100vh - 180px); overflow-y: auto; scrollbar-width: thin; scrollbar-color: #484F58 transparent; }
[class*="st-key-usr_sec_ind"] > div > details > [data-testid="stExpanderDetails"]::-webkit-scrollbar { width: 8px; }
[class*="st-key-usr_sec_ind"] > div > details > [data-testid="stExpanderDetails"]::-webkit-scrollbar-thumb { background: #484F58; border-radius: 4px; }
[data-testid="stLayoutWrapper"]:has(> .st-key-usr_ind_footer) { position: sticky; bottom: -8px; z-index: 5;
  background: #161B22; border-top: 1px solid #30363D; padding: 8px 0 6px; }
section[data-testid="stSidebar"][data-collapsed="false"] { width: 384px !important; min-width: 384px !important; max-width: 92vw !important; }
.st-key-usr_hdr > div > details > summary p { font-size: 13px; font-weight: 600; letter-spacing: .08em; }
[class*="st-key-usr_sec_"] > div > details > summary p, .st-key-usr_otros > div > details > summary p { font-size: 13px; font-weight: 600; }
.st-key-usr_hdr > div > details > [data-testid="stExpanderDetails"] { padding: 8px 6px; }
[class*="st-key-usr_sec_"] > div > details > [data-testid="stExpanderDetails"],
.st-key-usr_otros > div > details > [data-testid="stExpanderDetails"] { padding: 8px 4px; }
[class*="st-key-usr_wl_"] button { justify-content: flex-start; }
[class*="st-key-indrow_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .35rem !important; align-items: flex-start; }
[class*="st-key-indrow_"] [data-testid="stColumn"] { min-width: 0 !important; }
[class*="st-key-indrow_"] [data-testid="stCheckbox"] { padding-top: 10px; }
[class*="st-key-indrow_"] [data-testid="stExpander"] summary p { font-size: 13px; font-weight: 500; }
[class*="st-key-indrow_"] [data-testid="stPopover"] button { min-height: 38px; padding: 0 !important; width: 100%; justify-content: center; }
[class*="st-key-indrow_"] [data-testid="stPopover"] button > div { justify-content: center; width: 100%; gap: 0; }
[class*="st-key-indrow_"] [data-testid="stPopover"] button div[aria-hidden="true"] { display: none; }
[class*="st-key-indrow_"] [data-testid="stPopover"] button div { overflow: visible; min-width: 0; }
[class*="st-key-indrow_"] [data-testid="stPopover"] button p { font-size: 16px; line-height: 1; margin: 0; overflow: visible; }
[class*="st-key-indrow_"] [data-testid="stNumberInputContainer"] button { width: 20px; }
[class*="st-key-indrow_"] [data-testid="stSelectbox"] [data-baseweb="select"] > div { padding-left: 6px; }
[class*="st-key-indrow_"] [data-testid="stTab"] p { font-size: 12px; }
[class*="st-key-indrow_"] [data-baseweb="tab-list"] { gap: 10px; }
.ind-ficha dt { color: #8B949E; font-size: 11px; margin-top: 8px; }
.ind-ficha dd { margin: 2px 0 0 0; font-size: 12.5px; line-height: 1.5; }
.ind-grp { color: #8B949E; font-size: 11.5px; margin: 10px 0 2px; }
.ind-tag { color: #8B949E; font-size: 11px; }
.usr-focus { border: 1px solid #2962FF; border-radius: 6px; padding: 8px 10px; font-size: 12px; line-height: 1.5; }
</style>"""


# ---------------------------------------------------------------- copia de trabajo de los indicadores
def _saved_settings() -> dict:
    return profiles.merge_settings(st.session_state.get("technical_settings"))


def _num_norm(o):
    if isinstance(o, bool) or o is None:
        return o
    if isinstance(o, (int, float)):
        return float(o)
    if isinstance(o, dict):
        return {str(k): _num_norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_num_norm(v) for v in o]
    return o


def _canon(o) -> str:
    """JSON comparable: 2 y 2.0 cuentan igual (los campos numéricos devuelven float)."""
    return json.dumps(_num_norm(o), sort_keys=True, default=str)


def init_work(perfil: str | None = None, force: bool = False) -> None:
    """Prepara la copia de trabajo a partir de lo guardado (o de los valores del perfil si es nuevo)."""
    ss = st.session_state
    perfil = perfil or ss.get("ob_profile") or ss.get("trader_profile")
    if not force and "ind_work" in ss and ss.get("ind_perfil") == perfil:
        return
    S = _saved_settings()
    same = perfil == ss.get("trader_profile")
    base_engine = S if same else profiles.default_settings(perfil)
    cfg = I.merge_config(S.get("indicadores") if same else None, perfil, base_engine)
    ss.ind_work = cfg
    ss.ind_saved = _canon(cfg)
    ss.ind_perfil = perfil
    _clear_widgets()


def work() -> dict:
    init_work()
    return st.session_state.ind_work


def dirty() -> bool:
    return _canon(work()) != st.session_state.get("ind_saved")


def focus_mode() -> bool:
    return len(I.activos(work())) > I.MAX_SIN_ENFOQUE and dirty()


def _clear_widgets():
    for k in list(st.session_state):
        if isinstance(k, str) and k.startswith(W):
            del st.session_state[k]


def save(trader_profile: str | None = None, tf: str | None = None) -> list[str]:
    """Guarda la configuración completa de indicadores y sincroniza el motor. Devuelve errores si los hay."""
    cfg = work()
    errs = I.validar(cfg)
    if errs:
        return errs
    ss = st.session_state
    perfil = trader_profile or ss.get("ind_perfil") or ss.get("trader_profile")
    base = _saved_settings() if perfil == ss.get("trader_profile") else profiles.default_settings(perfil)
    base["vista"] = _saved_settings().get("vista") or base.get("vista")
    for it in cfg.values():  # los desactivados pasan a «Otros indicadores» (conservan su configuración)
        if not it["on"]:
            it["conf"] = False
    S = I.to_engine(cfg, base)
    profiles.save_user_view(tf=tf, settings=S, trader_profile=perfil)
    ss.ind_saved = _canon(cfg)
    ss.ind_saved_once = True
    return []


def cancel():
    init_work(force=True)


def reset_profile_defaults():
    ss = st.session_state
    perfil = ss.get("ind_perfil") or ss.get("trader_profile")
    ss.ind_work = I.default_config(perfil, profiles.default_settings(perfil))
    _clear_widgets()


# ---------------------------------------------------------------- panel de indicadores
def _is_float(f):
    return any(isinstance(v, float) and not float(v).is_integer() for v in (f.get("d"), f.get("st"), f.get("mn")))


def _field(it: dict, iid: str, f: dict, key_prefix: str):
    k, cur = f["k"], it["in"].get(f["k"], f["d"])
    key = f"{W}{key_prefix}{iid}_{k}"
    if f["t"] == "num":
        if _is_float(f):
            v = st.number_input(f["l"], float(f["mn"]), float(f["mx"]), float(I._num(cur, f["d"])), float(f["st"]),
                                key=key, format="%.3g")
        else:
            v = st.number_input(f["l"], int(f["mn"]), int(f["mx"]), int(I._num(cur, f["d"])), int(f["st"] or 1), key=key)
        it["in"][k] = v
    elif f["t"] == "sel":
        opts = [o[0] for o in f["o"]]
        names = dict((o[0], o[1]) for o in f["o"])
        v = st.selectbox(f["l"], opts, index=opts.index(cur) if cur in opts else 0, key=key,
                         format_func=lambda o: names.get(o, o))
        it["in"][k] = v
    else:
        it["in"][k] = st.checkbox(f["l"], bool(cur), key=key)


def _ficha(c: dict) -> str:
    rows = "".join(f"<dt>{lbl}</dt><dd>{c['info'].get(k, '')}</dd>" for k, lbl in I.FICHA)
    nota = ("<p class='ind-tag'>Este indicador se configura y guarda desde ya; su dibujo en el gráfico llega en la "
            "próxima entrega.</p>" if c["id"] in I.SIN_GRAFICO else "")
    return f"<b>{c['name']}</b><dl class='ind-ficha'>{rows}</dl>{nota}"


def _item(c: dict, cfg: dict):
    iid, it = c["id"], cfg[c["id"]]
    with st.container(key=f"indrow_{iid}"):
        a, b, d = st.columns([0.08, 0.77, 0.15])
        on = a.checkbox(f"Activar {c['name']}", it["on"], key=f"{W}on_{iid}", label_visibility="collapsed")
        if on != it["on"]:
            it["on"] = on
            it["conf"] = it["conf"] or on
        with d.popover("ⓘ", width="stretch", help=f"Qué es y cómo usar {c['name']}"):
            st.markdown(_ficha(c), unsafe_allow_html=True)
        with b.expander(c["name"] + (" · pronto en el gráfico" if iid in I.SIN_GRAFICO else "")):
            before = _canon(it)
            t1, t2, t3 = st.tabs(["Entradas", "Estilo", "Visibilidad"])
            with t1:
                for f in c["inputs"]:
                    _field(it, iid, f, "in_")
            with t2:
                for p in c["plots"]:
                    s = it["st"][p["k"]]
                    r1, r2 = st.columns([3, 1], vertical_alignment="center")
                    s["v"] = r1.checkbox(p["l"], bool(s["v"]), key=f"{W}v_{iid}_{p['k']}")
                    s["c"] = r2.color_picker(f"Color {p['l']}", s["c"], key=f"{W}c_{iid}_{p['k']}",
                                             label_visibility="collapsed")
                    q2, q3, q4 = st.columns([1.15, 0.85, 1])
                    s["o"] = q2.number_input("Opac. %", 0, 100, int(s["o"]), 5, key=f"{W}o_{iid}_{p['k']}",
                                             help="Opacidad de la línea (100 = sólida)")
                    s["w"] = q3.selectbox("Grosor", [1, 2, 3, 4], index=max(0, min(3, int(s["w"]) - 1)),
                                          key=f"{W}w_{iid}_{p['k']}", help="Grosor en píxeles")
                    dk = [x[0] for x in _DASHES]
                    s["s"] = q4.selectbox("Línea", dk, index=dk.index(s["s"]) if s["s"] in dk else 0,
                                          key=f"{W}s_{iid}_{p['k']}", format_func=lambda v: dict(_DASHES)[v])
                for f in c.get("extra", []):
                    _field(it, iid, f, "ex_")
            with t3:
                st.caption("Temporalidades en las que se muestra")
                cols = st.columns(4)
                for i, tf in enumerate(I.TFS):
                    it["vis"][tf] = cols[i % 4].checkbox(tf, bool(it["vis"].get(tf, True)), key=f"{W}vis_{iid}_{tf}")
            if it["conf"] and st.button("Mover a «Otros indicadores»", key=f"{W}mv_{iid}", type="tertiary"):
                it["conf"], it["on"] = False, False
                st.rerun()
            if _canon(it) != before:
                it["conf"] = True  # se configuró: queda en la lista principal


def indicadores_panel(con_guardar: bool = True):
    cfg = work()
    for c in I.CATALOGO:
        if cfg[c["id"]]["conf"]:
            _item(c, cfg)
    otros = [c for c in I.CATALOGO if not cfg[c["id"]]["conf"]]
    # La etiqueta no lleva el número: cambiarla reiniciaría el desplegable. El número se muestra con CSS.
    st.markdown(f"<style>.st-key-usr_otros > div > details > summary p::after{{content:' · {len(otros)}'}}</style>", unsafe_allow_html=True)
    with st.expander("Otros indicadores", key="usr_otros", on_change="rerun") as exp:
        if exp.open:  # se construye solo al abrir (son ~28 indicadores con sus controles)
            for g, gname in I.GRUPOS:
                items = [c for c in otros if c["g"] == g]
                if items:
                    st.markdown(f"<div class='ind-grp'>{gname}</div>", unsafe_allow_html=True)
                    for c in items:
                        _item(c, cfg)
    if con_guardar:
        _footer()


def _footer():
    with st.container(key="usr_ind_footer"):
        errs = I.validar(work())
        for e in errs:
            st.warning(e)
        d = dirty()
        st.caption("Cambios sin guardar" if d else "Todo guardado")
        f1, f2 = st.columns(2)
        if f1.button("Cancelar", key="usr_ind_cancel", width="stretch", disabled=not d):
            cancel()
            st.rerun()
        if f2.button("Guardar", key="usr_ind_save", type="primary", width="stretch", disabled=bool(errs)):
            e2 = save(tf=st.session_state.get("ob_tf"))
            if e2:
                st.warning(" ".join(e2))
            else:
                st.toast("Configuración de indicadores guardada", icon="✅")
                st.session_state.ind_rev = st.session_state.get("ind_rev", 0) + 1  # cierra el panel de indicadores
                st.rerun()
        with st.popover("Valores por defecto", width="stretch"):
            st.caption("Vuelve a los indicadores y parámetros sugeridos para tu perfil. No se guarda hasta pulsar Guardar.")
            if st.button("Restablecer configuración del perfil", key="usr_ind_reset", width="stretch"):
                reset_profile_defaults()
                st.rerun()


# ---------------------------------------------------------------- menú USER
def _snapshot(cfg: dict) -> str:
    return _canon([work(), cfg])


def render(profile: dict, admin: bool, cfg: dict, onboarding: bool = False, extra_admin=None):
    """Dibuja el menú USER en la barra lateral. `extra_admin` dibuja los ajustes de IA y datos (solo admin)."""
    st.markdown(CSS, unsafe_allow_html=True)
    init_work()
    _menu(profile, admin, cfg, onboarding, extra_admin)


@st.fragment
def _menu(profile: dict, admin: bool, cfg: dict, onboarding: bool, extra_admin):
    """Fragmento: abrir y cerrar secciones no recarga la página ni el gráfico. Abrir/cerrar los desplegables
    ocurre en el navegador; solo si cambia un valor (indicadores o configuración) se recarga la app para
    redibujar el gráfico."""
    init_work()
    before = _snapshot(cfg)
    with st.expander("USER", expanded=True, key="usr_hdr"):
        foc = focus_mode()
        if foc:
            st.markdown(f"<div class='usr-focus'>Tienes <b>{len(I.activos(work()))}</b> indicadores activos. El resto del "
                        "menú se oculta hasta que guardes la configuración.</div>", unsafe_allow_html=True)
        for k, label, icon in SECCIONES:
            if foc and k != "ind":
                continue
            if onboarding and k not in ("ind", "pr"):
                continue
            extra = f" · {len(I.activos(work()))} activos" if k == "ind" else ""
            with st.expander(f"{label}{extra}", expanded=(k == "ind" and (onboarding or foc)), icon=icon,
                             key=f"usr_sec_{k}" + (f"_r{st.session_state.get('ind_rev', 0)}" if k == "ind" else "")):
                if k == "ind":
                    indicadores_panel(con_guardar=True)
                elif k == "est":
                    _estrategias()
                elif k == "wl":
                    _watchlist()
                elif k == "pf":
                    st.caption("Cartera simulada: registra operaciones y compara el pronóstico inicial con el actualizado. "
                               "Disponible en la fase 5.")
                elif k == "al":
                    st.caption("Alertas por correo electrónico (precio, señal, entrada, stop y objetivos) con vencimiento. "
                               "Disponible en la fase 6.")
                elif k == "cf":
                    _configuracion(cfg, admin, extra_admin)
                elif k == "pr":
                    _perfil(profile, admin)
    if _snapshot(cfg) != before:
        st.rerun(scope="app")  # cambió un valor: redibujar el gráfico con la nueva configuración


def _estrategias():
    st.caption("Estrategias que el motor evaluará en cada análisis y en el escáner. Las reglas y su backtest llegan "
               "en una próxima entrega; por ahora el motor usa el puntaje técnico y la probabilidad histórica.")
    for k, n, dsc in (("pullback", "Pullback a la media en tendencia", "Retroceso a la EMA intermedia con ADX > 25"),
                      ("breakout", "Ruptura con volumen", "Cierre sobre resistencia con volumen relativo > 1,5"),
                      ("reversal", "Reversión en sobreventa", "RSI < 30 con divergencia alcista en soporte"),
                      ("trend", "Seguimiento de tendencia", "Supertrend alcista y precio sobre la MA de 200")):
        st.checkbox(n, value=k in ("pullback", "breakout"), key=f"usr_est_{k}", help=dsc, disabled=True)


def _watchlist():
    from . import store
    wl = store.watchlist()
    if not wl:
        st.caption("Tu watchlist está vacía. Agrega activos desde el escáner o el análisis.")
    for t in list(wl)[:12]:
        if st.button(t, key=f"usr_wl_{t}", type="tertiary", icon=":material/show_chart:"):
            st.session_state.ticker = t
            st.switch_page("views/analisis.py")
    st.page_link("views/watchlist.py", label=f"Abrir watchlist completa ({len(wl)})", icon=":material/open_in_new:")


def _configuracion(cfg: dict, admin: bool, extra_admin):
    cfg["capital"] = st.number_input("Capital de la cuenta (USD)", 100.0, 1e8, float(cfg["capital"]), 500.0, format="%.2f")
    cfg["riesgo_pct"] = st.number_input("Riesgo por operación (%)", 0.1, 5.0, float(cfg["riesgo_pct"]), 0.1, format="%.2f")
    c1, c2 = st.columns(2)
    cfg["tp_atr"] = c1.number_input("Objetivo (×ATR)", 1.0, 8.0, float(cfg["tp_atr"]), 0.5, format="%.2f")
    cfg["sl_atr"] = c2.number_input("Stop (×ATR)", 0.5, 5.0, float(cfg["sl_atr"]), 0.25, format="%.2f")
    cfg["horizonte"] = st.number_input("Horizonte en 1D (sesiones)", 24, 50, min(50, max(24, int(cfg["horizonte"]))), 1,
                                       help="Velas diarias (1D): mediano-largo plazo, 1 a 3 meses (24–50 sesiones). "
                                            "Las demás temporalidades usan su horizonte propio.")
    st.caption("El escáner usa velas 1D. Temporalidad mínima de la app: 10m.")
    if admin and extra_admin:
        st.markdown("**IA y datos (administrador)**")
        extra_admin()


def _perfil(profile: dict, admin: bool):
    from . import auth
    ss = st.session_state
    P = profiles.get((ss.get("ob_profile") if ss.get("onboarding") else None) or ss.get("trader_profile"))
    st.markdown(f"<b>{profile.get('name') or profile['email']}</b><br><span class='muted'>{profile['email']} · "
                f"{'Administrador' if admin else 'Invitado'}</span>", unsafe_allow_html=True)
    st.caption(f"Perfil de trader: {P['icono']} {P['nombre']} · {' / '.join(P['tfs'])}")
    if st.button("Cambiar perfil de trader", key="usr_chg_prof", icon=":material/tune:", width="stretch"):
        ss.onboarding = True
        ss.ob_step = 1
        st.rerun()
    if profile.get("email") != "owner@local" and st.button("Cerrar sesión", key="usr_logout", width="stretch"):
        auth.logout()
