from urllib.parse import quote

import pandas as pd
import streamlit as st

from core import auth, db
from core.ui import DISCLAIMER, GREEN, MUTED, NEUTRAL, RED, kpi_row

if not auth.is_admin():
    st.error("Solo el administrador puede ver esta página.")
    st.stop()

me = auth.current_profile()
st.markdown("## Invitaciones")
st.markdown("<div class='muted'>Genera enlaces de invitación. Los invitados usan Gemini para los informes de IA. "
            f"Base de datos: {db.backend_name()}</div>", unsafe_allow_html=True)

left, right = st.columns([1, 1.25], gap="medium")
with left:
    with st.container(border=True):
        st.markdown("<div class='sec'>Nueva invitación</div>", unsafe_allow_html=True)
        with st.form("new_inv", clear_on_submit=False):
            email = st.text_input("Correo del invitado (opcional)",
                                  help="Si lo indicas, solo esa persona podrá usar la invitación (recomendado).")
            c1, c2 = st.columns(2)
            uses = c1.number_input("Usos del enlace", 1, 500, 1, 1,
                                   help="1 = enlace personal. Más de 1 = enlace para un grupo.")
            days = c2.number_input("Vence en (días)", 1, 365, 7, 1)
            quota = 0
            note = st.text_input("Nota interna (opcional)", placeholder="p. ej. compañero de trading")
            ok = st.form_submit_button("Generar invitación", type="primary", use_container_width=True)
        if ok:
            inv = db.create_invite(me["email"], quota, uses, days, email, note, me.get("name") or "")
            st.session_state["last_invite"] = inv
            db.log_event(me["email"], "invite_created", inv["code"])

        inv = st.session_state.get("last_invite")
        if inv:
            link = auth.invite_link(inv["code"])
            st.success("Invitación creada. Copia el enlace con el botón de la derecha:")
            st.code(link, language=None)
            msg = (f"¡Hola! Te invito a TraDiX, mi plataforma de análisis de acciones con IA "
                   f"(escáner de mercado, análisis técnico y fundamental, entrada/stop/objetivos). "
                   f"Regístrate aquí: {link}")
            st.text_area("Mensaje listo para enviar", msg, height=110)
            c1, c2 = st.columns(2)
            c1.link_button("Enviar por WhatsApp", f"https://wa.me/?text={quote(msg)}", use_container_width=True)
            if inv.get("email"):
                c2.link_button("Enviar por correo", f"mailto:{inv['email']}?subject={quote('Invitación a TraDiX')}&body={quote(msg)}",
                               use_container_width=True)
            st.caption(f"Vence: {str(inv['expires_at'])[:10]} · usos: {inv['max_uses']} · "
                       + (f"solo para {inv['email']}" if inv.get("email") else "cualquier correo"))

invs = db.list_invites()
with right:
    rows = []
    for i in invs:
        stt = db.invite_status(i)
        rows.append({"Código": i["code"], "Estado": stt, "Para": i.get("email") or "Cualquiera",
                     "Usos": f"{int(i.get('uses') or 0)}/{int(i.get('max_uses') or 1)}",
                     "Vence": str(i.get("expires_at") or "")[:10], "Creada": str(i.get("created_at") or "")[:10],
                     "Nota": i.get("note") or ""})
    df = pd.DataFrame(rows)
    act = sum(1 for r in rows if r["Estado"] == "Activa")
    st.markdown(kpi_row([
        ("Invitaciones activas", f"{act}", "pendientes de usar", NEUTRAL),
        ("Usadas", f"{sum(1 for r in rows if r['Estado'] == 'Usada')}", "", GREEN),
        ("Vencidas o revocadas", f"{sum(1 for r in rows if r['Estado'] in ('Vencida', 'Revocada'))}", "", RED),
    ]), unsafe_allow_html=True)
    st.write("")
    if df.empty:
        st.info("Aún no hay invitaciones.")
    else:
        colr = {"Activa": NEUTRAL, "Usada": GREEN, "Vencida": MUTED, "Revocada": RED}
        sel = st.dataframe(df.style.map(lambda v: f"color: {colr.get(v, MUTED)}; font-weight: 600", subset=["Estado"]),
                           hide_index=True, use_container_width=True, height=420, on_select="rerun",
                           selection_mode="multi-row", key="inv_table")
        picked = df.iloc[sel.selection.rows] if sel and sel.selection.rows else df.iloc[0:0]
        c1, c2 = st.columns(2)
        if c1.button(f"Revocar seleccionadas ({len(picked)})", disabled=picked.empty, use_container_width=True):
            for c in picked["Código"]:
                db.revoke_invite(c)
            st.toast("Invitaciones revocadas")
            st.rerun()
        if len(picked) == 1:
            c2.code(auth.invite_link(picked.iloc[0]["Código"]), language=None)

st.markdown(DISCLAIMER, unsafe_allow_html=True)
