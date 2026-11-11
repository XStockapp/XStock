import html
import math

import pandas as pd
import streamlit as st

from core import ai, db, store
from core.analysis import full_analysis
from core.fundamental import BLOCK_W
import json

from core import profiles
from core.levels import MODOS
from core.timeframes import RANGO_NOMBRE, RANGOS, is_crypto, rango_valido, rango_velas, unidad
from core.ui import (AMBER, show_chart, DISCLAIMER, GREEN, MUTED, NEUTRAL, RED, SIGNAL_COLORS, color_for, equity_chart, is_mobile,
                     pill, price_chart)

cfg = st.session_state.cfg
E = html.escape
MOBILE = is_mobile()


@st.cache_data(ttl=900, show_spinner=False)
def _run(ticker, tp, sl, hz, acct, risk, av, prov, tf, settings_json):
    return full_analysis(ticker, tp, sl, hz, acct, risk, av or None, prov, tf, json.loads(settings_json))


PKEY = st.session_state.get("trader_profile")
PERF = profiles.get(PKEY)
SETTINGS = profiles.merge_settings(st.session_state.get("technical_settings"))
saved_range = profiles.saved_range


def ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def money(x):
    return f"${float(x):,.2f}" if ok(x) else "—"


def fmt(v, kind):
    if not ok(v):
        return "—"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "big":
        return f"${v / 1e9:,.1f} B" if v >= 1e9 else f"${v / 1e6:,.0f} M"
    if kind == "money":
        return f"${v:,.2f}"
    return f"{v:,.2f}"


def pfmt(v):
    return f"{float(v) * 100:.0f}%" if ok(v) else "—"


def sfmt(v):
    return f"{float(v):+.0f}" if ok(v) else "—"


def col_score(v, g=15, b=-15):
    return MUTED if not ok(v) else (GREEN if v > g else RED if v < b else NEUTRAL)


# ---------------------------------------------------------------- barra superior (estilo terminal)
def _mercado(crypto: bool) -> tuple[str, str]:
    """Estado del mercado de EE. UU. por la hora de Nueva York (sin feriados)."""
    if crypto:
        return "CRIPTO 24/7", GREEN
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    mins = now.hour * 60 + now.minute
    if now.weekday() < 5 and 570 <= mins < 960:
        return "MERCADO ABIERTO", GREEN
    if now.weekday() < 5 and 240 <= mins < 570:
        return "PREMERCADO", AMBER
    return "MERCADO CERRADO", MUTED


c1, ctf, crg, cst = st.columns([1.9, 1.6, 2.2, 3.1], vertical_alignment="bottom")
ticker = c1.text_input("Símbolo", st.session_state.get("ticker", "AAPL"),
                       placeholder="Acción o cripto, p. ej. NVDA o BTC-USD").strip().upper()
_tfs = PERF["tfs"]
_tf_def = st.session_state.get("default_tf") if st.session_state.get("default_tf") in _tfs else PERF["tf"]
TF = ctf.segmented_control("Velas", _tfs, default=_tf_def, key="tf_sel") or _tf_def
_rk = RANGOS[TF]
_rng_def = rango_valido(TF, saved_range(SETTINGS, TF))
rng = crg.segmented_control("Rango visible", _rk, default=_rng_def, key=f"rng_{TF}",
                            format_func=lambda r: r) or _rng_def
if TF != st.session_state.get("default_tf") or rng != _rng_def:
    try:
        profiles.save_user_view(TF, rng, SETTINGS)
        SETTINGS = st.session_state.technical_settings
    except Exception as _e:  # no bloquear el análisis si falla el guardado
        st.toast(f"No se pudo guardar la vista: {_e}")
if not ticker:
    st.stop()
st.session_state.ticker = ticker

_prof = st.session_state.get("profile") or {}
_is_admin = _prof.get("role") == "admin"
_gem_key = store.secret("GEMINI_API_KEY")
_cl_key = cfg["anthropic_key"]
_mk, _mkc = _mercado(is_crypto(ticker))
_ia = (cfg.get("modelo", "Claude").split(" (")[0] if (_is_admin and _cl_key) else
       ("Gemini" if _gem_key else "Reglas"))
cst.markdown(
    f"<div class='x-chips'><span class='x-chip'><i style='background:{_mkc}'></i>{_mk}</span>"
    f"<span class='x-chip'>IA · {E(_ia)}</span>"
    f"<span class='x-chip'>{E((_prof.get('name') or _prof.get('email') or 'Usuario').split('@')[0])}</span></div>",
    unsafe_allow_html=True)

try:
    with st.spinner(f"Analizando {ticker}…"):
        A = _run(ticker, cfg["tp_atr"], cfg["sl_atr"], int(cfg["horizonte"]) if TF == "1D" else None,
                 cfg["capital"], cfg["riesgo_pct"], cfg["alphavantage_key"],
                 "alphavantage" if cfg.get("proveedor", "").startswith("Alpha Vantage") else "yahoo",
                 TF, json.dumps(profiles.engine_settings(SETTINGS), sort_keys=True))
except Exception as e:
    st.error(f"No se pudo analizar {ticker}: {e}")
    st.stop()

d, tech, prob, m, fs = A["df"], A["tech"], A["prob"], A["metrics"], A["fscore"]
_seen = st.session_state.setdefault("_logged_analysis", set())
if _prof and ticker not in _seen:
    db.log_event(_prof["email"], "analysis", ticker)
    _seen.add(ticker)
last, prev = d.iloc[-1], d.iloc[-2]
chg = last["Close"] / prev["Close"] - 1
hi52, lo52 = float(d["High"].tail(252).max()), float(d["Low"].tail(252).min())

# ---------------------------------------------------------------- encabezado del símbolo + modo de entrada
_cc = GREEN if chg >= 0 else RED
st.markdown(
    f"<div class='qhead'><span class='qt'>{E(ticker)}</span>"
    f"<span class='qpx'>${last['Close']:,.2f}</span>"
    f"<span class='x-delta' style='color:{_cc};border-color:{_cc}55;background:{_cc}14'>{chg * 100:+.2f}% "
    f"({'+' if chg >= 0 else '−'}${abs(last['Close'] - prev['Close']):,.2f})</span>"
    f"<span class='muted x-meta'>{E(m.get('Nombre', ''))} · rango 52s <span class='num'>{money(lo52)} – {money(hi52)}</span>"
    f" · perfil {E(PERF['nombre'])} ({E(TF)}){' · ' + E(A.get('fuente')) if A.get('fuente') else ''}"
    f" · cierre {d.index[-1]:%d-%b %H:%M}</span></div>", unsafe_allow_html=True)
_rec = A["plan"]["modo_recomendado"]
_opts = {f"Auto · {MODOS[_rec].replace('Entrada ', '')}": "auto", "A mercado": "market", "Proyectada (Limit)": "limit"}
m1, m2, m3 = st.columns([4.2, 1, 1.25], vertical_alignment="bottom")
_mode_lbl = m1.segmented_control("Modo de entrada", list(_opts), default=list(_opts)[0], key=f"emode_{ticker}",
                                 label_visibility="collapsed",
                                 help="Auto elige la entrada proyectada (Limit) en el soporte más cercano cuando el "
                                      "impulso de corto plazo va en contra (MACD decreciente, pérdida de la EMA9, RSI "
                                      "agotado o precio extendido); si no, entrada a mercado.") or list(_opts)[0]
plan = A["planes"][_opts[_mode_lbl]]
m2.button("Analizar", type="primary", width="stretch")
times = ai.time_estimates(plan, prob, cfg["tp_atr"])
if m3.button("A watchlist", icon=":material/star:", width="stretch"):
    store.add_to_watchlist([{"Ticker": ticker, "Precio": float(last["Close"]), "Señal": None,
                             "Prob. ganancia": prob["probabilidad"], "Entrada": plan["entrada"], "Stop": plan["stop"],
                             "Objetivo 1": plan["objetivo_1"], "Objetivo 2": plan["objetivo_2"]}])
    st.toast(f"{ticker} agregado a la watchlist", icon="⭐")

ts, fsc, comb = tech["score"], fs["score"], A["combinado"]
p, ev = prob["probabilidad"], prob["valor_esperado_R"]
be = 1 / (1 + cfg["tp_atr"] / cfg["sl_atr"])
pio = A["piotroski"]
vpa = A["vprofile"] or {}
risk_pct = abs(plan["entrada"] - plan["stop"]) / plan["entrada"]
_wait = plan["estado_tipo"] == "esperar"

from core import indicators as IND  # noqa: E402
from core import tv, user_menu  # noqa: E402

IND_CFG = user_menu.work()  # copia de trabajo del panel USER › Indicadores
_act = IND.activos(IND_CFG, TF)

# franja de configuración
def _g(*parts):  # grupo de la franja: etiqueta y valores no se separan al saltar de línea
    return "<span class='x-g'>" + "".join(parts) + "</span>"


_pc = GREEN if p > be + 0.05 else (RED if p < be else NEUTRAL)
_ec = GREEN if ev > 0.1 else (RED if ev < 0 else NEUTRAL)
st.markdown(
    "<div class='x-strip'>"
    + _g("<span class='x-k'>Configuración</span>", f"<b style='color:{AMBER if _wait else GREEN}'>{E(plan['estado'])}</b>")
    + _g("<span class='x-k'>Zona clave</span>", f"<b class='num'>{money(plan['entrada'])}</b>",
         f"<span class='muted'>{E(plan['tipo_entrada'])}</span>")
    + _g("<span class='x-k'>Sesgo cuant.</span>", f"<b class='num' style='color:{_pc}'>{p * 100:.1f}%</b>",
         f"<b class='num' style='color:{_ec}'>VE {ev:+.2f} R</b>")
    + _g("<span class='x-k'>R/B</span>", f"<b class='num'>1:{plan['rr_2']:.1f}</b>")
    + _g("<span class='x-k'>Riesgo máx.</span>", f"<b class='num' style='color:{RED}'>−{money(plan['riesgo_monetario'])}</b>")
    + _g("<span class='x-k'>Indicadores</span>", f"<b>{E(user_menu.active())}</b>",
         f"<span class='muted'>({len(_act)} activos)</span>")
    + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- gráfico + plan de ejecución
bars = rango_velas(TF, rng, is_crypto(ticker), len(d))
akey = f"ai_{ticker}_{d.index[-1]:%Y%m%d}_{cfg['tp_atr']}_{cfg['sl_atr']}_{plan['modo_entrada']}_{TF}"
V = st.session_state.get(akey)
if MOBILE:
    left, right = st.container(), st.container()
else:
    left, right = st.columns([3.15, 1.2], gap="small")

with left:
    with st.container(border=True, key="x_chartcard"):
        g1, g2 = st.columns([2.6, 2], vertical_alignment="center")
        g1.markdown(f"<div class='x-tb'><b>{E(ticker)}</b><span class='muted'>· {E(TF)} · "
                    f"{E(RANGO_NOMBRE.get(rng, rng))}</span><span class='x-chip'>Indicadores ({len(_act)} activos)</span>"
                    "</div>", unsafe_allow_html=True)
        VISTAS = {"Gráfico avanzado": "tv", "XStock": "xs"}
        _vista = g2.segmented_control("Vista del gráfico", list(VISTAS), default="Gráfico avanzado", key="x_vista",
                                      label_visibility="collapsed",
                                      help="Gráfico avanzado: TradingView para dibujar, marcar y sumar sus indicadores "
                                           "(solo visual). XStock: tus indicadores, el plan y la proyección con los "
                                           "que se calcula el análisis.") or "Gráfico avanzado"
        if VISTAS[_vista] == "tv":
            tv.show(ticker, TF, height=560 if not MOBILE else 420)
            st.caption("TradingView es solo visual: dibuja y marca libremente. El análisis, el plan y la probabilidad "
                       "se calculan con tus indicadores y estrategia de XStock (vista «XStock»)."
                       + (f" Velas de {TF} no existen en TradingView: se muestra {tv.SIN_EQUIVALENTE[TF]}."
                          if TF in tv.SIN_EQUIVALENTE else ""))
        else:
            from core.technical import volume_profile
            _pv = IND_CFG["vrvp"]["in"]
            _rows = int(IND._num(_pv.get("rows"), 24))
            if _pv.get("layout") == "Ticks por fila":  # tamaño de fila en ticks de $0.01 → cantidad de filas
                _span = float(d.tail(bars)["High"].max() - d.tail(bars)["Low"].min())
                _rows = int(max(4, min(300, round(_span / (_rows * 0.01)))))
            _vp = (volume_profile(d.tail(bars), bins=max(4, min(300, _rows)), value_area=IND._num(_pv.get("va"), 70) / 100)
                   if "vrvp" in _act else None)
            _fig = price_chart(d, plan, _vp, V, bars=bars, times=times, mobile=MOBILE, tf=TF, crypto=is_crypto(ticker),
                               settings=SETTINGS, ind=IND_CFG)
            show_chart(_fig, f"{ticker}|{TF}|{rng}", MOBILE)


def row(label, val, color="#E6EDF3", sub=""):
    return (f"<div class='mp-i'><div class='mp-r'><span>{label}</span><b style='color:{color}'>{val}</b></div>"
            + (f"<div class='mp-s'>{sub}</div>" if sub else "") + "</div>")


def frow(i, c):
    return (f"<div class='fr'><span class='dot' style='background:{c}'></span><span class='fm'>{E(i['metrica'])}</span>"
            f"<span class='fv'>{E(i['valor'])}</span><div class='fl'>{E(i['lectura'])}"
            f"<span class='fb'> · {E(i['bloque'])}</span></div></div>")


items = sorted(fs.get("items", []), key=lambda i: -i["score"])
good = [i for i in items if i["score"] >= 35]
bad = [i for i in items if i["score"] <= -35][::-1]
neu = [i for i in items if -35 < i["score"] < 35]

with right:
    _lado = "COMPRA" if "COMPRA" in plan["direccion"] else "VENTA"
    _orden = f"{_lado} {'LIMIT' if plan['modo_entrada'] == 'limit' else 'MERCADO'}"
    _oc = GREEN if _lado == "COMPRA" else RED
    _sc = AMBER if _wait else GREEN

    def lvl(label, val, color, sub):
        return (f"<div class='x-lv'><span>{label}</span><b class='num' style='color:{color}'>{val}</b>"
                f"<span class='x-lvs'>{sub}</span></div>")

    t1_ = f" · ~{unidad(TF, times['sesiones_a_objetivo_1'])}" if times else ""
    t2_ = f" · ~{unidad(TF, times['sesiones_a_objetivo_2'])}" if times else ""
    st.markdown(
        f"<div class='x-plan'><div class='x-ph'><span>Plan de ejecución</span>"
        f"<span class='x-badge' style='color:{_oc};border-color:{_oc}66;background:{_oc}14'>{_orden}</span></div>"
        f"<div class='x-state' style='border-color:{_sc}66'><b style='color:{_sc}'>{E(plan['estado'])}</b>"
        + (f"<div class='mp-s'>{E(' · '.join(plan['motivos_impulso']))}</div>" if plan["motivos_impulso"] else
           "<div class='mp-s'>Impulso de corto plazo a favor de la señal de fondo.</div>")
        + f"<div class='mp-s'>{E(plan['marco_corto'])}</div></div>"
        f"<div class='x-entry'><div><div class='x-k'>{'Entrada proyectada' if plan['modo_entrada'] == 'limit' else 'Entrada a mercado'}</div>"
        f"<div class='x-big num'>{money(plan['entrada'])}</div><div class='mp-s'>{E(plan['tipo_entrada'])}</div></div>"
        f"<div class='x-lvls'>"
        + lvl("Stop loss", money(plan["stop"]), RED, f"−{risk_pct * 100:.1f}%")
        + lvl("TP1", money(plan["objetivo_1"]), GREEN, f"R/B {plan['rr_1']:.1f}{t1_}")
        + lvl("TP2", money(plan["objetivo_2"]), GREEN, f"R/B {plan['rr_2']:.1f}{t2_}")
        + "</div></div>"
        f"<div class='x-size'><span>Tamaño sugerido <b class='num'>{plan['acciones']} acc.</b></span>"
        f"<span>Riesgo <b class='num' style='color:{RED}'>−{money(plan['riesgo_monetario'])}</b></span></div>"
        + ("" if plan["modo_entrada"] == "limit" else
           f"<div class='mp-s'>Alternativa Limit: {money(plan['entrada_proyectada'])} en {E(plan['referencia_proyectada'])}</div>")
        + "</div>", unsafe_allow_html=True)
    if st.button("Registrar en portafolio", icon=":material/add_task:", type="primary", width="stretch",
                 key="x_reg", help="Guarda la operación (entrada, stop, TP1, TP2 y tamaño) en tu portafolio de práctica. "
                                   "No envía órdenes reales."):
        from core import portfolio
        portfolio.registrar(ticker, plan, TF, float(last["Close"]))
        st.toast(f"{ticker} registrado en el portafolio simulado", icon="✅")
        st.rerun()  # la barra lateral (USER › Portafolio) se dibuja antes que esta página
    if st.button("Añadir a watchlist", icon=":material/notifications:", width="stretch", key="x_wl2"):
        store.add_to_watchlist([{"Ticker": ticker, "Precio": float(last["Close"]), "Señal": None,
                                 "Prob. ganancia": prob["probabilidad"], "Entrada": plan["entrada"], "Stop": plan["stop"],
                                 "Objetivo 1": plan["objetivo_1"], "Objetivo 2": plan["objetivo_2"]}])
        st.toast(f"{ticker} agregado a la watchlist", icon="⭐")

    with st.expander(f"Score multivariable · {comb:+.0f}", expanded=False):
        st.markdown(
            "<div class='mp' style='border:none;padding:0;background:transparent'>"
            + row("Score técnico", f"{ts:+.0f}", col_score(ts))
            + row("Score fundamental", "—" if fsc is None else f"{fsc:+.0f}", col_score(fsc))
            + row("Score combinado", f"{comb:+.0f}", col_score(comb), "60% técnico · 40% fundamental")
            + row("Prob. de ganancia", f"{p * 100:.1f}%", GREEN if p > be + 0.05 else (RED if p < be else NEUTRAL),
                  f"{prob['casos_similares']} casos · equilibrio {be * 100:.0f}%")
            + row("Valor esperado", f"{ev:+.2f} R", GREEN if ev > 0.1 else (RED if ev < 0 else NEUTRAL))
            + row("Piotroski", f"{pio['score']}/{pio['max']}" if pio else "—",
                  (GREEN if pio["score"] >= 7 else RED if pio["score"] <= 3 else NEUTRAL) if pio else MUTED)
            + "<div class='mp-h'>Niveles</div>"
            + row("POC (180d)", money(vpa.get("poc")), AMBER)
            + row("Área de valor", f"{money(vpa.get('val'))} – {money(vpa.get('vah'))}")
            + (row("Soporte cercano", money(plan["soportes"][0][0]), GREEN) if plan["soportes"] else "")
            + (row("Resistencia cercana", money(plan["resistencias"][0][0]), RED) if plan["resistencias"] else "")
            + row("ATR (14)", f"{money(plan['atr'])} · {plan['atr'] / last['Close'] * 100:.1f}%")
            + "</div>", unsafe_allow_html=True)
    with st.expander(f"Métricas atractivas · {len(good)}", expanded=False):
        st.markdown("".join(frow(i, GREEN) for i in good) or "<div class='muted small'>Ninguna destacada.</div>",
                    unsafe_allow_html=True)
    with st.expander(f"Factores de riesgo y valuación · {len(bad)}", expanded=False):
        st.markdown("".join(frow(i, RED) for i in bad) or "<div class='muted small'>Ninguno destacado.</div>",
                    unsafe_allow_html=True)
    with st.expander(f"Métricas neutrales · {len(neu)}", expanded=False):
        st.markdown("".join(frow(i, NEUTRAL) for i in neu) or "<div class='muted small'>Sin datos.</div>",
                    unsafe_allow_html=True)
        bl = fs.get("bloques", {})
        st.markdown("<div class='sec2'>Puntaje por bloque (peso)</div>" + "".join(
            f"<div class='mp-r'><span>{E(b)} <span class='muted'>×{BLOCK_W[b]}</span></span>"
            f"<b style='color:{col_score(v['score'])}'>{sfmt(v['score'])}</b></div>"
            for b, v in bl.items()), unsafe_allow_html=True)

# ---------------------------------------------------------------- informe del analista (IA)
with left:
    with st.container(border=True, key="x_ai"):
        h1, h2 = st.columns([1.6, 2], vertical_alignment="center")
        h1.markdown("<div class='x-ph' style='margin:0'><span>Informe del analista (IA)</span></div>",
                    unsafe_allow_html=True)
        b1, b2, b3 = h2.columns(3)
        go_claude = b1.button("Claude", icon=":material/auto_awesome:", type="primary" if _is_admin else "secondary",
                              width="stretch", disabled=not (_is_admin and _cl_key),
                              help=("Informe con Claude (Anthropic)" if _is_admin else
                                    "Disponible solo para el administrador") if _cl_key else "Falta ANTHROPIC_API_KEY")
        go_gemini = b2.button("Gemini", icon=":material/bolt:", type="primary" if not _is_admin else "secondary",
                              width="stretch", disabled=not _gem_key,
                              help="Informe con Gemini Flash (Google, plan gratuito)" if _gem_key else "Falta GEMINI_API_KEY")
        go_rules = b3.button("Sin IA", icon=":material/calculate:", width="stretch",
                             help="Síntesis cuantitativa por reglas (no usa IA)")
        go = go_claude or go_gemini or go_rules
        engine = "claude" if go_claude else ("gemini" if go_gemini else "reglas")
        payload = ai.build_payload(ticker, tech, m, fs, pio, prob, A["bt"], plan, A["news"], A.get("finviz"),
                                   A.get("finviz_items"), A.get("vprofile"), cfg["tp_atr"],
                                   {"max_52s": hi52, "min_52s": lo52,
                                    "ret_3m": float(last["Close"] / d["Close"].iloc[-64] - 1),
                                    "ret_12m": float(last["Close"] / d["Close"].iloc[-253] - 1) if len(d) > 253 else None})
        if go:
            try:
                with st.spinner("Generando el informe del analista…"):
                    if engine == "claude":
                        V = ai.analyze(payload, cfg["anthropic_key"], ai.MODELOS[cfg["modelo"]])
                    elif engine == "gemini":
                        V = ai.analyze_gemini(payload, _gem_key, store.secret("GEMINI_MODEL") or None)
                    else:
                        V = ai.rule_based(payload)
                if engine != "reglas" and _prof:
                    db.log_event(_prof["email"], "ai_report", f"{ticker} · {engine}")
            except Exception as e:
                st.error(f"Error con la IA: {e}. Se muestra la síntesis por reglas.")
                V = ai.rule_based(payload)
            st.session_state[akey] = V
            st.rerun()
        if V:
            col = SIGNAL_COLORS.get(V.get("veredicto"), NEUTRAL)
            pa = V.get("probabilidad_ajustada")
            st.markdown(
                f"<div class='rep'>{pill(E(str(V.get('veredicto', ''))), col)} "
                f"{pill('Confianza ' + str(V.get('confianza', '—')) + '%', col)} "
                f"{pill('Prob. ajustada ' + (f'{float(pa) * 100:.0f}%' if ok(pa) else '—'), col)} "
                f"<span class='muted small'>&nbsp;{E(V.get('_modelo', ''))}</span>"
                f"<p class='lead'>{E(V.get('resumen_ejecutivo') or V.get('tesis', ''))}</p></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='muted small'>Elige un motor para obtener el informe: el porqué del pronóstico técnico "
                        "y fundamental, proyecciones a corto, mediano y largo plazo, toma de ganancias y qué cambios "
                        "alterarían la tesis. Mientras tanto, las pestañas muestran los datos del motor.</div>",
                        unsafe_allow_html=True)
        tt, tf_, te, temp = st.tabs([f"Técnico  {ts:+.0f}", "Fundamental" + ("" if fsc is None else f"  {fsc:+.0f}"),
                                     "Estrategia", f"Empírica  {p * 100:.0f}%"])
        with tt:
            from core import didactic as DD
            if V:
                st.markdown(f"<div class='rep-b'><b>Lectura del analista</b><br>{E(V.get('lectura_tecnica', ''))}</div>",
                            unsafe_allow_html=True)
            sig = pd.DataFrame(tech["señales"])
            sig["Aporte"] = sig["Señal"] * sig["Peso"]
            sig = sig.reindex(sig["Aporte"].abs().sort_values(ascending=False).index)
            st.markdown("<div class='dd-intro'>Cada tarjeta muestra el indicador sobre el precio simplificado o en su "
                        "panel, cómo lo lee el motor y cuánto aporta al score técnico (ordenadas por peso en la "
                        "decisión).</div>", unsafe_allow_html=True)

            def _cards(rows_, base=0):
                for k0 in range(0, len(rows_), 3):
                    cols_ = st.columns(3, gap="small")
                    for j_, (col_, (_, r_)) in enumerate(zip(cols_, rows_.iloc[k0:k0 + 3].iterrows())):
                        with col_.container(border=True, key=f"dd_{base + k0 + j_}"):
                            st.markdown(DD.card_head(r_["Indicador"], r_["Señal"], r_["Aporte"]), unsafe_allow_html=True)
                            fg = DD.mini(d, r_["Indicador"])
                            if fg is not None:
                                st.plotly_chart(fg, width="stretch", config={"displayModeBar": False},
                                                key=f"ddc_{base + k0 + j_}")
                            st.markdown(f"<div class='dd-l'>{E(r_['Lectura'])}</div>", unsafe_allow_html=True)

            _cards(sig.head(6))
            if len(sig) > 6:
                with st.expander(f"Ver las otras {len(sig) - 6} señales"):
                    _cards(sig.iloc[6:], base=6)
            with st.expander("Tabla de señales"):
                tb = sig.copy()
                tb["Sesgo"] = tb["Señal"].map(lambda v: DD.sesgo(v)[0])
                tb = tb[["Indicador", "Sesgo", "Señal", "Peso", "Aporte", "Lectura"]]
                colr = lambda v: f"color: {GREEN if v > 0.15 else RED if v < -0.15 else NEUTRAL}; font-weight: 600"
                sty = (tb.style.format({"Señal": "{:+.2f}", "Aporte": "{:+.2f}", "Peso": "{:.1f}"})
                       .map(colr, subset=["Señal", "Aporte"])
                       .map(lambda s_: colr(1 if s_.startswith("▲") else -1 if s_.startswith("▼") else 0), subset=["Sesgo"]))
                st.dataframe(sty, hide_index=True, width="stretch")
                st.caption("Cada indicador emite una señal de −1 a +1 ponderada por su fiabilidad; el score técnico es "
                           "el promedio ponderado × 100.")
        with tf_:
            if V:
                st.markdown(f"<div class='rep-b'><b>Lectura del analista</b><br>{E(V.get('lectura_fundamental', ''))}</div>",
                            unsafe_allow_html=True)
            bl = fs.get("bloques", {})
            st.markdown("<div class='dd-intro'>Puntaje de −100 a +100 por bloque (la barra parte del centro: a la derecha "
                        "suma, a la izquierda resta) y las métricas que más pesan en cada uno.</div>",
                        unsafe_allow_html=True)
            _bl = list(bl.items())
            for k0 in range(0, len(_bl), 3):
                cols_ = st.columns(3, gap="small")
                for col_, (bn, bv) in zip(cols_, _bl[k0:k0 + 3]):
                    col_.markdown(DD.block_card(bn, bv["score"], BLOCK_W[bn],
                                                [i for i in fs.get("items", []) if i["bloque"] == bn]),
                                  unsafe_allow_html=True)
            fv = A.get("finviz") or {}
            fitems = A.get("finviz_items") or []
            with st.expander("Detalle de Finviz (señales, ratings y ficha)"):
                if not fv.get("snapshot"):
                    st.caption("Finviz no respondió para este ticker (o estás en modo demo).")
                else:
                    bsc = (bl.get("Posicionamiento (Finviz)") or {}).get("score")
                    wtot = sum(BLOCK_W[b_] for b_, v in bl.items() if v["score"] is not None)
                    share = BLOCK_W["Posicionamiento (Finviz)"] / wtot * 100 if wtot else 0
                    st.markdown(f"**Peso de Finviz en el pronóstico:** bloque *Posicionamiento* con puntaje "
                                f"<b style='color:{col_score(bsc)}'>{'—' if bsc is None else f'{bsc:+.0f}'}</b>, que "
                                f"representa **{share:.0f}%** del score fundamental (y {share * 0.4:.0f}% del combinado).",
                                unsafe_allow_html=True)
                    if fitems:
                        fdf = pd.DataFrame([{"Métrica": i["metrica"], "Valor": i["valor"], "Impacto": i["impacto"],
                                             "Lectura": i["lectura"]} for i in fitems])
                        colr2 = lambda v: f"color: {GREEN if v > 0.15 else RED if v < -0.15 else NEUTRAL}; font-weight: 600"
                        st.dataframe(fdf.style.format({"Impacto": "{:+.2f}"}).map(colr2, subset=["Impacto"]),
                                     hide_index=True, width="stretch")
                    if fv.get("signals"):
                        st.markdown("**Señales de Finviz:** " + " · ".join(fv["signals"]))
                    if fv.get("ratings"):
                        st.markdown("**Cambios de rating de analistas**")
                        st.dataframe(pd.DataFrame(fv["ratings"]), hide_index=True, width="stretch")
                    st.dataframe(pd.DataFrame([{"Campo": k_, "Valor": v} for k_, v in fv["snapshot"].items()]),
                                 hide_index=True, width="stretch")
                    st.markdown(f"[Ver {ticker} en Finviz ↗](https://finviz.com/quote.ashx?t={ticker.replace('-', '.')})")
        with te:
            if not V:
                st.caption("La estrategia (proyecciones, toma de ganancias, invalidación) se genera con el informe del "
                           "analista: elige Claude, Gemini o Sin IA arriba.")
            else:
                pj = V.get("proyecciones") or []
                if pj:
                    rows = "".join(
                        f"<tr><td>{E(str(x.get('plazo', '')))}</td><td class='n' style='color:{RED}'>{money(x.get('bajista'))}</td>"
                        f"<td class='n'><b>{money(x.get('base'))}</b></td><td class='n' style='color:{GREEN}'>{money(x.get('alcista'))}</td>"
                        f"<td class='n'>{pfmt(x.get('probabilidad_base'))}</td>"
                        f"<td>{E(str(x.get('tiempo_estimado', '')))}</td><td class='small'>{E(str(x.get('fundamento', '')))}</td></tr>"
                        for x in pj)
                    st.markdown("<div class='sec2'>Proyecciones de precio</div><table class='qt-tab'><thead><tr><th>Plazo</th>"
                                "<th>Bajista</th><th>Base</th><th>Alcista</th><th>Prob.</th><th>Tiempo</th><th>Fundamento</th>"
                                f"</tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
                g1_, g2_ = st.columns(2)
                g1_.markdown("<div class='sec2'>Toma de ganancias</div>" + "<ul class='tl'>" + "".join(
                    f"<li>{E(str(x))}</li>" for x in V.get("gestion_ganancias", [])) + "</ul>"
                    + f"<div class='small muted'>TP1 {E(str(V.get('tiempo_objetivo_1', '')))} · TP2 {E(str(V.get('tiempo_objetivo_2', '')))}</div>",
                    unsafe_allow_html=True)
                g2_.markdown("<div class='sec2'>Si cambian las métricas…</div><ul class='tl'>" + "".join(
                    f"<li><b>{E(str(x.get('senal', '')))}</b> → {E(str(x.get('implica', '')))}. <i>{E(str(x.get('accion', '')))}</i></li>"
                    if isinstance(x, dict) else f"<li>{E(str(x))}</li>" for x in V.get("senales_de_cambio", [])) + "</ul>",
                    unsafe_allow_html=True)
                f1_, f2_ = st.columns(2)
                f1_.markdown(f"<div class='sec2' style='color:{GREEN}'>A favor</div><ul class='tl'>" +
                             "".join(f"<li>{E(str(x))}</li>" for x in V.get("factores_a_favor", [])) + "</ul>",
                             unsafe_allow_html=True)
                f2_.markdown(f"<div class='sec2' style='color:{RED}'>Riesgos</div><ul class='tl'>" +
                             "".join(f"<li>{E(str(x))}</li>" for x in V.get("riesgos", [])) + "</ul>", unsafe_allow_html=True)
                extra = f"<b>Invalidación:</b> {E(str(V.get('invalidacion', '')))}"
                if V.get("catalizadores"):
                    extra += " · <b>Catalizadores:</b> " + " · ".join(E(str(c)) for c in V["catalizadores"])
                if V.get("contexto_general"):
                    extra += (f"<br><span class='muted'>Contexto general (conocimiento del modelo, puede estar "
                              f"desactualizado): {E(V['contexto_general'])}</span>")
                st.markdown(f"<div class='small'>{extra}</div>", unsafe_allow_html=True)
        with temp:
            bt = A["bt"]
            st.markdown(
                "<div class='mp' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px 18px'>"
                + row("Tasa base de la acción", f"{(prob['tasa_base_accion'] or 0) * 100:.1f}%")
                + row("Casos similares (±15)", f"{prob['casos_similares']}")
                + row("R medio en similares", f"{prob['R_promedio_similares']:+.2f} R" if ok(prob["R_promedio_similares"]) else "—")
                + row("Sesiones medias a salida", f"{prob['dias_promedio_salida']:.0f}" if ok(prob["dias_promedio_salida"]) else "—")
                + row("Sesiones típicas a objetivo", f"{prob['sesiones_tipicas_a_objetivo']:.0f}" if ok(prob.get("sesiones_tipicas_a_objetivo")) else "—")
                + "</div>", unsafe_allow_html=True)
            st.caption(prob["parametros"])
            if bt.get("n"):
                st.markdown(f"**Backtest de la señal** (entrada cuando el puntaje cruza ±40, 5 años, sin solapamiento): "
                            f"{bt['n']} operaciones · acierto {bt['win_rate'] * 100:.0f}% · R medio {bt['avg_R']:+.2f} · "
                            f"profit factor {bt['profit_factor']:.2f} · total {bt['total_R']:+.1f} R · drawdown máx {bt['max_dd_R']:.1f} R")
                st.plotly_chart(equity_chart(bt["trades"]), width="stretch")
            else:
                st.info("La señal no generó operaciones en el periodo analizado.")

# ---------------------------------------------------------------- niveles y noticias
_ext = st.expander("Niveles (soportes, resistencias, Fibonacci) y noticias", expanded=False)
t4, t5 = _ext.tabs(["Niveles", "Noticias"])

with t4:
    c1, c2, c3 = st.columns(3, vertical_alignment="bottom")
    c1.markdown("**Soportes**")
    c1.dataframe(pd.DataFrame([{"Nivel": f"${lv:,.2f}", "Toques": n, "Distancia": f"{(lv / last['Close'] - 1) * 100:+.1f}%"}
                               for lv, n in plan["soportes"]]), hide_index=True, width="stretch")
    c2.markdown("**Resistencias**")
    c2.dataframe(pd.DataFrame([{"Nivel": f"${lv:,.2f}", "Toques": n, "Distancia": f"{(lv / last['Close'] - 1) * 100:+.1f}%"}
                               for lv, n in plan["resistencias"]]), hide_index=True, width="stretch")
    fib = plan["fibonacci"]
    c3.markdown(f"**Fibonacci** (tramo {fib['tramo']} 6 meses)")
    c3.dataframe(pd.DataFrame([{"Retroceso": k_, "Precio": f"${v:,.2f}"} for k_, v in fib["niveles"].items()]),
                 hide_index=True, width="stretch")

with t5:
    if A["news"]:
        for n in A["news"]:
            s_ = f" · sentimiento: {n['sentimiento']}" if n.get("sentimiento") else ""
            st.markdown(f"- [{n['titulo']}]({n['link']}) <span class='muted'>· {n['fuente'] or ''}{s_}</span>",
                        unsafe_allow_html=True)
    else:
        st.info("Sin noticias recientes disponibles.")

st.markdown(DISCLAIMER, unsafe_allow_html=True)
