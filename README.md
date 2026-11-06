# TraDiX: plataforma de análisis de acciones (NYSE / NASDAQ)

Escáner de mercado, análisis técnico + fundamental y veredicto con IA (Claude), con entrada, stop-loss y objetivos.

## Usuarios e invitaciones
Login propio con correo y contraseña (sesión de 30 días), registro solo por invitación, IA con Claude (administrador)
y Gemini gratis (invitados), y panel de administración con el uso de cada usuario (Supabase). Configuración: **CONFIGURAR_USUARIOS.md**.

## Usarla en la web (recomendado)
Sigue **DESPLIEGUE_WEB.md**: GitHub + Streamlit Cloud, gratis y sin instalar nada.

## Instalación local (opcional)

1. Instala **Python 3.10 o superior** desde python.org (en Windows marca "Add Python to PATH").
2. Descomprime esta carpeta.
3. Doble clic en **`iniciar_windows.bat`** (en Mac o Linux: `./iniciar_mac_linux.sh`).
   La primera vez crea un entorno e instala las dependencias (2-3 min). Luego se abre el navegador en `http://localhost:8501`.

Para probar sin internet: `iniciar_demo_windows.bat` (usa datos sintéticos).

## Claves (opcionales). Se configuran en ⚙️ Configuración, en la barra lateral

| Clave | Para qué | Costo |
|---|---|---|
| **Anthropic API key** (console.anthropic.com) | Veredicto con Claude en el análisis. Sin clave se usa una síntesis cuantitativa por reglas. | Pago por uso (céntimos por análisis) |
| **Alpha Vantage** (alphavantage.co/support/#api-key) | Universo "Movers del día", noticias con sentimiento y respaldo de fundamentales. Con plan premium también historial y fundamentales completos. | Gratis: ~25 consultas/día |

Las claves se guardan solo en tu PC (`datos/config.json`).

**Fuentes de datos (gratuitas):**
- **Yahoo Finance** (`yfinance`): historial de precios, fundamentales y estados financieros. Retraso de unos 15 min.
- **Finviz** (`finvizfinance`): screener de todo el mercado (nuevos máximos, volumen inusual, compras de insiders, upgrades, patrones) y una ficha de ~80 métricas por acción: short float, insiders, institucionales, rendimientos, fecha de resultados, cambios de rating y noticias.
- **Alpha Vantage**: movers del día y noticias con sentimiento.
Alpha Vantage gratuito no basta para escanear: solo entrega 100 días de historia y 25 consultas diarias, y el historial completo y los fundamentales son premium.

## Módulos

### 1. Escáner de mercado
- Universos: S&P 500, Nasdaq 100, Dow 30, S&P 500 + Nasdaq 100, **screeners de Finviz** (todo el mercado líquido, nuevos máximos, volumen inusual, top gainers, sobreventa, compras de insiders, upgrades, canal ascendente, doble suelo), **todo NYSE + NASDAQ** (~6.000 acciones, filtradas por precio y volumen en dólares), movers del día (Alpha Vantage) o una lista propia.
- Para cada acción calcula 12 indicadores, el puntaje técnico, la **probabilidad de ganancia**, el **valor esperado en R**, la fuerza relativa a 3 meses y los niveles de entrada, stop y objetivos.
- El ranking se ordena por valor esperado. Seleccionas filas y pulsas **⭐ Agregar a watchlist**, o **📊 Analizar**. También puedes exportar a CSV.

### 2. Análisis de acción
- **Técnico (12 indicadores, ponderados):** tendencia SMA50/200 (cruce dorado o de la muerte), SMA50/EMA21, cruce EMA9/21, MACD 12-26-9, RSI 14, ADX/DMI, Bollinger %B, estocástico 14-3-3, OBV y volumen relativo, Money Flow Index, VWAP de 20 días e Ichimoku.
- **Fundamental:** P/E, P/E forward, PEG, P/B, P/S, EV/EBITDA, FCF yield, ROE, ROA, márgenes, crecimiento, deuda/patrimonio, ratio corriente, consenso de analistas y **Piotroski F-Score**.
- **Probabilidad y backtest:** probabilidad histórica de la configuración actual y backtest de 5 años de la señal (acierto, profit factor, drawdown, curva de R).
- **Niveles:** soportes y resistencias por fractales agrupados, y retrocesos de Fibonacci.
- **Plan de operación:** entrada (a mercado, o límite en retroceso si el precio está extendido), stop (ATR o estructural), objetivo 1 (2R o la resistencia más cercana), objetivo 2 (3R) y tamaño de posición según tu capital y el % de riesgo.
- **Veredicto con IA:** Claude recibe toda la evidencia cuantitativa y devuelve COMPRAR / ESPERAR / EVITAR / VENDER EN CORTO, con confianza, probabilidad ajustada, tesis, riesgos, condición de invalidación y catalizadores.

### 3. Watchlist
Muestra la señal y la probabilidad actualizadas, más el estado frente a tus niveles: esperando retroceso, en zona de entrada, operación en curso, objetivo 1 o 2 alcanzado, o stop. También indica el rendimiento desde que agregaste cada acción, y tiene una columna de notas editable.

## Cómo se calcula la "probabilidad de ganancia"
Usa el método de **triple barrera**. Para cada día histórico se simula una compra al cierre con objetivo +3×ATR, stop −1.5×ATR y un máximo de 20 sesiones (los tres valores se pueden ajustar). Se toman los días cuyo **puntaje técnico era similar al actual (±15)** y se mide qué proporción tocó el objetivo antes que el stop. Ese resultado se ajusta con un prior bayesiano hacia la tasa del universo, para no sobreconfiar en pocas muestras.
Con una relación 2:1, el punto de equilibrio es un 33 % de acierto: por encima de eso, el valor esperado es positivo.

> Es una frecuencia histórica, no una garantía. No es asesoría financiera.

## Estructura
```
app.py               navegación y configuración
views/               scanner.py · analisis.py · watchlist.py
core/technical.py    indicadores y puntaje técnico
core/probability.py  triple barrera, probabilidad y backtest
core/fundamental.py  métricas, puntaje fundamental y Piotroski
core/levels.py       entrada, stop, objetivos y tamaño de posición
core/scanner.py      motor del escáner y ranking
core/ai.py           veredicto con Claude y síntesis por reglas
core/finviz.py       screener y ficha de Finviz
core/data.py         Yahoo Finance, Alpha Vantage, universos y modo demo
core/store.py        watchlist, último escaneo y configuración (carpeta datos/)
core/auth.py         acceso: login propio, invitaciones, sesión de 30 días, bloqueo de suspendidos
core/brand.py        logo e identidad TraDiX
core/db.py           usuarios, invitaciones, cuotas de IA y uso (Supabase o SQLite local)
views/admin_*.py     paneles de administración: invitaciones, y usuarios y uso
supabase_schema.sql  tablas para Supabase
```

## Versión dentro de Claude (sin instalar)
Página **TraDiX Claude** en claude.ai, conectada al conector Alpha Vantage del usuario:
- Datos gratuitos: precios diarios (100 días), semanal ajustado (15 años), EPS trimestral con sorpresas, movers del día y cotización.
- La probabilidad se calcula con velas semanales (+2×ATR semanal antes que −1×ATR, máximo 8 semanas).
- El veredicto lo da Claude dentro de la página, sin API key.
- La watchlist es privada y se guarda en Claude.
- Cada análisis nuevo usa 3 consultas (unos 8 análisis al día con el plan gratuito). Repetir el mismo ticker en el día no consume más.
