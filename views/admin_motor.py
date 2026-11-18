"""Datos y Motor A (solo administrador): diagnóstico en vivo del plan de Alpaca y reporte del último entrenamiento."""
import html

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import alpaca, auth
from core.motor_a import artefactos as AR
from core.ui import AMBER, GREEN, MUTED, RED

if not auth.is_admin():
    st.error("Solo el administrador puede ver esta página.")
    st.stop()

E = html.escape
MONO = "'JetBrains Mono','Fira Code',monospace"
st.markdown(f"""<style>
.ma-t{{width:100%;border-collapse:collapse;font-size:12px;margin:4px 0 10px}}
.ma-t th{{text-align:right;color:#8B949E;font-weight:600;border-bottom:1px solid #30363D;padding:5px 8px;white-space:nowrap}}
.ma-t th:first-child,.ma-t th.l,.ma-t td.l{{text-align:left}}
.ma-t td{{padding:5px 8px;border-bottom:1px solid #21262D;color:#E6EDF3;text-align:right;font-family:{MONO};
  font-variant-numeric:tabular-nums;white-space:nowrap}}
.ma-t td.l{{font-family:Inter,system-ui,sans-serif;white-space:normal}}
.ma-box{{background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:12.5px;
  line-height:1.55;color:#E6EDF3;overflow-x:auto}}
.ma-box h4{{margin:0 0 6px;font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
.ma-g{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}}
.ma-g div{{background:#161B22;border:1px solid #30363D;border-radius:8px;padding:8px 10px}}
.ma-g span{{display:block;font-size:11px;color:#8B949E}}
.ma-g b{{font-family:{MONO};font-variant-numeric:tabular-nums;font-size:14px;color:#E6EDF3}}
.ma-v{{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;border:1px solid}}
</style>""", unsafe_allow_html=True)

st.markdown("### Datos y Motor A")

# ------------------------------------------------------------------ diagnóstico de Alpaca
st.markdown("<div class='ma-box'><h4>Diagnóstico del plan de Alpaca</h4><div class='muted small'>Prueba en vivo qué permite "
            "la cuenta configurada en el servidor (las claves no se muestran).</div></div>", unsafe_allow_html=True)
if st.button("Ejecutar diagnóstico", key="ma_diag", type="primary"):
    with st.spinner("Consultando Alpaca…"):
        st.session_state["ma_diag_res"] = alpaca.diagnostico()
res = st.session_state.get("ma_diag_res")
if res:
    filas = []
    for r in res:
        col, txt = (GREEN, "Sí") if r["ok"] is True else (RED, "No") if r["ok"] is False else (MUTED, "Info")
        filas.append(f"<tr><td class='l'>{E(r['prueba'])}</td><td style='color:{col}'>{txt}</td>"
                     f"<td class='l'>{E(r['detalle'])}</td></tr>")
    st.markdown("<div class='ma-box'><table class='ma-t'><tr><th>Prueba</th><th>Resultado</th><th class='l'>Detalle</th></tr>"
                + "".join(filas) + "</table></div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ reporte del Motor A
def _etiqueta(n: str) -> str:
    if n == "reporte.json":
        return "Dirección · 10 sesiones (principal)"
    if n.startswith("reporte_vs_iv_"):
        return f"Movimiento vs IV · {n.removesuffix('.json').split('_H')[-1]} sesiones"
    partes = n.removesuffix(".json").split("_")  # reporte_<objetivo>_H<n>
    obj = {"direccion": "Dirección", "movimiento": "Movimiento"}.get(partes[1], partes[1]) if len(partes) > 2 else n
    return f"{obj} · {partes[-1][1:]} sesiones" if len(partes) > 2 else n


NOMBRES = AR.listar() or ["reporte.json"]
SEL = st.selectbox("Experimento", NOMBRES, format_func=_etiqueta, key="ma_exp") if len(NOMBRES) > 1 else NOMBRES[0]
REP = AR.leer_reporte(SEL)
if not REP:
    st.markdown("<div class='ma-box'><h4>Motor A · acción del precio</h4>Todavía no hay entrenamientos. Se entrena en "
                "GitHub Actions (flujo «Motor A», los domingos o a mano) y el reporte aparece aquí.</div>",
                unsafe_allow_html=True)
    st.stop()

def _f(v, fmt="{:.3f}"):
    return "—" if v is None or not np.isfinite(v) else fmt.format(v)


if REP.get("objetivo") == "vs_iv":
    C = REP

    def _p(v):
        return "—" if v is None or not np.isfinite(v) else f"{v * 100:.1f}%"
    gana = C["auc_modelo"] > C["auc_iv"] and C["brier_modelo"] < C["brier_iv_cal"]
    suma = C["auc_combinado"] > C["auc_iv"] + 0.002 and C["brier_combinado"] < C["brier_iv_cal"]
    vtxt = ("EL MODELO SUPERA A LA IV" if gana else "EL MODELO AÑADE INFORMACIÓN A LA IV" if suma
            else "LA IV YA DESCUENTA LO QUE VE EL MODELO")
    vcol2 = GREEN if gana else AMBER if suma else RED
    st.markdown(
        f"<div class='ma-box'><h4>Movimiento vs IV · H = {C['H']} sesiones</h4>"
        f"<span class='ma-v' style='color:{vcol2};border-color:{vcol2}'>{E(vtxt)}</span> "
        f"<span class='muted small'>Entrenado {E(C['generado_utc'])} UTC · {C['acciones']} acciones · {C['filas']:,} "
        f"lunes-acción · {E(C['desde'])} → {E(C['hasta'])} · medido desde {E(C['corte'])} ({C['filas_prueba']:,} filas)</span>"
        f"<div class='muted small' style='margin-top:6px'>IV ATM reconstruida con las barras históricas de opciones de "
        f"Alpaca (vencimiento ~2 semanas). Probabilidad «IV» = la que implica la IV de tocar ±{C['k']:g}σ√H; se calibra "
        f"y se combina con datos anteriores al corte y se mide después. IV mediana {_p(C['iv_mediana'])}; IV / vol. real "
        f"mediana {C['iv_vs_rv_mediana']:.2f}.</div></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='ma-g'>"
        f"<div><span>AUC IV · modelo · combinado</span><b>{_f(C['auc_iv'])} · {_f(C['auc_modelo'])} · "
        f"{_f(C['auc_combinado'])}</b></div>"
        f"<div><span>Brier IV · modelo · combinado</span><b>{_f(C['brier_iv_cal'], '{:.4f}')} · "
        f"{_f(C['brier_modelo'], '{:.4f}')} · {_f(C['brier_combinado'], '{:.4f}')}</b></div>"
        f"<div><span>Peso en la combinación IV · modelo</span><b>{C['coef_iv']:+.2f} · {C['coef_modelo']:+.2f}</b></div>"
        f"<div><span>Tasa real de movimiento</span><b>{_p(C['tasa_real'])}</b></div></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='ma-box'><h4>¿Cuándo ve el modelo más movimiento del que cobra la IV?</h4><div class='muted small'>"
        "Quintiles de la diferencia entre la probabilidad del modelo y la de la IV (calibrada). Si en el quintil más alto "
        "el movimiento real supera a lo que dice la IV, las opciones estaban baratas para quien compra.</div>"
        "<table class='ma-t'><tr><th>Quintil</th><th>Diferencia (logit)</th><th>IV dice</th><th>Modelo dice</th>"
        "<th>Real</th><th>Muestras</th></tr>" + "".join(
            f"<tr><td class='l'>{i + 1}</td><td>{t['dif']:+.2f}</td><td>{_p(t['p_iv'])}</td><td>{_p(t['p_modelo'])}</td>"
            f"<td style='color:{GREEN if t['real'] > t['p_iv'] + 0.02 else RED if t['real'] < t['p_iv'] - 0.02 else '#E6EDF3'}'>"
            f"{_p(t['real'])}</td><td>{t['n']:,}</td></tr>" for i, t in enumerate(C["tramos"]))
        + "</table></div>", unsafe_allow_html=True)
    st.stop()

R = REP["resumen"]
REF = REP.get("referencia", "momentum simple")
vcol = GREEN if R["veredicto"].startswith("VENTAJA") else AMBER if R["veredicto"].startswith("SEÑAL") else RED


st.markdown(
    f"<div class='ma-box'><h4>Motor A · acción del precio</h4>"
    f"<span class='ma-v' style='color:{vcol};border-color:{vcol}'>{E(R['veredicto'])}</span> "
    f"<span class='muted small'>Entrenado {E(REP['generado_utc'])} UTC · {REP['acciones']} acciones · "
    f"{REP['filas']:,} filas · {E(REP['desde'])} → {E(REP['hasta'])} · {E(REP['fuente'])}</span>"
    f"<div class='muted small' style='margin-top:6px'>"
    + (f"Predice si el precio se mueve al menos {REP['k']:g}σ·√H, en cualquier dirección, dentro de H = {REP['H']} "
       f"sesiones (referencia: volatilidad realizada reciente, no la IV). " if REP.get("objetivo") == "movimiento" else
       f"Predice la probabilidad de que el precio toque +{REP['k']:g}σ·√H antes que −{REP['k']:g}σ·√H en "
       f"H = {REP['H']} sesiones. ")
    + f"Todo se mide fuera de muestra: cada año se predice con un "
    f"modelo entrenado solo con los años anteriores. {E(R['criterio'])}</div></div>", unsafe_allow_html=True)

st.markdown(
    "<div class='ma-g'>"
    f"<div><span>AUC modelo · {E(REF)} · azar</span><b>{_f(R['auc'])} · {_f(R['auc_momentum'])} · 0.500</b></div>"
    f"<div><span>Brier skill vs tasa base</span><b>{_f(R['bss'], '{:+.4f}')}</b></div>"
    f"<div><span>IC de rango (t-estadístico)</span><b>{_f(R['ic_medio'], '{:+.3f}')} (t={_f(R['ic_t'], '{:.1f}')})</b></div>"
    f"<div><span>Acierto decil alto · bajo · real</span><b>{R['decil_alto']['real'] * 100:.1f}% · "
    f"{R['decil_bajo']['real'] * 100:.1f}% · {R['tasa_real'] * 100:.1f}%</b></div></div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    fia = R["fiabilidad"]
    fig = go.Figure()
    fig.add_scatter(x=[0.3, 0.7], y=[0.3, 0.7], mode="lines", line=dict(color=MUTED, dash="dot", width=1),
                    name="Calibración perfecta", hoverinfo="skip")
    fig.add_scatter(x=[f["p_media"] for f in fia], y=[f["real"] for f in fia], mode="lines+markers",
                    line=dict(color=GREEN, width=2), name="Modelo (fuera de muestra)",
                    hovertemplate="predicho %{x:.1%} · real %{y:.1%}<extra></extra>")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="#161B22", font=dict(color="#E6EDF3", size=11),
                      title=dict(text="Fiabilidad: probabilidad predicha vs frecuencia real", font=dict(size=12)),
                      xaxis=dict(tickformat=".0%", gridcolor="#21262D"), yaxis=dict(tickformat=".0%", gridcolor="#21262D"),
                      legend=dict(orientation="h", y=-0.2, font=dict(size=11)))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with c2:
    imp = REP.get("importancia") or []
    st.markdown("<div class='ma-box'><h4>Variables que más pesan</h4><table class='ma-t'><tr><th>Variable</th><th>Peso</th></tr>"
                + "".join(f"<tr><td class='l'>{E(i['variable'])}</td><td>{i['peso'] * 100:.1f}%</td></tr>" for i in imp[:10])
                + "</table></div>", unsafe_allow_html=True)

BL = REP.get("bloques") or []
if BL:
    st.markdown("<div class='ma-box'><h4>Qué aporta cada bloque (fuera de muestra)</h4><div class='muted small'>Se agregan "
                "en orden; un bloque entra al modelo final solo si mejora a la vez el AUC y el Brier skill.</div>"
                "<table class='ma-t'><tr><th>Bloque</th><th>Variables</th><th>AUC</th><th>Brier skill</th><th>IC t</th>"
                "<th>Decisión</th></tr>" + "".join(
                    f"<tr><td class='l'>{E(b['bloque'])}</td><td>{b['variables']}</td><td>{_f(b['auc'], '{:.4f}')}</td>"
                    f"<td>{_f(b['bss'], '{:+.4f}')}</td><td>{_f(b['ic_t'], '{:.1f}')}</td>"
                    f"<td style='color:{GREEN if b['entra'] else MUTED}'>{'Entra' if b['entra'] else 'No entra'}</td></tr>"
                    for b in BL) + "</table></div>", unsafe_allow_html=True)
MA = REP.get("mis_acciones")
if MA:
    mcol = GREEN if MA["veredicto"].startswith("VENTAJA") else AMBER if MA["veredicto"].startswith("SEÑAL") else RED
    st.markdown(
        f"<div class='ma-box'><h4>En tus acciones ({MA['acciones']})</h4>"
        f"<span class='ma-v' style='color:{mcol};border-color:{mcol}'>{E(MA['veredicto'])}</span>"
        f"<div class='ma-g' style='margin-top:8px'>"
        f"<div><span>AUC modelo · {E(REF)}</span><b>{_f(MA['auc'])} · {_f(MA['auc_momentum'])}</b></div>"
        f"<div><span>Brier skill</span><b>{_f(MA['bss'], '{:+.4f}')}</b></div>"
        f"<div><span>IC (t)</span><b>{_f(MA['ic_medio'], '{:+.3f}')} ({_f(MA['ic_t'], '{:.1f}')})</b></div>"
        f"<div><span>Acierto decil alto · bajo</span><b>{MA['decil_alto']['real'] * 100:.1f}% · "
        f"{MA['decil_bajo']['real'] * 100:.1f}%</b></div></div>"
        f"<div class='muted small'>{E(', '.join(REP.get('mis_acciones_lista', [])[:60]))}</div></div>",
        unsafe_allow_html=True)

filas = "".join(
    f"<tr><td class='l'>{d['anio']}</td><td>{d['n_test']:,}</td><td>{d['tasa_base'] * 100:.1f}%</td>"
    f"<td style='color:{GREEN if d['auc'] > max(0.5, d['auc_momentum']) else RED if d['auc'] < 0.5 else '#E6EDF3'}'>{_f(d['auc'])}</td>"
    f"<td>{_f(d['auc_momentum'])}</td><td>{_f(d['bss'], '{:+.4f}')}</td></tr>" for d in REP["pliegues"])
st.markdown("<div class='ma-box'><h4>Resultado por año (fuera de muestra)</h4><table class='ma-t'><tr><th>Año</th>"
            "<th>Muestras</th><th>Tasa base</th><th>AUC modelo</th><th>AUC " + E(REF) + "</th><th>Brier skill</th></tr>"
            + filas + "</table></div>", unsafe_allow_html=True)
st.markdown("<div class='ma-box'><h4>Limitaciones conocidas</h4>" + "<br>".join(f"· {E(x)}" for x in REP.get("limitaciones", []))
            + "</div>", unsafe_allow_html=True)
