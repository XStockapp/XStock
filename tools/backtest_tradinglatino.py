"""Backtest del método TradingLatino (EMA 55 + Squeeze Momentum de LazyBear + ADX con nivel clave 23).

Reglas codificadas tal como las describe la guía (checklist alcista; la bajista es el espejo):
  DIRECCIÓN  precio por encima de la EMA 55.
  IMPULSO    el Squeeze Momentum sale de un valle rojo: el histograma cruza a positivo (estricta) o sigue negativo
             pero pierde fuerza, «rojo transparentito» (relajada); y no hay squeeze (cruces grises).
  FUERZA     el ADX(14) está sobre 23 y con pendiente positiva (estricta: lo cruzó en las últimas 3 velas).
Entrada en la APERTURA de la vela siguiente (sin mirar el futuro). Salidas: horizonte fijo de 5/10/20 velas y la
salida táctica del método (el momentum pierde fuerza: histograma «verde transparentito», o cierre bajo la EMA 55;
máximo 40 velas). Costos: 0.10 % ida y vuelta.

Para saber qué aporta cada pieza se mide también cada filtro por separado (ablación) y la referencia sin filtro.
Las estadísticas usan el promedio por fecha (las acciones se mueven juntas: contar cada señal como independiente
inflaría la significancia).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

COSTO = 0.001
HS = (5, 10, 20)
CRIPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "LTC-USD", "LINK-USD", "AVAX-USD", "BCH-USD",
          "DOT-USD", "UNI-USD", "AAVE-USD"]


def _tr(df):
    pc = df["Close"].shift()
    return pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)


def _lsma(s: pd.Series, n: int) -> pd.Series:
    """Regresión lineal móvil evaluada en la última vela (linreg de Pine con offset 0)."""
    x = np.arange(n, dtype=float)
    xm = x.mean()
    w = (x - xm) / ((x - xm) ** 2).sum()

    def f(y):
        return y.mean() + (w * y).sum() * (n - 1 - xm)
    return s.rolling(n).apply(f, raw=True)


def indicadores(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    d = pd.DataFrame(index=df.index)
    d["ema55"] = c.ewm(span=55, adjust=False).mean()
    n = 20
    basis, dev = c.rolling(n).mean(), 2.0 * c.rolling(n).std(ddof=0)
    kma, krg = c.rolling(n).mean(), _tr(df).rolling(n).mean() * 1.5
    d["sq_on"] = ((basis - dev) > (kma - krg)) & ((basis + dev) < (kma + krg))
    mid = ((df["High"].rolling(n).max() + df["Low"].rolling(n).min()) / 2 + kma) / 2
    d["val"] = _lsma(c - mid, n)
    up, dn = df["High"].diff(), -df["Low"].diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = _tr(df).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / tr
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    d["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    d["pdi"], d["ndi"] = pdi, ndi
    d["atr"] = tr
    d["vol_ma20"] = df["Volume"].rolling(20).mean()
    dlt = c.diff()
    g = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    p_ = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + g / p_.replace(0, np.nan))
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["macd"], d["macd_sig"] = m, m.ewm(span=9, adjust=False).mean()
    return d


def vrvp(df: pd.DataFrame, d: pd.DataFrame, idx: np.ndarray, lado: int, n: int = 100, bins: int = 24):
    """Aproximación del VRVP (perfil de volumen del rango visible) en las velas idx: volumen por nivel de precio de
    las últimas n velas. Para una compra (espejo para venta) es favorable que haya un nodo de alto volumen (≥ p70 de
    los niveles) entre el precio y 1 ATR por debajo (soporte), y aparte se mide si NO hay un nodo muy fuerte (≥ p90)
    hasta 1.5 ATR por encima (sin techo)."""
    tp = ((df["High"] + df["Low"] + df["Close"]) / 3).to_numpy()
    vol = df["Volume"].fillna(0).to_numpy()
    c, atr = df["Close"].to_numpy(), d["atr"].to_numpy()
    ok, libre, nodo = np.zeros(len(df), bool), np.zeros(len(df), bool), np.zeros(len(df), bool)
    for i in idx:
        if i < n or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        h, bordes = np.histogram(tp[i - n + 1:i + 1], bins=bins, weights=vol[i - n + 1:i + 1])
        if h.sum() <= 0:
            continue
        centros = (bordes[:-1] + bordes[1:]) / 2
        dist = lado * (centros - c[i])  # > 0: del lado al que se quiere ir
        hvn, fuerte = h >= np.percentile(h, 70), h >= np.percentile(h, 90)
        soporte = (hvn & (dist <= 0) & (dist >= -atr[i])).any()
        techo = (fuerte & (dist > 0) & (dist <= 1.5 * atr[i])).any()
        k = min(max(np.searchsorted(bordes, c[i]) - 1, 0), bins - 1)  # nivel donde está el precio
        ok[i], libre[i], nodo[i] = soporte, not techo, fuerte[k] or (k > 0 and fuerte[k - 1]) or (k < bins - 1 and fuerte[k + 1])
    return ok, libre, nodo


def senales_anexo(df: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """Lógica de giro del anexo (como la usa el indicador «Multiple strategies [LPWN]»):
    direccionalidad = pendiente del Squeeze Momentum (sube → alcista); el ADX con pendiente negativa tras un
    movimiento fuerte indica que ese movimiento pierde fuerza.
      GIRO ALCISTA: movimiento bajista previo con fuerza (ADX llegó a > 23 con −DI > +DI) · valle rojo que asciende
                    (momentum < 0 y subiendo) · ADX girando a la baja.
      + RSI: el RSI(14) estuvo en zona baja (< 35) en las últimas 5 velas.
      + MACD: la línea MACD cruzó sobre su señal en las últimas 3 velas (confirmación completa del usuario).
      CONTINUACIÓN (Jaime Merino): direccionalidad alcista y ADX con pendiente positiva cruzando 23.
    Espejo para el lado bajista."""
    v, pv, a = d["val"], d["val"].shift(), d["adx"]

    def primera(x):
        x = x.fillna(False).astype(bool)
        return x & ~x.shift(fill_value=False)

    def reciente(x, k):
        return x.fillna(False).astype(int).rolling(k, min_periods=1).max().astype(bool)
    S = pd.DataFrame(index=df.index)
    adx_baja, adx_sube = a < a.shift(), a > a.shift()
    for lado, s in (("L", 1), ("C", -1)):
        contra_fuerte = (a > 23) & ((d["ndi"] > d["pdi"]) if s == 1 else (d["pdi"] > d["ndi"]))
        previo = reciente(contra_fuerte, 10)
        valle_sube = (s * v < 0) & (s * v > s * pv)
        giro = primera(previo & valle_sube & adx_baja)
        rsi_ext = reciente((d["rsi"] < 35) if s == 1 else (d["rsi"] > 65), 5)
        macd_x = (s * (d["macd"] - d["macd_sig"]) > 0) & (s * (d["macd"].shift() - d["macd_sig"].shift()) <= 0)
        S[f"{lado}_giro"] = giro
        S[f"{lado}_giro_rsi"] = primera(previo & valle_sube & adx_baja & rsi_ext)
        S[f"{lado}_giro_rsi_macd"] = primera(reciente(previo & valle_sube & adx_baja, 5) & reciente(rsi_ext, 8)
                                             & macd_x)
        S[f"{lado}_continuacion"] = primera((s * v > s * pv) & adx_sube & reciente(a <= 23, 3) & (a > 23))
        # referencia: solo «valle que asciende», sin ADX ni confirmaciones
        S[f"{lado}_solo_valle_sube"] = primera(valle_sube)
        # filtros discrecionales del anexo: VRVP (soporte de volumen debajo, sin techo fuerte encima) y la regla de
        # la EMA 55: no operar si el precio está pegado a la EMA 55 en contra y sin volumen
        cerca_ema = (s * (d["ema55"] - df["Close"]) > 0) & (s * (d["ema55"] - df["Close"]) < 0.5 * d["atr"])
        ema_mala = cerca_ema & (df["Volume"] < d["vol_ma20"])
        base = [f"{lado}_giro", f"{lado}_giro_rsi_macd", f"{lado}_solo_valle_sube"]
        cand = np.flatnonzero(S[base].any(axis=1).to_numpy())
        sop, lib, _ = vrvp(df, d, cand, s)
        ok_v, sin_techo = pd.Series(sop, index=df.index), pd.Series(lib, index=df.index)
        for b in base:
            S[f"{b}_vrvp"] = S[b] & ok_v
            S[f"{b}_sintecho"] = S[b] & sin_techo
            S[f"{b}_ema55"] = S[b] & ~ema_mala
            S[f"{b}_filtros"] = S[b] & ok_v & ~ema_mala
    S["todas_las_velas"] = True
    return S


def senales(df: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    c, v, pv, a = df["Close"], d["val"], d["val"].shift(), d["adx"]
    S = pd.DataFrame(index=df.index)
    def primera(x):  # solo la vela en que la condición empieza a cumplirse (no repetir la misma señal)
        x = x.fillna(False).astype(bool)
        return x & ~x.shift(fill_value=False)

    def reciente(x, k):  # ocurrió en alguna de las últimas k velas
        return x.fillna(False).astype(int).rolling(k, min_periods=1).max().astype(bool)
    adx_ok = (a > 23) & (a > a.shift())
    adx_cruce = adx_ok & reciente(a <= 23, 5)  # cruzó el nivel 23 hace pocas velas y sigue subiendo
    sin_squeeze = ~d["sq_on"]
    for lado, s in (("L", 1), ("C", -1)):
        dir_ = (c > d["ema55"]) if s == 1 else (c < d["ema55"])
        cruce = (s * v > 0) & (s * pv <= 0)
        crece = (s * v > 0) & (s * v > s * pv) & reciente(cruce, 3)  # montañita recién nacida y creciendo
        pierde = (s * v < 0) & (s * v > s * pv)  # valle que pierde fuerza (rojo transparentito)
        S[f"{lado}_estricta"] = primera(dir_ & crece & sin_squeeze & adx_cruce)
        S[f"{lado}_relajada"] = primera(dir_ & (crece | pierde) & sin_squeeze & adx_ok)
        # ablación: cada pieza sola y combinaciones de dos
        S[f"{lado}_solo_ema"] = dir_
        S[f"{lado}_solo_squeeze"] = primera(crece & sin_squeeze)
        S[f"{lado}_solo_adx"] = primera(adx_cruce)
        S[f"{lado}_ema_squeeze"] = primera(dir_ & crece & sin_squeeze)
        S[f"{lado}_ema_adx"] = primera(dir_ & adx_cruce)
    S["todas_las_velas"] = True
    return S


def resultados(df: pd.DataFrame, d: pd.DataFrame, S: pd.DataFrame, ticker: str, anexo: bool = False) -> list[dict]:
    o, c = df["Open"].to_numpy(), df["Close"].to_numpy()
    val, ema = d["val"].to_numpy(), d["ema55"].to_numpy()
    n = len(df)
    filas = []
    for col in S.columns:
        lado = -1 if col.startswith("C_") else 1
        idx = np.flatnonzero(S[col].to_numpy())
        if col in ("todas_las_velas", "L_solo_ema", "C_solo_ema"):
            idx = idx[idx % 5 == 0]  # referencias muy frecuentes: 1 de cada 5 velas basta y ahorra memoria
        for i in idx:
            e = i + 1
            if e >= n or not np.isfinite(o[e]) or i < 60:
                continue
            f = {"ticker": ticker, "fecha": df.index[i], "regla": col}
            for H in HS:
                j = e + H - 1
                f[f"r{H}"] = lado * (c[j] / o[e] - 1) - COSTO if j < n else np.nan
            # salida táctica del método: momentum pierde fuerza o cierre al otro lado de la EMA 55 (máx. 40 velas)
            j = e
            while j < min(n - 1, e + 40):
                if anexo:  # el monitor cambia de direccionalidad o toca el punto 0 desde arriba
                    pierde = lado * val[j] < lado * val[j - 1] and j > e
                else:
                    pierde = lado * val[j] > 0 and lado * val[j] < lado * val[j - 1]
                rompe = (not anexo) and lado * (c[j] - ema[j]) < 0
                if pierde or rompe:
                    break
                j += 1
            f["r_tactica"] = lado * (c[j] / o[e] - 1) - COSTO
            f["velas_tactica"] = j - e + 1
            filas.append(f)
    return filas


def resumir(R: pd.DataFrame) -> pd.DataFrame:
    out = []
    ref = {H: R.loc[R["regla"] == "todas_las_velas", f"r{H}"].mean() for H in HS}
    for regla, g in R.groupby("regla"):
        fila = {"regla": regla, "senales": len(g), "acciones": g["ticker"].nunique()}
        for k in [f"r{H}" for H in HS] + ["r_tactica"]:
            x = g[k].dropna()
            por_fecha = x.groupby(g.loc[x.index, "fecha"]).mean()
            t = por_fecha.mean() / (por_fecha.std(ddof=1) / np.sqrt(len(por_fecha))) if len(por_fecha) > 2 else np.nan
            fila[f"{k}_media%"] = 100 * x.mean()
            fila[f"{k}_acierto%"] = 100 * (x > 0).mean()
            fila[f"{k}_t"] = t
        fila["velas_tactica"] = g["velas_tactica"].mean()
        x = g["r_tactica"].dropna()
        fila["gana_media%"] = 100 * x[x > 0].mean()
        fila["pierde_media%"] = 100 * x[x <= 0].mean()
        lado = -1 if regla.startswith("C_") else 1
        fila["exceso_r10%"] = 100 * (g["r10"].mean() - lado * ref[10]) if regla != "todas_las_velas" else 0.0
        out.append(fila)
    return pd.DataFrame(out).set_index("regla")


def a_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Velas de 4 horas a partir de las de 1 hora (sesión de Nueva York: 9:30-13:30 y 13:30-cierre)."""
    x = df.copy()
    if x.index.tz is None:
        x.index = x.index.tz_localize("UTC")
    x.index = x.index.tz_convert("America/New_York")
    g = x.resample("4h", offset="1h30min", label="right", closed="left")
    out = g.agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    out.index = out.index.tz_convert(df.index.tz or "UTC")
    if df.index.tz is None:
        out.index = out.index.tz_localize(None)
    return out


def contexto_4h(df1: pd.DataFrame) -> pd.DataFrame:
    """Lectura de 4h llevada a cada vela de 1h usando solo velas de 4h YA CERRADAS (label = cierre del bloque):
    direccionalidad (pendiente del Squeeze), giro reciente del anexo, y el VRVP de ~6 meses (250 velas de 4h):
    soporte de volumen debajo y precio sobre un nodo enorme."""
    d4f = a_4h(df1)
    d4 = indicadores(d4f)
    S4 = senales_anexo(d4f, d4)
    todos = np.arange(len(d4f))
    C = pd.DataFrame(index=d4f.index)
    for lado, s in (("L", 1), ("C", -1)):
        sop, _, nodo = vrvp(d4f, d4, todos, s, n=250)
        C[f"{lado}_dir4h"] = (s * d4["val"] > s * d4["val"].shift()).to_numpy()
        C[f"{lado}_giro4h"] = S4[[f"{lado}_giro", f"{lado}_solo_valle_sube"]].any(axis=1).astype(int) \
            .rolling(3, min_periods=1).max().astype(bool).to_numpy()
        C[f"{lado}_vol4h"] = sop | nodo
    # una vela de 4h se conoce al cerrar: se lleva a las velas de 1h posteriores a su cierre
    return C.reindex(C.index.union(df1.index)).ffill().reindex(df1.index).fillna(False).astype(bool)


def senales_mtf(df: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    S = senales_anexo(df, d)
    C = contexto_4h(df)
    for lado in ("L", "C"):
        for b in (f"{lado}_giro", f"{lado}_giro_rsi_macd", f"{lado}_solo_valle_sube"):
            S[f"{b}_dir4h"] = S[b] & C[f"{lado}_dir4h"]
            S[f"{b}_giro4h"] = S[b] & C[f"{lado}_giro4h"]
            S[f"{b}_giro4h_vol4h"] = S[b] & C[f"{lado}_giro4h"] & C[f"{lado}_vol4h"]
    return S


def meta_xpulse(barras: dict, R: pd.DataFrame, log=print) -> pd.DataFrame | None:
    """Meta-etiquetado: ¿las señales de la estrategia rinden más cuando X-Pulse (fuera de muestra) espera un
    movimiento fuerte? X-Pulse se reentrena por años (walk-forward) con las mismas variables del modelo publicado,
    así cada señal se cruza con una predicción hecha SIN ver ese año."""
    import os
    from core.motor_a import artefactos as AR, dataset as DS, macro as MC, modelo as MO, sec as SE
    import requests
    url, h = AR._sb()
    r = requests.get(f"{url}/storage/v1/object/{AR.BUCKET}/{AR.PREFIJO}/reporte_movimiento_H10.json", headers=h,
                     timeout=60) if url else None
    crudo = r.content if r is not None and r.status_code == 200 else None
    if not crudo:
        log("Sin reporte de X-Pulse: se omite el meta-etiquetado.")
        return None
    rep = json.loads(crudo)
    spy = DS.descargar(["SPY"], desde_anios=11)["SPY"]
    sec_datos = SE.descargar(list(barras)) if os.environ.get(SE.UA_ENV) else None
    panel = DS.construir(barras, spy, 10, rep["k"], sec_datos, MC.variables(spy, MC.descargar_dgs2()), "movimiento")
    cols = [c for c in rep["variables"] if c in panel.columns]
    w = MO.walk_forward(panel, 10, cols=cols, ref=MO.REFERENCIAS["movimiento"][0], log=lambda *_: None)
    O = w["oos"]
    rango = O["p"].groupby(level="fecha").rank(pct=True).rename("xp")
    rango = rango.reset_index()
    rango["fecha"] = pd.to_datetime(rango["fecha"])
    M = R.assign(fecha=pd.to_datetime(R["fecha"])).merge(rango, on=["fecha", "ticker"], how="inner")
    M["tercio"] = pd.cut(M["xp"], [0, 1 / 3, 2 / 3, 1.0001], labels=["X-Pulse bajo", "medio", "X-Pulse alto"])
    reglas = ["todas_las_velas", "L_solo_valle_sube", "L_giro", "L_giro_rsi_macd", "L_giro_filtros",
              "L_giro_rsi_macd_filtros", "C_giro", "C_giro_rsi_macd"]
    filas = []
    for regla in reglas:
        g = M[M["regla"] == regla]
        for t, h in g.groupby("tercio", observed=True):
            filas.append({"regla": regla, "tercio": t, "senales": len(h), "r10_media%": 100 * h["r10"].mean(),
                          "r10_acierto%": 100 * (h["r10"] > 0).mean(), "mov_abs10%": 100 * h["r10"].abs().mean(),
                          "tactica_media%": 100 * h["r_tactica"].mean(),
                          "tactica_acierto%": 100 * (h["r_tactica"] > 0).mean()})
    T = pd.DataFrame(filas).set_index(["regla", "tercio"])
    print(f"\n===== META-ETIQUETADO CON X-PULSE · {M['fecha'].min():%Y} → {M['fecha'].max():%Y} (fuera de muestra) =====")
    print(T.round(2).to_string())
    return T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--marco", default="1D", help="1D, 1W o 1h")
    ap.add_argument("--reglas", default="checklist", help="checklist (láminas), anexo (giros) o mtf (contexto 4h + entrada 1h)")
    ap.add_argument("--meta", action="store_true", help="cruzar las señales con X-Pulse fuera de muestra")
    a = ap.parse_args()
    from core.motor_a import dataset as DS
    from core import alpaca
    tickers = DS.universo(maximo=a.max)
    def horas(lista, por=5):  # 1h se arma con velas de 30 min: en bloques chicos para no cortar la paginación
        out = {}
        for i in range(0, len(lista), por):
            try:
                out.update(alpaca.batch_bars(lista[i:i + por], "1h", 4))
            except Exception as e:
                print(f"  1h {lista[i:i + por]}: {e}")
        print(f"  velas de 1h: {len(out)}/{len(lista)} símbolos")
        return out
    barras = horas(tickers) if a.marco == "1h" else DS.descargar(tickers, desde_anios=11)
    try:
        cr = horas(CRIPTO, 1) if a.marco == "1h" else alpaca.batch_bars(CRIPTO, "1D", 6)
    except Exception as e:
        print(f"Cripto no disponible: {e}")
        cr = {}
    todas = []
    for grupo, B in (("acciones", barras), ("cripto", cr)):
        filas = []
        for t, df in B.items():
            df = df.dropna(subset=["Open", "Close"])
            if a.marco == "1W":
                df = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                               "Volume": "sum"}).dropna()
            if len(df) < 150:
                continue
            d = indicadores(df)
            anexo = a.reglas in ("anexo", "mtf")
            fn = senales_mtf if a.reglas == "mtf" else (senales_anexo if anexo else senales)
            filas += resultados(df, d, fn(df, d), t, anexo)
        if not filas:
            continue
        R = pd.DataFrame(filas)
        R["grupo"] = grupo
        todas.append(R)
        T = resumir(R)
        pd.set_option("display.width", 250)
        print(f"\n===== {grupo.upper()} · reglas {a.reglas} · marco {a.marco} · {R['ticker'].nunique()} símbolos · "
              f"{R['fecha'].min():%Y-%m} → {R['fecha'].max():%Y-%m} =====")
        cols = ["senales", "r5_media%", "r10_media%", "r10_acierto%", "r10_t", "r20_media%", "r20_t",
                "r_tactica_media%", "r_tactica_acierto%", "gana_media%", "pierde_media%", "r_tactica_t", "velas_tactica",
                "exceso_r10%"]
        print(T[cols].round(2).to_string())
        # robustez en el tiempo de la regla principal
        for regla in ("L_estricta", "L_relajada", "C_relajada", "L_giro_rsi_macd", "L_giro", "L_giro_rsi_macd_filtros",
                      "L_giro_rsi_macd_giro4h_vol4h"):
            g = R[R["regla"] == regla]
            if len(g):
                anual = g.groupby(g["fecha"].dt.year)["r10"].agg(["count", "mean"])
                anual["mean"] *= 100
                print(f"{regla} por año (n, retorno medio a 10 velas %):",
                      "; ".join(f"{y}: {int(r['count'])}, {r['mean']:+.2f}" for y, r in anual.iterrows()))
    if a.meta and todas and a.marco == "1D":
        meta_xpulse(barras, todas[0])
    if todas:
        R = pd.concat(todas)
        Path("datos/motor_a").mkdir(parents=True, exist_ok=True)
        R.to_parquet(f"datos/motor_a/tradinglatino_{a.reglas}_{a.marco}.parquet")
        json.dump({g: resumir(R[R["grupo"] == g]).round(4).reset_index().to_dict("records")
                   for g in R["grupo"].unique()},
                  open(f"datos/motor_a/reporte_tradinglatino_{a.reglas}_{a.marco}.json", "w"), default=float, indent=1)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
