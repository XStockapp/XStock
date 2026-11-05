import time

import pandas as pd
import streamlit as st

from core import data, store
from core.scanner import scan
from core.ui import AMBER, DISCLAIMER, GREEN, RED, kpi

cfg = st.session_state.cfg
st.markdown("## Watchlist")
st.markdown("<div class='muted'>Seguimiento de tus acciones: señal actualizada, probabilidad vigente y estado frente "
            "a los niveles de entrada, stop y objetivos guardados.</div>", unsafe_allow_html=True)

wl = store.watchlist()

with st.container(border=True):
    a, b = st.columns([4, 1])
    new = a.text_input("Agregar tickers manualmente", placeholder="p. ej. NVDA, AMD, PLTR", label_visibility="collapsed")
    if b.button("➕ Agregar", use_container_width=True) and new.strip():
        tick = [t.strip().upper() for t in new.replace(";", ",").split(",") if t.strip()]
        n = store.add_to_watchlist([{"Ticker": t} for t in tick])
        st.toast(f"{n} agregadas", icon="⭐")
        st.rerun()

if not wl:
    st.info("Tu watchlist está vacía. Desde el **Escáner** selecciona filas y pulsa **Agregar a watchlist**.")
    st.stop()


@st.cache_data(ttl=900, show_spinner=False)
def _live(tickers: tuple, tp, sl, hz, stamp):
    prices = data.batch_history(list(tickers), "2y")
    return scan(prices, 0, 0, tp, sl, hz), prices


if st.button("🔄 Actualizar datos"):
    st.session_state.wl_stamp = time.time()
with st.spinner("Actualizando señales…"):
    live, prices = _live(tuple(sorted(wl)), cfg["tp_atr"], cfg["sl_atr"], int(cfg["horizonte"]),
                 st.session_state.get("wl_stamp", 0))
live = live.set_index("Ticker") if not live.empty else pd.DataFrame()

rows = []
for t, w in wl.items():
    L = live.loc[t] if t in live.index else None
    px = float(L["Precio"]) if L is not None else None
    entry = w.get("entrada") or (float(L["Entrada"]) if L is not None else None)
    stop = w.get("stop") or (float(L["Stop"]) if L is not None else None)
    t1 = w.get("objetivo_1") or (float(L["Objetivo 1"]) if L is not None else None)
    t2 = w.get("objetivo_2") or (float(L["Objetivo 2"]) if L is not None else None)
    estado = "Sin datos"
    sg = int(w.get("dir") or 1)  # 1 = compra (long), -1 = venta en corto
    if px and entry and stop and t1 and t in prices:
        h = prices[t]
        since = h[h.index >= pd.Timestamp(str(w.get("agregado", "1900-01-01"))[:10])]
        if since.empty:
            since = h.tail(1)
        p_add = w.get("precio_agregado") or px
        touched = (since["Low"] <= entry * 1.002) if sg > 0 else (since["High"] >= entry * 0.998)
        filled = ((p_add - entry * (1.005 if sg > 0 else 0.995)) * sg <= 0) or touched.any()
        if not filled:
            estado = "🎯 En zona de entrada" if abs(px / entry - 1) <= 0.01 else "⏳ Esperando retroceso a la entrada"
        else:
            after = since.loc[touched.idxmax():] if touched.any() else since
            hit_stop = ((after["Low"] <= stop).any() if sg > 0 else (after["High"] >= stop).any()) or (px - stop) * sg <= 0
            hit_t2 = t2 and ((after["High"] >= t2).any() if sg > 0 else (after["Low"] <= t2).any())
            hit_t1 = (after["High"] >= t1).any() if sg > 0 else (after["Low"] <= t1).any()
            if hit_stop:
                estado = "⛔ Stop alcanzado"
            elif hit_t2:
                estado = "🏁 Objetivo 2 alcanzado"
            elif hit_t1:
                estado = "✅ Objetivo 1 alcanzado"
            elif abs(px / entry - 1) <= 0.01:
                estado = "🎯 En zona de entrada"
            else:
                estado = "🟢 Operación en curso"
    p0 = w.get("precio_agregado")
    rows.append({
        "Ticker": t,
        "Lado": "▲ Long" if sg > 0 else "▼ Short",
        "Estado": estado,
        "Señal actual": L["Señal"] if L is not None else "—",
        "Prob. ganancia": float(L["Prob. ganancia"]) if L is not None else None,
        "EV (R)": float(L["Valor esperado (R)"]) if L is not None else None,
        "Score técnico": float(L["Score técnico"]) if L is not None else None,
        "Precio": px,
        "Var. 1d %": float(L["Var. 1d %"]) if L is not None else None,
        "Desde que se agregó %": (px / p0 - 1) * 100 * sg if px and p0 else None,
        "Entrada": entry, "Stop": stop, "Objetivo 1": t1, "Objetivo 2": t2,
        "Señal al agregar": w.get("señal_agregado") or "—",
        "Agregado": w.get("agregado"),
        "Notas": w.get("notas", ""),
    })
df = pd.DataFrame(rows).sort_values("Prob. ganancia", ascending=False, na_position="last")

k = st.columns(4)
kpi(k[0], "Acciones en seguimiento", f"{len(df)}")
kpi(k[1], "Con señal de compra", f"{df['Señal actual'].isin(['COMPRA FUERTE', 'COMPRA']).sum()}", "", GREEN)
kpi(k[2], "En zona de entrada", f"{(df['Estado'] == '🎯 En zona de entrada').sum()}", "", AMBER)
avg = df["Desde que se agregó %"].mean()
kpi(k[3], "Rendimiento medio", "—" if pd.isna(avg) else f"{avg:+.1f}%", "desde que se agregaron",
    GREEN if (avg or 0) >= 0 else RED)
st.write("")

money = st.column_config.NumberColumn(format="$%.2f")
ed = st.data_editor(
    df, hide_index=True, use_container_width=True, height=min(80 + 36 * len(df), 620), key="wl_editor",
    disabled=[c for c in df.columns if c != "Notas"],
    column_config={
        "Prob. ganancia": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "EV (R)": st.column_config.NumberColumn(format="%+.2f"),
        "Score técnico": st.column_config.NumberColumn(format="%+.0f"),
        "Precio": money, "Entrada": money, "Stop": money, "Objetivo 1": money, "Objetivo 2": money,
        "Var. 1d %": st.column_config.NumberColumn(format="%+.2f%%"),
        "Desde que se agregó %": st.column_config.NumberColumn(format="%+.1f%%"),
        "Notas": st.column_config.TextColumn(width="large"),
    })
for _, r in ed.iterrows():
    if r["Notas"] != wl[r["Ticker"]].get("notas", ""):
        store.update_watch(r["Ticker"], notas=r["Notas"])

c1, c2, c3 = st.columns([2, 1, 1])
pick = c1.multiselect("Seleccionar", list(df["Ticker"]), label_visibility="collapsed", placeholder="Selecciona tickers…")
if c2.button("📊 Analizar", disabled=len(pick) != 1, use_container_width=True):
    st.session_state.ticker = pick[0]
    st.switch_page("views/analisis.py")
if c3.button("🗑️ Quitar de la watchlist", disabled=not pick, use_container_width=True):
    store.remove_from_watchlist(pick)
    st.rerun()
st.caption("Los niveles de entrada/stop/objetivos son los del momento en que agregaste la acción. "
           "Para recalcularlos, quítala y vuelve a agregarla desde el escáner o el análisis.")
st.markdown(DISCLAIMER, unsafe_allow_html=True)
