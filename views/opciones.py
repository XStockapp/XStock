"""Módulo de Opciones: cadena Put/Call lado a lado (estilo institucional), métricas de flujo y lectura con IA."""
import html
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from core import ai, db, options as OP, profiles, store
from core.analysis import full_analysis
from core.timeframes import is_crypto
from core.ui import AMBER, DISCLAIMER, GREEN, MUTED, NEUTRAL, RED, pill

cfg = st.session_state.cfg
E = html.escape
ACC = "#2962FF"
BG, PANEL, BORDER, TXT = "#0D1117", "#161B22", "#30363D", "#E6EDF3"


@st.cache_data(ttl=900, show_spinner=False)
def _run(ticker, tp, sl, acct, risk, av, prov, tf, settings_json):
    return full_analysis(ticker, tp, sl, None, acct, risk, av or None, prov, tf, json.loads(settings_json))


st.markdown("""<style>
.op-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:6px 0 10px}
.op-k{background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px 10px}
.op-k .l{font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.04em}
.op-k .v{font-family:'JetBrains Mono','Fira Code',monospace;font-variant-numeric:tabular-nums;font-size:16px;color:#E6EDF3;margin-top:2px}
.op-k .s{font-size:11px;color:#8B949E;margin-top:1px;font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums}
.op-box{background:#161B22;border:1px solid #30363D;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:12.5px;color:#E6EDF3;line-height:1.5}
.op-box h4{font-size:12px;color:#8B949E;text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px;font-weight:600}
.op-box table{width:100%;border-collapse:collapse;font-size:12px}
.op-box td,.op-box th{padding:4px 6px;border-bottom:1px solid #21262D;text-align:left}
.op-box th{color:#8B949E;font-weight:600}
.op-box .num{font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums}
.op-hl{border-left:3px solid #2962FF}
.op-hdr{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#161B22;border:1px solid #30363D;border-radius:6px;
  padding:7px 10px;margin:2px 0 8px}
.op-hdr .tk{font-family:'JetBrains Mono',monospace;font-size:17px;font-weight:700;color:#E6EDF3}
.op-hdr .px{font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;font-size:16px;color:#E6EDF3}
.op-sum{display:inline-flex;gap:12px;flex-wrap:wrap;border:1px solid #30363D;border-radius:999px;padding:2px 10px;font-size:12px;color:#8B949E}
.op-sum b,.op-rec b{font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;color:#E6EDF3;font-weight:600}
.op-rec{font-size:12px;color:#8B949E;border:1px solid #2962FF;border-radius:999px;padding:2px 10px}
.op-cmp{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}
.op-cmp th{text-align:left;color:#8B949E;font-weight:600;border-bottom:1px solid #30363D;padding:5px 8px;font-size:12px}
.op-cmp td{padding:5px 8px;border-bottom:1px solid #21262D;color:#E6EDF3}
.op-cmp td.n{font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;text-align:right}
.op-cmp tr td:first-child{color:#8B949E}
.op-cmp .best{color:#26A69A;font-weight:600}
@media (max-width:900px){.op-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- entrada
c1, c2, c3 = st.columns([1.4, 1.6, 4], vertical_alignment="bottom")
ticker = c1.text_input("Símbolo", st.session_state.get("ticker", "AAPL"), key="opt_ticker").strip().upper()
TF = c2.segmented_control("Contexto técnico", ["1h", "4h", "1D"], default="1h", key="opt_tf") or "1h"
c3.markdown("<div class='muted small'>Cadena de Alpaca · vencimientos ≤ 45 días · strikes ±15 % del spot · "
            "caché de 3 minutos</div>", unsafe_allow_html=True)
if not ticker:
    st.stop()
st.session_state.ticker = ticker
if is_crypto(ticker):
    st.info("Las opciones solo están disponibles para acciones y ETF de EE. UU.")
    st.stop()

SETTINGS = st.session_state.get("technical_settings") or profiles.BASE_SETTINGS
try:
    with st.spinner(f"Analizando {ticker}…"):
        A = _run(ticker, cfg["tp_atr"], cfg["sl_atr"], cfg["capital"], cfg["riesgo_pct"], cfg["alphavantage_key"],
                 "alphavantage" if cfg.get("proveedor", "").startswith("Alpha Vantage") else "yahoo",
                 TF, json.dumps(profiles.engine_settings(SETTINGS), sort_keys=True))
except Exception as e:
    st.error(f"No se pudo analizar {ticker}: {e}")
    st.stop()

d = A["df"]
spot = float(d["Close"].iloc[-1])
MET = A.get("metodo") or {}
ADX, CON = MET.get("adx") or {}, MET.get("consolidado") or {}
VP = A.get("vprofile") or {}
try:
    with st.spinner("Descargando la cadena de opciones…"):
        CH, INFO = OP.chain(ticker, round(spot, 1))
except Exception as e:
    st.error(f"{e}")
    st.stop()
if CH.empty:
    st.warning(f"{ticker} no tiene opciones listadas en Alpaca para los próximos {OP.DIAS_MAX} días.")
    st.stop()

SM = OP.resumen(CH, spot)
WALLS = OP.muros(CH)
CONF = OP.confluencias(WALLS, VP, spot)
GEXS = OP.gex_por_strike(CH, spot)
CANDS = {s: OP.candidatos(CH, spot, s, walls=WALLS, gex=GEXS) for s in ("alcista", "bajista")}
ESC = CON.get("escenario_base") or "Neutral"
HL_RULE = OP.destacar(CANDS, ESC, ADX, WALLS, CONF, spot)

payload = {
    "ticker": ticker, "spot_price": round(spot, 2), "timestamp_utc": INFO["timestamp_utc"],
    "technical_context": {
        "timeframe": TF.upper(), "adx_14_14_23": ADX.get("adx"),
        "trend_status": (f"Tendencia {ADX.get('direccion', '')} (ADX > {ADX.get('nivel_clave', 23):g})"
                         if ADX.get("regimen") == "tendencia" else f"Rango / consolidación (ADX < {ADX.get('nivel_clave', 23):g})"),
        "regimen_adx": ADX.get("regimen"), "escenario": ESC, "confianza_global": CON.get("confianza_global"),
        "score_tecnico": A["tech"].get("score") if isinstance(A.get("tech"), dict) else None,
        "macd": next((s_.get("Lectura") for s_ in (A["tech"].get("señales") or []) if str(s_.get("Indicador", "")).startswith("MACD")), None)
        if isinstance(A.get("tech"), dict) else None,
        "vrvp_poc": round(VP["poc"], 2) if VP.get("poc") else None,
        "vrvp_vah": round(VP["vah"], 2) if VP.get("vah") else None,
        "vrvp_val": round(VP["val"], 2) if VP.get("val") else None,
    },
    "options_summary": {k: v for k, v in SM.items()},
    "highlighted_option": HL_RULE,
    "key_liquidity_walls": {k: v for k, v in WALLS.items() if k != "criterio"},
    "confluencias_vrvp": CONF,
    "candidatos": CANDS["alcista"] + CANDS["bajista"],
    "info": INFO,
}

# ---------------------------------------------------------------- lectura (reglas por defecto, IA a pedido)
akey = f"opt_ai_{ticker}_{TF}"
R = st.session_state.get(akey) or ai.options_rule_based(payload)
HL = R.get("highlighted_option")
if HL and "exp" not in HL:  # resultado de la IA: validar contra la cadena real
    HL = ai.validar_destacado(HL, payload["candidatos"])

EXPS = sorted(CH["exp"].unique())
LBL = {e: f"{OP.etiqueta_venc(e)} · {int(CH[CH['exp'] == e]['dte'].iloc[0])}d" for e in EXPS}
hl_exp = next((e for e in EXPS if HL and OP.etiqueta_venc(e).upper() == HL["target_expiration_tab"].upper()), None)
# apertura automática de la pestaña del vencimiento recomendado (una vez por recomendación nueva)
sig = f"{ticker}|{HL['option_type']}|{HL['strike']}|{HL['target_expiration_tab']}" if hl_exp else None
if sig and st.session_state.get("opt_hl_sig") != sig:
    st.session_state["opt_hl_sig"] = sig
    st.session_state["opt_exp"] = LBL[hl_exp]
if st.session_state.get("opt_exp_tk") != ticker and not sig:
    st.session_state["opt_exp"] = LBL[EXPS[0]]
st.session_state["opt_exp_tk"] = ticker
if st.session_state.get("opt_exp") not in LBL.values():
    st.session_state["opt_exp"] = LBL[EXPS[0]]

# ---------------------------------------------------------------- cabecera minimalista
gex_pos = (SM.get("gex_total") or 0) >= 0
ec = GREEN if ESC == "Alcista" else RED if ESC == "Bajista" else NEUTRAL
em = SM.get("expected_move_usd")
SUMMARY = {"expected_move": "—" if em is None else f"±${em:,.2f}",
           "max_pain": "—" if not SM.get("max_pain") else f"${SM['max_pain']:,.2f} ({SM['nearest_expiration']})",
           "gex_status": SM["net_gamma_exposure_gex"], "bias": ESC}
payload["summary_bar"] = SUMMARY
payload["ai_optimal_recommendation"] = (None if not HL else {"expiration": HL["target_expiration_tab"],
                                                             "type": HL["option_type"], "strike": HL["strike"]})
st.markdown(
    f"<div class='op-hdr'>"
    f"<span class='tk'>{E(ticker)}</span><span class='px'>${spot:,.2f}</span>"
    f"{pill('Sesgo ' + ESC, ec)}"
    f"<span class='op-sum'><span>Mov. esperado <b>{E(SUMMARY['expected_move'])}</b></span>"
    f"<span>Max pain <b>{E(SUMMARY['max_pain'])}</b></span>"
    f"<span>GEX <b style='color:{GREEN if gex_pos else RED}'>{E(SUMMARY['gex_status'])}</b></span></span>"
    + (f"<span class='op-rec'>Óptima del motor <b>{E(HL['option_type'])} {HL['strike']:g} · {E(HL['target_expiration_tab'])}</b></span>"
       if HL else "")
    + f"<span class='muted small'>Feed {E(INFO['feed'])} · {E(INFO['timestamp_utc'])}</span></div>",
    unsafe_allow_html=True)


def _k(label, val, sub=""):
    return f"<div class='op-k'><div class='l'>{E(label)}</div><div class='v'>{val}</div><div class='s'>{sub}</div></div>"


def _m(v, pre="$"):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{pre}{v:,.2f}"


# ---------------------------------------------------------------- acordeón 1: análisis del motor / IA
with st.expander("Análisis del motor e IA · diagnóstico cuantitativo y recomendación", expanded=False,
                 icon=":material/insights:"):
    cw = " · ".join(f"{w['strike']:g}" for w in WALLS["call_walls"]) or "—"
    pw = " · ".join(f"{w['strike']:g}" for w in WALLS["put_walls"]) or "—"
    st.markdown(
        "<div class='op-grid'>"
        + _k("PCR volumen", "—" if SM["pcr_volumen"] is None else f"{SM['pcr_volumen']:.2f}", "puts / calls")
        + _k("PCR interés abierto", "—" if SM["pcr_open_interest"] is None else f"{SM['pcr_open_interest']:.2f}", "puts / calls")
        + _k("Movimiento esperado", "—" if em is None else f"±${em:,.2f}",
             f"{SM['nearest_expiration']} · {SM['dte']}d" + ("" if em is None else f" · ±{em / spot * 100:.1f}%"))
        + _k("IV ATM", "—" if SM["iv_rank_or_avg_iv"] is None else f"{SM['iv_rank_or_avg_iv']:.1f}%", "vencimiento próximo")
        + _k("GEX neto", f"<span style='color:{GREEN if gex_pos else RED}'>{E(SM['net_gamma_exposure_gex'])}</span>",
             "Γ × OI × 100 × S² × 1 %")
        + _k("Gamma flip", _m(SM.get("gamma_flip_level")),
             "—" if not SM.get("gamma_flip_level") else f"spot {'sobre' if spot > SM['gamma_flip_level'] else 'bajo'} el flip")
        + _k("Max pain", _m(SM.get("max_pain")), SM["nearest_expiration"])
        + _k("Muros calls / puts", f"<span style='color:{RED}'>{cw}</span> / <span style='color:{GREEN}'>{pw}</span>",
             WALLS["criterio"])
        + "</div>", unsafe_allow_html=True)

    # ---------------------------------------------------------------- motor de lectura
    _prof = st.session_state.get("profile") or {}
    _is_admin = _prof.get("role") == "admin"
    _gem_key, _cl_key = store.secret("GEMINI_API_KEY"), cfg["anthropic_key"]
    with st.container(border=True):
        h1, h2 = st.columns([2.2, 2], vertical_alignment="center")
        h1.markdown(f"<div class='op-box op-hl' style='margin:0'><h4>Lectura del flujo de opciones · {E(R.get('_modelo', ''))}</h4>"
                    f"{E(R.get('diagnostico', ''))}</div>", unsafe_allow_html=True)
        b1, b2, b3 = h2.columns(3)
        go_cl = b1.button("Claude", icon=":material/auto_awesome:", width="stretch", disabled=not (_is_admin and _cl_key),
                          type="primary" if _is_admin else "secondary",
                          help="Lectura con Claude" if _is_admin else "Disponible solo para el administrador")
        go_ge = b2.button("Gemini", icon=":material/bolt:", width="stretch", disabled=not _gem_key,
                          type="primary" if not _is_admin else "secondary")
        go_rb = b3.button("Sin IA", icon=":material/calculate:", width="stretch")
        if go_cl or go_ge or go_rb:
            try:
                with st.spinner("Analizando el flujo de opciones…"):
                    if go_cl:
                        out = ai.analyze(payload, _cl_key, ai.MODELOS[cfg["modelo"]], system=ai.SYSTEM_OPCIONES)
                    elif go_ge:
                        out = ai.analyze_gemini(payload, _gem_key, store.secret("GEMINI_MODEL") or None, system=ai.SYSTEM_OPCIONES)
                    else:
                        out = ai.options_rule_based(payload)
                if (go_cl or go_ge) and _prof:
                    db.log_event(_prof["email"], "ai_options", f"{ticker} · {'claude' if go_cl else 'gemini'}")
            except Exception as e:
                st.error(f"Error con la IA: {e}. Se muestra la lectura por reglas.")
                out = ai.options_rule_based(payload)
            st.session_state[akey] = out
            st.session_state.pop("opt_hl_sig", None)
            st.rerun()

    # ---------------------------------------------------------------- contrato destacado y niveles
    bx1, bx2, bx3, bx4 = st.columns([1, 1.35, 1, 1])
    # contrato destacado
    _w = bx1
    if HL:
        col = GREEN if HL["option_type"] == "CALL" else RED
        _w.markdown(
            f"<div class='op-box op-hl'><h4>Contrato destacado</h4>"
            f"<div style='font-size:15px;font-weight:700;color:{col};font-family:JetBrains Mono,monospace'>"
            f"{E(HL['option_type'])} {HL['strike']:g} · {E(HL['target_expiration_tab'])}</div>"
            f"<div class='num muted small'>Δ {HL.get('delta', '—')} · {HL.get('dte', '—')}d · bid/ask "
            f"{_m(HL.get('bid'))}/{_m(HL.get('ask'))} · IV {HL.get('iv', '—')}%</div>"
            f"<div style='margin-top:6px'>{E(HL.get('rationale', ''))}</div></div>", unsafe_allow_html=True)
    else:
        _w.markdown("<div class='op-box'><h4>Contrato destacado</h4>Ninguno: el escenario cuantitativo es neutral o el "
                    "flujo de opciones lo contradice.</div>", unsafe_allow_html=True)
    niv = R.get("niveles_institucionales") or []
    if niv:
        bx2.markdown("<div class='op-box'><h4>Niveles institucionales</h4><table><tr><th>Nivel</th><th>Tipo</th><th>Efecto</th></tr>"
                    + "".join(f"<tr><td class='num'>{float(n_['nivel']):,.2f}</td><td>{E(str(n_.get('tipo', '')))}"
                              + (f"<div class='muted small'>{E(str(n_.get('confluencia')))}</div>" if n_.get('confluencia') else "")
                              + f"</td><td>{E(str(n_.get('efecto', '')))}</td></tr>"
                              for n_ in niv if n_.get("nivel") is not None)
                    + "</table></div>", unsafe_allow_html=True)
    bx3.markdown(f"<div class='op-box'><h4>Régimen gamma · {E(str(R.get('regimen_gex', '')))}</h4>"
                f"{E(R.get('lectura_regimen', ''))}"
                + (f"<div style='margin-top:6px'>Flujo {E(str(R.get('sesgo_flujo', '')).lower())} · "
                   f"{'valida' if R.get('valida_escenario') else 'contradice'} el escenario · confianza "
                   f"<span class='num'>{R.get('confianza', '—')}%</span></div>")
                + "</div>", unsafe_allow_html=True)
    if R.get("advertencias"):
        bx4.markdown("<div class='op-box'><h4>Advertencias</h4><ul style='margin:0 0 0 16px;padding:0'>"
                    + "".join(f"<li>{E(a)}</li>" for a in R["advertencias"]) + "</ul></div>", unsafe_allow_html=True)



# ---------------------------------------------------------------- acordeón 2: simulador híbrido
EXP_LBL = {OP.etiqueta_venc(e): e for e in EXPS}
OPT = None
if HL:
    _r = OP.contrato(CH, EXP_LBL.get(HL["target_expiration_tab"]), HL["strike"], HL["option_type"])
    OPT = OP.evaluar(_r, spot, CH, WALLS, GEXS) if _r is not None else None
with st.expander("Simulador de decisión · Auto / Manual", expanded=True, icon=":material/tune:"):
    t_def = HL["option_type"] if HL else ("PUT" if ESC == "Bajista" else "CALL")
    g1, g2, g3, g4 = st.columns([0.9, 1.6, 1.6, 1.1], vertical_alignment="bottom")
    tipo = g1.segmented_control("Tipo", ["CALL", "PUT"], default=t_def, key=f"sim_tipo_{ticker}") or t_def
    opt_same = OPT if (OPT and OPT["tipo"] == tipo) else None
    if opt_same is None:
        # sin recomendación en esa dirección: óptimo matemático del motor para el tipo elegido
        _best = [b for b in (OP.mejor_strike(CH, spot, e, tipo, WALLS, GEXS) for e in EXPS if
                             int(CH[CH["exp"] == e]["dte"].iloc[0]) >= 7) if b]
        opt_same = max(_best, key=lambda b: b["ve"]) if _best else None
    with g2:
        m_exp = st.segmented_control("Fecha de expiración", ["Auto", "Manual"], default="Auto", key=f"sim_mexp_{ticker}") or "Auto"
        exp_opts = list(EXP_LBL)
        e_def = opt_same["vencimiento"] if opt_same else exp_opts[0]
        if m_exp == "Auto":
            st.selectbox("Vencimiento", [e_def], disabled=True, label_visibility="collapsed", key=f"sim_ea_{ticker}")
            sel_e = None
        else:
            sel_e = st.selectbox("Vencimiento", exp_opts, index=exp_opts.index(e_def) if e_def in exp_opts else 0,
                                 label_visibility="collapsed", key=f"sim_e_{ticker}")
    with g3:
        m_k = st.segmented_control("Strike", ["Auto", "Manual"], default="Auto", key=f"sim_mk_{ticker}") or "Auto"
        ks_src = CH[(CH["type"] == tipo.lower()) & ((CH["exp"] == EXP_LBL[sel_e]) if sel_e else True)]
        k_opts = sorted(ks_src["strike"].unique())
        k_def = opt_same["strike"] if opt_same else float(k_opts[int(np.argmin([abs(k - spot) for k in k_opts]))])
        if m_k == "Auto":
            st.selectbox("Strike", [f"{k_def:,.2f}"], disabled=True, label_visibility="collapsed", key=f"sim_ka_{ticker}")
            sel_k = None
        else:
            sel_k = st.selectbox("Strike", k_opts, index=k_opts.index(k_def) if k_def in k_opts else 0,
                                 format_func=lambda v: f"{v:,.2f}", label_visibility="collapsed", key=f"sim_k_{ticker}")
    run_sim = g4.button("Analizar Opción", type="primary", icon=":material/play_arrow:", width="stretch")
    SIM_CFG = {"expiration_mode": m_exp.upper(), "strike_mode": m_k.upper(),
               "selected_expiration": sel_e or e_def, "selected_strike": float(sel_k if sel_k is not None else k_def),
               "option_type": tipo}
    payload["decision_simulator_config"] = SIM_CFG
    skey = f"sim_res_{ticker}_{TF}"
    if run_sim:
        if sel_e and sel_k is None:          # escenario A: fecha manual, strike auto
            res, modo = OP.mejor_strike(CH, spot, EXP_LBL[sel_e], tipo, WALLS, GEXS), "A"
        elif sel_k is not None and not sel_e:  # escenario B: strike manual, fecha auto
            res, modo = OP.mejor_vencimiento(CH, spot, sel_k, tipo, WALLS, GEXS), "B"
        elif sel_e and sel_k is not None:     # ambos manuales: evaluar exactamente ese contrato
            _r = OP.contrato(CH, EXP_LBL[sel_e], sel_k, tipo)
            res, modo = (OP.evaluar(_r, spot, CH, WALLS, GEXS) if _r is not None else None), "M"
        else:                                  # ambos auto: la combinación óptima del motor
            res, modo = opt_same, "AUTO"
        st.session_state[skey] = {"res": res, "modo": modo, "cfg": SIM_CFG}
    SIMR = st.session_state.get(skey)
    if SIMR:
        res, modo = SIMR["res"], SIMR["modo"]
        if res is None:
            st.warning("No hay contratos líquidos (bid/ask e interés abierto) para esa combinación.")
        else:
            txt_modo = {"A": f"Mejor strike para el {res['vencimiento']} (fecha manual, strike automático)",
                        "B": f"Mejor vencimiento para el strike {res['strike']:g} (strike manual, fecha automática)",
                        "M": "Contrato elegido manualmente", "AUTO": "Combinación óptima del motor"}[modo]
            riesg = OP.riesgos(res, ESC, ADX, SM.get("gex_total") or 0, SM.get("gamma_flip_level"), spot)
            colr = GREEN if res["tipo"] == "CALL" else RED
            r1, r2 = st.columns([1.1, 1.4])
            r1.markdown(
                f"<div class='op-box op-hl'><h4>{E(txt_modo)}</h4>"
                f"<div style='font-size:16px;font-weight:700;color:{colr};font-family:JetBrains Mono,monospace'>"
                f"{E(res['contrato'])} · {E(res['vencimiento'])} · {res['dte']}d</div>"
                f"<div style='margin-top:6px'>Prima <b class='num'>${res['prima']:,.2f}</b> (${res['prima'] * 100:,.0f} por contrato) · "
                f"breakeven <b class='num'>${res['breakeven']:,.2f}</b> ({res['dist_breakeven_pct']:+.1f}%) · objetivo "
                f"<b class='num'>${res['objetivo']:,.2f}</b> en {res['horizonte_dias']:.0f} días.</div>"
                f"<div style='margin-top:4px'>Si toca el objetivo: <b class='num' style='color:{GREEN if res['roi_objetivo'] >= 0 else RED}'>{res['roi_objetivo']:+.0f}%</b> · "
                f"si el precio no se mueve: <b class='num' style='color:{GREEN if res['roi_sin_movimiento'] >= 0 else RED}'>{res['roi_sin_movimiento']:+.0f}%</b> · "
                f"probabilidad de tocar el objetivo <b class='num'>{res['p_toque']:.0f}%</b> · valor esperado "
                f"<b class='num' style='color:{GREEN if res['ve'] >= 0 else RED}'>{res['ve']:+.1f}%</b></div></div>",
                unsafe_allow_html=True)
            r1.markdown("<div class='op-box'><h4>Riesgos y cuidados</h4>"
                        + ("<ul style='margin:0 0 0 16px;padding:0'>" + "".join(f"<li>{E(x)}</li>" for x in riesg) + "</ul>"
                           if riesg else "Sin alertas relevantes con los datos actuales.") + "</div>", unsafe_allow_html=True)
            o = opt_same

            def _v(e, k, f):
                if not e or e.get(k) is None:
                    return "—"
                return f(e[k])

            filas = [
                ("Contrato", lambda e: f"{e['contrato']} · {e['vencimiento']}", None),
                ("Días al vencimiento", lambda e: f"{e['dte']}", None),
                ("Prima (medio)", lambda e: f"${e['prima']:,.2f}", None),
                ("Breakeven", lambda e: f"${e['breakeven']:,.2f} ({e['dist_breakeven_pct']:+.1f}%)", None),
                ("Delta", lambda e: "—" if e["delta"] is None else f"{e['delta']:+.2f}", None),
                ("IV", lambda e: f"{e['iv']:.1f}%", None),
                ("Theta por día", lambda e: "—" if e["theta_dia_pct"] is None else f"{e['theta_dia_pct']:.1f}% de la prima", "min_theta"),
                ("Objetivo (muro / mov. esperado)", lambda e: f"${e['objetivo']:,.2f}", None),
                ("Rentabilidad si toca el objetivo", lambda e: f"{e['roi_objetivo']:+.0f}%", "max_roi"),
                ("Si el precio no se mueve", lambda e: f"{e['roi_sin_movimiento']:+.0f}%", "max_roi0"),
                ("Prob. de tocar el objetivo", lambda e: f"{e['p_toque']:.0f}%", "max_p"),
                ("Valor esperado", lambda e: f"{e['ve']:+.1f}%", "max_ve"),
                ("Spread", lambda e: f"{e['spread_pct']:.1f}%", "min_spread"),
                ("Interés abierto / volumen", lambda e: f"{e['oi'] or 0:,} / {e['volumen']:,}", None),
                ("GEX en el strike", lambda e: "—" if e["gex_strike"] is None else OP._fmt_m(e["gex_strike"]), None),
            ]
            mejor = {"min_theta": ("theta_dia_pct", min), "max_roi": ("roi_objetivo", max), "max_roi0": ("roi_sin_movimiento", max),
                     "max_p": ("p_toque", max), "max_ve": ("ve", max), "min_spread": ("spread_pct", min)}
            rows_ = []
            for lab, f, crit in filas:
                a_, b_ = _v(res, "contrato", lambda _: f(res)), _v(o, "contrato", lambda _: f(o))
                ca = cb = ""
                if crit and o and res is not o:
                    k_, fn = mejor[crit]
                    va, vb = res.get(k_), o.get(k_)
                    if va is not None and vb is not None and round(va, 1) != round(vb, 1):
                        w = fn(va, vb)
                        ca, cb = ("best", "") if w == va else ("", "best")
                rows_.append(f"<tr><td>{E(lab)}</td><td class='n {ca}'>{E(a_)}</td><td class='n {cb}'>{E(b_)}</td></tr>")
            r2.markdown("<div class='op-box'><h4>Comparativa · tu selección vs combinación óptima del motor</h4>"
                        "<table class='op-cmp'><tr><th></th><th style='text-align:right'>Tu selección</th>"
                        "<th style='text-align:right'>Óptima del motor (IA)</th></tr>" + "".join(rows_) + "</table>"
                        "<div class='muted small' style='margin-top:6px'>Verde = mejor valor de la fila. Valor esperado = "
                        "P(toca objetivo) × rentabilidad en el objetivo + (1 − P) × resultado sin movimiento − medio spread, "
                        "con Black-Scholes a la IV actual en un horizonte de min(días/2, 10).</div></div>",
                        unsafe_allow_html=True)
    # ---- gráfico P&L dinámico (time-to-target): opción del simulador vs óptima del motor
    _u = (SIMR or {}).get("res")
    _cs = []
    if _u:
        _cs.append(("Tu selección · " + _u["contrato"] + " · " + _u["vencimiento"], _u, "#F0B429"))
    if opt_same and not (_u and _u["contrato"] == opt_same["contrato"] and _u["exp"] == opt_same["exp"]):
        _cs.append(("Óptima del motor · " + opt_same["contrato"] + " · " + opt_same["vencimiento"], opt_same, "#7C9CFF"))
    if _cs:
        from core import pnl_widget as PW
        _obj = (_u or opt_same)["objetivo"]
        _ks = [c[1]["strike"] for c in _cs] + [_obj, spot]
        _lo, _hi = min(min(_ks), spot * 0.9), max(max(_ks), spot * 1.1)
        _pad = (_hi - _lo) * 0.08
        _niv = ([{"v": w["strike"], "t": "C-wall", "c": RED} for w in WALLS["call_walls"]]
                + [{"v": w["strike"], "t": "P-wall", "c": GREEN} for w in WALLS["put_walls"]])
        st.markdown("<div class='muted small' style='margin:6px 0 2px'><b>P&amp;L dinámico por trayectoria</b> · "
                    "elige en cuántos días llega el precio al objetivo (deslizador, botones o arrastrando el punto)</div>",
                    unsafe_allow_html=True)
        components.html(PW.html(spot, _obj,
                                [{"nombre": n, "tipo": c["tipo"], "strike": c["strike"], "iv": c["iv"] / 100,
                                  "prima": c["prima"], "dte": c["dte"], "color": colr_} for n, c, colr_ in _cs],
                                int(round((_u or opt_same)["horizonte_dias"])), (_lo - _pad, _hi + _pad), _niv),
                        height=640, scrolling=False)
    if not SIMR:
        st.markdown("<div class='muted small'>Ambos campos en <b>Auto</b> muestran la combinación óptima del motor. Pasa la "
                    "fecha o el strike a <b>Manual</b> y pulsa <b>Analizar Opción</b>: con la fecha manual XStock busca el "
                    "mejor strike; con el strike manual, el mejor vencimiento.</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- pestañas de vencimiento
labels = [LBL[e] for e in EXPS]
st.markdown("<div class='muted small' style='margin-top:4px'>Vencimientos</div>", unsafe_allow_html=True)
if hl_exp is not None:
    k = labels.index(LBL[hl_exp]) + 1
    st.markdown(
        f"<style>.st-key-opt_exp button:nth-of-type({k}){{animation:opexp 1.4s ease-in-out infinite;"
        f"border-color:{ACC} !important}}"
        f"@keyframes opexp{{0%,100%{{background-color:rgba(41,98,255,.10)}}50%{{background-color:rgba(41,98,255,.45)}}}}"
        f"</style>", unsafe_allow_html=True)
sel_lbl = st.segmented_control("Vencimiento", labels, key="opt_exp", label_visibility="collapsed") or labels[0]
sel_exp = EXPS[labels.index(sel_lbl)]
DX = CH[CH["exp"] == sel_exp]

# ---------------------------------------------------------------- cadena Put/Call lado a lado
cwk = {w["strike"] for w in WALLS["call_walls"]}
pwk = {w["strike"] for w in WALLS["put_walls"]}
hl_here = HL if (hl_exp is not None and sel_exp == hl_exp) else None
_sr = (st.session_state.get(f"sim_res_{ticker}_{TF}") or {}).get("res")
sim_here = _sr if (_sr and _sr["exp"] == sel_exp) else None
calls = DX[DX["type"] == "call"].set_index("strike")
puts = DX[DX["type"] == "put"].set_index("strike")
ks = sorted(set(calls.index) | set(puts.index))
em_sel = OP.expected_move(DX, spot)


def _n(v, f="{:,.2f}"):
    return "" if v is None or pd.isna(v) else f.format(v)


def _i(v):
    return "" if v is None or pd.isna(v) else f"{int(v):,}"


rows = []
spot_done = False
for k in ks:
    if not spot_done and k > spot:
        rows.append(f"<tr class='spot'><td colspan='15'>SPOT ${spot:,.2f}"
                    + (f" · movimiento esperado ±${em_sel:,.2f} ({spot - em_sel:,.2f} – {spot + em_sel:,.2f})" if em_sel else "")
                    + "</td></tr>")
        spot_done = True
    c = calls.loc[k] if k in calls.index else None
    p = puts.loc[k] if k in puts.index else None
    hc = bool(hl_here and hl_here["option_type"] == "CALL" and abs(hl_here["strike"] - k) < 1e-6)
    hp = bool(hl_here and hl_here["option_type"] == "PUT" and abs(hl_here["strike"] - k) < 1e-6)
    sc = bool(sim_here and sim_here["tipo"] == "CALL" and abs(sim_here["strike"] - k) < 1e-6 and not hc)
    sp = bool(sim_here and sim_here["tipo"] == "PUT" and abs(sim_here["strike"] - k) < 1e-6 and not hp)
    itm_c, itm_p = k < spot, k > spot
    tags = ("<span class='tg tc'>C-WALL</span>" if k in cwk else "") + ("<span class='tg tp'>P-WALL</span>" if k in pwk else "")
    if SM.get("max_pain") == k and sel_exp == EXPS[0]:
        tags += "<span class='tg tm'>MAX PAIN</span>"

    def side(r, cols, itm, hot, sim=False):
        cls = ("itm " if itm else "") + ("hot" if hot else "") + (" sim" if sim else "")
        if r is None:
            return "".join(f"<td class='{cls}'></td>" for _ in cols)
        out = []
        for name in cols:
            v = r[name]
            txt = (_n(v, "{:,.3f}") if name in ("delta", "theta") else _n(v, "{:,.4f}") if name == "gamma"
                   else _i(v) if name in ("volume", "oi") else _n(v))
            extra = " q" if name in ("bid", "ask") else ""
            out.append(f"<td class='{cls}{extra}'>{txt}</td>")
        return "".join(out)

    rows.append(f"<tr id='{'hl' if (hc or hp) else ''}'>"
                + side(c, ["theta", "gamma", "delta", "volume", "oi", "bid", "ask"], itm_c, hc, sc)
                + f"<td class='k{' hotk' if (hc or hp) else ''}'>{k:,.2f}{tags}</td>"
                + side(p, ["ask", "bid", "oi", "volume", "delta", "gamma", "theta"], itm_p, hp, sp) + "</tr>")

head = ("<tr class='g'><th colspan='7' class='gc'>CALLS</th><th></th><th colspan='7' class='gp'>PUTS</th></tr>"
        "<tr><th>Theta</th><th>Gamma</th><th>Delta</th><th>Volumen</th><th>Int. abierto</th><th>Bid</th><th>Ask</th>"
        "<th class='k'>Ejercicio</th>"
        "<th>Ask</th><th>Bid</th><th>Int. abierto</th><th>Volumen</th><th>Delta</th><th>Gamma</th><th>Theta</th></tr>")
CHAIN_HTML = f"""<!doctype html><html><head><style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');
body{{margin:0;background:{BG};color:{TXT};font-family:'JetBrains Mono','Fira Code',monospace}}
.wrap{{height:600px;overflow:auto;border:1px solid {BORDER};border-radius:6px;background:{PANEL}}}
table{{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}}
th{{position:sticky;top:0;background:#1C2128;color:#8B949E;font-weight:600;padding:5px 6px;text-align:right;
  border-bottom:1px solid {BORDER};font-family:Inter,system-ui,sans-serif;font-size:11px;z-index:2;white-space:nowrap;height:16px}}
tr.g th{{top:0;text-align:center;letter-spacing:.08em}}
tr:nth-child(2) th{{top:25px}}
th.gc{{color:{GREEN}}} th.gp{{color:{RED}}}
td{{padding:4px 6px;text-align:right;border-bottom:1px solid #21262D;white-space:nowrap}}
td.itm{{background:rgba(41,98,255,.06)}}
td.q{{color:{TXT};font-weight:600}}
td.k,th.k{{text-align:center;background:#1C2128;color:{TXT};font-weight:600;min-width:150px;border-left:1px solid {BORDER};
  border-right:1px solid {BORDER}}}
tr.spot td{{text-align:center;background:rgba(41,98,255,.18);color:#9DB6FF;font-size:11px;padding:3px;
  border-top:1px solid {ACC};border-bottom:1px solid {ACC}}}
.tg{{display:inline-block;font-size:11px;line-height:14px;padding:0 3px;margin-left:5px;border-radius:3px}}
.tc{{color:{RED};border:1px solid {RED}88}} .tp{{color:{GREEN};border:1px solid {GREEN}88}} .tm{{color:{AMBER};border:1px solid {AMBER}88}}
td.hot{{animation:pulse 1.2s ease-in-out infinite}}
td.sim{{background:rgba(240,180,41,.16);box-shadow:inset 0 1px 0 {AMBER},inset 0 -1px 0 {AMBER}}}
td.hotk{{animation:pulsek 1.2s ease-in-out infinite;color:#fff}}
@keyframes pulse{{0%,100%{{background:rgba(41,98,255,.08)}}50%{{background:rgba(41,98,255,.55)}}}}
@keyframes pulsek{{0%,100%{{background:#1C2128}}50%{{background:{ACC}}}}}
</style></head><body><div class='wrap' id='w'><table>{head}{''.join(rows)}</table></div>
<script>
const w=document.getElementById('w');const h=document.getElementById('hl')||document.querySelector('tr.spot');
if(h){{w.scrollTop=Math.max(0,h.offsetTop-w.clientHeight/2);}}
</script></body></html>"""

components.html(CHAIN_HTML, height=612, scrolling=False)
st.caption("Fondo azul tenue = dentro del dinero. C-WALL / P-WALL = muros de mayor interés abierto (≤ 45 días). "
           + ("La fila que destella es la combinación óptima del motor. " if hl_here else "")
           + ("La fila en ámbar es el contrato del simulador." if sim_here else ""))

# ---------------------------------------------------------------- GEX por strike
gx = GEXS
with st.expander("Ver Mapa GEX / Muros", expanded=False, icon=":material/bar_chart:"):
    if len(gx):
        fig = go.Figure(go.Bar(x=gx.values / 1e6, y=gx.index, orientation="h",
                               marker_color=[GREEN if v >= 0 else RED for v in gx.values],
                               hovertemplate="Strike %{y:,.2f}<br>GEX %{x:,.1f} M$<extra></extra>"))
        lines = [(spot, ACC, f"Spot {spot:,.2f}", "solid", "bottom right")]
        if SM.get("gamma_flip_level"):
            lines.append((SM["gamma_flip_level"], AMBER, f"Gamma flip {SM['gamma_flip_level']:,.2f}", "dash", "top left"))
        if VP.get("poc"):
            lines.append((VP["poc"], MUTED, f"POC VRVP {VP['poc']:,.2f}", "dot", "top right"))
        for y, colr, txt, dash, pos in lines:
            fig.add_hline(y=y, line=dict(color=colr, width=1, dash=dash), annotation_text=txt,
                          annotation_position=pos, annotation_font=dict(size=11, color=colr))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor=PANEL, plot_bgcolor=PANEL,
                          font=dict(family="JetBrains Mono, monospace", size=11, color=TXT), bargap=0.15,
                          title=dict(text="Exposición gamma neta por strike (≤ 45 días, millones de $ por 1 % de movimiento)",
                                     font=dict(size=12, color="#8B949E")),
                          xaxis=dict(gridcolor="#21262D", zerolinecolor=BORDER),
                          yaxis=dict(gridcolor="#21262D", tickformat=",.2f"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

st.caption("Cálculos: PCR = Σ puts / Σ calls · movimiento esperado = (call ATM + put ATM) × 0.85 · GEX = Γ × OI × 100 × S² × "
           "0.01 (calls +, puts −) · max pain = strike con el menor pago intrínseco total · gamma flip = precio donde el GEX "
           "total cambia de signo. El interés abierto corresponde al cierre anterior.")
st.markdown(DISCLAIMER, unsafe_allow_html=True)
