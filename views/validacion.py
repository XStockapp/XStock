"""Validación del modelo (solo administrador): walk-forward fuera de muestra del puntaje técnico y del MTF."""
import html
import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import profiles, validacion as V
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
.vl-box{{background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:12.5px;
  line-height:1.55;color:#E6EDF3}}
.vl-box h4{{margin:0 0 6px;font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
.vl-v{{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px}}
</style>""", unsafe_allow_html=True)

st.markdown("### Validación del modelo")
st.markdown("<div class='muted small'>Prueba fuera de muestra (walk-forward) del puntaje técnico y de las tres formas de "
            "combinar temporalidades. Usa solo velas cerradas de las temporalidades mayores; los modelos se ajustan con el "
            "pasado y se evalúan en el tramo siguiente. Los intervalos usan N efectivo = N / horizonte (muestras solapadas).</div>",
            unsafe_allow_html=True)

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

SETTINGS = st.session_state.get("technical_settings") or profiles.BASE_SETTINGS
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
