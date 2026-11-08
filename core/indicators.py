"""
Panel de indicadores del usuario (menú USER › Indicadores).

* Catálogo de 34 indicadores (core/indicadores_catalogo.json): campos con los nombres de TradingView
  ("Entradas de datos"), estilos de cada línea ("Estilo"), ficha informativa y grupo.
* Configuración del usuario por indicador: activo, configurado (visible fuera de "Otros indicadores"),
  entradas, estilos y temporalidades donde se muestra ("Visibilidad"). Se guarda dentro de
  technical_settings["indicadores"] y se sincroniza con los ajustes del motor (medias, RSI, MACD, ADX,
  Bollinger y Fibonacci) para que el puntaje y el plan usen los mismos parámetros.
* Cálculo de lo que se dibuja en el gráfico: líneas, bandas, nubes, marcas y paneles inferiores.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

_RAW = json.loads((Path(__file__).with_name("indicadores_catalogo.json")).read_text(encoding="utf-8"))
CATALOGO: list[dict] = _RAW["catalogo"]
GRUPOS: list[list[str]] = _RAW["grupos"]
BYID = {c["id"]: c for c in CATALOGO}
TFS = ["10m", "30m", "1h", "4h", "1D", "1W", "1M"]
# Indicadores que aún no tienen dibujo propio en el gráfico (se configuran y guardan igual)
SIN_GRAFICO = {c["id"] for c in CATALOGO if c.get("draw") == "none"}
ACTIVOS_POR_PERFIL = {
    "day": ["ma", "vwap", "vrvp", "vol", "rsi", "macd"],
    "swing": ["ma", "bb", "vrvp", "vol", "rsi", "macd"],
    "position": ["ma", "vrvp", "vol", "rsi", "macd", "adx"],
    "fundamental": ["ma", "vol", "rsi", "macd"],
    "crypto": ["ma", "bb", "vrvp", "vol", "rsi", "macd"],
}
MAX_SIN_ENFOQUE = 10  # con más indicadores activos, el menú USER entra en modo enfoque hasta guardar
PALETA = ["#F23645", "#FF9800", "#FFEB3B", "#4CAF50", "#089981", "#00BCD4", "#2962FF", "#2196F3", "#7E57C2",
          "#E91E63", "#787B86", "#B2B5BE", "#FBC02D", "#FFFFFF"]
FICHA = [("que", "Para qué sirve"), ("perfil", "Perfil de trader"), ("ayuda", "En qué te ayuda"),
         ("combina", "Combínalo con"), ("tf", "Temporalidad más confiable"), ("uso", "Cómo usarlo"),
         ("esperar", "Qué esperar")]


# ---------------------------------------------------------------- configuración
def _item_default(c: dict, activo: bool) -> dict:
    return {"on": activo, "conf": activo,
            "in": {f["k"]: f["d"] for f in c["inputs"] + c.get("extra", [])},
            "st": {p["k"]: {"c": p["c"], "o": p["o"], "w": p["w"], "s": p["s"], "v": True} for p in c["plots"]},
            "vis": {t: True for t in TFS}}


def default_config(perfil: str | None = None, engine: dict | None = None) -> dict:
    act = ACTIVOS_POR_PERFIL.get(perfil or "", ACTIVOS_POR_PERFIL["swing"])
    cfg = {c["id"]: _item_default(c, c["id"] in act) for c in CATALOGO}
    if engine:
        _from_engine(cfg, engine)
    if perfil == "day":
        cfg["vwap"]["in"]["anchor"] = "Sesión"
    return cfg


def merge_config(saved: dict | None, perfil: str | None = None, engine: dict | None = None) -> dict:
    """Configuración guardada completada con los valores por defecto (para indicadores o campos nuevos)."""
    cfg = default_config(perfil, engine)
    if not saved:
        return cfg
    for iid, it in saved.items():
        if iid not in cfg or not isinstance(it, dict):
            continue
        base = cfg[iid]
        base["on"], base["conf"] = bool(it.get("on", base["on"])), bool(it.get("conf", base["conf"]))
        base["in"].update({k: v for k, v in (it.get("in") or {}).items() if k in base["in"]})
        for pk, ps in (it.get("st") or {}).items():
            if pk in base["st"] and isinstance(ps, dict):
                base["st"][pk].update(ps)
        base["vis"].update({k: bool(v) for k, v in (it.get("vis") or {}).items() if k in base["vis"]})
    return cfg


def _from_engine(cfg: dict, s: dict) -> None:
    """Copia al panel los parámetros del perfil (medias, RSI, MACD, ADX, Bollinger, Fibonacci)."""
    for i, m in enumerate((s.get("mas") or [])[:4], 1):
        cfg["ma"]["in"][f"l{i}"], cfg["ma"]["in"][f"t{i}"] = int(m["periodo"]), m["tipo"]
        cfg["ma"]["st"][f"m{i}"]["c"] = m.get("color", cfg["ma"]["st"][f"m{i}"]["c"])
    r = s.get("rsi") or {}
    cfg["rsi"]["in"].update({k: r[src] for k, src in (("len", "periodo"), ("ob", "sobrecompra"), ("os", "sobreventa")) if src in r})
    m = s.get("macd") or {}
    cfg["macd"]["in"].update({k: m[src] for k, src in (("fast", "rapida"), ("slow", "lenta"), ("sig", "senal")) if src in m})
    a = s.get("adx") or {}
    cfg["adx"]["in"].update({k: a[src] for k, src in (("smooth", "periodo"), ("di", "periodo"), ("key", "umbral")) if src in a})
    b = s.get("bollinger") or {}
    cfg["bb"]["in"].update({k: b[src] for k, src in (("len", "periodo"), ("mult", "desv")) if src in b})
    if (s.get("fibonacci") or {}).get("velas"):
        cfg["fib"]["in"]["bars"] = int(s["fibonacci"]["velas"])


def to_engine(cfg: dict, s: dict) -> dict:
    """Lleva al motor (puntaje, plan, IA) los parámetros configurados en el panel."""
    s = copy.deepcopy(s)
    ma = cfg["ma"]
    if s.get("mas"):
        for i in range(4):
            m = s["mas"][i]
            m["periodo"] = int(_num(ma["in"].get(f"l{i + 1}"), m["periodo"]))
            t = ma["in"].get(f"t{i + 1}")
            m["tipo"] = t if t in ("SMA", "EMA", "WMA") else m["tipo"]  # el motor admite SMA/EMA/WMA
            m["color"] = ma["st"][f"m{i + 1}"]["c"]
    r = cfg["rsi"]["in"]
    s["rsi"] = {"periodo": int(_num(r["len"], 14)), "sobrecompra": int(_num(r["ob"], 70)), "sobreventa": int(_num(r["os"], 30))}
    m = cfg["macd"]["in"]
    s["macd"] = {"rapida": int(_num(m["fast"], 12)), "lenta": int(_num(m["slow"], 26)), "senal": int(_num(m["sig"], 9))}
    a = cfg["adx"]["in"]
    s["adx"] = {"periodo": int(_num(a["di"], 14)), "umbral": int(_num(a["key"], 25))}
    b = cfg["bb"]["in"]
    s["bollinger"] = {"periodo": int(_num(b["len"], 20)), "desv": float(_num(b["mult"], 2))}
    s["fibonacci"] = {"velas": int(_num(cfg["fib"]["in"]["bars"], 126))}
    s["indicadores"] = cfg
    return s


def validar(cfg: dict) -> list[str]:
    err = []
    m = cfg["macd"]["in"]
    if _num(m["fast"], 12) >= _num(m["slow"], 26):
        err.append("MACD: la longitud rápida debe ser menor que la lenta.")
    for iid in ("rsi", "stoch", "mfi"):
        i = cfg[iid]["in"]
        if "os" in i and _num(i["os"], 30) >= _num(i["ob"], 70):
            err.append(f"{BYID[iid]['name']}: la banda inferior debe ser menor que la superior.")
    return err


def activos(cfg: dict, tf: str | None = None) -> list[str]:
    return [c["id"] for c in CATALOGO if cfg[c["id"]]["on"] and (tf is None or cfg[c["id"]]["vis"].get(tf, True))]


def _num(v, d):
    try:
        x = float(v)
        return x if math.isfinite(x) else d
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- medias y utilidades
def src_of(df: pd.DataFrame, k: str) -> pd.Series:
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    return {"open": o, "high": h, "low": l, "hl2": (h + l) / 2, "hlc3": (h + l + c) / 3,
            "ohlc4": (o + h + l + c) / 4}.get(k, c)


def _wma(s, n):
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda a: np.dot(a, w) / w.sum(), raw=True)


def _lsma(s, n):
    x = np.arange(n, dtype=float)
    xm = x.mean()
    den = ((x - xm) ** 2).sum()

    def f(a):
        b = ((x - xm) * (a - a.mean())).sum() / den
        return a.mean() + b * (n - 1 - xm)
    return s.rolling(n).apply(f, raw=True)


def _alma(s, n, off=0.85, sig=6):
    m, sg = off * (n - 1), n / sig
    w = np.exp(-((np.arange(n) - m) ** 2) / (2 * sg * sg))
    w /= w.sum()
    return s.rolling(n).apply(lambda a: np.dot(a, w), raw=True)


def _kama(s, n, fast=2, slow=30):
    a = s.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    k = np.nan
    for i in range(n, len(a)):
        ch = abs(a[i] - a[i - n])
        vol = np.abs(np.diff(a[i - n:i + 1])).sum()
        sc = ((ch / vol if vol else 0) * (fsc - ssc) + ssc) ** 2
        k = a[i - 1] if np.isnan(k) else k
        k = k + sc * (a[i] - k)
        out[i] = k
    return pd.Series(out, index=s.index)


def ma(tipo: str, s: pd.Series, n, vol: pd.Series | None = None) -> pd.Series:
    n = max(1, int(_num(n, 20)))
    if tipo == "EMA":
        return s.ewm(span=n, adjust=False, min_periods=n).mean()
    if tipo == "RMA":
        return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    if tipo == "WMA":
        return _wma(s, n)
    if tipo == "HMA":
        return _wma(2 * _wma(s, max(1, n // 2)) - _wma(s, n), max(1, int(round(math.sqrt(n)))))
    if tipo == "DEMA":
        e = s.ewm(span=n, adjust=False, min_periods=n).mean()
        return 2 * e - e.ewm(span=n, adjust=False, min_periods=n).mean()
    if tipo == "TEMA":
        e1 = s.ewm(span=n, adjust=False, min_periods=n).mean()
        e2 = e1.ewm(span=n, adjust=False, min_periods=n).mean()
        return 3 * e1 - 3 * e2 + e2.ewm(span=n, adjust=False, min_periods=n).mean()
    if tipo == "VWMA" and vol is not None:
        return (s * vol).rolling(n).sum() / vol.rolling(n).sum()
    if tipo == "ALMA":
        return _alma(s, n)
    if tipo == "KAMA":
        return _kama(s, n)
    if tipo == "LSMA":
        return _lsma(s, n)
    return s.rolling(n).mean()


def _tr(df):
    pc = df["Close"].shift()
    return pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)


def _rsi(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _hh(s, n):
    return s.rolling(n).max()


def _ll(s, n):
    return s.rolling(n).min()


# ---------------------------------------------------------------- cálculo para el gráfico
def overlay(df: pd.DataFrame, iid: str, p: dict, tf: str = "1D") -> list[dict]:
    """Elementos sobre el precio. Cada elemento: {"kind": line|step|band|cloud|marks, "plot": clave de estilo, …}"""
    c, h, l = df["Close"], df["High"], df["Low"]
    if iid == "ma":
        src = src_of(df, p.get("src", "close"))
        return [{"kind": "line", "plot": f"m{i}", "y": ma(p.get(f"t{i}", "SMA"), src, p.get(f"l{i}"), df["Volume"]),
                 "label": f"{p.get(f't{i}')} {int(_num(p.get(f'l{i}'), 20))}"} for i in range(1, 5)]
    if iid == "bb":
        s = src_of(df, p.get("src", "close"))
        n, k, off = int(_num(p["len"], 20)), _num(p["mult"], 2), int(_num(p.get("off", 0), 0))
        b = ma(p.get("mat", "SMA"), s, n)
        sd = s.rolling(n).std(ddof=0)
        up, dn = (b + k * sd).shift(off), (b - k * sd).shift(off)
        return [{"kind": "band", "plot": "fill", "up": up, "dn": dn},
                {"kind": "line", "plot": "basis", "y": b.shift(off), "label": f"BB {n} {k:g}"},
                {"kind": "line", "plot": "upper", "y": up}, {"kind": "line", "plot": "lower", "y": dn}]
    if iid == "kc":
        s = src_of(df, p.get("src", "close"))
        n, k = int(_num(p["len"], 20)), _num(p["mult"], 2)
        b = s.ewm(span=n, adjust=False).mean() if p.get("ema", True) else s.rolling(n).mean()
        r = (h - l).ewm(span=n, adjust=False).mean() if p.get("bs") == "Rango" else _tr(df).ewm(
            alpha=1 / int(_num(p.get("atrl", 10), 10)), adjust=False).mean()
        return [{"kind": "line", "plot": "basis", "y": b, "label": f"KC {n} {k:g}"},
                {"kind": "line", "plot": "upper", "y": b + k * r}, {"kind": "line", "plot": "lower", "y": b - k * r}]
    if iid == "dc":
        n = int(_num(p["len"], 20))
        U, L = _hh(h, n), _ll(l, n)
        return [{"kind": "line", "plot": "upper", "y": U, "label": f"DC {n}"}, {"kind": "line", "plot": "lower", "y": L},
                {"kind": "line", "plot": "basis", "y": (U + L) / 2}]
    if iid == "ichi":
        a, b, sb, dsp = (int(_num(p[k], d)) for k, d in (("conv", 9), ("base", 26), ("spanb", 52), ("disp", 26)))
        tk, kj = (_hh(h, a) + _ll(l, a)) / 2, (_hh(h, b) + _ll(l, b)) / 2
        sa, sbb = ((tk + kj) / 2).shift(dsp), ((_hh(h, sb) + _ll(l, sb)) / 2).shift(dsp)
        return [{"kind": "cloud", "plot": "cloudUp", "a": sa, "b": sbb, "up": True},
                {"kind": "cloud", "plot": "cloudDn", "a": sa, "b": sbb, "up": False},
                {"kind": "line", "plot": "tk", "y": tk, "label": f"Ichimoku {a} {b} {sb} {dsp}"},
                {"kind": "line", "plot": "kj", "y": kj}]
    if iid == "psar":
        return [{"kind": "marks", "plot": "sar", "y": _psar(df, _num(p["start"], .02), _num(p["inc"], .02), _num(p["max"], .2)),
                 "label": f"SAR {p['start']} {p['inc']} {p['max']}"}]
    if iid == "st":
        up, dn = _supertrend(df, int(_num(p["atr"], 10)), _num(p["fac"], 3))
        return [{"kind": "line", "plot": "up", "y": up, "label": f"Supertrend {p['atr']} {p['fac']}"},
                {"kind": "line", "plot": "dn", "y": dn}]
    if iid == "vwap":
        m, sd = _vwap(df, src_of(df, p.get("src", "hlc3")), p.get("anchor", "Mes"), tf)
        out = [{"kind": "step", "plot": "vwap", "y": m, "label": f"VWAP {p.get('anchor')}"}]
        if p.get("bands"):
            k = _num(p.get("bm"), 1)
            out += [{"kind": "step", "plot": "band", "y": m + k * sd}, {"kind": "step", "plot": "band", "y": m - k * sd}]
        return out
    if iid == "nw":
        up, dn = _nadaraya(src_of(df, p.get("src", "close")), _num(p["bw"], 8), _num(p["mult"], 3), int(_num(p["win"], 500)))
        return [{"kind": "line", "plot": "upper", "y": up, "label": f"Nadaraya-Watson {p['bw']} {p['mult']}"},
                {"kind": "line", "plot": "lower", "y": dn}]
    if iid == "piv":
        return _pivots(df, p, tf)
    return []


def fib_levels(df: pd.DataFrame, p: dict) -> dict:
    n = min(int(_num(p["bars"], 126)), len(df))
    w = df.tail(n)
    H, L = float(w["High"].max()), float(w["Low"].min())
    return {"x0": w.index[0], "levels": [(k, H - (H - L) * k) for k in (0, .236, .382, .5, .618, .786, 1)]}


def pane(df: pd.DataFrame, iid: str, p: dict) -> dict | None:
    """Panel inferior: {"title", "lines": [(plot, serie)], "hist": (plot, serie) | None, "zone": (lo, hi) | None,
    "refs": [niveles], "range": (min, max) | None}"""
    c = df["Close"]
    if iid == "rsi":
        r = _rsi(src_of(df, p.get("src", "close")), int(_num(p["len"], 14)))
        lines = [("rsi", r)]
        if p.get("mat") not in (None, "Ninguna"):
            lines.append(("ma", ma(p["mat"], r, p.get("mal", 14))))
        lo, hi = _num(p["os"], 30), _num(p["ob"], 70)
        return {"title": f"RSI {int(_num(p['len'], 14))}", "lines": lines, "zone": (lo, hi), "refs": [hi, 50, lo], "range": (0, 100)}
    if iid == "macd":
        s = src_of(df, p.get("src", "close"))
        f, sl = ma(p.get("mao", "EMA"), s, p["fast"]), ma(p.get("mao", "EMA"), s, p["slow"])
        m = f - sl
        sg = ma(p.get("mas", "EMA"), m, p["sig"])
        return {"title": f"MACD {p['fast']} {p['slow']} {p['sig']}", "lines": [("macd", m), ("signal", sg)],
                "hist": ("hist", m - sg), "refs": [0]}
    if iid == "stoch":
        kn = int(_num(p["k"], 14))
        raw = 100 * (c - _ll(df["Low"], kn)) / (_hh(df["High"], kn) - _ll(df["Low"], kn)).replace(0, np.nan)
        k = raw.rolling(int(_num(p["ks"], 1))).mean()
        d = k.rolling(int(_num(p["d"], 3))).mean()
        lo, hi = _num(p["os"], 20), _num(p["ob"], 80)
        return {"title": f"Estocástico {p['k']} {p['ks']} {p['d']}", "lines": [("k", k), ("d", d)], "zone": (lo, hi),
                "refs": [hi, lo], "range": (0, 100)}
    if iid == "srsi":
        r = _rsi(c, int(_num(p["rl"], 14)))
        n = int(_num(p["sl"], 14))
        st = 100 * (r - r.rolling(n).min()) / (r.rolling(n).max() - r.rolling(n).min()).replace(0, np.nan)
        k = st.rolling(int(_num(p["k"], 3))).mean()
        return {"title": f"RSI estocástico {p['k']} {p['d']} {p['rl']} {p['sl']}",
                "lines": [("k", k), ("d", k.rolling(int(_num(p["d"], 3))).mean())], "zone": (20, 80), "refs": [80, 20],
                "range": (0, 100)}
    if iid == "cci":
        s, n = src_of(df, p.get("src", "hlc3")), int(_num(p["len"], 20))
        m = s.rolling(n).mean()
        md = s.rolling(n).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True)
        return {"title": f"CCI {n}", "lines": [("cci", (s - m) / (0.015 * md))], "zone": (-100, 100), "refs": [100, 0, -100]}
    if iid == "willr":
        n = int(_num(p["len"], 14))
        H, L = _hh(df["High"], n), _ll(df["Low"], n)
        return {"title": f"%R {n}", "lines": [("wr", -100 * (H - c) / (H - L).replace(0, np.nan))], "zone": (-80, -20),
                "refs": [-20, -80], "range": (-100, 0)}
    if iid == "wt":
        s = src_of(df, p.get("src", "hlc3"))
        ch, av = int(_num(p["ch"], 9)), int(_num(p["avg"], 12))
        esa = s.ewm(span=ch, adjust=False).mean()
        dd = (s - esa).abs().ewm(span=ch, adjust=False).mean()
        w1 = ((s - esa) / (0.015 * dd)).ewm(span=av, adjust=False).mean()
        return {"title": f"WaveTrend {ch} {av}", "lines": [("wt1", w1), ("wt2", w1.rolling(int(_num(p["mal"], 3))).mean())],
                "refs": [_num(p["ob"], 53), 0, _num(p["os"], -53)]}
    if iid == "sqz":
        n = int(_num(p["kcl"], 20))
        mid = ((_hh(df["High"], n) + _ll(df["Low"], n)) / 2 + c.rolling(n).mean()) / 2
        return {"title": "Squeeze Momentum", "lines": [], "hist": ("mom", _lsma(c - mid, n)), "refs": [0]}
    if iid == "adx":
        adx, pdi, ndi = _adx(df, int(_num(p["smooth"], 14)), int(_num(p["di"], 14)))
        return {"title": f"ADX {p['smooth']} {p['di']}", "lines": [("adx", adx), ("pdi", pdi), ("ndi", ndi)],
                "refs": [_num(p["key"], 25)]}
    if iid == "atr":
        tr = _tr(df)
        return {"title": f"ATR {p['len']}", "lines": [("atr", ma(p.get("sm", "RMA"), tr, p["len"]))]}
    if iid == "obv":
        obv = (np.sign(c.diff()).fillna(0) * df["Volume"]).cumsum()
        lines = [("obv", obv)]
        if p.get("mat") not in (None, "Ninguno"):
            lines.append(("ma", ma(p["mat"], obv, p.get("mal", 20))))
        return {"title": "OBV", "lines": lines}
    if iid == "mfi":
        tp = src_of(df, "hlc3")
        n = int(_num(p["len"], 14))
        mf = tp * df["Volume"]
        pos = mf.where(tp > tp.shift(), 0).rolling(n).sum()
        neg = mf.where(tp < tp.shift(), 0).rolling(n).sum()
        lo, hi = _num(p["os"], 20), _num(p["ob"], 80)
        return {"title": f"MFI {n}", "lines": [("mfi", 100 - 100 / (1 + pos / neg.replace(0, np.nan)))], "zone": (lo, hi),
                "refs": [hi, lo], "range": (0, 100)}
    if iid == "cmf":
        n = int(_num(p["len"], 20))
        rng = (df["High"] - df["Low"]).replace(0, np.nan)
        mfv = ((c - df["Low"]) - (df["High"] - c)) / rng * df["Volume"]
        return {"title": f"CMF {n}", "lines": [("cmf", mfv.rolling(n).sum() / df["Volume"].rolling(n).sum())], "refs": [0]}
    return None


# ---------------------------------------------------------------- cálculos auxiliares
def _psar(df, start, inc, mx):
    H, L = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    out = np.full(len(H), np.nan)
    if len(H) < 3:
        return pd.Series(out, index=df.index)
    up, af, ep, sar = True, start, H[0], L[0]
    for i in range(1, len(H)):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, L[i - 1], L[i - 2] if i > 1 else L[i - 1])
            if L[i] < sar:
                up, sar, ep, af = False, ep, L[i], start
            elif H[i] > ep:
                ep, af = H[i], min(af + inc, mx)
        else:
            sar = max(sar, H[i - 1], H[i - 2] if i > 1 else H[i - 1])
            if H[i] > sar:
                up, sar, ep, af = True, ep, H[i], start
            elif L[i] < ep:
                ep, af = L[i], min(af + inc, mx)
        out[i] = sar
    return pd.Series(out, index=df.index)


def _supertrend(df, n, f):
    atr = _tr(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    hl2 = ((df["High"] + df["Low"]) / 2).to_numpy()
    c = df["Close"].to_numpy()
    up, dn = np.full(len(c), np.nan), np.full(len(c), np.nan)
    fu = fd = np.nan
    d = 1
    for i in range(len(c)):
        if np.isnan(atr[i]):
            continue
        bu, bd = hl2[i] - f * atr[i], hl2[i] + f * atr[i]
        fu = bu if np.isnan(fu) or c[i - 1] < fu else max(bu, fu)
        fd = bd if np.isnan(fd) or c[i - 1] > fd else min(bd, fd)
        if d == 1 and c[i] < fu:
            d = -1
        elif d == -1 and c[i] > fd:
            d = 1
        if d == 1:
            up[i] = fu
        else:
            dn[i] = fd
    return pd.Series(up, index=df.index), pd.Series(dn, index=df.index)


def _vwap(df, src, anchor, tf):
    idx = df.index
    if anchor == "Sesión":
        key = idx.normalize()
    else:
        key = {"Semana": idx.to_period("W"), "Mes": idx.to_period("M"), "Trimestre": idx.to_period("Q"),
               "Año": idx.to_period("Y")}.get(anchor, idx.to_period("M"))
    g = pd.Series(np.asarray(key), index=idx)
    pv = (src * df["Volume"]).groupby(g.values).cumsum()
    vv = df["Volume"].groupby(g.values).cumsum()
    p2 = (src * src * df["Volume"]).groupby(g.values).cumsum()
    m = pv / vv
    sd = np.sqrt((p2 / vv - m * m).clip(lower=0))
    return m, sd


def _nadaraya(s, bw, mult, win):
    L = int(min(win, 120))
    w = np.exp(-(np.arange(L) ** 2) / (2 * bw * bw))
    a = s.to_numpy(float)
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        k = min(L, i + 1)
        seg = a[i - k + 1:i + 1][::-1]
        out[i] = np.dot(seg, w[:k]) / w[:k].sum()
    est = pd.Series(out, index=s.index)
    mae = (s - est).abs().rolling(min(win, 100)).mean()
    return est + mult * mae, est - mult * mae


def _adx(df, sm, di):
    up, dn = df["High"].diff(), -df["Low"].diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = _tr(df).ewm(alpha=1 / di, adjust=False, min_periods=di).mean()
    pdi = 100 * pdm.ewm(alpha=1 / di, adjust=False, min_periods=di).mean() / tr
    ndi = 100 * ndm.ewm(alpha=1 / di, adjust=False, min_periods=di).mean() / tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / sm, adjust=False, min_periods=sm).mean(), pdi, ndi


def _pivots(df, p, tf):
    per = {"Diario": "D", "Semanal": "W", "Mensual": "M", "Trimestral": "Q", "Anual": "Y"}.get(p.get("tf"))
    if not per:
        per = {"10m": "D", "30m": "D", "1h": "W", "4h": "W", "1D": "M", "1W": "Y", "1M": "Y"}.get(tf, "M")
    key = df.index.to_period(per)
    g = df.groupby(key).agg(H=("High", "max"), L=("Low", "min"), C=("Close", "last"))
    prev = g.shift(1)
    H, L, C = (prev[k].reindex(key).to_numpy() for k in ("H", "L", "C"))
    rg = H - L
    t = p.get("type", "Tradicional")
    P = (H + L + 2 * C) / 4 if t == "Woodie" else (H + L + C) / 3
    if t == "Fibonacci":
        r1, r2, s1, s2 = P + .382 * rg, P + .618 * rg, P - .382 * rg, P - .618 * rg
    elif t == "Camarilla":
        r1, r2, s1, s2 = C + rg * 1.1 / 12, C + rg * 1.1 / 6, C - rg * 1.1 / 12, C - rg * 1.1 / 6
    else:
        r1, s1, r2, s2 = 2 * P - L, 2 * P - H, P + rg, P - rg
    back = int(_num(p.get("back"), 1))
    keep = np.isin(np.asarray(key), list(g.index[-back:]))
    S = lambda a: pd.Series(np.where(keep, a, np.nan), index=df.index)  # noqa: E731
    return [{"kind": "step", "plot": "p", "y": S(P), "label": f"Pivotes {t}"},
            {"kind": "step", "plot": "r", "y": S(r1)}, {"kind": "step", "plot": "r", "y": S(r2)},
            {"kind": "step", "plot": "s", "y": S(s1)}, {"kind": "step", "plot": "s", "y": S(s2)}]
