# Activar usuarios, invitaciones y registro (Google + código por correo)

Mientras no hagas estos pasos, la app sigue funcionando en **modo personal**: entras con tu `APP_PASSWORD` como único usuario y administrador.

Se usan dos servicios gratuitos:
- **Supabase**: base de datos de usuarios, invitaciones, cuotas de IA y uso. Gratis hasta 500 MB.
- **Auth0**: pantalla de registro con **Google** y con **correo + código de verificación**. Gratis hasta 25.000 usuarios.

Tiempo total: unos 20 minutos, una sola vez.

---

## Parte A. Supabase (base de datos)

1. Entra a https://supabase.com, pulsa **Start your project** y entra con tu cuenta de GitHub.
2. Pulsa **New project**:
   - Name: `quantdesk`.
   - Database password: genera una y guárdala.
   - Region: **East US (North Virginia)**, la misma que usa Streamlit Cloud.
   - Pulsa **Create new project** y espera unos 2 minutos.
3. En el menú izquierdo abre **SQL Editor** y pulsa **New query**. Abre el archivo `supabase_schema.sql` de esta carpeta, copia **todo** su contenido, pégalo y pulsa **Run**. Debe decir *Success*.
4. Ve a **Project Settings (engranaje) → API** y copia dos datos:
   - **Project URL**, algo como `https://abcd1234.supabase.co`, para `SUPABASE_URL`.
   - En *Project API keys*, la clave **`service_role`** (pulsa *Reveal*), para `SUPABASE_SERVICE_KEY`.
     Esta clave es secreta: solo va en los Secrets de Streamlit, nunca en GitHub.

## Parte B. Auth0 (inicio de sesión)

1. Entra a https://auth0.com, pulsa **Sign up** y créate una cuenta. Elige región **US** y un nombre de tenant, por ejemplo `quantdesk`.
2. Ve a **Applications → Applications → Create Application**:
   - Name: `QuantDesk`.
   - Tipo: **Regular Web Applications**. Pulsa **Create**.
3. En la pestaña **Settings** de la aplicación:
   - Copia el **Domain**, el **Client ID** y el **Client Secret**.
   - En **Allowed Callback URLs** pega `https://TU-APP.streamlit.app/oauth2callback`.
   - En **Allowed Logout URLs** y **Allowed Web Origins** pega `https://TU-APP.streamlit.app`.
   - Baja hasta el final y pulsa **Save**.

   En los tres casos reemplaza `TU-APP` por el nombre real de tu app (el link que usas para abrirla).
4. **Google:** en **Authentication → Social**, `google-oauth2` viene activado de fábrica. En la pestaña **Applications** de esa conexión, activa QuantDesk.
   Auth0 usa claves de Google de prueba, que sirven para la beta. Más adelante puedes poner tus propias claves de Google Cloud para quitar el aviso de "desarrollo".
5. **Correo con código:** en **Authentication → Passwordless**, activa **Email**. Revisa que **OTP Length = 6**, pulsa **Save** y en su pestaña **Applications** activa QuantDesk.
6. En **Authentication → Authentication Profile** elige **Identifier First**. Así la pantalla muestra "Continuar con Google" y un campo para el correo, y al poner el correo llega el código.
7. **Opcional, para que se vea como la imagen de referencia:** en **Branding → Universal Login → Customization Options** pon tu logo, el color primario `#22c55e` y el fondo `#0b0f17`.
8. Para quitar los usuarios de prueba que crea Auth0, puedes desactivar la conexión **Username-Password-Authentication** en la pestaña *Connections* de la aplicación.

## Parte C. Secrets de Streamlit

En share.streamlit.io, en tu app: **⋮ → Settings → Secrets**. Reemplaza todo por este bloque y completa los valores.

El orden importa: las líneas sueltas van **arriba** y las secciones `[auth]` van **al final**.

```toml
ADMIN_EMAILS = "edwinjespinoza@gmail.com"
ANTHROPIC_API_KEY = "sk-ant-..."
ALPHAVANTAGE_API_KEY = ""
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_SERVICE_KEY = "eyJ..."
APP_URL = "https://TU-APP.streamlit.app"

[auth]
redirect_uri = "https://TU-APP.streamlit.app/oauth2callback"
cookie_secret = "9YHhp12hbOot1ORDPSFOtwGGD_TSXwsF4wElKuhBP2o"

[auth.auth0]
client_id = "CLIENT_ID_DE_AUTH0"
client_secret = "CLIENT_SECRET_DE_AUTH0"
server_metadata_url = "https://TU-DOMINIO.us.auth0.com/.well-known/openid-configuration"
```

- `ADMIN_EMAILS`: el correo con el que tú entrarás (con Google o con código). Ese correo es administrador y no necesita invitación. Para varios administradores, sepáralos con comas.
- `cookie_secret`: ya va generado al azar, déjalo así.
- `server_metadata_url`: usa el **Domain** que copiaste de Auth0, por ejemplo `https://quantdesk.us.auth0.com/.well-known/openid-configuration`.
- `APP_PASSWORD` ya no hace falta: con Auth0 activo se ignora.

Guarda y luego ve a **Manage app → ⋮ → Reboot app**.

## Parte D. Probar

1. Abre tu app. Verás la pantalla **QuantDesk · Inicia sesión**. Pulsa **Continuar con Google o correo** y entra con tu correo de administrador.
2. En el menú lateral aparece **Administración → Invitaciones**. Crea una invitación para un correo tuyo secundario y abre el enlace en otro navegador (o en modo incógnito).
3. Registra ese segundo correo. Te llegará el código de 6 dígitos y quedarás dentro, con la cuota de IA que asignaste.
4. En **Usuarios y uso** verás al nuevo usuario con su último ingreso y su uso.

## Cómo funciona

- **Invitaciones:**
  - Cada enlace tiene una cuota de informes de IA, un número de usos (1 = enlace personal) y una fecha de vencimiento.
  - Si indicas un correo, solo esa persona puede usar el enlace.
  - Si alguien entra sin invitación, la app le pide un código. No puede usar la plataforma.
- **Informes de IA:**
  - Cada informe generado con Claude descuenta 1 de la cuota del usuario. La síntesis por reglas no descuenta.
  - Desde *Usuarios y uso* puedes subir la cuota o reiniciar lo usado (por ejemplo, cada mes).
- **Expulsar o eliminar:**
  - *Suspender* bloquea el acceso de inmediato, y se puede revertir.
  - *Eliminar* deja la cuenta inactiva. Para volver, la persona necesita una invitación nueva.
  - *Eliminar definitivamente* borra también su historial y su watchlist.
- **Watchlist:** cada usuario tiene la suya.
- **Suscripciones (futuro):** el campo `plan` de cada usuario y la cuota de IA son la base para conectar luego un sistema de pagos como Stripe.
