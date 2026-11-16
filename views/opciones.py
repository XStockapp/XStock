"""Terminal de Opciones (maqueta PowerPoint + estilo Stitch).

Distribución:
  [símbolo y precio] [MARKET % · datos técnicos y fundamentales] [OPTIONS % · mejor strike OPT1/OPT2/OPT3]
  [entradas: contexto, rango, balance, inversión, money · análisis manual] [pestañas CALL/PUT con explicación y gráficos]
  [option chain] [mapa GEX]
"""
import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from core import ai, calendario as CAL, data, db, mtf as MTF, options as OP, perfil_opciones as PO, pnl_widget as PW, profiles, store
from core.analysis import analisis_usuario
from core.timeframes import is_crypto
from core.ui import AMBER, DISCLAIMER, GREEN, MUTED, RED

cfg = st.session_state.cfg
ss = st.session_state
E = html.escape
ACC = "#2962FF"
BG, PANEL, BORDER, TXT = "#0D1117", "#161B22", "#30363D", "#E6EDF3"
MONO = "'JetBrains Mono','Fira Code',monospace"




@st.cache_data(ttl=600, show_spinner=False)
def _diario(ticker):
    h = data.history_tf(ticker, "1D")
    return float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])


def _m(v, pre="$", dec=2):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{pre}{v:,.{dec}f}"


st.markdown(f"""<style>
.ox-h{{font-family:{MONO};font-size:34px;font-weight:700;line-height:1;color:{TXT};letter-spacing:.02em}}
.ox-name{{color:#8B949E;font-size:12px;margin:4px 0 8px}}
.ox-q{{display:grid;grid-template-columns:auto auto;gap:2px 14px;font-size:12px;width:max-content}}
.ox-q span{{color:#8B949E}} .ox-q b{{font-family:{MONO};font-variant-numeric:tabular-nums;font-size:14px;color:{TXT};text-align:right}}
.ox-bar{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.ox-bar .t{{font-size:13px;font-weight:700;letter-spacing:.06em;color:{TXT};min-width:66px}}
.ox-bar .tr{{flex:1;height:10px;background:#21262D;border-radius:5px;overflow:hidden}}
.ox-bar .fl{{height:100%;border-radius:5px;animation:oxg 1.2s ease-out}}
@keyframes oxg{{from{{width:0}}}}
.ox-bar .p{{font-family:{MONO};font-size:12px;color:{TXT};min-width:38px;text-align:right}}
.ox-bar .b{{font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px;letter-spacing:.04em}}
.ox-box{{background:{PANEL};border:1px solid {BORDER};border-radius:8px;padding:10px 12px;margin-bottom:8px}}
.ox-box h4{{margin:0 0 6px;font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
.ox-dt{{display:grid;grid-template-columns:1fr;gap:0}}
.ox-dt div{{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid #21262D;padding:3px 0;font-size:12px}}
.ox-dt span{{color:#8B949E;min-width:0;flex:1 1 auto}} .ox-dt b{{font-family:{MONO};font-variant-numeric:tabular-nums;font-weight:600;color:{TXT};text-align:right;min-width:0;overflow-wrap:anywhere}}
.ox-st{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}}
.ox-st .k{{font-family:{MONO};font-size:24px;font-weight:700}}
.ox-st .v{{font-size:11px;padding:2px 8px;border-radius:4px;background:#21262D;color:{TXT};font-family:{MONO}}}
.ox-g3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:8px 0}}
.ox-g3 div span{{display:block;color:#8B949E;font-size:11px}}
.ox-g3 div b{{font-family:{MONO};font-variant-numeric:tabular-nums;font-size:13px;color:{TXT};white-space:nowrap}}
.ox-just{{font-size:12px;color:{TXT};line-height:1.5;border-top:1px solid #21262D;padding-top:6px}}
.ox-alert{{border:1px solid {AMBER};background:rgba(210,153,34,.08);border-radius:6px;padding:8px 10px;font-size:12px;
  line-height:1.5;margin:6px 0}}
.ox-red{{color:{RED};font-size:12px;line-height:1.45}}
.ox-exp{{font-size:12.5px;line-height:1.6;color:{TXT}}}
.ox-exp b{{font-family:{MONO};font-variant-numeric:tabular-nums}}
.ox-chips{{display:flex;flex-wrap:wrap;gap:4px;margin:2px 0 6px}}\n.ox-chip{{font-size:11px;padding:2px 7px;border-radius:6px;background:#0D1117;border:1px solid #30363D;color:#C9D1D9}}\n.ox-invl{{display:flex;justify-content:space-between;align-items:baseline;gap:6px;font-size:14px;color:#E6EDF3;margin:2px 0 4px}}
.ox-invl span{{white-space:nowrap}}
.ox-invl b{{font-family:{MONO};font-size:11px;white-space:nowrap;font-weight:600;color:#8B949E;font-variant-numeric:tabular-nums}}
.ox-lbl{{font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.05em;margin:2px 0 4px}}
.ox-mbar{{height:6px;background:#21262D;border-radius:3px;overflow:hidden;margin:2px 0 6px}}
.ox-mbar div{{height:100%;background:{GREEN};border-radius:3px}}
.ox-cmp{{width:100%;border-collapse:collapse;font-size:12px}}
.ox-cmp th{{text-align:right;color:#8B949E;font-weight:600;border-bottom:1px solid {BORDER};padding:4px 6px}}
.ox-cmp th:first-child,.ox-cmp td:first-child{{text-align:left;color:#8B949E}}
.ox-cmp td{{text-align:right;padding:4px 6px;border-bottom:1px solid #21262D;font-family:{MONO};font-variant-numeric:tabular-nums}}
@media (max-width:900px){{.ox-g3{{grid-template-columns:repeat(2,minmax(0,1fr))}}.ox-dt{{grid-template-columns:1fr}}}}
</style>""", unsafe_allow_html=True)

# ================================================================== entradas (columna izquierda)
ss.setdefault("opt_tf", "1h")
ss.setdefault("opt_rng", "1M")
ss.setdefault("opt_modo", "Mi perfil")
@st.cache_data(ttl=600, show_spinner=False)
def _precios_pf(tickers: tuple) -> dict:
    return data.batch_history(list(tickers), "1y")


# balance = valor de las posiciones abiertas del portafolio simulado + la inversión que se está evaluando
try:
    from core import portfolio as PF
    _ops_pf = PF.ops()
    _px_pf = _precios_pf(tuple(sorted({o["ticker"] for o in _ops_pf}))) if _ops_pf else {}
    PORT = PF.valor_abierto(_px_pf)
except Exception:
    PORT = 0.0
_CAP = float(cfg.get("capital") or 0)
ss.setdefault("opt_inv", float(round(max(_CAP * 0.3, 100) / 5) * 5) if _CAP else 200.0)
if ss.get("opt_inv_set") is not None:  # «Ajustar a $XX» desde la alerta de capital
    ss["opt_inv"] = float(ss.pop("opt_inv_set"))

# columna izquierda continua (cotización + entradas, sin hueco bajo la cotización); a la derecha, MARKET/OPTIONS
# arriba y el análisis debajo
left, right = st.columns([1.05, 3.2], gap="small")
with left:
    top_a = st.container()
with right:
    top_b, top_c = st.columns(2, gap="small")

with left:
    with st.container(border=True, key="ox_cfg"):
        ss.setdefault("opt_ticker", ss.get("ticker") or "SPY")
        tk_in = st.text_input("Símbolo", key="opt_ticker").strip().upper()
        st.segmented_control("Contexto técnico", ["1h", "4h", "1D"], key="opt_tf")
        st.segmented_control("Rango visible (vencimientos)", list(OP.RANGOS), key="opt_rng",
                             help="Hasta qué fecha de vencimiento se buscan las opciones: 2 semanas, 1, 3 o 6 meses")
        inv_ph = st.empty()  # balance + inversión (se rellena tras el análisis para poder destellar)
        perf_ph = st.empty()  # tipo de análisis + perfil táctico (se rellena cuando se conoce la acción)
        st.button("Analizar Opción", type="primary", icon=":material/bolt:", width="stretch", key="ox_go")

ticker = tk_in or "SPY"
try:  # próxima publicación de resultados (riesgo de gap e IV crush) y vela de evento reciente
    from core import eventos as EV
    RES_PROX = EV.proximos_resultados(ticker, CAL.hoy_ny())
except Exception:
    RES_PROX = None
try:
    _dd_ev = data.history_tf(ticker, "1D")
    EV_REC = EV.avisos(EV.analizar(ticker, _dd_ev, dias=10), _dd_ev, None)
except Exception:
    EV_REC = []
ss.ticker = ticker
TF, RNG = ss.get("opt_tf") or "1h", ss.get("opt_rng") or "1M"
if is_crypto(ticker):
    st.info("Las opciones solo están disponibles para acciones y ETF de EE. UU.")
    st.stop()

SETTINGS = ss.get("technical_settings") or profiles.BASE_SETTINGS
SETS = profiles.merge_settings(ss.get("technical_settings"))


def _guardar_perfil(p: dict, todas: bool):
    profiles.save_user_view(settings=PO.guardar(profiles.merge_settings(ss.get("technical_settings")), ticker, p, todas))


_DESC_CL = {"ITM": "dentro del dinero: más caro, se mueve casi como la acción",
            "ATM": "en el dinero: equilibrio entre costo y velocidad",
            "OTM": "fuera del dinero: barato y apalancado, sensible a la theta"}


@st.dialog("Primer análisis de opciones", width="medium")
def _dlg_primer(tk: str):
    st.markdown(f"**¿Con qué contratos trabajas en {tk}?** Elige una, dos o las tres. Es obligatorio: el motor solo "
                "buscará en las clases que actives, por encima de cualquier otro criterio (también en el modo Default).")
    cl = st.pills("Clases de contrato", list(PO.CLASES), selection_mode="multi", key="pp_clases")
    st.markdown("".join(f"<div class='muted small'><b>{k}</b> · {v}</div>" for k, v in _DESC_CL.items()),
                unsafe_allow_html=True)
    alc = st.segmented_control("Guardar esta elección para", [f"Solo {tk}", "Todas mis acciones"],
                               default=f"Solo {tk}", key="pp_alc") or f"Solo {tk}"
    if cl == ["OTM"]:
        st.caption("Con solo OTM, el estilo «cierro antes, por ganancia» es el que mejor encaja; si eliges esperar al "
                   "vencimiento, la app te avisará de la baja probabilidad.")
    b1, b2 = st.columns(2)
    p = PO.normalizar({**PO.DEFAULT, "clases": cl or []})
    if b1.button("Ajustar mi perfil táctico", disabled=not cl, width="stretch"):
        _guardar_perfil(p, alc.startswith("Todas"))
        ss["ox_editar"] = True
        st.rerun()
    if b2.button("Analizar con valores por defecto", type="primary", disabled=not cl, width="stretch"):
        _guardar_perfil(p, alc.startswith("Todas"))
        st.rerun()
    if not cl:
        st.caption("Activa al menos una clase para continuar.")


PERFIL, ALCANCE = PO.leer(SETS, ticker)
if PERFIL is None:
    _dlg_primer(ticker)
    st.info(f"Elige con qué contratos trabajas para analizar las opciones de {ticker}.")
    st.stop()
MODO_PERFIL = (ss.get("opt_modo") or "Mi perfil") == "Mi perfil"
MONEY = PERFIL["clases"]
MONEY_TXT = " + ".join(MONEY)
try:
    with st.spinner(f"Analizando {ticker}…"):
        A = analisis_usuario(ticker, TF, cfg, profiles.engine_settings(SETTINGS))
        CH, INFO = OP.chain(ticker, round(float(A["df"]["Close"].iloc[-1]), 1), OP.RANGOS[RNG])
except Exception as e:
    st.error(f"No se pudo analizar {ticker}: {e}")
    st.stop()
if CH.empty:
    st.warning(f"{ticker} no tiene opciones listadas en Alpaca dentro del rango elegido.")
    st.stop()

d = A["df"]
spot = float(d["Close"].iloc[-1])
r_ = d.iloc[-1]
MET = A.get("metodo") or {}
ADX, CON = MET.get("adx") or {}, MET.get("consolidado") or {}
VP = A.get("vprofile") or {}
MX = A.get("metrics") or {}
PLAN = A.get("plan") or {}
ESC = CON.get("escenario_base") or "Neutral"
COMB = float(A.get("combinado") or 0)
try:
    if data._demo():  # en demo las series 1D y 1h son sintéticas e independientes
        raise ValueError
    ult, prev = _diario(ticker)
except Exception:
    ult, prev = spot, float(d["Close"].iloc[-8] if len(d) > 8 else d["Close"].iloc[0])
SM = OP.resumen(CH, spot)
WALLS = OP.muros(CH)
GEXS = OP.gex_por_strike(CH, spot)
CONF = OP.confluencias(WALLS, VP, spot)
VENT = OP.RANGOS[RNG]
INV = float(ss.get("opt_inv") or 0)
BAL = PORT + INV
rsi = float(r_["RSI"])

# ---- multi-temporalidad: la temporalidad elegida + dos mayores; los pesos dependen del vencimiento
AN = {TF: A}
with st.spinner("Analizando temporalidades mayores…"):
    for _t in MTF.triada(TF):
        if _t not in AN:
            try:
                AN[_t] = analisis_usuario(ticker, _t, cfg, profiles.engine_settings(SETTINGS))
            except Exception:
                pass
ss.setdefault("opt_sel", 1)
H_TIER = {1: float(min(max(VENT * 0.6, 14), 45)), 2: 7.0, 3: 1.5}  # horizonte típico de cada nivel
MT0 = MTF.combinar(AN, H_TIER.get(ss["opt_sel"], 14), TF) if len(AN) > 1 else None
NIVM = (MT0 or {}).get("niveles") or []
SC_MTF = MT0["puntaje"] if MT0 else COMB

# lado principal: el del puntaje multi-temporalidad para el horizonte del nivel elegido
LADO = "CALL" if SC_MTF >= 0 else "PUT"
OPUESTO = "PUT" if LADO == "CALL" else "CALL"


def _mtf_dte(dte: int):
    """Análisis multi-temporalidad con los pesos del vencimiento exacto de un contrato."""
    if len(AN) < 2:
        return None
    m_ = MTF.combinar(AN, max(float(dte), 0.5), TF)
    ob = m_["limites"].get("objetivo")
    return {"puntaje": m_["puntaje"], "niveles": m_["niveles"], "objetivo": ob["precio"] if ob else None,
            "pesos": {k: round(v, 3) for k, v in m_["pesos"].items()}}


EVS = OP.evaluar_todos(CH, spot, LADO, WALLS, GEXS, NIVM, _mtf_dte)
EVS_OP = OP.evaluar_todos(CH, spot, OPUESTO, WALLS, GEXS, NIVM, _mtf_dte)
EVS_RAW = EVS
if MODO_PERFIL:
    EVS = PO.anotar(EVS, spot, PERFIL, RES_PROX)
    _FILTRO = lambda e: e.get("tac_estado") == "ok"  # noqa: E731
    _CLAVE = PO.orden if PERFIL["estilo"] == "tactico" else (lambda e: -(e.get("tac") or {}).get("P", 0))  # noqa: E731
else:  # Default: el motor estándar (valor esperado), pero siempre dentro de las clases del perfil
    EVS = PO.marcar_clases(EVS, spot)
    _FILTRO = _CLAVE = None
EVS_OP = PO.marcar_clases(EVS_OP, spot)
NIV = OP.niveles(EVS, spot, MONEY, VENT, INV, _FILTRO, _CLAVE)


_VER_COL = {"VIABLE": GREEN, "EXIGENTE": AMBER, "ESPERAR": MUTED}


def _badge(ver: str, size: int = 11) -> str:
    vc = _VER_COL.get(ver, MUTED)
    return (f'<span style="font-family:{MONO};font-size:{size}px;font-weight:700;color:{vc};border:1px solid {vc}88;'
            f'background:{vc}1A;border-radius:6px;padding:2px 8px;white-space:nowrap">{ver}</span>')


def _tac_html(o: dict, cabecera: bool = True) -> str:
    """Fila de métricas del perfil táctico en la tarjeta OPT, con el veredicto."""
    t = o["tac"]
    ver = PO.veredicto(t, PERFIL)
    cab = (f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:8px'>"
           f"<span class='ox-lbl' style='margin:0'>Tu perfil · {E(' · '.join(PO.resumen(PERFIL)))}</span>"
           f"{_badge(ver)}</div>") if cabecera else ""
    if t.get("modo") == "vencimiento":
        return cab + (f"<div class='ox-g3'><div><span>Terminar con ganancia</span><b>{t['P']:.0f}%</b></div>"
                      f"<div><span>Breakeven</span><b>${t['be']:,.2f}</b></div>"
                      f"<div><span>Movimiento</span><b>{t['z']:.2f}σ</b></div></div>")
    rc = t.get("ruido_corte")
    ma_txt = "—" if t.get("meta_antes") is None else f"{t['meta_antes']:.0f}%"
    col_r = RED if (rc or 0) >= 50 else AMBER if (rc or 0) >= 35 else "#E6EDF3"
    return cab + (
        f"<div class='ox-g3'><div><span>Meta +{PERFIL['meta']}% en</span><b>${t['s_meta']:,.2f}</b>"
        f"<i class='muted small' style='display:block;font-style:normal'>{t['mov_meta']:+.1f}% · {t['z']:.2f}σ</i></div>"
        f"<div><span>Tocar la meta ({PERFIL['dias']} ses.)</span><b>{t['P']:.0f}%</b></div>"
        f"<div><span>Meta antes que el corte</span><b>{ma_txt}</b></div>"
        f"<div><span>Te saca el ruido</span><b style='color:{col_r}'>{'—' if rc is None else f'{rc:.0f}%'}</b>"
        + (f"<i class='muted small' style='display:block;font-style:normal'>corte ${t['s_corte']:,.2f}</i>" if t.get("s_corte") else "") + "</div>"
        f"<div><span>Quieto {PERFIL['dias']} ses.</span><b style='color:{RED if t['quieto'] <= -15 else '#E6EDF3'}'>"
        f"{t['quieto']:+.0f}%</b></div>"
        f"<div><span>Resiste estancamiento</span><b>{'—' if not t.get('resiste') else str(t['resiste']) + ' d'}</b></div></div>")


# ---- editor del perfil táctico (ventana con guía y cálculo en vivo sobre la cadena actual)
_META_OPS = {"+20 %": 20, "+30 %": 30, "+50 %": 50, "+100 %": 100}
_CORTE_OPS = {"−25 %": 25, "−35 %": 35, "−50 %": 50, "Sin corte": 0}
_EST_OPS = {"Cierro antes, por ganancia": "tactico", "Espero al vencimiento": "vencimiento"}
_AP_OPS = {v["txt"]: k for k, v in PO.APETITO.items()}
_RES_OPS = {"Evitar": "evitar", "Permitir con alerta": "permitir"}


def _abrir_editor():
    inv = lambda d, v: next(k for k, x in d.items() if x == v)  # noqa: E731
    ss["pe_clases"] = list(PERFIL["clases"])
    ss["pe_alc"] = "Todas mis acciones" if ALCANCE == "todas" else f"Solo {ticker}"
    ss["pe_est"] = inv(_EST_OPS, PERFIL["estilo"])
    ss["pe_meta"] = inv(_META_OPS, PERFIL["meta"]) if PERFIL["meta"] in _META_OPS.values() else "+50 %"
    ss["pe_corte"] = inv(_CORTE_OPS, PERFIL["corte"]) if PERFIL["corte"] in _CORTE_OPS.values() else "−35 %"
    ss["pe_dias"] = int(PERFIL["dias"])
    ss["pe_ap"] = PO.APETITO[PERFIL["apetito"]]["txt"]
    ss["pe_res"] = inv(_RES_OPS, PERFIL["resultados"])
    _dlg_editor()


@st.dialog("Perfil táctico de opciones", width="large")
def _dlg_editor():
    c1, c2 = st.columns([1.05, 1], gap="medium")
    with c1:
        cl = st.pills("1 · Con qué contratos trabajas (regla maestra)", list(PO.CLASES), selection_mode="multi",
                      key="pe_clases")
        alc = st.segmented_control("Guardar para", [f"Solo {ticker}", "Todas mis acciones"], key="pe_alc") or f"Solo {ticker}"
        est = _EST_OPS[st.segmented_control("2 · Cómo cierras tus operaciones", list(_EST_OPS), key="pe_est")
                       or "Cierro antes, por ganancia"]
        tac = est == "tactico"
        meta = _META_OPS[st.segmented_control("3 · Ganancia con la que cierras (sobre la prima)", list(_META_OPS),
                                              key="pe_meta", disabled=not tac) or "+50 %"]
        corte = _CORTE_OPS[st.segmented_control("4 · Pérdida máxima que aceptas (sobre la prima)", list(_CORTE_OPS),
                                                key="pe_corte", disabled=not tac) or "−35 %"]
        dias = int(st.number_input("5 · Días que sueles sostener la posición (sesiones)", 1, 15, step=1, key="pe_dias",
                                   disabled=not tac))
        ap = _AP_OPS[st.segmented_control("6 · ¿Qué tan probable debe ser tu meta?", list(_AP_OPS), key="pe_ap")
                     or "Equilibrado"]
        res = _RES_OPS[st.segmented_control("7 · Resultados trimestrales", list(_RES_OPS), key="pe_res") or "Evitar"]
    tmp = PO.normalizar({"clases": cl or [], "estilo": est, "meta": meta, "corte": corte, "dias": dias,
                         "apetito": ap, "resultados": res})
    with c2:
        if not cl:
            st.warning("Activa al menos una clase: el motor necesita un universo de contratos.")
            return
        an = PO.anotar(EVS_RAW, spot, tmp, RES_PROX, max_sim=25)
        fil = lambda e: e.get("tac_estado") == "ok"  # noqa: E731
        cla = PO.orden if tac else (lambda e: -(e.get("tac") or {}).get("P", 0))
        niv = OP.niveles(an, spot, tmp["clases"], VENT, None, fil, cla)
        best = niv.get(1) or niv.get(2) or niv.get(3)
        ver = PO.veredicto(best["tac"] if best else None, tmp)
        st.markdown(f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                    f"<span class='ox-lbl' style='margin:0'>Viabilidad con {E(ticker)} hoy · {LADO}</span>"
                    f"{_badge(ver, 12)}</div>", unsafe_allow_html=True)
        msgs = [f"Universo: solo {' + '.join(tmp['clases'])}. Ningún otro ajuste, ni el modo Default, recomienda otra clase."]
        if best:
            t = best["tac"]
            st.markdown(f"<div class='muted small'>Contrato elegido: <b style='color:#E6EDF3'>{E(best['contrato'])} · "
                        f"{E(best['vencimiento'])} · {E(best['clase'])}</b></div>"
                        + _tac_html_tmp(best, tmp), unsafe_allow_html=True)
            msgs += PO.avisos(t, tmp, best, spot)
        else:
            mo = {}
            for e in an:
                mo[e.get("tac_estado")] = mo.get(e.get("tac_estado"), 0) + 1
            msgs.append(f"Ningún contrato {' + '.join(tmp['clases'])} cumple hoy estas reglas "
                        f"({mo.get('bloqueado', 0)} bloqueados por meta improbable, {mo.get('apetito', 0)} bajo tu apetito, "
                        f"{mo.get('resultados', 0)} cruzan resultados): el resultado sería ESPERAR.")
        for m_ in msgs:
            st.markdown(f"<div class='ox-exp' style='font-size:12px;margin:4px 0'>{E(m_)}</div>", unsafe_allow_html=True)
        st.caption(f"Límites fijos: se bloquea una meta que exija más de {PO.SIGMA_BLOQUEO}σ o tenga menos de "
                   f"{PO.P_BLOQUEO:.0f} % de probabilidad · spread ≤ 25 % · vencimiento ≥ {PO.dte_minimo(tmp)} días "
                   "recomendado. Probabilidades con la IV de cada prima y sin ventaja direccional.")
        en_uni = [e for e in an if e.get("tac")]
        bloqueado = bool(en_uni) and all(e["tac_estado"] in ("bloqueado", "resultados") for e in en_uni)
        b1, b2 = st.columns(2)
        if b1.button("Restablecer", width="stretch"):
            for k_ in ("pe_est", "pe_meta", "pe_corte", "pe_dias", "pe_ap", "pe_res"):
                ss.pop(k_, None)
            st.rerun(scope="fragment")
        if b2.button("No se puede guardar: meta fuera de rango" if bloqueado else "Guardar perfil", type="primary",
                     disabled=bloqueado, width="stretch"):
            _guardar_perfil(tmp, alc.startswith("Todas"))
            st.rerun()


def _tac_html_tmp(o, p):
    global PERFIL
    guard = PERFIL
    try:
        PERFIL = p
        return _tac_html(o, cabecera=False)
    finally:
        PERFIL = guard


# bloque del perfil en la columna izquierda
with perf_ph.container():
    st.segmented_control("Tipo de análisis", ["Mi perfil", "Default"], key="opt_modo",
                         help="Mi perfil: meta, corte y días de tu perfil táctico. Default: el motor estándar (valor "
                              "esperado), siempre dentro de tus clases de contrato.")
    _chips = "".join(f"<span class='ox-chip'>{E(c)}</span>" for c in PO.resumen(PERFIL))
    st.markdown(f"<div class='ox-lbl'>Perfil táctico · {'todas tus acciones' if ALCANCE == 'todas' else E(ticker)}</div>"
                f"<div class='ox-chips'>{_chips}</div>"
                + ("" if MODO_PERFIL else "<div class='muted small'>Modo Default: sin meta, corte ni días del perfil; "
                   f"solo contratos {E(MONEY_TXT)}.</div>"), unsafe_allow_html=True)
    if st.button("Editar perfil", key="ox_edit", width="stretch", icon=":material/tune:"):
        ss["ox_editar"] = True
if ss.pop("ox_editar", False):
    _abrir_editor()
if not NIV.get(ss["opt_sel"]):
    ss["opt_sel"] = next((t for t in (1, 2, 3) if NIV.get(t)), 1)
SEL = NIV.get(ss["opt_sel"])
AJ = (SEL or {}).get("ajuste")
# con el contrato elegido, los pesos se recalculan con su vencimiento exacto
MT = MTF.combinar(AN, max(SEL["dte"], 0.5), TF) if (SEL and len(AN) > 1) else MT0

# balance e inversión (con destello si el presupuesto limita el pronóstico)
with inv_ph.container():
    pct_inv = INV / BAL * 100 if BAL else 0
    st.markdown(f"<div class='ox-lbl'>Balance</div><div class='ox-mbar'><div style='width:100%'></div></div>"
                f"<div style='font-family:{MONO};font-size:14px;margin:-2px 0 0'>{_m(BAL)}</div>"
                f"<div class='muted small' style='margin:0 0 6px'>Portafolio {_m(PORT)} + inversión {_m(INV)}</div>",
                unsafe_allow_html=True)
    if AJ:
        st.markdown("<style>.st-key-opt_inv input{animation:oxinv 1s ease-in-out infinite}"
                    f"@keyframes oxinv{{0%,100%{{box-shadow:inset 0 0 0 1px {AMBER}55}}50%{{box-shadow:inset 0 0 0 2px {AMBER};"
                    "background:rgba(210,153,34,.15)}}</style>", unsafe_allow_html=True)
    st.markdown(f"<div class='ox-invl'><span>Inversión (USD)</span><b>{pct_inv:.0f}% del bal.</b></div>",
                unsafe_allow_html=True)
    st.number_input("Inversión (USD)", 0.0, 1e8, step=5.0, format="%.2f", key="opt_inv", label_visibility="collapsed")
    st.markdown(f"<div class='ox-mbar'><div style='width:{min(pct_inv, 100):.0f}%;background:{ACC}'></div></div>",
                unsafe_allow_html=True)

# ================================================================== cabecera (fila superior)
chg = ult - prev
chg_pct = chg / prev * 100 if prev else 0
cc = GREEN if chg >= 0 else RED
with top_a:
    st.markdown(f"<div class='ox-h'>{E(ticker)}</div><div class='ox-name'>{E(str(MX.get('Nombre') or ''))}</div>"
                f"<div class='ox-q'><span>ÚLTIMA</span><b>{ult:,.2f}</b>"
                f"<span>CBO</span><b style='color:{cc}'>{chg:+,.2f} {'▲' if chg >= 0 else '▼'}</b>"
                f"<span>CAMBIO</span><b style='color:{cc}'>{chg_pct:+.2f}% {'▲' if chg >= 0 else '▼'}</b></div>",
                unsafe_allow_html=True)

MK = float(np.clip(((MT['puntaje'] if MT else COMB) + 100) / 2, 0, 100))
mk_lbl, mk_col = (("STRONG BUY", GREEN) if MK >= 70 else ("BUY", GREEN) if MK >= 57 else ("NEUTRAL", MUTED)
                  if MK > 43 else ("SELL", RED) if MK > 30 else ("STRONG SELL", RED))
if MT and MT["estado"] in ("Mixto", "Lateral") and mk_lbl != "NEUTRAL":  # sin acuerdo entre temporalidades no hay señal limpia
    mk_lbl, mk_col = MT["estado"].upper(), MUTED
PC = OP.porcentaje_calls(CH)
op_lbl = SEL["tipo"] if SEL else "ESPERAR"
op_col = GREEN if op_lbl == "CALL" else RED if op_lbl == "PUT" else MUTED


def _bar(t, pct, lbl, col):
    return (f"<div class='ox-bar'><span class='t'>{t}</span><div class='tr'><div class='fl' style='width:{pct:.0f}%;"
            f"background:{col}'></div></div><span class='p'>{pct:.0f}%</span>"
            f"<span class='b' style='background:{col}22;color:{col};border:1px solid {col}88'>{lbl}</span></div>")


FLUJO = OP.flujo_neto(CH)
with top_b:
    ema_x = "EMA9 > EMA21" if r_["EMA9"] > r_["EMA21"] else "EMA9 < EMA21"
    filas = [
        ("Alineación " + " · ".join(f["tf"] for f in MT["filas"]) if MT else "Alineación",
         " ".join("▲" if f["puntaje"] >= 15 else "▼" if f["puntaje"] <= -15 else "◆" for f in MT["filas"]) + f"  {MT['estado']}"
         if MT else "—"),
        ("Precio vs VWAP 20", f"{(spot / r_['VWAP20'] - 1) * 100:+.2f}%"),
        ("Cruce de medias", ema_x),
        ("SMA50 / SMA200", f"{r_['SMA50']:,.2f} / {r_['SMA200']:,.2f}" if pd.notna(r_["SMA200"]) else f"{r_['SMA50']:,.2f} / —"),
        (f"RSI 14 ({TF})", f"{rsi:.1f}"),
        ("MACD hist.", f"{r_['MACD_hist']:+.3f}"),
        ("ADX 14/14/23", f"{ADX.get('adx', '—')} · {ADX.get('regimen', '')}"),
        ("POC VRVP", _m(VP.get("poc"))),
        ("VAH / VAL", f"{_m(VP.get('vah'), '')} / {_m(VP.get('val'), '')}"),
        ("Flujo neto opciones", f"{OP._fmt_m(FLUJO)} {'calls' if FLUJO >= 0 else 'puts'}"),
        ("PCR vol. / OI", f"{SM['pcr_volumen'] or '—'} / {SM['pcr_open_interest'] or '—'}"),
        (f"IV ATM ({SM.get('iv_atm_dte', 30)}d)", "—" if SM["iv_rank_or_avg_iv"] is None else f"{SM['iv_rank_or_avg_iv']:.1f}%"),
        ("GEX / gamma flip", f"{SM['net_gamma_exposure_gex'].split(' ')[0]} / {_m(SM.get('gamma_flip_level'), '')}"),
        ("Max pain", _m(SM.get("max_pain"))),
        ("P/E forward", "—" if not MX.get("P/E forward") else f"{MX['P/E forward']:.1f}"),
        ("Próx. resultados", f"{RES_PROX:%d/%m/%y}" if RES_PROX else "—"),
        ("Próximo feriado bolsa", next((f"{d_:%d/%m} {n_[:22]}" for d_, n_ in CAL.proximos(CAL.hoy_ny(), 1)), "—")),
    ]
    st.markdown(_bar("MARKET", MK, mk_lbl, mk_col)
                + "<div class='ox-box'><h4>Datos técnicos y fundamentales</h4><div class='ox-dt'>"
                + "".join(f"<div><span>{E(a)}</span><b>{E(str(b))}</b></div>" for a, b in filas) + "</div></div>",
                unsafe_allow_html=True)

with top_c:
    st.markdown(_bar("OPTIONS", PC or 0, op_lbl, op_col), unsafe_allow_html=True)
    with st.container(border=True, key="ox_best"):
        st.markdown("<div class='ox-lbl'>Mejor strike disponible</div>", unsafe_allow_html=True)
        _vis_opts = [f"OPT{t}" for t in (1, 2, 3)]
        ss.setdefault("ox_view", f"OPT{ss['opt_sel']}")
        vis = st.segmented_control("Nivel", _vis_opts, key="ox_view", label_visibility="collapsed") or f"OPT{ss['opt_sel']}"
        tv = int(vis[-1])
        O = NIV.get(tv)
        nom, dsc, _ = OP.TIERS[tv]
        if not O:
            if MODO_PERFIL:
                _mo = PO.motivos(EVS, MONEY, VENT, tv, spot)
                _det = ", ".join(f"{n} {t}" for t, n in (("fuera de tus clases", _mo.get("fuera", 0)),
                                                        ("bloqueados por meta improbable", _mo.get("bloqueado", 0)),
                                                        ("bajo tu apetito", _mo.get("apetito", 0)),
                                                        ("cruzan resultados", _mo.get("resultados", 0))) if n)
                st.markdown(f"<div class='ox-st'><span class='k' style='color:{MUTED}'>ESPERAR</span>"
                            f"<span class='muted small'>{nom} · {dsc}</span></div>"
                            f"<div class='muted small'>Ningún contrato {E(MONEY_TXT)} cumple hoy tu perfil"
                            + (f" ({E(_det)})" if _det else "") + ". No se recomienda otra clase.</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='muted small'>{nom}: sin contratos líquidos {E(MONEY_TXT)} con {dsc}.</div>",
                            unsafe_allow_html=True)
        else:
            colr = GREEN if O["tipo"] == "CALL" else RED
            cont = (f"{O['contratos']} contrato(s) · ${O['contratos'] * O['costo']:,.0f}" if O.get("contratos")
                    else "fuera de presupuesto" if INV else "")
            st.markdown(
                f"<div class='ox-st'><span class='k' style='color:{colr}'>${O['strike']:g} {O['tipo'][0]}</span>"
                f"<span class='v'>{E(O['vencimiento'])} · {O['dte']} DTE · {O['sesiones_venc']} ses.</span>"
                f"<span class='muted small'>{nom} · {dsc}</span></div>"
                f"<div class='ox-g3'><div><span>Prima</span><b>${O['prima']:,.2f}</b></div>"
                f"<div><span>Costo total</span><b>${O['costo']:,.0f}</b></div>"
                f"<div><span>R/R</span><b>1:{O['rr']:.1f}</b></div><div><span>Breakeven</span><b>${O['breakeven']:,.2f}</b></div>"
                f"<div><span>Delta</span><b>{O['delta']:+.2f}</b></div><div><span>Theta</span><b>{O['theta'] or 0:+.2f}</b></div>"
                f"<div><span>Prob. éxito</span><b style='color:{colr}'>{O['pop']:.0f}%</b></div>"
                f"<div><span>Valor esperado</span><b>{O['ve']:+.1f}%</b></div>"
                f"<div><span>Clase</span><b>{E(O.get('clase', '—'))}</b></div></div>"
                + (_tac_html(O) if MODO_PERFIL and O.get("tac") else "")
                + f"<div class='ox-just'><b>Justificación:</b> objetivo ${O['objetivo']:,.2f} (muro / movimiento esperado) en "
                f"≤ {O['horizonte_dias']:.0f} días; si lo alcanza {O['roi_objetivo']:+.0f}%, si el precio no se mueve "
                f"{O['roi_sin_movimiento']:+.0f}%." + (f" <span class='muted'>{cont}</span>" if cont else "") + "</div>",
                unsafe_allow_html=True)
            if st.button(f"Seleccionar strike (OPT{tv})", key="ox_pick", width="stretch",
                         type="primary" if tv != ss["opt_sel"] else "secondary", disabled=tv == ss["opt_sel"]):
                ss["opt_sel"] = tv
                st.rerun()

# ================================================================== análisis manual (columna izquierda)
with left:
    with st.container(border=True, key="ox_man"):
        st.markdown("<div class='ox-lbl'>Análisis manual</div>", unsafe_allow_html=True)
        m_tipo = st.segmented_control("Tipo", ["CALL", "PUT"], default=LADO, key=f"man_tipo_{ticker}",
                                      label_visibility="collapsed") or LADO
        ks_all = sorted(CH[CH["type"] == m_tipo.lower()]["strike"].unique())
        if m_tipo == "CALL":
            k_def = next((k for k in ks_all if k > spot), ks_all[-1])
        else:
            k_def = next((k for k in reversed(ks_all) if k < spot), ks_all[0])
        paso = float(np.min(np.diff(ks_all))) if len(ks_all) > 1 else 1.0
        m_k = st.number_input("Strike", float(min(ks_all)), float(max(ks_all)), float(k_def), step=paso, format="%.2f",
                              key=f"man_k_{ticker}_{m_tipo}")
        m_d = st.number_input("Rango (días)", 0, int(CH["dte"].max()), min(10, int(CH["dte"].max())), 1, key=f"man_d_{ticker}")
        m_money = st.segmented_control("Money", ["ITM", "OTM", "ATM"], default="OTM", key=f"man_m_{ticker}") or "OTM"
        if m_money == "OTM":
            ok_m = m_k > spot if m_tipo == "CALL" else m_k < spot
        elif m_money == "ITM":
            ok_m = m_k < spot if m_tipo == "CALL" else m_k > spot
        else:
            ok_m = abs(m_k / spot - 1) <= 0.025
        if not ok_m:
            regla = {("CALL", "OTM"): "mayor", ("CALL", "ITM"): "menor", ("PUT", "OTM"): "menor", ("PUT", "ITM"): "mayor"}
            msg = (f"Para {m_tipo}/{m_money}, el strike debe ser {regla[(m_tipo, m_money)]} al precio del subyacente "
                   f"({spot:,.2f} USD)." if m_money != "ATM" else
                   f"Para ATM, el strike debe estar a ±2.5% del precio del subyacente ({spot:,.2f} USD).")
            st.markdown(f"<div class='ox-red'><b>ALERTA:</b> {E(msg)}</div>", unsafe_allow_html=True)
        if st.button("Analizar Opción", icon=":material/bolt:", width="stretch", key="ox_man_go", disabled=not ok_m,
                     type="primary"):
            ks_t = np.array(ks_all)
            k_real = float(ks_t[np.argmin(abs(ks_t - m_k))])
            exps = sorted(CH["exp"].unique())
            dtes = [int(CH[CH["exp"] == e]["dte"].iloc[0]) for e in exps]
            e_real = exps[int(np.argmin([abs(x - m_d) for x in dtes]))]
            row = OP.contrato(CH, e_real, k_real, m_tipo)
            ss[f"man_res_{ticker}"] = (OP.evaluar(row, spot, CH, WALLS, GEXS, NIVM, _mtf_dte(int(row["dte"])))
                                       if row is not None else None)
MAN = ss.get(f"man_res_{ticker}")

# ================================================================== contraria (escenario alternativo)
stop_ = PLAN.get("stop")
if MT and MT["limites"].get("invalidacion"):
    stop_ = MT["limites"]["invalidacion"]["precio"]
if LADO == "CALL":
    pw_ = [w["strike"] for w in WALLS["put_walls"] if w["strike"] < spot]
    disparo = max([x for x in [stop_] + pw_ if x is not None and x < spot] or [spot * 0.97])
else:
    cw_ = [w["strike"] for w in WALLS["call_walls"] if w["strike"] > spot]
    disparo = min([x for x in [stop_] + cw_ if x is not None and x > spot] or [spot * 1.03])
ALT = OP.contraria(EVS_OP, spot, MONEY, VENT, disparo, OPUESTO)
ALT2 = None
if EVS_OP and ALT:
    _l2 = OP.opciones_tier(EVS_OP, spot, MONEY, VENT, 2)
    if _l2 and (_l2[0]["contrato"], _l2[0]["exp"]) != (ALT["contrato"], ALT["exp"]):
        ALT2 = dict(_l2[0])
        ALT2["disparo"] = disparo
        ALT2["limite"] = OP.bs_price(disparo, ALT2["strike"], max(ALT2["dte"] - 1, 0.25) / 365, ALT2["iv"] / 100,
                                     OPUESTO == "CALL")

# ================================================================== lectura IA (opcional)
payload = {
    "ticker": ticker, "spot_price": round(spot, 2), "timestamp_utc": INFO["timestamp_utc"],
    "technical_context": {"timeframe": TF.upper(), "adx_14_14_23": ADX.get("adx"), "regimen_adx": ADX.get("regimen"),
                          "escenario": ESC, "confianza_global": CON.get("confianza_global"), "market_pct": round(MK),
                          "rsi": round(rsi, 1), "macd_hist": round(float(r_["MACD_hist"]), 4),
                          "vrvp_poc": VP.get("poc"), "vrvp_vah": VP.get("vah"), "vrvp_val": VP.get("val")},
    "options_summary": SM, "key_liquidity_walls": {k: v for k, v in WALLS.items() if k != "criterio"},
    "confluencias_vrvp": CONF, "flujo_neto_usd": FLUJO, "porcentaje_calls": PC,
    "opt_tiers": {f"OPT{t}": (None if not v else {k: v[k] for k in ("contrato", "vencimiento", "dte", "prima", "breakeven",
                                                                    "delta", "pop", "ve", "objetivo")})
                  for t, v in NIV.items()},
    "inversion_usd": INV, "info": INFO, "multi_temporalidad": MTF.resumen_ia(MT) if MT else None,
}
akey = f"opt_ai_{ticker}_{TF}"
RAI = ss.get(akey)


def _explicacion(o: dict) -> str:
    """Cómo se hizo el análisis y cómo interactuaron los datos técnicos con la cadena de opciones."""
    sesgo_txt = {"Alcista": "alcista", "Bajista": "bajista"}.get(ESC, "neutral")
    w_fav = (WALLS["call_walls"] if o["tipo"] == "CALL" else WALLS["put_walls"])
    wtxt = ", ".join(f"{w['strike']:g}" for w in w_fav) or "—"
    conf = "; ".join(f"{c['tipo'].lower()} {c['strike']:g} coincide con el {c['nodo_vrvp']} del VRVP" for c in CONF[:2])
    em = o.get("mov_esperado") or SM.get("expected_move_usd")  # el del vencimiento del contrato
    _tec = float((A.get("tech") or {}).get("score", COMB))
    _fs = (A.get("fscore") or {}).get("score")
    t = (f"<b>1 · Motor cuantitativo (70 %).</b> Escenario <b>{sesgo_txt}</b> en {TF}: puntaje técnico "
         f"<b>{_tec:+.0f}</b>" + (f" (fundamental {_fs:+.0f}, se pondera aparte según el horizonte)" if _fs is not None else "")
         + f", ADX <b>{ADX.get('adx', '—')}</b> ({'tendencia' if ADX.get('regimen') == 'tendencia' else 'rango'} "
         f"respecto al nivel 23), RSI <b>{rsi:.1f}</b>, MACD {'positivo' if r_['MACD_hist'] > 0 else 'negativo'} y "
         f"precio {'sobre' if spot > (VP.get('poc') or spot) else 'bajo'} el POC del VRVP (<b>{_m(VP.get('poc'))}</b>). "
         f"<br><b>2 · Flujo de opciones (30 %).</b> GEX {SM['net_gamma_exposure_gex'].lower()} "
         f"({'movimientos amortiguados, el precio gravita hacia muros y max pain' if (SM.get('gex_total') or 0) >= 0 else 'movimientos amplificados'}); "
         f"PCR {SM['pcr_open_interest'] or SM['pcr_volumen'] or '—'}; flujo neto {OP._fmt_m(FLUJO)}; "
         f"muros a favor en <b>{wtxt}</b>" + (f"; {conf}" if conf else "") + "."
         f"<br><b>3 · Selección del contrato.</b> Se evaluaron {len(EVS)} contratos {o['tipo']} líquidos con money "
         f"{MONEY_TXT}. El objetivo es <b>{_m(o['objetivo'])}</b> (primer muro o nivel fuerte a favor, acotado por el movimiento esperado"
         + (f" del vencimiento ±{_m(em)}" if em else "") + f"). El <b>{o['contrato']} · {o['vencimiento']}</b> maximiza el valor esperado "
         f"(<b>{o['ve']:+.1f}%</b>): {o['p_toque']:.0f}% de probabilidad de tocar el objetivo en {o['horizonte_dias']:.0f} "
         f"días, {o['roi_objetivo']:+.0f}% si lo toca y {o['roi_sin_movimiento']:+.0f}% si el precio no se mueve. "
         f"Probabilidad de terminar con ganancia al vencimiento: <b>{o['pop']:.0f}%</b>.")
    if MT:
        pw_txt = " / ".join(f"{f['tf']} {f['peso'] * 100:.0f}%" for f in MT["filas"])
        L_ = MT["limites"]
        t += (f"<br><b>4 · Multi-temporalidad.</b> Con {o['dte']} días al vencimiento los pesos son {pw_txt} "
              f"(a menor plazo mandan las temporalidades menores; a mayor plazo, las mayores). Puntaje técnico "
              f"<b>{MT.get('puntaje_tecnico', MT['puntaje']):+.0f}</b>, con fundamental <b>{MT['puntaje']:+.0f}</b>, alineación <b>{MT['alineacion'] * 100:.0f}%</b>: <b>{MT['estado'].lower()}</b>. "
              f"Objetivo {MTF.etiqueta(L_['objetivo'])}, invalidación {MTF.etiqueta(L_['invalidacion'])}, "
              f"segundo nivel {MTF.etiqueta(L_['segundo_nivel'])}.")
        if MT["estado"] in ("Rebote contra la tendencia mayor", "Operativa en contra"):
            t += " <b>Cuidado:</b> la operación va contra una temporalidad de peso; conviene un vencimiento corto y tamaño menor."
    if ESC == "Neutral":
        t += (" <br><b>Atención:</b> el escenario es neutral; esta opción es un escenario condicionado a la ruptura "
              "a favor, no una señal confirmada.")
    return t


def _riesgos_html(o):
    rs = ((PO.avisos(o["tac"], PERFIL, o, spot) if MODO_PERFIL and o.get("tac") else []) + EV_REC
          + OP.riesgos(o, ESC, ADX, SM.get("gex_total") or 0, SM.get("gamma_flip_level"), spot, RES_PROX))
    return ("<div class='ox-box'><h4>Riesgos y cuidados</h4><ul style='margin:0 0 0 16px;padding:0;font-size:12px'>"
            + "".join(f"<li>{E(x)}</li>" for x in rs) + "</ul></div>") if rs else ""


def _graficos(principal: dict, extra=()):
    cs = [{"nombre": principal["contrato"] + " · " + principal["vencimiento"], "tipo": principal["tipo"],
           "strike": principal["strike"], "iv": principal["iv"] / 100, "prima": principal["prima"],
           "dte": max(principal["dte"], 1), "color": GREEN}]
    for n, c, col in extra:
        cs.append({"nombre": n, "tipo": c["tipo"], "strike": c["strike"], "iv": c["iv"] / 100, "prima": c["prima"],
                   "dte": max(c["dte"], 1), "color": col})
    ks_ = [c["strike"] for c in cs] + [principal["objetivo"], spot]
    lo, hi = min(min(ks_), spot * 0.93), max(max(ks_), spot * 1.07)
    pad = (hi - lo) * 0.06
    niv = ([{"v": w["strike"], "t": f"C-wall {w['strike']:g}", "c": RED} for w in WALLS["call_walls"]]
           + [{"v": w["strike"], "t": f"P-wall {w['strike']:g}", "c": GREEN} for w in WALLS["put_walls"]])
    if MT:
        for k_, c_ in (("objetivo", GREEN), ("invalidacion", RED), ("segundo_nivel", MUTED)):
            n_ = MT["limites"].get(k_)
            if n_:
                niv.append({"v": n_["precio"], "t": f"{n_['tipo']} {n_['tf']} {n_['precio']:,.0f}", "c": c_})
    components.html(PW.html(spot, principal["objetivo"], cs, int(round(principal["horizonte_dias"])), (lo - pad, hi + pad), niv),
                    height=385, scrolling=True)


# ================================================================== pestañas CALL / PUT (columna derecha)
with right:
    tabs_def = []
    if SEL:
        tabs_def.append((f"{SEL['tipo']} OPT{ss['opt_sel']}", "main", GREEN if SEL["tipo"] == "CALL" else RED))
    if ALT:
        tabs_def.append((f"{OPUESTO} {ALT['strike']:g}", "alt", GREEN if OPUESTO == "CALL" else RED))
    if ALT2:
        tabs_def.append((f"{OPUESTO} {ALT2['strike']:g} · {ALT2['dte']}d", "alt2", GREEN if OPUESTO == "CALL" else RED))
    if MAN:
        tabs_def.append((f"MANUAL {MAN['contrato']}", "man", AMBER))
    if not tabs_def:
        st.info("No hay contratos líquidos para los criterios elegidos. Cambia el rango visible o el money.")
    else:
        css = "".join(
            f".st-key-ox_tabs [data-testid='stTab']:nth-child({i + 1}){{border:1px solid {BORDER};border-bottom:0;"
            f"border-radius:6px 6px 0 0;padding:4px 14px;margin-right:4px;color:#8B949E}}"
            f".st-key-ox_tabs [data-testid='stTab']:nth-child({i + 1})[aria-selected='true']{{background:{c}22;"
            f"color:{c};border-color:{c}}}"
            for i, (_, _, c) in enumerate(tabs_def))
        st.markdown(f"<style>{css}.st-key-ox_tabs [data-baseweb='tab-highlight']{{display:none}}</style>",
                    unsafe_allow_html=True)
        with st.container(key="ox_tabs"):
            T_ = st.tabs([t[0] for t in tabs_def])
        for (lbl, kind, colr), tab in zip(tabs_def, T_):
            with tab:
                if kind == "main":
                    o = SEL
                    if RAI and RAI.get("diagnostico"):
                        _adv = "".join(f"<li>{E(str(a_))}</li>" for a_ in (RAI.get("advertencias") or [])[:4])
                        st.markdown(f"<div class='ox-box'><h4>Lectura de la IA · {E(RAI.get('_modelo', ''))}</h4>"
                                    f"<div class='ox-exp'>{E(RAI['diagnostico'])}</div>"
                                    + (f"<ul style='margin:6px 0 0 16px;padding:0;font-size:12px'>{_adv}</ul>" if _adv else "")
                                    + "</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='ox-box'><h4>Cómo se hizo el análisis · {E(o['contrato'])} · "
                                f"{E(o['vencimiento'])}</h4><div class='ox-exp'>{_explicacion(o)}</div></div>",
                                unsafe_allow_html=True)
                    if MT:
                        st.markdown(MTF.tarjeta_html(MT), unsafe_allow_html=True)
                        if (ss.get("profile") or {}).get("role") == "admin":
                            st.page_link("views/validacion.py", label="Calibrar la fórmula multi-temporalidad (admin)",
                                         icon=":material/query_stats:")
                    if AJ:
                        alt_ = AJ["alcanzable"]
                        st.markdown(
                            "<div class='ox-alert'><b>Inversión limitada:</b> con "
                            f"{_m(INV)} no alcanza para 1 contrato de {E(o['contrato'])} ({_m(o['costo'], dec=0)}). "
                            + (f"La opción más cercana dentro del presupuesto es <b>{E(alt_['contrato'])} · {E(alt_['vencimiento'])}</b> "
                               f"(valor esperado {AJ['impacto_ve']:+.1f} pts, probabilidad de éxito {AJ['impacto_pop']:+.0f} pts "
                               f"frente a OPT{ss['opt_sel']}). " if alt_ else "Ningún contrato de este nivel cabe en el presupuesto. ")
                            + f"Capital sugerido: óptimo <b>{_m(AJ['capital_optimo'], dec=0)}</b> · cercano "
                            f"<b>{_m(AJ['capital_cercano'], dec=0)}</b> ({E(AJ['contrato_cercano'])}).</div>",
                            unsafe_allow_html=True)
                        b1, b2, _ = st.columns([1, 1, 2])
                        if b1.button(f"Ajustar a {_m(AJ['capital_optimo'], dec=0)}", key="ox_aj1"):
                            ss["opt_inv_set"] = AJ["capital_optimo"]
                            st.rerun()
                        if AJ["capital_cercano"] != AJ["capital_optimo"] and b2.button(
                                f"Ajustar a {_m(AJ['capital_cercano'], dec=0)}", key="ox_aj2"):
                            ss["opt_inv_set"] = AJ["capital_cercano"]
                            st.rerun()
                    ex = [("Manual · " + MAN["contrato"] + " · " + MAN["vencimiento"], MAN, AMBER)] if MAN else []
                    _graficos(o, ex)
                    st.markdown(_riesgos_html(o), unsafe_allow_html=True)
                    _prof = ss.get("profile") or {}
                    _adm = _prof.get("role") == "admin"
                    _gk, _ck = store.secret("GEMINI_API_KEY"), cfg["anthropic_key"]
                    c1, c2, _ = st.columns([1, 1, 3])
                    g_cl = c1.button("Lectura Claude", icon=":material/auto_awesome:", disabled=not (_adm and _ck), key="ox_cl")
                    g_ge = c2.button("Lectura Gemini", icon=":material/bolt:", disabled=not _gk, key="ox_ge")
                    if g_cl or g_ge:
                        try:
                            with st.spinner("Analizando con IA…"):
                                out = (ai.analyze(payload, _ck, ai.MODELOS[cfg["modelo"]], system=ai.SYSTEM_OPCIONES) if g_cl
                                       else ai.analyze_gemini(payload, _gk, store.secret("GEMINI_MODEL") or None,
                                                              system=ai.SYSTEM_OPCIONES))
                            if _prof:
                                db.log_event(_prof["email"], "ai_options", f"{ticker} · {'claude' if g_cl else 'gemini'}")
                            ss[akey] = out
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error con la IA: {e}")
                elif kind in ("alt", "alt2"):
                    o = ALT if kind == "alt" else ALT2
                    dirx = "pierde" if LADO == "CALL" else "supera"
                    st.markdown(
                        f"<div class='ox-box'><h4>Escenario alternativo · {E(o['contrato'])} · {E(o['vencimiento'])}</h4>"
                        f"<div class='ox-exp'>El análisis principal es <b>{LADO}</b>. Esta opción {OPUESTO} solo aparecería "
                        f"si el precio <b>{dirx} {_m(o['disparo'])}</b> con cierre de vela y aumento de volumen/ADX "
                        f"(nivel que invalida el escenario principal: stop del plan o muro de "
                        f"{'puts' if LADO == 'CALL' else 'calls'}). <br><b>¿Considerarla?</b> "
                        + ("Solo como cobertura o ante un cambio de escenario confirmado; hoy va contra el motor cuantitativo. "
                           if ESC != "Neutral" else "El escenario es neutral: es tan válida como la principal si se confirma la ruptura. ")
                        + f"<br><b>Punto de entrada:</b> orden límite ≈ <b>{_m(o['limite'])}</b> por acción "
                        f"(prima estimada si el subyacente llega a {_m(o['disparo'])}; hoy cotiza {_m(o['prima'])}). "
                        f"Breakeven {_m(o['breakeven'])} · prob. de éxito {o['pop']:.0f}% · {o['dte']} días.</div></div>",
                        unsafe_allow_html=True)
                    if len(AN) > 1:
                        st.markdown(MTF.tarjeta_html(MTF.combinar(AN, max(o["dte"], 0.5), TF)), unsafe_allow_html=True)
                    _graficos(o)
                else:
                    o = MAN
                    st.markdown(
                        f"<div class='ox-box'><h4>Análisis manual · {E(o['contrato'])} · {E(o['vencimiento'])} · {o['dte']}d</h4>"
                        f"<div class='ox-exp'>Prima <b>{_m(o['prima'])}</b> ({_m(o['costo'], dec=0)} por contrato"
                        + (f", {int(INV // o['costo'])} con tu inversión" if INV and o["costo"] else "") + f") · breakeven "
                        f"<b>{_m(o['breakeven'])}</b> ({o['dist_breakeven_pct']:+.1f}%) · objetivo <b>{_m(o['objetivo'])}</b> · "
                        f"prob. de tocarlo {o['p_toque']:.0f}% · valor esperado <b>{o['ve']:+.1f}%</b> · prob. de éxito "
                        f"{o['pop']:.0f}%.</div></div>", unsafe_allow_html=True)
                    if SEL:
                        rows_ = [("Contrato", lambda e: f"{e['contrato']} · {e['vencimiento']}"),
                                 ("Prima", lambda e: _m(e["prima"])), ("Breakeven", lambda e: _m(e["breakeven"])),
                                 ("Delta", lambda e: f"{e['delta']:+.2f}" if e["delta"] is not None else "—"),
                                 ("Theta / día", lambda e: f"{e['theta_dia_pct']:.1f}%" if e["theta_dia_pct"] else "—"),
                                 ("Si toca el objetivo", lambda e: f"{e['roi_objetivo']:+.0f}%"),
                                 ("Prob. de éxito", lambda e: f"{e['pop']:.0f}%"), ("Valor esperado", lambda e: f"{e['ve']:+.1f}%")]
                        st.markdown("<div class='ox-box'><h4>Manual vs OPT" + str(ss["opt_sel"]) + "</h4><table class='ox-cmp'>"
                                    "<tr><th></th><th>Manual</th><th>Motor</th></tr>"
                                    + "".join(f"<tr><td>{E(n)}</td><td>{E(f(o))}</td><td>{E(f(SEL))}</td></tr>" for n, f in rows_)
                                    + "</table></div>", unsafe_allow_html=True)
                    if len(AN) > 1:
                        st.markdown(MTF.tarjeta_html(MTF.combinar(AN, max(o["dte"], 0.5), TF)), unsafe_allow_html=True)
                    _graficos(o, [("OPT" + str(ss["opt_sel"]) + " · " + SEL["contrato"], SEL, "#7C9CFF")] if SEL else [])
                    st.markdown(_riesgos_html(o), unsafe_allow_html=True)

# ================================================================== option chain (debajo del análisis)
EXPS = sorted(CH["exp"].unique())
_hoy = CAL.hoy_ny()
LBL = {e: f"{OP.etiqueta_venc(e)} · {int(CH[CH['exp'] == e]['dte'].iloc[0])}d"
          + (" · feriado" if CAL.feriados_entre(_hoy, e) else "") for e in EXPS}
labels = [LBL[e] for e in EXPS]
sig = f"{ticker}|{SEL['contrato']}|{SEL['vencimiento']}" if SEL else None
if sig and ss.get("opt_hl_sig") != sig:  # apertura automática del vencimiento del contrato seleccionado
    ss["opt_hl_sig"] = sig
    ss["opt_exp"] = LBL[SEL["exp"]]
if ss.get("opt_exp") not in labels:
    ss["opt_exp"] = labels[0]
st.markdown("<div class='ox-lbl' style='margin-top:10px'>Cadena de opciones (option chain)</div>", unsafe_allow_html=True)
if SEL:
    kx = labels.index(LBL[SEL["exp"]]) + 1
    st.markdown(f"<style>.st-key-opt_exp button:nth-of-type({kx}){{animation:opexp 1.4s ease-in-out infinite;"
                f"border-color:{ACC} !important}}@keyframes opexp{{0%,100%{{background-color:rgba(41,98,255,.10)}}"
                f"50%{{background-color:rgba(41,98,255,.45)}}}}</style>", unsafe_allow_html=True)
sel_lbl = st.segmented_control("Vencimiento", labels, key="opt_exp", label_visibility="collapsed") or labels[0]
sel_exp = EXPS[labels.index(sel_lbl)]
DX = CH[CH["exp"] == sel_exp]
calls = DX[DX["type"] == "call"].set_index("strike")
puts = DX[DX["type"] == "put"].set_index("strike")
ks = sorted(set(calls.index) | set(puts.index))
em_sel = OP.expected_move(DX, spot)
cwk = {w["strike"] for w in WALLS["call_walls"]}
pwk = {w["strike"] for w in WALLS["put_walls"]}
atm_k = ks[int(np.argmin([abs(k - spot) for k in ks]))] if ks else None
paso_k = (ks[1] - ks[0]) if len(ks) > 1 else 1
marcas = {}  # (tipo, strike) -> (etiqueta, clase)
for t, v in NIV.items():
    if v and v["exp"] == sel_exp:
        marcas[(v["tipo"], v["strike"])] = ({1: "RECOMENDADO · OPT1", 2: "AGRESIVO · OPT2", 3: "ULTRA RISK · OPT3"}[t],
                                             "hot" if t == ss["opt_sel"] else "t2")
if MAN and MAN["exp"] == sel_exp:
    marcas.setdefault((MAN["tipo"], MAN["strike"]), ("MANUAL", "sim"))


def _n(v, f="{:,.2f}"):
    return "" if v is None or pd.isna(v) else f.format(v)


def _i(v):
    return "" if v is None or pd.isna(v) else f"{int(v):,}"


COLS_C = [("oi", "OI"), ("volume", "VOL"), ("iv", "IV"), ("delta", "DELTA"), ("theta", "THETA"), ("bid", "BID"), ("ask", "ASK")]
COLS_P = list(reversed(COLS_C))


def side(r, cols, itm, mark):
    cls = ("itm " if itm else "") + (mark[1] if mark else "")
    if r is None:
        return "".join(f"<td class='{cls}'></td>" for _ in cols)
    o_ = []
    for name, _ in cols:
        v = r[name]
        txt = (_n(v * 100, "{:.1f}%") if name == "iv" else _n(v, "{:+.2f}") if name in ("delta", "theta")
               else _i(v) if name in ("volume", "oi") else _n(v))
        o_.append(f"<td class='{cls}{' q' if name in ('bid', 'ask') else ''}'>{txt}</td>")
    return "".join(o_)


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
    mc, mp = marcas.get(("CALL", k)), marcas.get(("PUT", k))
    tags = []
    if k in pwk:
        tags.append(("PUT HEDGE", "tp"))
    if k in cwk:
        tags.append(("C-WALL", "tc"))
    if VP.get("poc") and abs(k - VP["poc"]) <= paso_k / 2:
        tags.append(("POC / VRVP", "tv"))
    if k == atm_k:
        tags.append(("ATM SPOT", "ta"))
    for m_ in (mc, mp):
        if m_:
            tags.append((m_[0], "tr" if m_[1] == "hot" else "tm"))
    hot = bool((mc and mc[1] == "hot") or (mp and mp[1] == "hot"))
    rows.append(f"<tr{' id=hl class=big' if hot else ''}>" + side(c, COLS_C, k < spot, mc)
                + f"<td class='k{' hotk' if hot else ''}'><div>${k:,.2f}</div>"
                + "".join(f"<span class='tg {cl}'>{E(t)}</span>" for t, cl in tags) + "</td>"
                + side(p, COLS_P, k > spot, mp) + "</tr>")

head = ("<tr class='g'><th colspan='7' class='gc'>CALLS (COMPRADORES ALCISTAS)</th><th class='k'>STRIKE</th>"
        "<th colspan='7' class='gp'>PUTS (COBERTURA / BAJISTAS)</th></tr><tr>"
        + "".join(f"<th>{h}</th>" for _, h in COLS_C) + "<th class='k'>PRECIO</th>"
        + "".join(f"<th>{h}</th>" for _, h in COLS_P) + "</tr>")
CHAIN_HTML = f"""<!doctype html><html><head><style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;600&display=swap');
body{{margin:0;background:{BG};color:{TXT};font-family:{MONO}}}
.wrap{{height:560px;overflow:auto;border:1px solid {BORDER};border-radius:8px;background:{PANEL}}}
table{{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}}
th{{position:sticky;background:#1C2128;color:#8B949E;font-weight:600;padding:5px 6px;text-align:right;white-space:nowrap;height:16px;
  border-bottom:1px solid {BORDER};font-family:Inter,system-ui,sans-serif;font-size:11px;z-index:2}}
tr.g th{{top:0;text-align:center;letter-spacing:.06em}} tr:nth-child(2) th{{top:27px}}
th.gc{{color:{GREEN}}} th.gp{{color:{RED}}}
td{{padding:5px 6px;text-align:right;border-bottom:1px solid #21262D;white-space:nowrap;color:#C9D1D9}}
td.itm{{background:rgba(38,166,154,.05)}}
td.q{{color:{TXT};font-weight:600}}
td.k,th.k{{text-align:center;background:#1C2128;color:{TXT};font-weight:700;min-width:150px;border-left:1px solid {BORDER};
  border-right:1px solid {BORDER}}}
td.k div{{font-size:12px}}
tr.big td{{padding:10px 6px;font-size:13px}}
tr.big td.k div{{font-size:17px}}
tr.spot td{{text-align:center;background:rgba(41,98,255,.16);color:#9DB6FF;font-size:11px;padding:3px;
  border-top:1px solid {ACC};border-bottom:1px solid {ACC}}}
.tg{{display:inline-block;font-size:11px;line-height:14px;padding:0 4px;margin:2px 2px 0;border-radius:3px;font-family:Inter,sans-serif;
  font-weight:600}}
.tc{{color:{RED};border:1px solid {RED}88}} .tp{{color:{GREEN};border:1px solid {GREEN}88}}
.tv{{color:#9DB6FF;border:1px solid #9DB6FF88}} .ta{{color:{TXT};background:#30363D}}
.tr{{color:#fff;background:{GREEN}}} .tm{{color:{AMBER};border:1px solid {AMBER}}}
td.hot{{animation:pulse 1.3s ease-in-out infinite}}
td.hotk{{animation:pulsek 1.3s ease-in-out infinite}}
td.t2{{background:rgba(210,153,34,.08)}}
td.sim{{background:rgba(240,180,41,.16);box-shadow:inset 0 1px 0 {AMBER},inset 0 -1px 0 {AMBER}}}
@keyframes pulse{{0%,100%{{background:rgba(38,166,154,.10)}}50%{{background:rgba(38,166,154,.45)}}}}
@keyframes pulsek{{0%,100%{{background:#1C2128}}50%{{background:rgba(38,166,154,.55)}}}}
</style></head><body><div class='wrap' id='w'><table>{head}{''.join(rows)}</table></div>
<script>const w=document.getElementById('w');const h=document.getElementById('hl')||document.querySelector('tr.spot');
if(h){{w.scrollTop=Math.max(0,h.offsetTop-w.clientHeight/2);}}</script></body></html>"""
components.html(CHAIN_HTML, height=572, scrolling=False)
st.caption("Fondo verde tenue = dentro del dinero. La fila que destella es el contrato seleccionado (OPT"
           f"{ss['opt_sel']}); en ámbar, los otros niveles y el análisis manual. PUT HEDGE / C-WALL = muros de mayor interés "
           "abierto. Datos: Alpaca (" + INFO["feed"] + ") · " + INFO["timestamp_utc"]
           + ". IV y griegas recalculadas desde la prima (precio medio)"
           + (f", subyacente implícito por paridad put-call {INFO['spot_paridad']:,.2f}" if INFO.get("spot_paridad") else "") + ".")

with st.expander("Ver Mapa GEX / Muros", expanded=False, icon=":material/bar_chart:"):
    gx = GEXS
    if len(gx):
        fig = go.Figure(go.Bar(x=gx.values / 1e6, y=gx.index, orientation="h",
                               marker_color=[GREEN if v >= 0 else RED for v in gx.values],
                               hovertemplate="Strike %{y:,.2f}<br>GEX %{x:,.1f} M$<extra></extra>"))
        lns = [(spot, ACC, f"Spot {spot:,.2f}", "solid", "bottom right")]
        if SM.get("gamma_flip_level"):
            lns.append((SM["gamma_flip_level"], AMBER, f"Gamma flip {SM['gamma_flip_level']:,.2f}", "dash", "top left"))
        if VP.get("poc"):
            lns.append((VP["poc"], MUTED, f"POC VRVP {VP['poc']:,.2f}", "dot", "top right"))
        for y, colr, txt, dash, pos in lns:
            fig.add_hline(y=y, line=dict(color=colr, width=1, dash=dash), annotation_text=txt,
                          annotation_position=pos, annotation_font=dict(size=11, color=colr))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor=PANEL, plot_bgcolor=PANEL,
                          font=dict(family="JetBrains Mono, monospace", size=11, color=TXT), bargap=0.15,
                          title=dict(text="Exposición gamma neta por strike (millones de $ por 1 % de movimiento)",
                                     font=dict(size=12, color="#8B949E")),
                          xaxis=dict(gridcolor="#21262D", zerolinecolor=BORDER), yaxis=dict(gridcolor="#21262D", tickformat=",.2f"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

st.caption("Cálculos: valor esperado = P(toca objetivo) × rentabilidad en el objetivo + (1 − P) × resultado sin movimiento − "
           "medio spread (Black-Scholes, IV actual) · prob. de éxito = P(precio al vencimiento más allá del breakeven) · "
           "PCR = Σ puts / Σ calls · GEX = Γ × OI × 100 × S² × 0.01 · max pain = strike con menor pago intrínseco. "
           "MARKET = puntaje multi-temporalidad (técnico + fundamental según el horizonte, 0–100; MIXTO si las temporalidades no coinciden) · OPTIONS = % del volumen en calls.")
st.markdown(DISCLAIMER, unsafe_allow_html=True)
