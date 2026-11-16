"""Validación del modelo (solo administrador): walk-forward fuera de muestra del puntaje técnico y del MTF."""
import html
import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import backtest_cortes as BC, profiles, validacion as V
from core.ui import AMBER, GREEN, MUTED, RED

cfg = st.session_state.cfg
E = html.escape
MONO = "'JetBrains Mono','Fira Code',monospace"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _evaluar(tickers: tuple, tf: str, hz: tuple, prov: str, av: str, settings_json: str):
    return V.evaluar(list(tickers), tf, hz, prov, av, json.loads(settings_json))


st.markdown(f"""<style>
.vl-t{{width:100%;border-collapse:collapse;font-size:12px;margin:4px 0 10px}}
.vl-t th{{text-align:right;color:#8B949E;font-weight:600;border-bottom:1px solid #30363D;padding:5px 8px;white-space:nowrap}}
.vl-t th:first-child,.vl-t th:nth-child(2),.vl-t td:first-child,.vl-t td.l{{text-align:left}}
.vl-t td{{padding:5px 8px;border-bottom:1px solid #21262D;color:#E6EDF3;text-align:right;
  font-family:{MONO};font-variant-numeric:tabular-nums;white-space:nowrap}}
.vl-t td.l{{font-family:Inter,system-ui,sans-serif}}
.vl-box{{overflow-x:auto;background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:12.5px;
  line-height:1.55;color:#E6EDF3}}
.vl-box h4{{margin:0 0 6px;font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
.vl-v{{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px}}
</style>""", unsafe_allow_html=True)

st.markdown("### Validación del modelo")
st.markdown("<div class='muted small'>Prueba fuera de muestra (walk-forward) del puntaje técnico y de las tres formas de "
            "combinar temporalidades. Usa solo velas cerradas de las temporalidades mayores; los modelos se ajustan con el "
            "pasado y se evalúan en el tramo siguiente. Los intervalos usan N efectivo = N / horizonte (muestras solapadas).</div>",
            unsafe_allow_html=True)

MODO = st.segmented_control("Prueba", ["Backtest por cortes", "Estadística walk-forward"], default="Backtest por cortes",
                            key="vl_modo") or "Backtest por cortes"
SETTINGS = st.session_state.get("technical_settings") or profiles.BASE_SETTINGS
PROV = "alphavantage" if cfg.get("proveedor", "").startswith("Alpha Vantage") else "yahoo"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _cortes(tickers: tuple, tf: str, hz: tuple, tp: float, sl: float, prov: str, av: str, settings_json: str):
    return BC.ejecutar(list(tickers), tf, hz, tp, sl, prov, av, json.loads(settings_json))


def _p(v, d=1):
    return "—" if v is None or not np.isfinite(v) else f"{v * 100:.{d}f}%"


def _pf(v):
    return "—" if v is None or not np.isfinite(v) else f"{v:.2f}"


def _r(v):
    return "—" if v is None or not np.isfinite(v) else f"{v:+.2f} R"


if MODO == "Backtest por cortes":
    st.markdown("<div class='muted small'>En cada vela del pasado se corta la serie como si fuera la última, se calcula la "
                "señal multi-temporalidad con lo que se sabía en ese momento y se mide qué hizo el precio después: si tocó "
                "primero el objetivo o el stop dentro del horizonte. Los parámetros de la fórmula se eligen en el primer 60 % "
                "de la historia y se juzgan en el 40 % final, que el ajuste no vio.</div>", unsafe_allow_html=True)
    b1, b2, b3, b4 = st.columns([2.6, 1.1, 2, 1.1], vertical_alignment="bottom")
    tks_b = b1.text_input("Activos", "SPY, AMD, TSLA, AMZN", key="bc_tks")
    tf_b = b2.segmented_control("Operativa", ["1h", "4h", "1D"], default="1h", key="bc_tf") or "1h"
    hz_b = b3.multiselect("Horizontes (días)", [1, 3, 7, 14, 30, 60],
                          default=list({"1h": (1, 3, 7), "4h": (3, 7, 14), "1D": (7, 14, 30)}[tf_b]), key=f"bc_hz_{tf_b}")
    go_b = b4.button("Ejecutar backtest", type="primary", width="stretch", key="bc_go")
    lst_b = tuple(dict.fromkeys(t.strip().upper() for t in tks_b.split(",") if t.strip()))
    kb = (lst_b, tf_b, tuple(sorted(hz_b)))
    if go_b:
        st.session_state["bc_key"] = kb
    if st.session_state.get("bc_key") != kb:
        st.info(f"Objetivo {cfg['tp_atr']:g} × ATR y stop {cfg['sl_atr']:g} × ATR (los de tu configuración). Pulsa "
                "**Ejecutar backtest**. Prueba 54 combinaciones de la fórmula por horizonte; tarda 1–3 minutos la primera vez.")
        st.stop()
    try:
        with st.spinner("Cortando la serie vela a vela y simulando…"):
            RB = _cortes(lst_b, tf_b, tuple(sorted(hz_b)), float(cfg["tp_atr"]), float(cfg["sl_atr"]), PROV,
                         cfg.get("alphavantage_key") or "", json.dumps(profiles.engine_settings(SETTINGS), sort_keys=True))
    except Exception as e:
        st.error(f"No se pudo ejecutar: {e}")
        st.stop()
    if RB["errores"]:
        st.caption("Sin datos: " + ", ".join(RB["errores"]))
    per = RB["periodo"]
    st.markdown("<div class='muted small'>Temporalidades " + " · ".join(RB["tfs"]) + " · objetivo "
                f"{RB['tp']:g}×ATR / stop {RB['sl']:g}×ATR (R:R {RB['tp'] / RB['sl']:.1f}) · "
                + " · ".join(f"{k}: entrenamiento {a}→{b}, prueba {b}→{c}" for k, (a, b, c) in per.items()) + "</div>",
                unsafe_allow_html=True)

    def _fmt_p(pr):
        return f"σ {pr['sigma']:g} · escala {pr['escala']:g} · umbral {pr['umbral']} · {pr['filtro']}"

    filas_b, recs = [], []
    for f in RB["horizontes"]:
        for nom, blk in (("Fórmula actual", f["actual"]), ("Fórmula ajustada", f.get("ajustado"))):
            if not blk:
                continue
            te, tr = blk["test"], blk["train"]
            filas_b.append(
                f"<tr><td class='l'>{f['horizonte_dias']} d</td><td class='l'>{nom}<div class='muted small'>{E(_fmt_p(blk['param']))}"
                f"</div></td><td>{tr['ops']}</td><td>{_r(tr['esperanza_r'])}</td><td>{te['ops']}</td>"
                f"<td>{_p(te['ganadoras'])}</td><td>{_p(te['acierto_dir'])}</td>"
                f"<td style='color:{GREEN if te['esperanza_r'] > 0 else RED}'>{_r(te['esperanza_r'])} "
                f"<span class='muted'>[{_r(te['ic_lo'])}, {_r(te['ic_hi'])}]</span></td>"
                f"<td>{_pf(te['profit_factor'])}</td>"
                f"<td>{te['r_total']:+.1f} R</td></tr>")
        a, b = f["actual"]["test"], (f.get("ajustado") or {}).get("test")
        if b and b["ops"] >= 15 and np.isfinite(b["esperanza_r"]) and b["esperanza_r"] > a["esperanza_r"] + 0.05 \
                and b["ic_lo"] > a["ic_lo"]:
            recs.append((f["horizonte_dias"], "ajustar", f["ajustado"]["param"], a, b))
        else:
            recs.append((f["horizonte_dias"], "mantener", f["actual"]["param"], a, b))
    st.markdown("<div class='vl-box'><h4>Resultado de los cortes · entrenamiento vs prueba</h4><table class='vl-t'><tr>"
                "<th>Horizonte</th><th>Fórmula</th><th>Ops. entr.</th><th>Esperanza entr.</th><th>Ops. prueba</th>"
                "<th>Ganadoras</th><th>Acierto dirección</th><th>Esperanza prueba [IC 95 %]</th><th>Profit factor</th>"
                "<th>R total</th></tr>" + "".join(filas_b) + "</table><div class='muted small'>R = múltiplos del riesgo "
                "(1 R = distancia al stop). Esperanza = ganancia media por operación en R. Una operación que no toca ni "
                "objetivo ni stop se cierra al final del horizonte a precio de mercado. Si objetivo y stop caen en la misma "
                "vela se cuenta el stop.</div></div>", unsafe_allow_html=True)
    filas_e = []
    for f in RB["horizontes"]:
        for nom, blk in (("Actual", f["actual"]), ("Ajustada", f.get("ajustado"))):
            if not blk or "sin_eventos" not in blk["test"]:
                continue
            te = blk["test"]
            filas_e.append(f"<tr><td class='l'>{f['horizonte_dias']} d</td><td class='l'>{nom}</td>"
                           + "".join(f"<td>{te[k]['ops']}</td><td>{_r(te[k]['esperanza_r'])}</td><td>{_p(te[k]['ganadoras'])}</td>"
                                     for k in ("sin_eventos", "con_eventos")) + "</tr>")
    if filas_e:
        st.markdown("<div class='vl-box'><h4>Prueba separada por velas de evento</h4><table class='vl-t'><tr><th>Horizonte</th>"
                    "<th>Fórmula</th><th>Sin eventos · ops</th><th>Esperanza</th><th>Ganadoras</th><th>Con eventos · ops</th>"
                    "<th>Esperanza</th><th>Ganadoras</th></tr>" + "".join(filas_e) + "</table><div class='muted small'>"
                    "Una operación «con evento» cruza una vela anómala (retorno |z| ≥ 4, gap ≥ 2 ATR o volumen ≥ 3× con "
                    "|z| ≥ 3): resultados, noticias o shocks de sector. Su resultado depende del evento, no de la fórmula; "
                    "por eso el ajuste elige los parámetros con las operaciones sin eventos.</div></div>",
                    unsafe_allow_html=True)
    txt = []
    for hd, acc, pr, a, b in recs:
        if acc == "ajustar":
            txt.append(f"<li><b>{hd} d:</b> ajustar a {E(_fmt_p(pr))}: en prueba la esperanza pasa de {_r(a['esperanza_r'])} "
                       f"a {_r(b['esperanza_r'])}.</li>")
        else:
            txt.append(f"<li><b>{hd} d:</b> mantener la fórmula actual; ninguna combinación la superó de forma consistente "
                       "fuera de la muestra de ajuste.</li>")
    st.markdown("<div class='vl-box'><h4>Recomendación</h4><ul style='margin:0 0 0 16px;padding:0'>" + "".join(txt)
                + "</ul><div class='muted small' style='margin-top:6px'>Solo se recomienda un cambio si mejora la esperanza "
                "en el tramo de prueba en al menos 0.05 R y también su peor caso (extremo bajo del intervalo).</div></div>",
                unsafe_allow_html=True)
    with st.expander("Detalle por activo y mejores combinaciones en entrenamiento", expanded=False):
        for f in RB["horizontes"]:
            st.markdown(f"**{f['horizonte_dias']} días**")
            pa = f["actual"]["por_activo"]
            pb = (f.get("ajustado") or {}).get("por_activo") or {}
            st.markdown("<table class='vl-t'><tr><th>Activo</th><th>Actual · ops</th><th>Actual · esperanza</th>"
                        "<th>Ajustada · ops</th><th>Ajustada · esperanza</th></tr>"
                        + "".join(f"<tr><td class='l'>{k}</td><td>{v['ops']}</td><td>{_r(v['esperanza_r'])}</td>"
                                  f"<td>{(pb.get(k) or {}).get('ops', '—')}</td><td>{_r((pb.get(k) or {}).get('esperanza_r'))}</td></tr>"
                                  for k, v in pa.items()) + "</table>", unsafe_allow_html=True)
            if f.get("top"):
                st.markdown("<table class='vl-t'><tr><th>Top entrenamiento</th><th>Ops.</th><th>Esperanza</th></tr>"
                            + "".join(f"<tr><td class='l'>{E(_fmt_p(t['param']))}</td><td>{t['train']['ops']}</td>"
                                      f"<td>{_r(t['train']['esperanza_r'])}</td></tr>" for t in f["top"]) + "</table>",
                            unsafe_allow_html=True)
    st.stop()

DEF = {"1h": (1, 3, 7, 14), "4h": (3, 7, 14, 30), "1D": (7, 14, 30, 60)}
c1, c2, c3, c4 = st.columns([2.6, 1.1, 2, 1.1], vertical_alignment="bottom")
tks = c1.text_input("Activos (separados por coma)", "SPY, QQQ, AAPL, MSFT, NVDA, AMZN, META, TSLA", key="vl_tks")
tf = c2.segmented_control("Operativa", ["1h", "4h", "1D"], default="1h", key="vl_tf") or "1h"
hz = c3.multiselect("Horizontes (días)", [1, 3, 7, 14, 30, 60], default=list(DEF[tf]), key=f"vl_hz_{tf}")
go_ = c4.button("Ejecutar validación", type="primary", width="stretch")

lista = tuple(dict.fromkeys(t.strip().upper() for t in tks.split(",") if t.strip()))
key = (lista, tf, tuple(sorted(hz)))
if go_:
    st.session_state["vl_key"] = key
if st.session_state.get("vl_key") != key:
    st.info("Elige activos, temporalidad y horizontes y pulsa **Ejecutar validación**. Con 8 activos tarda alrededor de un "
            "minuto la primera vez; el resultado queda guardado 6 horas.")
    st.stop()

try:
    with st.spinner("Ejecutando la validación walk-forward…"):
        R = _evaluar(lista, tf, tuple(sorted(hz)),
                     "alphavantage" if cfg.get("proveedor", "").startswith("Alpha Vantage") else "yahoo",
                     cfg.get("alphavantage_key") or "", json.dumps(profiles.engine_settings(SETTINGS), sort_keys=True))
except Exception as e:
    st.error(f"No se pudo validar: {e}")
    st.stop()

if R["errores"]:
    st.caption("Sin datos suficientes: " + ", ".join(R["errores"]))
st.markdown(f"<div class='muted small'>{len(R['tickers'])} activos · temporalidades {' · '.join(R['tfs'])} · "
            f"{R['velas']:,} velas · {E(R['desde'][:10])} → {E(R['hasta'][:10])}</div>", unsafe_allow_html=True)
if not R["horizontes"]:
    st.warning("Ningún horizonte reunió la muestra mínima (N efectivo ≥ 20). Agrega activos o usa horizontes más cortos.")
    st.stop()

NOMBRE = {"operativa": "Solo operativa", "mtf_curva": "MTF · curva log-normal", "mtf_estimado": "MTF · pesos estimados"}


def _veredicto(m):
    """Hay evidencia si el IC de Spearman o el acierto excluyen el azar y el Brier skill es positivo."""
    sig = (np.isfinite(m["ic_lo"]) and m["ic_lo"] > 0) or (np.isfinite(m["acierto_lo"]) and m["acierto_lo"] > 0.5)
    if sig and m.get("bss", -1) > 0:
        return "Ventaja medible", GREEN
    if (np.isfinite(m["ic_hi"]) and m["ic_hi"] < 0) or (np.isfinite(m["acierto_hi"]) and m["acierto_hi"] < 0.5):
        return "Peor que el azar", RED
    return "Sin evidencia", MUTED


def _pct(v, d=1):
    return "—" if v is None or not np.isfinite(v) else f"{v * 100:.{d}f}%"


filas = []
for f in R["horizontes"]:
    for k in ("operativa", "mtf_curva", "mtf_estimado"):
        m = f[k]
        vtxt, vc = _veredicto(m)
        filas.append(
            f"<tr><td class='l'>{f['horizonte_dias']} d <span class='muted'>({f['velas']} velas)</span></td>"
            f"<td class='l'>{NOMBRE[k]}</td><td>{_pct(m['acierto'])} <span class='muted'>[{_pct(m['acierto_lo'], 0)}–"
            f"{_pct(m['acierto_hi'], 0)}]</span></td>"
            f"<td>{m['ic']:+.3f} <span class='muted'>[{m['ic_lo']:+.2f}, {m['ic_hi']:+.2f}]</span></td>"
            f"<td style='color:{GREEN if m['bss'] > 0 else RED}'>{m['bss'] * 100:+.1f}%</td>"
            f"<td>{m['n_efectivo']:,.0f}</td>"
            f"<td><span class='vl-v' style='color:{vc};border:1px solid {vc}88'>{vtxt}</span></td></tr>")
st.markdown("<div class='vl-box'><h4>Capacidad predictiva fuera de muestra</h4><table class='vl-t'><tr><th>Horizonte</th>"
            "<th>Modelo</th><th>Acierto direccional [IC 95 %]</th><th>IC Spearman [IC 95 %]</th><th>Brier skill</th>"
            "<th>N efectivo</th><th>Veredicto</th></tr>" + "".join(filas) + "</table>"
            "<div class='muted small'>Acierto: solo velas con |puntaje| ≥ 15. Brier skill &gt; 0: la probabilidad del modelo "
            "predice mejor que la frecuencia histórica de subidas. «Ventaja medible» exige que el intervalo excluya el azar "
            "y que el Brier skill sea positivo.</div></div>", unsafe_allow_html=True)

# ---- pesos curva vs estimados
pf = "".join(
    f"<tr><td class='l'>{f['horizonte_dias']} d</td>"
    + "".join(f"<td>{_pct(f['pesos_curva'][t], 0)}</td>" for t in R["tfs"])
    + "".join(f"<td>{_pct(f['pesos_estimados'][t], 0) if f['pesos_estimados'][t] is not None else '—'}</td>" for t in R["tfs"])
    + "</tr>" for f in R["horizontes"])
c_a, c_b = st.columns(2)
c_a.markdown("<div class='vl-box'><h4>Pesos: curva log-normal vs estimados con los datos</h4><table class='vl-t'><tr><th>Horizonte</th>"
             + "".join(f"<th>Curva {t}</th>" for t in R["tfs"]) + "".join(f"<th>Datos {t}</th>" for t in R["tfs"])
             + "</tr>" + pf
             + "</table><div class='muted small'>Pesos estimados: regresión logística regularizada del retorno futuro sobre "
             "los puntajes de cada temporalidad (coeficientes negativos se toman como 0). Si se parecen a la curva, la "
             "curva está bien calibrada; si no, conviene ajustarla.</div></div>", unsafe_allow_html=True)

al = "".join(
    f"<tr><td class='l'>{f['horizonte_dias']} d</td><td>{_pct(f['alineadas']['acierto']) if f['alineadas'] else '—'}</td>"
    f"<td>{f['alineadas']['senales'] if f['alineadas'] else '—'}</td>"
    f"<td>{_pct(f['no_alineadas']['acierto']) if f['no_alineadas'] else '—'}</td>"
    f"<td>{f['no_alineadas']['senales'] if f['no_alineadas'] else '—'}</td></tr>" for f in R["horizontes"])
corr = R["correlacion"]
ct = "".join(f"<tr><td class='l'>{a}</td>" + "".join(f"<td>{corr.loc[a, b]:+.2f}</td>" for b in corr.columns) + "</tr>"
             for a in corr.index)
c_b.markdown("<div class='vl-box'><h4>¿Sirve exigir alineación?</h4><table class='vl-t'><tr><th>Horizonte</th>"
             "<th>Acierto alineadas</th><th>Señales</th><th>Acierto no alineadas</th><th>Señales</th></tr>" + al + "</table>"
             "<h4 style='margin-top:10px'>Correlación entre temporalidades (Spearman)</h4><table class='vl-t'><tr><th></th>"
             + "".join(f"<th>{c}</th>" for c in corr.columns) + "</tr>" + ct + "</table><div class='muted small'>Una "
             "correlación alta indica que las temporalidades repiten la misma información: la alineación cuenta menos "
             "de lo que parece.</div></div>", unsafe_allow_html=True)

# ---- curva de calibración
if R["calibracion"]:
    hsel = st.segmented_control("Calibración (MTF curva) · horizonte", [f"{h} d" for h in R["calibracion"]],
                                default=f"{list(R['calibracion'])[0]} d", key="vl_cal") or f"{list(R['calibracion'])[0]} d"
    cal = R["calibracion"][int(hsel.split()[0])]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=MUTED, dash="dot", width=1),
                             name="Calibración perfecta", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=cal["pred"], y=cal["obs"], mode="lines+markers", line=dict(color=AMBER, width=2),
                             marker=dict(size=8), name="Modelo", customdata=cal["n"],
                             hovertemplate="Predicho %{x:.0%}<br>Observado %{y:.0%}<br>%{customdata} velas<extra></extra>"))
    lo = float(min(cal["pred"].min(), cal["obs"].min(), 0.35))
    hi = float(max(cal["pred"].max(), cal["obs"].max(), 0.65))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="#161B22", plot_bgcolor="#161B22",
                      font=dict(family="JetBrains Mono, monospace", size=11, color="#E6EDF3"),
                      xaxis=dict(title="Probabilidad de subida predicha", tickformat=".0%", range=[lo, hi], gridcolor="#21262D"),
                      yaxis=dict(title="Frecuencia observada", tickformat=".0%", range=[lo, hi], gridcolor="#21262D"),
                      legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Si los puntos siguen la diagonal, las probabilidades significan lo que dicen (60 % → sube 6 de cada 10 veces).")

st.markdown("<div class='vl-box'><h4>Cómo leer esto</h4>"
            "<b>Sin evidencia</b> no significa que el modelo esté mal: significa que la muestra no permite distinguirlo del "
            "azar. Se gana poder estadístico con más activos y horizontes más cortos. En acciones grandes, un acierto "
            "sostenido de 52–56 % con intervalo por encima de 50 % ya es una ventaja real. Si «MTF · pesos estimados» supera "
            "de forma consistente a la curva, conviene ajustar los plazos naturales de core/mtf.py hacia los pesos estimados."
            "</div>", unsafe_allow_html=True)
