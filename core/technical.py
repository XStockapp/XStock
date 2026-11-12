"""
Análisis técnico: indicadores profesionales calculados con pandas/numpy
(sin dependencias externas, fórmulas estándar de Wilder, Appel, Bollinger, etc.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Indicadores base
# --------------------------------------------------------------------------
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    """Media suavizada de Wilder (RMA)."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = wilder(d.clip(lower=0), n)
    dn = wilder(-d.clip(upper=0), n)
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(up.notna())


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["Close"].shift()
    return pd.concat(
        [df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return wilder(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14):
    up = df["High"].diff()
    dn = -df["Low"].diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = wilder(true_range(df), n)
    pdi = 100 * wilder(plus_dm, n) / tr
    mdi = 100 * wilder(minus_dm, n) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return wilder(dx, n), pdi, mdi


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std(ddof=0)
    return mid + k * sd, mid, mid - k * sd


def stochastic(df: pd.DataFrame, n=14, d=3):
    ll = df["Low"].rolling(n).min()
    hh = df["High"].rolling(n).max()
    k = 100 * (df["Close"] - ll) / (hh - ll).replace(0, np.nan)
    k = k.rolling(3).mean()  # estocástico lento
    return k, k.rolling(d).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    sign = np.sign(df["Close"].diff()).fillna(0)
    return (sign * df["Volume"]).cumsum()


def mfi(df: pd.DataFrame, n=14) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    rmf = tp * df["Volume"]
    pos = rmf.where(tp > tp.shift(), 0.0).rolling(n).sum()
    neg = rmf.where(tp < tp.shift(), 0.0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def rolling_vwap(df: pd.DataFrame, n=20) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).rolling(n).sum() / df["Volume"].rolling(n).sum()


def ichimoku(df: pd.DataFrame):
    h, l = df["High"], df["Low"]
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    return tenkan, kijun, span_a, span_b


# --------------------------------------------------------------------------
# Soportes / resistencias y Fibonacci
# --------------------------------------------------------------------------
def pivot_levels(df: pd.DataFrame, window: int = 5, lookback: int = 250, tol: float = 0.015):
    """Detecta máximos/mínimos locales (fractales) y los agrupa en niveles."""
    d = df.tail(lookback)
    highs, lows = d["High"].values, d["Low"].values
    pts = []
    for i in range(window, len(d) - window):
        if highs[i] == highs[i - window : i + window + 1].max():
            pts.append(highs[i])
        if lows[i] == lows[i - window : i + window + 1].min():
            pts.append(lows[i])
    pts.sort()
    clusters: list[list[float]] = []
    for p in pts:
        if clusters and abs(p - np.mean(clusters[-1])) / p < tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    # nivel = promedio del grupo; fuerza = cantidad de toques
    levels = [(float(np.mean(c)), len(c)) for c in clusters]
    price = float(df["Close"].iloc[-1])
    supports = sorted([lv for lv in levels if lv[0] < price], key=lambda x: -x[0])
    resist = sorted([lv for lv in levels if lv[0] > price], key=lambda x: x[0])
    return supports, resist


def fibonacci(df: pd.DataFrame, lookback: int = 126):
    d = df.tail(lookback)
    hi, lo = float(d["High"].max()), float(d["Low"].min())
    up = d["High"].idxmax() > d["Low"].idxmin()  # tramo alcista (mínimo antes que máximo)
    rng = hi - lo
    ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    if up:
        lv = {f"{r*100:.1f}%": hi - r * rng for r in ratios}
    else:
        lv = {f"{r*100:.1f}%": lo + r * rng for r in ratios}
    return {"tramo": "alcista" if up else "bajista", "max": hi, "min": lo, "niveles": lv}


# --------------------------------------------------------------------------
# Cálculo completo
# --------------------------------------------------------------------------
def wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n, min_periods=n).apply(lambda x: float(np.dot(x, w) / w.sum()), raw=True)


def _ma(s: pd.Series, tipo: str, n: int) -> pd.Series:
    n = max(2, int(n))
    return ema(s, n) if tipo == "EMA" else (wma(s, n) if tipo == "WMA" else sma(s, n))


def compute_all(df: pd.DataFrame, settings: dict | None = None) -> pd.DataFrame:
    """Calcula todos los indicadores. Con `settings` (ajustes del perfil del usuario) las cuatro
    medias, el RSI, el MACD, el ADX y Bollinger usan los periodos elegidos; sin ajustes, los clásicos.
    Las medias se guardan en las ranuras EMA9 / EMA21 / SMA50 / SMA200 (rápida, media, lenta, larga)."""
    from .profiles import BASE_SETTINGS, MA_SLOTS
    st_ = settings or BASE_SETTINGS
    df = df.copy()
    c = df["Close"]
    df["SMA20"] = sma(c, 20)
    for slot, m in zip(MA_SLOTS, st_["mas"]):
        df[slot] = _ma(c, m.get("tipo", "EMA"), m.get("periodo", 20))
    df["RSI"] = rsi(c, int(st_["rsi"]["periodo"]))
    df["MACD"], df["MACD_signal"], df["MACD_hist"] = macd(c, int(st_["macd"]["rapida"]), int(st_["macd"]["lenta"]),
                                                           int(st_["macd"]["senal"]))
    df["ATR"] = atr(df)
    df["ADX"], df["+DI"], df["-DI"] = adx(df, int(st_["adx"]["periodo"]))
    df["ADX_KEY"] = float((st_.get("adx") or {}).get("umbral", ADX_KEY))
    df["BB_up"], df["BB_mid"], df["BB_low"] = bollinger(c, int(st_["bollinger"]["periodo"]), float(st_["bollinger"]["desv"]))
    df["STOCH_K"], df["STOCH_D"] = stochastic(df)
    df["OBV"] = obv(df)
    df["OBV_EMA"] = ema(df["OBV"], 20)
    df["MFI"] = mfi(df)
    df["VWAP20"] = rolling_vwap(df)
    df["VOL_SMA20"] = sma(df["Volume"], 20)
    df["TENKAN"], df["KIJUN"], df["SPAN_A"], df["SPAN_B"] = ichimoku(df)
    df.attrs["settings"] = st_
    return df


# --------------------------------------------------------------------------
# Señales vectorizadas (cada una en [-1, +1]) y puntaje técnico
# --------------------------------------------------------------------------
WEIGHTS = {
    "Tendencia SMA50/200": 2.0,
    "Tendencia SMA50/EMA21": 1.5,
    "Cruce EMA9/EMA21": 1.0,
    "MACD (12,26,9)": 1.5,
    "RSI (14)": 1.2,
    "ADX/DMI (14)": 1.2,
    "Bollinger %B": 0.8,
    "Estocástico (14,3,3)": 0.8,
    "Volumen / OBV": 1.2,
    "Money Flow Index": 0.6,
    "VWAP 20 días": 0.6,
    "Ichimoku": 1.0,
    "Canal / rango": 1.2,
}

CANAL_N = 60
ADX_KEY = 23.0  # nivel clave por defecto del ADX (suavizado 14, DI 14, nivel 23)
# Filtro de régimen del ADX: con ADX bajo el nivel clave (rango) las señales seguidoras de tendencia pierden
# validez; con ADX sobre el nivel clave (tendencia) los osciladores de reversión pierden validez.
_TENDENCIA = ("Tendencia SMA50/EMA21", "Cruce EMA9/EMA21", "MACD (12,26,9)", "Ichimoku")
_OSCILADORES = ("RSI (14)", "Bollinger %B", "Estocástico (14,3,3)", "Money Flow Index")


def adx_key(df: pd.DataFrame) -> float:
    return float(df["ADX_KEY"].iloc[-1]) if "ADX_KEY" in df and pd.notna(df["ADX_KEY"].iloc[-1]) else ADX_KEY


def adx_regimen(df: pd.DataFrame) -> dict:
    """Estado del filtro principal: ADX(14,14,nivel clave) y dirección del DMI en la última vela."""
    r = df.iloc[-1]
    key = adx_key(df)
    a, pdi, ndi = float(r["ADX"]), float(r["+DI"]), float(r["-DI"])
    sube = bool(len(df) > 3 and a > float(df["ADX"].iloc[-4]))
    reg = "tendencia" if a >= key else "rango"
    return {"adx": round(a, 1), "+DI": round(pdi, 1), "-DI": round(ndi, 1), "nivel_clave": key,
            "configuracion": f"ADX Smoothing 14 · DI Length 14 · Key Level {key:g}",
            "regimen": reg, "adx_creciente": sube,
            "direccion": "alcista" if pdi > ndi else "bajista",
            "lectura": (f"ADX {a:.1f} sobre el nivel clave {key:g}: tendencia {'alcista' if pdi > ndi else 'bajista'} "
                        f"con fuerza{' creciente' if sube else ''}; las señales de tendencia son válidas y los "
                        f"osciladores en extremo pierden peso." if reg == "tendencia" else
                        f"ADX {a:.1f} bajo el nivel clave {key:g}: mercado en rango o consolidación; las señales de "
                        f"tendencia (medias, MACD) pierden validez y se prioriza operar entre soporte y resistencia.")}


def channel_frame(df: pd.DataFrame, n: int = CANAL_N) -> pd.DataFrame:
    """Canal de regresión móvil (vectorizado) para cada vela: tipo (1 alcista, −1 bajista, 0 lateral, NaN sin
    canal claro) y posición del cierre dentro del canal (0 = soporte −2σ, 1 = resistencia +2σ)."""
    c = df["Close"].astype(float)
    i = pd.Series(np.arange(len(c), dtype=float), index=c.index)
    my, mi = c.rolling(n).mean(), i.rolling(n).mean()
    vt = (n * n - 1) / 12.0
    b = ((c * i).rolling(n).mean() - mi * my) / vt
    vy = c.rolling(n).var(ddof=0)
    rv = (vy - b * b * vt).clip(lower=1e-12)
    r2 = 1 - rv / vy.replace(0, np.nan)
    sd = np.sqrt(rv)
    yhat = my + b * (n - 1) / 2
    lower, upper = yhat - 2 * sd, yhat + 2 * sd
    pos = (c - lower) / (upper - lower).replace(0, np.nan)
    a = df["ATR"] if "ATR" in df else atr(df)
    move = b * n
    tipo = pd.Series(np.select([(r2 >= 0.55) & (move >= 2 * a), (r2 >= 0.55) & (move <= -2 * a),
                                (move.abs() < 1.5 * a) & ((upper - lower) <= 8 * a)], [1.0, -1.0, 0.0], np.nan),
                     index=c.index).where(my.notna())
    return pd.DataFrame({"tipo": tipo, "pos": pos, "sup": upper, "inf": lower})


def channel_signal_series(ch: pd.DataFrame) -> pd.Series:
    """Misma regla que patterns.channel_signal, vela a vela."""
    t, p = ch["tipo"], ch["pos"]
    up = np.where(p < -0.05, -0.6, np.clip(0.3 + (0.5 - p), -0.1, 0.8))
    dn = np.where(p > 1.05, 0.6, np.clip(-0.3 - (p - 0.5), -0.8, 0.1))
    lat = np.where(p > 1.05, 0.5, np.where(p < -0.05, -0.5, np.clip((0.5 - p) * 1.2, -0.6, 0.6)))
    out = np.select([t == 1, t == -1, t == 0], [up, dn, lat], np.nan)
    return pd.Series(out, index=ch.index).where(p.notna())


def _pm(cond) -> pd.Series:
    return pd.Series(np.where(cond, 1.0, -1.0), index=cond.index)


def signal_matrix(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    S = pd.DataFrame(index=df.index)
    S["Tendencia SMA50/200"] = ((_pm(c > df["SMA200"]) + 0.5 * _pm(df["SMA50"] > df["SMA200"])) / 1.5).where(df["SMA200"].notna())
    S["Tendencia SMA50/EMA21"] = (0.6 * _pm(c > df["SMA50"]) + 0.4 * _pm(df["EMA21"] > df["SMA50"])).where(df["SMA50"].notna())
    S["Cruce EMA9/EMA21"] = _pm(df["EMA9"] > df["EMA21"]).where(df["EMA21"].notna())
    S["MACD (12,26,9)"] = (0.5 * _pm(df["MACD"] > df["MACD_signal"]) + 0.3 * _pm(df["MACD"] > 0)
                           + 0.2 * _pm(df["MACD_hist"] > df["MACD_hist"].shift())).where(df["MACD_signal"].notna())
    r = df["RSI"]
    S["RSI (14)"] = np.select([r >= 70, r <= 30], [-0.6, 0.6], ((r - 50) / 20).clip(-1, 1))
    key = df["ADX_KEY"] if "ADX_KEY" in df else ADX_KEY
    S["ADX/DMI (14)"] = (_pm(df["+DI"] > df["-DI"]) * ((df["ADX"] - (key - 8)) / 16).clip(0, 1)).where(df["ADX"].notna())
    pb = (c - df["BB_low"]) / (df["BB_up"] - df["BB_low"]).replace(0, np.nan)
    S["Bollinger %B"] = np.select([pb < 0.05, pb > 0.95], [0.5, -0.5], ((pb - 0.5) * 0.8).clip(-1, 1))
    k, d = df["STOCH_K"], df["STOCH_D"]
    S["Estocástico (14,3,3)"] = np.select([(k < 20) & (k > d), (k > 80) & (k < d)], [0.8, -0.8], 0.3 * _pm(k > d))
    vr = df["Volume"] / df["VOL_SMA20"].replace(0, np.nan)
    up_day = c > c.shift()
    vol = 0.6 * _pm(df["OBV"] > df["OBV_EMA"]) + np.where(vr > 1.5, np.where(up_day, 0.4, -0.4), 0.0)
    S["Volumen / OBV"] = vol.clip(-1, 1)
    m = df["MFI"]
    S["Money Flow Index"] = np.select([m > 80, m < 20], [-0.6, 0.6], ((m - 50) / 30).clip(-1, 1))
    S["VWAP 20 días"] = (0.7 * _pm(c > df["VWAP20"])).where(df["VWAP20"].notna())
    top = df[["SPAN_A", "SPAN_B"]].max(axis=1)
    bot = df[["SPAN_A", "SPAN_B"]].min(axis=1)
    cloud = np.select([c > top, c < bot], [1.0, -1.0], 0.0)
    S["Ichimoku"] = (0.7 * cloud + 0.3 * _pm(df["TENKAN"] > df["KIJUN"])).where(df["SPAN_B"].notna())
    S["Canal / rango"] = channel_signal_series(channel_frame(df))
    # NaN en indicadores ⇒ NaN en señal
    for col in ("RSI (14)", "Bollinger %B", "Estocástico (14,3,3)", "Money Flow Index"):
        base = {"RSI (14)": r, "Bollinger %B": pb, "Estocástico (14,3,3)": k, "Money Flow Index": m}[col]
        S[col] = S[col].where(base.notna())
    # filtro de régimen del ADX (condiciona la validez del resto de métricas)
    tend = (df["ADX"] >= key)
    for col in _TENDENCIA:
        S[col] = S[col] * np.where(tend, 1.0, 0.5)
    for col in _OSCILADORES:
        S[col] = S[col] * np.where(tend, 0.7, 1.0)
    return S


def score_series(df: pd.DataFrame) -> pd.Series:
    """Puntaje técnico -100..+100 para cada barra (requiere compute_all)."""
    S = signal_matrix(df)
    w = pd.Series(WEIGHTS)
    num = (S * w).sum(axis=1, min_count=1)
    den = S.notna().mul(w).sum(axis=1)
    out = 100 * num / den.replace(0, np.nan)
    return out.where(S.notna().sum(axis=1) >= 10)


def _txt_canal(df: pd.DataFrame) -> str:
    ch = channel_frame(df).iloc[-1]
    if pd.isna(ch["tipo"]):
        return "Sin canal claro en las últimas 60 velas"
    nom = {1.0: "Canal alcista", -1.0: "Canal bajista", 0.0: "Rango lateral"}[float(ch["tipo"])]
    p = float(ch["pos"])
    zona = ("ruptura por abajo" if p < -0.05 else "ruptura por arriba" if p > 1.05 else "cerca del soporte" if p < 0.25
            else "cerca de la resistencia" if p > 0.75 else "zona media")
    return f"{nom} · precio {zona} ({p * 100:.0f}% del ancho)"


def explain_last(df: pd.DataFrame) -> dict:
    """Detalle legible de las señales de la última barra."""
    S = signal_matrix(df).iloc[-1]
    r, p = df.iloc[-1], df.iloc[-2]
    px = r["Close"]
    txt = {
        "Tendencia SMA50/200": f"Precio {'sobre' if px > r['SMA200'] else 'bajo'} SMA200 · "
                               f"{'Cruce dorado (SMA50>SMA200)' if r['SMA50'] > r['SMA200'] else 'Cruce de la muerte (SMA50<SMA200)'}",
        "Tendencia SMA50/EMA21": f"Precio {'sobre' if px > r['SMA50'] else 'bajo'} SMA50",
        "Cruce EMA9/EMA21": "EMA9 sobre EMA21" if r["EMA9"] > r["EMA21"] else "EMA9 bajo EMA21",
        "MACD (12,26,9)": f"MACD {'sobre' if r['MACD'] > r['MACD_signal'] else 'bajo'} la señal · histograma "
                          f"{'creciente' if r['MACD_hist'] > p['MACD_hist'] else 'decreciente'}",
        "RSI (14)": f"RSI {r['RSI']:.1f} · " + ("sobrecompra" if r["RSI"] >= 70 else "sobreventa" if r["RSI"] <= 30 else "zona neutral"),
        "ADX/DMI (14)": f"ADX {r['ADX']:.1f} · {'tendencia (sobre nivel ' + format(adx_key(df), 'g') + ')' if r['ADX'] >= adx_key(df) else 'rango (bajo nivel ' + format(adx_key(df), 'g') + ')'} · "
                        f"{'+DI domina' if r['+DI'] > r['-DI'] else '-DI domina'}",
        "Bollinger %B": f"%B {((px - r['BB_low']) / (r['BB_up'] - r['BB_low'])):.2f}",
        "Estocástico (14,3,3)": f"%K {r['STOCH_K']:.1f} / %D {r['STOCH_D']:.1f}",
        "Volumen / OBV": f"OBV en {'acumulación' if r['OBV'] > r['OBV_EMA'] else 'distribución'} · volumen "
                         f"{r['Volume'] / r['VOL_SMA20']:.1f}x promedio",
        "Money Flow Index": f"MFI {r['MFI']:.1f}",
        "VWAP 20 días": f"Precio {'sobre' if px > r['VWAP20'] else 'bajo'} el VWAP de 20 días",
        "Canal / rango": _txt_canal(df),
        "Ichimoku": "Precio " + ("sobre" if px > max(r['SPAN_A'], r['SPAN_B']) else
                                 "bajo" if px < min(r['SPAN_A'], r['SPAN_B']) else "dentro de") + " la nube",
    }
    rows = []
    for k_, v in S.items():
        if pd.notna(v):
            rows.append({"Indicador": k_, "Señal": float(v), "Peso": WEIGHTS[k_], "Lectura": txt.get(k_, "")})
    sc = score_series(df).iloc[-1]
    return {"score": float(sc) if pd.notna(sc) else 0.0, "señales": rows}


# --------------------------------------------------------------------------
# Perfil de volumen del rango visible (VRVP): POC, VAH, VAL
# --------------------------------------------------------------------------
def volume_profile(df: pd.DataFrame, bins: int = 48, value_area: float = 0.70) -> dict:
    lo, hi = float(df["Low"].min()), float(df["High"].max())
    if hi <= lo:
        return {}
    edges = np.linspace(lo, hi, bins + 1)
    up = np.zeros(bins)
    dn = np.zeros(bins)
    for h, l, o, c, v in df[["High", "Low", "Open", "Close", "Volume"]].itertuples(index=False):
        if not np.isfinite(v) or v <= 0:
            continue
        rng = max(h - l, 1e-9)
        ov = np.clip(np.minimum(edges[1:], h) - np.maximum(edges[:-1], l), 0, None) / rng
        if ov.sum() == 0:
            ov[min(bins - 1, int((c - lo) / (hi - lo) * bins))] = 1
        (up if c >= o else dn)[:] += v * ov / ov.sum()
    tot = up + dn
    poc_i = int(tot.argmax())
    # área de valor: expandir desde el POC hasta cubrir el 70% del volumen
    lo_i = hi_i = poc_i
    acc, target = tot[poc_i], tot.sum() * value_area
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        a = tot[lo_i - 1] if lo_i > 0 else -1
        b = tot[hi_i + 1] if hi_i < bins - 1 else -1
        if b >= a:
            hi_i += 1
            acc += tot[hi_i]
        else:
            lo_i -= 1
            acc += tot[lo_i]
    mid = (edges[:-1] + edges[1:]) / 2
    return {"precios": mid, "up": up, "down": dn, "alto_bin": edges[1] - edges[0],
            "poc": float(mid[poc_i]), "vah": float(edges[hi_i + 1]), "val": float(edges[lo_i])}
