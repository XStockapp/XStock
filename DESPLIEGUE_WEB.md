# Despliegue de XStock

XStock corre en **Render** y se publica en **https://xstockapp.com**.
Cada cambio que entra a la rama `main` de GitHub (`xstockapp/XStock`) se despliega solo.

## Servicio en Render (`xstock`)

| Campo | Valor |
|---|---|
| Runtime | Python 3 |
| Region | Ohio (US East) |
| Instance | Starter ($7/mes) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `mkdir -p .streamlit && cp /etc/secrets/secrets.toml .streamlit/secrets.toml; streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |
| Health Check Path | `/_stcore/health` |
| Auto-Deploy | On Commit |

**Environment Variables:** `PYTHON_VERSION = 3.11.9`, `COOKIE_SECRET` (valor aleatorio).

**Secret File `secrets.toml`:** `ADMIN_EMAILS`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `ALPHAVANTAGE_API_KEY`, `APP_URL = "https://xstockapp.com"`
y, opcionales, `SMTP_USER` / `SMTP_PASSWORD`. El archivo vive solo en Render, nunca en el repositorio.

## Dominio (Cloudflare DNS)

| Tipo | Nombre | Destino | Proxy |
|---|---|---|---|
| CNAME | `@` | `xstock-r3jx.onrender.com` | DNS only |
| CNAME | `www` | `xstock-r3jx.onrender.com` | DNS only |

`www.xstockapp.com` redirige a `xstockapp.com`. Los registros MX/TXT son del correo
(Cloudflare Email Routing → `contacto@xstockapp.com`): no tocarlos.

## Datos

Usuarios, invitaciones, uso y watchlists viven en **Supabase**. El disco de Render es efímero:
lo que quede en `datos/` (configuración global, caché del último escaneo) se reinicia en cada despliegue.
