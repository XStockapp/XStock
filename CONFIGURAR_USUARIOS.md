# XStock · Usuarios, invitaciones e IA

XStock usa **solo dos servicios externos** para el modo multiusuario:

| Servicio | Para qué | Costo |
|---|---|---|
| **Supabase** | Guarda usuarios, contraseñas (cifradas), invitaciones, uso y watchlists | Gratis |
| **Gemini (Google AI Studio)** | Informe IA de los invitados | Gratis (plan Flash) |

El login es propio (correo + contraseña), con sesión recordada 30 días. No hay Auth0 ni login de Streamlit.

---

## 1. Supabase (una sola vez)

1. Entra a https://supabase.com → **Start your project** → *Continue with GitHub*.
2. **New project**: nombre `xstock`, genera la *Database password* (guárdala), región **East US (North Virginia)**. **No** uses "Connect GitHub".
3. **SQL Editor → New query** → pega todo `supabase_schema.sql` → **Run** → debe decir *Success*.
4. Copia:
   - **Project URL** (botón *Copy* en la portada del proyecto) → `SUPABASE_URL`
   - **Project Settings ⚙️ → API Keys → Secret keys** (`sb_secret_...`) → `SUPABASE_SERVICE_KEY`
     (también sirve la clave antigua `service_role` que empieza con `eyJ...`).

> La clave secreta da acceso total a la base. Solo va en los Secrets de Streamlit. Nunca en GitHub ni en chats.

## 2. Gemini

1. https://aistudio.google.com/apikey → **Create API key**.
2. Pega la clave en `GEMINI_API_KEY`. XStock usa el modelo Flash vigente y cambia solo a otro si Google retira uno.
3. Plan gratuito: tiene límite por minuto/día por proyecto y Google puede usar esos datos para mejorar sus modelos.

## 3. Secrets de Streamlit

Render → servicio `xstock` → **Environment → Secret Files → secrets.toml** → pega el contenido de `.streamlit/secrets.toml.ejemplo` con tus valores → **Save**.

## 4. Primer ingreso (administrador)

1. Abre la app → **Tengo una invitación** → regístrate con el correo que pusiste en `ADMIN_EMAILS`.
   Los administradores pueden registrarse sin invitación.
2. Verás la sección **Administración** en la barra lateral.

## 5. Invitar usuarios

**Administración → Invitaciones**: correo (opcional), número de usos y días de vigencia → **Generar invitación**.
Comparte el link por WhatsApp o correo. El invitado abre el link, pone nombre, correo y contraseña, y entra.

## 6. Gestionar usuarios

**Administración → Usuarios y uso**: último ingreso, ingresos, análisis, escaneos, estado.
Marca uno o varios y usa **Expulsar/suspender**, **Reactivar**, **Restablecer contraseña** (genera una temporal `XS-...` que le envías) o **Eliminar**.

## 7. IA por rol

| | Claude (Anthropic) | Gemini | Sin IA (reglas) |
|---|---|---|---|
| Administrador | ✅ | ✅ | ✅ |
| Invitado | gris | ✅ | ✅ |

## Opcional (más adelante)

- **Códigos por correo** (verificación al registrarse y "Olvidé mi contraseña"): Gmail → Seguridad → Verificación en 2 pasos → *Contraseñas de aplicación* → crea una y llena `SMTP_*`. Sin esto, si alguien olvida su contraseña, la restableces tú desde el panel.
- **Botón Google**: Google Cloud Console → APIs y servicios → Credenciales → *ID de cliente OAuth* (aplicación web) con URI de redirección `https://xstockapp.com/oauth2callback`; descomenta `[auth]` y `[auth.google]` en los Secrets.
