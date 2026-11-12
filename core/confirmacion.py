"""Capa de confirmación por patrones (herramienta secundaria) y su ponderación con el motor cuantitativo.

El motor cuantitativo existente (score técnico con filtro ADX, probabilidad histórica de triple barrera, backtest,
fundamental, VRVP) sigue siendo la base. Esta capa NO lo reemplaza: detecta patrones de apoyo y ajusta la confianza.

Patrones de apoyo:
- Continuación: banderas, triángulos.            - Reversión: HCH, doble/triple techo o suelo, cuñas.
- Liquidez/estructura: Spring/Upthrust, BOS/CHoCH, FVG.  - Velas: envolventes, pin bars, estrellas (solo en niveles clave).

Ponderación (mezcla lineal de probabilidades):
    conf_global = (1 − w) · conf_cuant + w · conf_patrones
    conf_patrones = 50 + 50 · E,  E ∈ [−1, 1] = Σ sentido · calidad de cada patrón (acotado)
    calidad = estado (confirmado 1 · pendiente 0.6 · en formación 0.35) × volumen (1 · 0.6) × confluencia (1 · 0.85 · 0.7)
              × tipo (velas y FVG 0.5)
Vigencia: solo patrones del movimiento en curso (terminan en las últimas 20 velas), nunca caducados ni con el objetivo
ya alcanzado, y solo en temporalidades ≥ 1H (en 10m/30m el motor cuantitativo pesa 100%). Un patrón en formación o
pendiente de ruptura NO suma confianza todavía: se expresa como escenario condicionado («si rompe X con cierre y
volumen…») con el aporte que tendría al confirmarse. Solo los recién confirmados suman al pronóstico actual.
El peso w se calibra con el historial del propio activo: ventaja (acierto − 50%) de los patrones frente a la del
motor cuantitativo, con contracción bayesiana hacia el 30% del diseño y acotado a 10%–30% (el motor cuantitativo
conserva siempre ≥ 70%). Si el patrón contradice al escenario cuantitativo, su peso se reduce a la mitad
(prioridad a la evidencia cuantitativa) y se emite una alerta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import patterns as PT

HORIZONTE = 10          # velas para medir el acierto histórico
VENTANA_EVAL = 20       # en el historial, el patrón se evalúa solo si pertenece al tramo vigente
W_PRIOR, W_MIN, W_MAX = 0.30, 0.10, 0.30
K_SHRINK = 20           # muestras equivalentes del prior
EST_Q = {"Recién confirmado": 1.0, "Pendiente de confirmación": 0.6, "En formación": 0.35}
_META = {"CONFIRMED": "Recién confirmado", "PENDING_BREAKOUT": "Pendiente de confirmación", "FORMING": "En formación"}

_CAT = {"Hombro-cabeza-hombro": "Reversión", "Hombro-cabeza-hombro invertido": "Reversión",
        "Doble techo": "Reversión", "Doble suelo": "Reversión", "Triple techo": "Reversión",
        "Triple suelo": "Reversión", "Cuña ascendente": "Reversión", "Cuña descendente": "Reversión",
        "Triángulo simétrico": "Continuación", "Triángulo ascendente": "Continuación",
        "Triángulo descendente": "Continuación", "Bandera alcista": "Continuación", "Bandera bajista": "Continuación"}


def _vol_ok(d: pd.DataFrame, n: int = 3) -> bool:
    v = d["Volume"].astype(float)
    base = v.tail(23).head(20).mean()
    return bool(base > 0 and v.tail(n).mean() >= 1.1 * base)


def _niveles(d: pd.DataFrame, vp: dict | None, canal: dict | None) -> list[float]:
    lv = []
    for k in ("poc", "vah", "val"):
        if vp and vp.get(k) is not None:
            lv.append(float(vp[k]))
    for c in ("SMA50", "SMA200", "EMA21"):
        if c in d and pd.notna(d[c].iloc[-1]):
            lv.append(float(d[c].iloc[-1]))
    if canal and canal.get("superior") is not None:
        lv += [float(canal["superior"]), float(canal["inferior"])]
    lv += [float(d["High"].tail(20).max()), float(d["Low"].tail(20).min())]
    return lv


def _cerca(p: float, niveles: list[float], tol: float) -> bool:
    return any(abs(p - x) <= tol for x in niveles)


def _velas(d: pd.DataFrame, niveles: list[float], atr: float) -> list[dict]:
    """Velas de confirmación en las 2 últimas velas, válidas solo sobre un nivel clave."""
    o, h, l, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    out = []
    n = len(d)
    for i in (n - 1, n - 2):
        if i < 3:
            continue
        body, rng = abs(c[i] - o[i]), (h[i] - l[i]) or 1e-9
        found = None
        if c[i - 1] < o[i - 1] and c[i] > o[i] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body > abs(c[i - 1] - o[i - 1]):
            found = ("Envolvente alcista", "alcista", l[i])
        elif c[i - 1] > o[i - 1] and c[i] < o[i] and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body > abs(c[i - 1] - o[i - 1]):
            found = ("Envolvente bajista", "bajista", h[i])
        elif min(o[i], c[i]) - l[i] >= 2 * body and min(o[i], c[i]) - l[i] >= 0.6 * rng:
            found = ("Pin bar alcista", "alcista", l[i])
        elif h[i] - max(o[i], c[i]) >= 2 * body and h[i] - max(o[i], c[i]) >= 0.6 * rng:
            found = ("Pin bar bajista", "bajista", h[i])
        else:
            b1, b2 = abs(c[i - 2] - o[i - 2]), abs(c[i - 1] - o[i - 1])
            if c[i - 2] < o[i - 2] and b1 >= 0.8 * atr and b2 <= 0.3 * b1 and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2:
                found = ("Estrella de la mañana", "alcista", min(l[i - 2:i + 1]))
            elif c[i - 2] > o[i - 2] and b1 >= 0.8 * atr and b2 <= 0.3 * b1 and c[i] < o[i] and c[i] < (o[i - 2] + c[i - 2]) / 2:
                found = ("Estrella vespertina", "bajista", max(h[i - 2:i + 1]))
        if not found or not _cerca(found[2], niveles, 0.6 * atr):
            continue
        nom, ses, _ = found
        act = float(h[i] if ses == "alcista" else l[i])
        inv = float(l[i] if ses == "alcista" else h[i])
        if i == n - 1:
            est = "Pendiente de confirmación"
        else:
            sig = (c[n - 1] > h[i]) if ses == "alcista" else (c[n - 1] < l[i])
            if not sig:
                continue
            est = "Recién confirmado"
        out.append({"nombre": nom, "categoria": "Vela de confirmación", "sesgo": ses, "estado": est,
                    "activacion": act, "invalidacion": inv,
                    "condicion": (f"Si la siguiente vela cierra {'sobre' if ses == 'alcista' else 'bajo'} {act:.2f} "
                                  f"con volumen, la vela gatillo se confirma; se invalida con cierre "
                                  f"{'bajo' if ses == 'alcista' else 'sobre'} {inv:.2f}."),
                    "volumen": bool(d["Volume"].iloc[i] >= 1.1 * d["Volume"].iloc[max(0, i - 20):i].mean()),
                    "confluencia": True, "barra": i,
                    "texto": "Vela de giro sobre un nivel clave (VRVP, media o extremo de 20 velas)."})
        break
    return out


def _liquidez(d: pd.DataFrame, atr: float) -> list[dict]:
    """BOS / CHoCH sobre pivotes en zigzag, Spring / Upthrust y el último FVG sin rellenar."""
    out = []
    n = len(d)
    c, h, l = d["Close"].to_numpy(float), d["High"].to_numpy(float), d["Low"].to_numpy(float)
    pv = PT.zigzag(d.tail(200))
    off = n - min(n, 200)
    pv = [(i + off, p, t) for i, p, t in pv]
    Hs = [p for p in pv if p[2] == "H"]
    Ls = [p for p in pv if p[2] == "L"]
    if len(Hs) >= 2 and len(Ls) >= 2:
        tend = 1 if (Hs[-1][1] > Hs[-2][1] and Ls[-1][1] > Ls[-2][1]) else -1 if (Hs[-1][1] < Hs[-2][1] and Ls[-1][1] < Ls[-2][1]) else 0
        sh, sl = Hs[-1], Ls[-1]
        for k in range(max(sh[0], sl[0]) + 1, n):
            if k < n - 5:
                continue
            if c[k] > sh[1] and c[k - 1] <= sh[1]:
                nom = "CHoCH alcista" if tend < 0 else "BOS alcista"
                out.append({"nombre": nom, "categoria": "Liquidez / estructura", "sesgo": "alcista", "estado": "Recién confirmado",
                            "volumen": _vol_ok(d.iloc[:k + 1], 1), "confluencia": True, "barra": k,
                            "texto": ("Cambio de carácter: el cierre supera el último máximo tras una estructura bajista."
                                      if tend < 0 else "Ruptura de estructura a favor de la tendencia (nuevo máximo).")})
                break
            if c[k] < sl[1] and c[k - 1] >= sl[1]:
                nom = "CHoCH bajista" if tend > 0 else "BOS bajista"
                out.append({"nombre": nom, "categoria": "Liquidez / estructura", "sesgo": "bajista", "estado": "Recién confirmado",
                            "volumen": _vol_ok(d.iloc[:k + 1], 1), "confluencia": True, "barra": k,
                            "texto": ("Cambio de carácter: el cierre pierde el último mínimo tras una estructura alcista."
                                      if tend > 0 else "Ruptura de estructura a favor de la tendencia (nuevo mínimo).")})
                break
        # Spring / Upthrust: barrido del pivote con cierre de regreso
        for k in range(n - 3, n):
            if l[k] < sl[1] - 0.1 * atr and c[k] > sl[1] and k > sl[0]:
                out.append({"nombre": "Spring (barrido de mínimos)", "categoria": "Liquidez / estructura", "sesgo": "alcista",
                            "estado": "Recién confirmado", "volumen": _vol_ok(d.iloc[:k + 1], 1), "confluencia": True, "barra": k,
                            "texto": "El precio barre la liquidez bajo el último mínimo y cierra de vuelta dentro del rango."})
                break
            if h[k] > sh[1] + 0.1 * atr and c[k] < sh[1] and k > sh[0]:
                out.append({"nombre": "Upthrust (barrido de máximos)", "categoria": "Liquidez / estructura", "sesgo": "bajista",
                            "estado": "Recién confirmado", "volumen": _vol_ok(d.iloc[:k + 1], 1), "confluencia": True, "barra": k,
                            "texto": "El precio barre la liquidez sobre el último máximo y cierra de vuelta dentro del rango."})
                break
    # FVG: hueco de 3 velas en las últimas 20, aún sin rellenar
    for i in range(n - 1, max(2, n - 20), -1):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= 0.3 * atr and l[i + 1:].min(initial=np.inf) > h[i - 2]:
            out.append({"nombre": f"FVG alcista {h[i - 2]:.2f}–{l[i]:.2f}", "categoria": "Liquidez / estructura",
                        "sesgo": "alcista", "estado": "En formación", "volumen": _vol_ok(d.iloc[:i + 1], 1),
                        "confluencia": True, "barra": i, "zona": (float(h[i - 2]), float(l[i])),
                        "activacion": float(l[i]), "invalidacion": float(h[i - 2]),
                        "condicion": f"Si el precio retrocede a {h[i - 2]:.2f}–{l[i]:.2f} y cierra con rechazo alcista, "
                                     f"la zona de demanda se confirma; un cierre bajo {h[i - 2]:.2f} la invalida.",
                        "texto": "Hueco de valor razonable sin rellenar: zona de demanda probable en un retroceso."})
            break
        if h[i] < l[i - 2] and l[i - 2] - h[i] >= 0.3 * atr and h[i + 1:].max(initial=-np.inf) < l[i - 2]:
            out.append({"nombre": f"FVG bajista {h[i]:.2f}–{l[i - 2]:.2f}", "categoria": "Liquidez / estructura",
                        "sesgo": "bajista", "estado": "En formación", "volumen": _vol_ok(d.iloc[:i + 1], 1),
                        "confluencia": True, "barra": i, "zona": (float(h[i]), float(l[i - 2])),
                        "activacion": float(h[i]), "invalidacion": float(l[i - 2]),
                        "condicion": f"Si el precio rebota a {h[i]:.2f}–{l[i - 2]:.2f} y cierra con rechazo bajista, "
                                     f"la zona de oferta se confirma; un cierre sobre {l[i - 2]:.2f} la invalida.",
                        "texto": "Hueco de valor razonable sin rellenar: zona de oferta probable en un rebote."})
            break
    return out


def apoyos(d: pd.DataFrame, vp: dict | None = None, canal: dict | None = None, figuras: list | None = None,
           adx_tend: bool | None = None, tf: str | None = None) -> list[dict]:
    """Patrones de apoyo VIGENTES con categoría, estado, volumen, confluencia y escenario condicionado.
    En temporalidades menores a 1H devuelve una lista vacía (módulo inhabilitado)."""
    if len(d) < 40 or not PT.patrones_habilitados(tf):
        return []
    atr = PT._atr(d)
    niv = _niveles(d, vp, canal)
    out = []
    for f in (figuras if figuras is not None else PT.patterns(d, tf=tf)):
        est = _META.get(f.get("estado_meta"))
        if est is None:
            continue
        cat = _CAT.get(f["nombre"], "Reversión")
        ult = f["puntos"][-1]
        try:
            barra = int(d.index.get_loc(ult[0]))
        except Exception:
            barra = len(d) - 1
        vrvp = _cerca(float(f.get("activacion", ult[1])), niv, 0.75 * atr)
        adx_ok = None if adx_tend is None else (adx_tend if cat == "Continuación" else not adx_tend)
        out.append({"nombre": f["nombre"], "categoria": cat, "sesgo": f["sesgo"], "estado": est,
                    "volumen": _vol_ok(d), "confluencia": vrvp and adx_ok is not False,
                    "confluencia_parcial": vrvp or bool(adx_ok), "barra": barra,
                    "activacion": f.get("activacion"), "invalidacion": f.get("invalidacion"),
                    "objetivo": f.get("objetivo"), "condicion": f.get("condicion", ""), "texto": f.get("texto", "")})
    out += _velas(d, niv, atr)
    out += _liquidez(d, atr)
    return out


def calidad(a: dict) -> float:
    q = EST_Q.get(a["estado"], 0.35)
    q *= 1.0 if a.get("volumen") else 0.6
    q *= 1.0 if a.get("confluencia") else (0.85 if a.get("confluencia_parcial") else 0.7)
    if a["categoria"] == "Vela de confirmación" or a["nombre"].startswith("FVG"):
        q *= 0.5
    return q


def evidencia(aps: list[dict], sentido: int, solo_confirmados: bool = True) -> float:
    """E ∈ [−1, 1]: + respalda el sentido cuantitativo, − lo contradice. Los neutrales no suman.
    Por defecto solo cuentan los patrones recién confirmados (la geometría sola no es señal)."""
    e = 0.0
    for a in aps:
        if solo_confirmados and a["estado"] != "Recién confirmado":
            continue
        s = {"alcista": 1, "bajista": -1}.get(a["sesgo"], 0)
        q = calidad(a if solo_confirmados else {**a, "estado": "Recién confirmado", "volumen": True})
        e += s * sentido * q
    return float(np.clip(e, -1, 1))


def calibrar(d: pd.DataFrame, score: pd.Series, h: int = HORIZONTE, ventana: int = 400, paso: int = 3,
             tf: str | None = None) -> dict:
    """Acierto direccional histórico del motor cuantitativo y de los patrones (al confirmarse) en este activo, y el
    peso resultante. En temporalidades menores a 1H el peso de los patrones es 0."""
    if not PT.patrones_habilitados(tf):
        return {"horizonte_velas": h, "acierto_cuantitativo": None, "muestras_cuantitativo": 0,
                "acierto_patrones": None, "muestras_patrones": 0, "peso_patrones": 0.0, "peso_cuantitativo": 1.0,
                "habilitado": False}
    c = d["Close"].to_numpy(float)
    n = len(d)
    i0 = max(60, n - ventana)
    fut = pd.Series(c).shift(-h).to_numpy() - c
    sc = score.reindex(d.index).to_numpy(float)
    m = [(np.sign(sc[i]) == np.sign(fut[i])) for i in range(i0, n - h) if np.isfinite(sc[i]) and abs(sc[i]) >= 15
         and np.isfinite(fut[i]) and fut[i] != 0]
    acc_q, n_q = (float(np.mean(m)), len(m)) if m else (0.5, 0)
    hits = []
    for i in range(i0, n - h, paso):
        w = d.iloc[: i + 1]
        try:
            aps = [a for a in apoyos(w) if a["estado"] == "Recién confirmado" and a["barra"] >= i - VENTANA_EVAL
                   and a["sesgo"] in ("alcista", "bajista")]
        except Exception:
            continue
        for a in aps:
            s = 1 if a["sesgo"] == "alcista" else -1
            if fut[i] != 0 and np.isfinite(fut[i]):
                hits.append(np.sign(fut[i]) == s)
    acc_p, n_p = (float(np.mean(hits)), len(hits)) if hits else (0.5, 0)
    e_q, e_p = max(acc_q - 0.5, 0.0), max(acc_p - 0.5, 0.0)
    r = e_p / (e_q + e_p) if (e_q + e_p) > 0 else W_MIN  # sin ventaja en ninguno: patrones al mínimo
    w = (n_p * r + K_SHRINK * W_PRIOR) / (n_p + K_SHRINK)
    w = float(np.clip(w, W_MIN, W_MAX))
    return {"horizonte_velas": h, "acierto_cuantitativo": round(acc_q, 3), "muestras_cuantitativo": n_q,
            "acierto_patrones": round(acc_p, 3), "muestras_patrones": n_p,
            "peso_patrones": round(w, 3), "peso_cuantitativo": round(1 - w, 3), "habilitado": True}


def consolidar(prob: float, sentido: int, aps: list[dict], cal: dict, score: float, adx: dict) -> dict:
    """Confianza global = mezcla del motor cuantitativo (ancla: probabilidad histórica) y de los patrones
    recién confirmados. Los patrones pendientes aportan solo de forma condicionada (aporte_si_confirma)."""
    conf_q = float(np.clip(prob * 100, 1, 99))
    habil = cal.get("habilitado", True)
    e = evidencia(aps, sentido) if habil else 0.0
    w = cal["peso_patrones"] * (0.5 if e < 0 else 1.0) if (habil and any(a["estado"] == "Recién confirmado" for a in aps)) else 0.0
    conf_p = 50 + 50 * e
    conf_g = float(np.clip((1 - w) * conf_q + w * conf_p, 1, 99))
    # escenario condicionado: cuánto sumaría la confianza si los patrones pendientes se confirman (con volumen)
    pend = [a for a in aps if a["estado"] != "Recién confirmado"]
    e_h = evidencia(aps, sentido, solo_confirmados=False) if (habil and pend) else None
    if e_h is not None:
        w_h = cal["peso_patrones"] * (0.5 if e_h < 0 else 1.0)
        si_conf = float(np.clip((1 - w_h) * conf_q + w_h * (50 + 50 * e_h), 1, 99)) - conf_q
    else:
        si_conf = None
    nivel = "Alta" if conf_g >= 60 else "Media" if conf_g >= 45 else "Baja"
    if adx.get("regimen") == "rango" and abs(score) < 30:
        esc = "Neutral"
    else:
        esc = "Alcista" if score >= 15 else "Bajista" if score <= -15 else "Neutral"
    alertas = [f"{a['nombre']} ({a['estado'].lower()}) contradice el escenario cuantitativo"
               for a in aps if {"alcista": 1, "bajista": -1}.get(a["sesgo"], 0) * sentido < 0]
    return {"escenario_base": esc, "sentido_plan": "alcista" if sentido > 0 else "bajista",
            "patrones_habilitados": habil,
            "confianza_cuantitativa": round(conf_q, 1), "evidencia_patrones": round(e, 2),
            "peso_patrones_aplicado": round(w, 3), "confianza_patrones": round(conf_p, 1),
            "aporte_patrones": round(conf_g - conf_q, 1),
            "aporte_si_confirma": None if si_conf is None else round(si_conf, 1),
            "confianza_global": round(conf_g, 1), "nivel": nivel, "alertas": alertas,
            "formula": "conf_global = (1 − w)·conf_cuant + w·(50 + 50·E), E solo con patrones recién confirmados"}
