"""
Acceso a TraDiX (sin Auth0).

Modo multiusuario (si existen SUPABASE_URL + SUPABASE_SERVICE_KEY, o en modo demo):
  * Registro solo con invitación: nombre, correo y contraseña. Opcional: código de verificación por correo
    (si se configuran SMTP_* en Secrets).
  * Inicio de sesión con correo + contraseña, o con Google (opcional, si existe [auth.google] en Secrets).
  * La sesión se recuerda 30 días en ese navegador (cookie firmada).
  * Los correos en ADMIN_EMAILS son administradores y pueden registrarse sin invitación.

Modo personal (sin Supabase): un solo usuario (el dueño, administrador), con APP_PASSWORD opcional.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import random
import re
import secrets as _secrets
import smtplib
import time
from email.mime.text import MIMEText

import streamlit as st

from core import brand

from . import db
from .store import secret

E = html.escape
SESSION_DAYS = 30
COOKIE = "qd_session"


# =============================================================================
# Configuración
# =============================================================================
def multiuser() -> bool:
    return bool(secret("SUPABASE_URL") and secret("SUPABASE_SERVICE_KEY")) or os.environ.get("TRADING_DEMO") == "1" \
        or secret("MULTIUSER") == "1"


def google_enabled() -> bool:
    try:
        a = st.secrets.get("auth")
        return bool(a and a.get("google"))
    except Exception:
        return False


def smtp_enabled() -> bool:
    return bool(secret("SMTP_USER") and secret("SMTP_PASSWORD"))


def app_base_url() -> str:
    u = secret("APP_URL")
    if u:
        return u.rstrip("/")
    try:
        from urllib.parse import urlparse
        p = urlparse(st.context.url)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""


def invite_link(code: str) -> str:
    return f"{app_base_url()}/?invite={code}"


def _key() -> bytes:
    k = secret("COOKIE_SECRET") or secret("SUPABASE_SERVICE_KEY") or "quantdesk-demo-secret"
    return hashlib.sha256(k.encode()).digest()


# =============================================================================
# Contraseñas y sesión
# =============================================================================
def hash_password(pw: str) -> str:
    salt = _secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2${salt}${h}"


def check_password(pw: str, stored: str | None) -> bool:
    try:
        _, salt, h = (stored or "").split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def _make_token(email: str, pwd_hash: str | None) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    ver = (pwd_hash or "g")[-10:]  # cambiar la contraseña invalida las sesiones guardadas
    msg = f"{email}|{exp}|{ver}"
    sig = hmac.new(_key(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{msg}|{sig}".encode()).decode()


def _read_token(tok: str | None) -> str | None:
    try:
        email, exp, ver, sig = base64.urlsafe_b64decode(tok.encode()).decode().split("|")
        if int(exp) < time.time():
            return None
        if not hmac.compare_digest(sig, hmac.new(_key(), f"{email}|{exp}|{ver}".encode(), hashlib.sha256).hexdigest()[:32]):
            return None
        p = db.get_profile(email)
        if not p or (p.get("password_hash") or "g")[-10:] != ver:
            return None
        return email
    except Exception:
        return None


def _js_cookie(name: str, value: str, max_age: int) -> None:
    import streamlit.components.v1 as components
    v = re.sub(r"[^A-Za-z0-9_\-=.]", "", value)
    components.html(
        f"<script>(function(){{var c='{name}={v}; path=/; max-age={max_age}; SameSite=Lax';"
        f"try{{window.parent.document.cookie=c;}}catch(e){{document.cookie=c;}}}})();</script>", height=0)


def _cookie(name: str) -> str | None:
    try:
        return st.context.cookies.get(name)
    except Exception:
        return None


def _start_session(email: str, name: str, provider: str, remember: bool = True) -> None:
    st.session_state["ident"] = {"email": email, "name": name, "provider": provider}
    st.session_state.pop("logged_out", None)
    if remember and provider != "google":
        p = db.get_profile(email)
        st.session_state["_set_cookie"] = _make_token(email, (p or {}).get("password_hash"))


# =============================================================================
# Correo con código (opcional)
# =============================================================================
def send_code(email: str, purpose: str) -> bool:
    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    st.session_state[f"code_{purpose}"] = {"email": email, "hash": hashlib.sha256(code.encode()).hexdigest(),
                                          "exp": time.time() + 900, "tries": 0}
    subject = "Tu código de TraDiX"
    body = (f"Tu código de verificación es: {code}\n\nVence en 15 minutos.\n"
            f"Si no pediste este código, ignora este correo.\n\nTraDiX")
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, secret("SMTP_FROM") or secret("SMTP_USER"), email
        host, port = secret("SMTP_HOST") or "smtp.gmail.com", int(secret("SMTP_PORT") or 465)
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            s.login(secret("SMTP_USER"), secret("SMTP_PASSWORD"))
            s.send_message(msg)
        return True
    except Exception as e:
        st.error(f"No se pudo enviar el correo: {e}")
        return False


def check_code(purpose: str, code: str) -> bool:
    c = st.session_state.get(f"code_{purpose}")
    if not c or time.time() > c["exp"] or c["tries"] >= 5:
        return False
    c["tries"] += 1
    return hmac.compare_digest(c["hash"], hashlib.sha256(code.strip().encode()).hexdigest())


# =============================================================================
# Pantallas
# =============================================================================
LANDING_CSS = brand.FONTS + """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: none !important; }
.block-container { max-width: 440px !important; padding-top: 6vh !important; }
.qd-card { background: #111A2C; border: 1px solid #22304A; border-radius: 14px; padding: 24px 22px 6px; }
.qd-logo { margin-bottom: 10px; }
.qd-tag { color: #8b95a7; font-family: 'JetBrains Mono', monospace; font-size: .74rem; margin-top: 2px; }
.qd-inv { border: 1px solid #2563eb; background: rgba(37,99,235,.08); border-radius: 10px; padding: 12px; text-align: center;
          margin: 18px 0 4px; font-size: .9rem; }
.qd-inv small { display: block; color: #8b95a7; font-family: 'JetBrains Mono', monospace; font-size: .72rem; margin-top: 4px; }
.qd-h { font-size: 1.35rem; font-weight: 600; margin: 16px 0 2px; }
.qd-sub { color: #8b95a7; font-size: .85rem; margin-bottom: 6px; }
.qd-or { display:flex; align-items:center; gap:10px; color:#6b7280; font-size:.75rem; margin: 8px 0; }
.qd-or:before, .qd-or:after { content:""; flex:1; border-top:1px solid #1f2937; }
.qd-err { border: 1px solid #ef4444; background: rgba(239,68,68,.08); border-radius: 10px; padding: 12px; font-size: .88rem; }
div[data-testid="stForm"] { border: 0; padding: 0; }
</style>
"""


def _pending_invite_code() -> str | None:
    q = st.query_params.get("invite")
    if q:
        st.session_state["pending_invite"] = q
        return q
    return st.session_state.get("pending_invite") or _cookie("qd_invite")


def _head(inv: dict | None, title: str, sub: str) -> None:
    box = ""
    if inv and db.invite_status(inv) == "Activa":
        who = E(inv.get("inviter_name") or "El administrador")
        box = (f"<div class='qd-inv'><b>{who}</b> te invitó a TraDiX."
               f"<small>Acceso beta — regístrate para reclamar tu lugar.</small></div>")
    elif inv:
        box = f"<div class='qd-err' style='margin-top:14px'>Esta invitación está {E(db.invite_status(inv).lower())}. Pide un nuevo enlace.</div>"
    st.markdown(LANDING_CSS + f"<div class='qd-card'><div class='qd-logo'>{brand.wordmark(38, '#111A2C', tagline=True)}</div>"
                f"<div class='qd-tag'>Escáner · análisis técnico y fundamental · IA</div>{box}"
                f"<div class='qd-h'>{title}</div><div class='qd-sub'>{sub}</div></div>", unsafe_allow_html=True)


def _google_button() -> None:
    if google_enabled():
        st.markdown("<div class='qd-or'>O</div>", unsafe_allow_html=True)
        if st.button("Continuar con Google", icon=":material/account_circle:", use_container_width=True):
            st.login("google")


def _screen_signup(code: str | None) -> None:
    inv = db.get_invite(code) if code else None
    if code:
        _js_cookie("qd_invite", code, 3600)
    step = st.session_state.get("signup_step")
    _head(inv, "Crea tu cuenta" if step != "verify" else "Verifica tu correo",
          "Gratis durante la beta." if step != "verify" else
          f"Enviamos un código de 6 dígitos a <b>{E(st.session_state.get('signup_data', {}).get('email', ''))}</b>.")
    if step == "verify":
        with st.form("verify"):
            c = st.text_input("Código de verificación", max_chars=6, placeholder="123456")
            ok = st.form_submit_button("Verificar y entrar", type="primary", use_container_width=True)
        if ok:
            if check_code("signup", c):
                _finish_signup(st.session_state.pop("signup_data"))
            else:
                st.error("Código incorrecto o vencido.")
        if st.button("Volver", use_container_width=True):
            st.session_state.pop("signup_step", None)
            st.rerun()
        return
    with st.form("signup"):
        name = st.text_input("Nombre completo", placeholder="Nombre completo", label_visibility="collapsed")
        email = st.text_input("Correo", placeholder="Correo electrónico", label_visibility="collapsed",
                              value=(inv or {}).get("email") or "")
        pw = st.text_input("Contraseña", type="password", placeholder="Contraseña (mínimo 8 caracteres)",
                           label_visibility="collapsed")
        ok = st.form_submit_button("Crear cuenta", type="primary", use_container_width=True)
    if ok:
        email = email.strip().lower()
        err = _validate_signup(name, email, pw, code)
        if err:
            st.error(err)
        else:
            data = {"name": name.strip(), "email": email, "pw": hash_password(pw), "code": code}
            if smtp_enabled():
                if send_code(email, "signup"):
                    st.session_state["signup_data"] = data
                    st.session_state["signup_step"] = "verify"
                    st.rerun()
            else:
                _finish_signup(data)
    _google_button()
    if st.button("¿Ya tienes cuenta? Inicia sesión", type="tertiary", use_container_width=True):
        st.session_state["auth_view"] = "login"
        st.rerun()


def _validate_signup(name, email, pw, code) -> str | None:
    if not name.strip():
        return "Escribe tu nombre."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return "Correo no válido."
    if len(pw) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    p = db.get_profile(email)
    if p and p.get("status") != "deleted":
        return "Ese correo ya tiene cuenta. Inicia sesión."
    if email in db.admin_emails():
        return None
    if not code:
        return "Necesitas un enlace de invitación para registrarte."
    inv, err = db.check_invite(code, email)
    return err or None


def _finish_signup(data: dict) -> None:
    email = data["email"]
    if email in db.admin_emails():
        p = db.get_profile(email)
        if p:
            db.update_profile(email, password_hash=data["pw"], status="active", role="admin", name=data["name"])
        else:
            db.create_profile(email, data["name"], "admin", 0, None, "password", data["pw"])
    else:
        inv, err = db.check_invite(data.get("code") or "", email)
        if not inv:
            st.error(err or "Invitación no válida.")
            return
        db.redeem_invite(inv, email, data["name"], "password", data["pw"])
        _js_cookie("qd_invite", "", 0)
    st.session_state.pop("pending_invite", None)
    st.session_state.pop("signup_step", None)
    st.session_state["_login_logged"] = True
    _start_session(email, data["name"], "password")
    st.rerun()


def _screen_login() -> None:
    step = st.session_state.get("reset_step")
    if step:
        return _screen_reset(step)
    _head(None, "Inicia sesión", "Acceso solo para usuarios invitados.")
    with st.form("login"):
        email = st.text_input("Correo", placeholder="Correo electrónico", label_visibility="collapsed")
        pw = st.text_input("Contraseña", type="password", placeholder="Contraseña", label_visibility="collapsed")
        ok = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if ok:
        tries = st.session_state.get("_login_tries", 0)
        if tries >= 6:
            st.error("Demasiados intentos. Espera unos minutos y recarga la página.")
        else:
            email = email.strip().lower()
            p = db.get_profile(email)
            if p and check_password(pw, p.get("password_hash")):
                st.session_state.pop("_login_tries", None)
                _start_session(email, p.get("name") or "", "password")
                st.rerun()
            else:
                st.session_state["_login_tries"] = tries + 1
                st.error("Correo o contraseña incorrectos.")
    _google_button()
    c1, c2 = st.columns(2)
    if c1.button("Olvidé mi contraseña", type="tertiary", use_container_width=True):
        st.session_state["reset_step"] = "ask"
        st.rerun()
    if c2.button("Tengo una invitación", type="tertiary", use_container_width=True):
        st.session_state["auth_view"] = "signup"
        st.rerun()


def _screen_reset(step: str) -> None:
    if not smtp_enabled():
        _head(None, "Restablecer contraseña", "")
        st.info("Pide al administrador que restablezca tu contraseña desde el panel de usuarios. "
                "Te dará una contraseña temporal.")
        if st.button("Volver", use_container_width=True):
            st.session_state.pop("reset_step", None)
            st.rerun()
        return
    if step == "ask":
        _head(None, "Restablecer contraseña", "Te enviaremos un código a tu correo.")
        with st.form("reset_ask"):
            email = st.text_input("Correo", placeholder="Correo electrónico", label_visibility="collapsed")
            ok = st.form_submit_button("Enviar código", type="primary", use_container_width=True)
        if ok:
            email = email.strip().lower()
            if db.get_profile(email) and send_code(email, "reset"):
                st.session_state["reset_email"] = email
                st.session_state["reset_step"] = "set"
                st.rerun()
            elif not db.get_profile(email):
                st.error("No hay una cuenta con ese correo.")
    else:
        _head(None, "Nueva contraseña", f"Código enviado a <b>{E(st.session_state.get('reset_email', ''))}</b>.")
        with st.form("reset_set"):
            c = st.text_input("Código", max_chars=6, placeholder="123456", label_visibility="collapsed")
            pw = st.text_input("Nueva contraseña", type="password", placeholder="Nueva contraseña (mín. 8)",
                               label_visibility="collapsed")
            ok = st.form_submit_button("Guardar y entrar", type="primary", use_container_width=True)
        if ok:
            em = st.session_state.get("reset_email", "")
            if len(pw) < 8:
                st.error("Mínimo 8 caracteres.")
            elif check_code("reset", c):
                db.update_profile(em, password_hash=hash_password(pw))
                p = db.get_profile(em)
                for k in ("reset_step", "reset_email"):
                    st.session_state.pop(k, None)
                _start_session(em, p.get("name") or "", "password")
                st.rerun()
            else:
                st.error("Código incorrecto o vencido.")
    if st.button("Volver", use_container_width=True):
        st.session_state.pop("reset_step", None)
        st.rerun()


def _screen_message(title: str, msg: str, email: str) -> None:
    _head(None, title, f"Cuenta: <b>{E(email)}</b>")
    st.markdown(f"<div class='qd-err'>{msg}</div>", unsafe_allow_html=True)
    if st.button("Salir", use_container_width=True):
        logout()


def logout() -> None:
    google = bool((st.session_state.get("ident") or {}).get("provider") == "google")
    for k in ("profile", "ident", "pending_invite", "_login_logged", "auth_ok", "_set_cookie"):
        st.session_state.pop(k, None)
    st.session_state["logged_out"] = True
    if google:
        st.logout()
    st.rerun()


# =============================================================================
# Puerta de acceso
# =============================================================================
def _identity() -> dict | None:
    if st.session_state.get("ident"):
        return st.session_state["ident"]
    if google_enabled():
        try:
            if st.user.is_logged_in:
                ident = {"email": str(st.user.get("email") or "").lower(), "name": st.user.get("name") or "",
                         "provider": "google"}
                st.session_state["ident"] = ident
                return ident
        except Exception:
            pass
    if not st.session_state.get("logged_out"):
        em = _read_token(_cookie(COOKIE))
        if em:
            p = db.get_profile(em) or {}
            ident = {"email": em, "name": p.get("name") or "", "provider": "password"}
            st.session_state["ident"] = ident
            return ident
    return None


def gate() -> dict:
    """Devuelve el perfil con acceso; si no, muestra la pantalla correspondiente y detiene la app."""
    if not multiuser():  # ---------- modo personal
        pwd = secret("APP_PASSWORD")
        if pwd and not st.session_state.get("auth_ok"):
            _head(None, "Acceso privado", "Ingresa tu contraseña.")
            with st.form("pwd"):
                p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    if p == pwd:
                        st.session_state.auth_ok = True
                        st.rerun()
                    st.error("Contraseña incorrecta")
            st.stop()
        p = db.get_profile("owner@local") or db.create_profile("owner@local", "Administrador", "admin", 0, None, "local")
        st.session_state["profile"] = p
        return p

    if st.session_state.get("logged_out"):  # borrar la cookie tras cerrar sesión
        _js_cookie(COOKIE, "", 0)

    try:
        ident = _identity()
    except Exception as e:
        st.error(f"No se pudo conectar con la base de datos de usuarios: {e}")
        st.stop()

    code = _pending_invite_code()
    if not ident:
        view = st.session_state.get("auth_view") or ("signup" if code else "login")
        _screen_signup(code) if view == "signup" else _screen_login()
        st.stop()

    email = ident["email"]
    p = db.get_profile(email)
    is_admin = email in db.admin_emails()

    if is_admin:
        if not p:
            p = db.create_profile(email, ident.get("name") or "Administrador", "admin", 0, None, ident["provider"])
        elif p.get("role") != "admin" or p.get("status") != "active":
            db.update_profile(email, role="admin", status="active")
            p = db.get_profile(email)
    elif not p or p.get("status") == "deleted":
        # entró con Google sin cuenta: necesita invitación válida
        inv, err = (db.check_invite(code, email) if code else (db.find_invite_for_email(email), ""))
        if not inv:
            _head(None, "Necesitas una invitación", f"Entraste como <b>{E(email)}</b>.")
            st.markdown(f"<div class='qd-err'>{E(err or 'No encontramos una invitación para tu cuenta. Abre el enlace que te enviaron.')}</div>",
                        unsafe_allow_html=True)
            if st.button("Salir", use_container_width=True):
                logout()
            st.stop()
        p = db.redeem_invite(inv, email, ident.get("name") or "", ident["provider"])
        st.session_state["_login_logged"] = True
        _js_cookie("qd_invite", "", 0)
        st.toast("¡Bienvenido a TraDiX! Tu cuenta quedó activada.", icon="🎉")
    elif p.get("status") == "suspended":
        st.session_state.pop("ident", None)
        _js_cookie(COOKIE, "", 0)
        _screen_message("Acceso suspendido", "Tu acceso a TraDiX fue suspendido por el administrador.", email)
        st.stop()

    if st.session_state.get("_set_cookie"):
        _js_cookie(COOKIE, st.session_state.pop("_set_cookie"), SESSION_DAYS * 86400)
    if "invite" in st.query_params:
        del st.query_params["invite"]
    st.session_state.pop("pending_invite", None)
    if not st.session_state.get("_login_logged"):
        db.touch_login(p)
        st.session_state["_login_logged"] = True
        p = db.get_profile(email) or p
    st.session_state["profile"] = p
    return p


def current_profile() -> dict | None:
    return st.session_state.get("profile")


def is_admin() -> bool:
    p = current_profile()
    return bool(p and p.get("role") == "admin")


def admin_reset_password(email: str) -> str:
    """El administrador genera una contraseña temporal para un usuario."""
    tmp = "QD-" + _secrets.token_urlsafe(6)
    db.update_profile(email, password_hash=hash_password(tmp))
    return tmp
