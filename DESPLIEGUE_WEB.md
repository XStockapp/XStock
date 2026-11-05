# Publicar QuantDesk en la web (gratis, sin instalar nada)

Tiempo total: unos 15 minutos, una sola vez. Al final tendrás un link del tipo
`https://tu-app.streamlit.app` que abres desde tu PC o tu celular.

---

## Paso 1. Crear la cuenta de GitHub
1. Entra a https://github.com/signup y crea la cuenta (correo, contraseña y nombre de usuario).
2. Confirma el código que llega a tu correo y elige el plan **Free**.

## Paso 2. Crear el repositorio y subir los archivos
1. Ya dentro de GitHub, pulsa **+** (arriba a la derecha) y luego **New repository**.
2. En *Repository name* escribe `quantdesk`.
3. Marca **Private** (solo tú ves el código). Streamlit Cloud gratuito admite repos privados.
4. Pulsa **Create repository**.
5. En la página del repo vacío, haz clic en el enlace **uploading an existing file**.
6. Descomprime `QuantDesk.zip` en tu PC, abre la carpeta `trading_app` y **arrastra todo su contenido** a la ventana de GitHub.
   Eso incluye las carpetas `core`, `views` y `.streamlit`, y los archivos `app.py`, `requirements.txt` y los demás.
   Arrastra lo que hay *dentro* de `trading_app`, no la carpeta en sí: `app.py` tiene que quedar en la raíz del repo.
7. Abajo pulsa **Commit changes**.

## Paso 3. Desplegar en Streamlit Community Cloud
1. Entra a https://share.streamlit.io y elige **Continue with GitHub**. Autoriza el acceso, incluyendo los repos privados.
2. Pulsa **Create app**, luego **Deploy a public app from GitHub**.
3. Completa:
   - Repository: `tu-usuario/quantdesk`
   - Branch: `main`
   - Main file path: `app.py`
   - App URL: elige un nombre, por ejemplo `edwin-quantdesk`
4. Abre **Advanced settings**, elige **Python 3.12** y pega esto en **Secrets**, con tus valores:
   ```toml
   APP_PASSWORD = "elige-una-contraseña-segura"
   ANTHROPIC_API_KEY = "sk-ant-..."
   ALPHAVANTAGE_API_KEY = "tu-clave-alpha-vantage"
   GIST_TOKEN = "github_pat_..."
   ```
   Puedes dejar fuera cualquier línea que todavía no tengas y agregarla después (*Settings → Secrets*).
5. Pulsa **Deploy**. La primera vez instala todo en 2-4 minutos. Después la app se abre sola.

> La **contraseña es importante**: el link es público y, sin ella, cualquiera podría usar tu API key de Claude.

## Paso 4 (recomendado). Watchlist sincronizada en la nube
Sin este paso, la watchlist se borra cada vez que Streamlit reinicia la app.
1. En GitHub ve a tu foto → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Ponle de nombre `quantdesk-watchlist` y como vencimiento 1 año.
3. En *Permissions*, sección **Account permissions**, busca **Gists** y elige **Read and write**.
4. Pulsa **Generate token**, copia el valor (`github_pat_...`) y pégalo como `GIST_TOKEN` en los Secrets de la app.

La app crea un *gist* privado llamado `quantdesk_watchlist.json` y guarda ahí tu watchlist. La verás igual en el PC y en el celular.

## Dónde conseguir las claves
- **Anthropic (Claude):** https://console.anthropic.com → API Keys → Create key. Necesita algo de saldo; cada análisis cuesta centavos.
- **Alpha Vantage:** https://www.alphavantage.co/support/#api-key (gratis).

## Actualizar la app más adelante
Sube los archivos nuevos al repo (*Add file → Upload files*). Streamlit Cloud se actualiza solo en uno o dos minutos.

## Limitaciones del plan gratuito de Streamlit Cloud
- La app "duerme" tras unos días sin uso. Se despierta con un clic en unos 30 segundos.
- ~1 GB de RAM. Escanear "Todo NYSE + NASDAQ" (~6.000 acciones) puede ser lento o quedarse sin memoria. Para todo el mercado usa **"Finviz · Todo el mercado líquido"**, que ya filtra unas 1.500 acciones con volumen y capitalización suficientes.
- Yahoo y Finviz a veces limitan las peticiones desde servidores en la nube. Si un escaneo falla, espera un minuto y repite.
