"""Estructura del precio: canales (alcista, bajista, lateral) y figuras chartistas clásicas.

- Canal: regresión lineal del cierre en la ventana con mejor ajuste (40–150 velas). Las líneas paralelas pasan por
  los extremos de máximos y mínimos de esa ventana (como se dibuja a mano). Un canal se considera confirmado con
  al menos 2 toques en cada línea.
- Figuras: pivotes en zigzag (giro mínimo = 1.5 ATR) y reglas de forma para hombro-cabeza-hombro (normal e
  invertido), doble techo / doble suelo y triángulos (simétrico, ascendente y descendente).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VENTANAS = (40, 60, 90, 120, 150)


# ------------------------------------------------------------------------------------------- canales
def _atr(d: pd.DataFrame) -> float:
    if "ATR" in d and pd.notna(d["ATR"].iloc[-1]):
        return float(d["ATR"].iloc[-1])
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - d["Close"].shift()).abs(),
                    (d["Low"] - d["Close"].shift()).abs()], axis=1).max(axis=1)
    return float(tr.tail(14).mean())


def channel(d: pd.DataFrame) -> dict | None:
    """Canal vigente: tipo, pendiente, líneas (inicio/fin) y posición del precio dentro del canal (0 = soporte,
    1 = resistencia)."""
    if len(d) < 45:
        return None
    atr = _atr(d)
    cands = []
    for n in VENTANAS:
        if len(d) < n + 5:
            break
        y = d.tail(n)["Close"].to_numpy(float)
        t = np.arange(n, dtype=float)
        b, a = np.polyfit(t, y, 1)
        ss_res = float(((y - (a + b * t)) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum()) or 1e-9
        cands.append((n, a, b, 1 - ss_res / ss_tot))
    if not cands:
        return None
    # 1) canal con tendencia: mejor ajuste (a igualdad, la ventana más larga) con pendiente significativa
    trend = [c for c in cands if c[3] >= 0.55 and abs(c[2] * c[0]) >= 2.0 * atr]
    if trend:
        n, a, b, r2 = max(trend, key=lambda c: c[3] + 0.0008 * c[0])
    else:  # 2) rango lateral: la ventana más larga (≥ 60 velas si hay datos)
        n, a, b, r2 = cands[-1]
    w = d.tail(n)
    t = np.arange(n, dtype=float)
    mid = a + b * t
    up_off = float((w["High"].to_numpy(float) - mid).max())
    lo_off = float((mid - w["Low"].to_numpy(float)).max())
    width = up_off + lo_off
    tol = max(0.25 * atr, width * 0.06)
    tq_up = _toques(w["High"].to_numpy(float), mid + up_off, tol, kind="max")
    tq_lo = _toques(w["Low"].to_numpy(float), mid - lo_off, tol, kind="min")
    move = b * n  # desplazamiento total de la línea media en la ventana
    if r2 >= 0.55 and abs(move) >= 2.0 * atr:
        tipo = "alcista" if b > 0 else "bajista"
    elif abs(move) < 1.5 * atr and width <= 8 * atr:
        tipo = "lateral"
    else:
        tipo = "indefinido"
    last = float(d["Close"].iloc[-1])
    lo_now, up_now = mid[-1] - lo_off, mid[-1] + up_off
    pos = (last - lo_now) / (up_now - lo_now) if up_now > lo_now else 0.5
    return {
        "tipo": tipo, "ventana": n, "r2": float(r2), "pendiente": float(b), "ancho": float(width),
        "confirmado": tq_up >= 2 and tq_lo >= 2, "toques_sup": tq_up, "toques_inf": tq_lo,
        "x0": w.index[0], "x1": w.index[-1], "mid0": float(mid[0]), "mid1": float(mid[-1]),
        "up_off": up_off, "lo_off": lo_off, "superior": float(up_now), "inferior": float(lo_now),
        "media": float(mid[-1]), "posicion": float(pos), "atr": atr,
    }


def _toques(v: np.ndarray, line: np.ndarray, tol: float, kind: str) -> int:
    """Toques separados (al menos 4 velas entre sí) del precio sobre la línea."""
    near = np.where(np.abs(v - line) <= tol)[0]
    n, last = 0, -10
    for i in near:
        if i - last >= 4:
            n, last = n + 1, i
    return n


def channel_signal(ch: dict | None) -> float | None:
    """Señal de −1 a +1 según el tipo de canal y la posición del precio (cómo opera un profesional):
    canal alcista: comprar cerca del soporte; bajista: vender cerca de la resistencia; lateral: reversión a la
    media (comprar soporte, vender resistencia); rupturas del canal: señal en la dirección de la ruptura."""
    if not ch or ch["tipo"] == "indefinido":
        return None
    p = ch["posicion"]
    if ch["tipo"] == "alcista":
        if p < -0.05:
            return -0.6  # ruptura bajista del canal alcista
        return float(np.clip(0.3 + (0.5 - p) * 1.0, -0.1, 0.8))
    if ch["tipo"] == "bajista":
        if p > 1.05:
            return 0.6  # ruptura alcista del canal bajista
        return float(np.clip(-0.3 - (p - 0.5) * 1.0, -0.8, 0.1))
    # lateral
    if p > 1.05:
        return 0.5
    if p < -0.05:
        return -0.5
    return float(np.clip((0.5 - p) * 1.2, -0.6, 0.6))


def lectura_canal(ch: dict | None, money=lambda v: f"${v:,.2f}") -> dict:
    """Texto didáctico y reglas de operación para el canal vigente."""
    if not ch or ch["tipo"] == "indefinido":
        return {"titulo": "Sin canal claro", "texto": "El precio no respeta un canal definido: las señales de "
                "tendencia y de rango pierden fiabilidad. Conviene esperar una estructura clara o operar solo "
                "rupturas con volumen.", "reglas": []}
    p, sup, inf, med = ch["posicion"], ch["superior"], ch["inferior"], ch["media"]
    zona = ("bajo el canal (ruptura)" if p < -0.05 else "sobre el canal (ruptura)" if p > 1.05 else
            "cerca del soporte" if p < 0.25 else "cerca de la resistencia" if p > 0.75 else "en la zona media")
    conf = "confirmado" if ch["confirmado"] else "en formación"
    base = f"Canal {ch['tipo']} {conf} ({ch['ventana']} velas, {ch['toques_sup']}+{ch['toques_inf']} toques); precio {zona} ({p * 100:.0f}% del ancho)."
    if ch["tipo"] == "alcista":
        reglas = [f"Comprar en retrocesos al soporte del canal (~{money(inf)}), no en la resistencia.",
                  f"Objetivo natural: la línea superior (~{money(sup)}); tomar parte en la media ({money(med)}).",
                  f"Stop bajo el soporte del canal; un cierre bajo {money(inf)} rompe el canal y anula la tesis alcista.",
                  "Evitar ventas en corto contra el canal salvo divergencia clara en la resistencia."]
    elif ch["tipo"] == "bajista":
        reglas = [f"Vender (o no comprar) en rebotes a la resistencia del canal (~{money(sup)}).",
                  f"Objetivo natural de los cortos: la línea inferior (~{money(inf)}).",
                  f"Compras solo tras ruptura y cierre sobre {money(sup)}, idealmente con retesteo y volumen.",
                  "No comprar el soporte de un canal bajista esperando giro: suele ser rebote corto."]
    else:
        reglas = [f"Rango lateral: comprar cerca del soporte (~{money(inf)}) y vender cerca de la resistencia (~{money(sup)}).",
                  f"Objetivos en la media ({money(med)}) o en el lado opuesto del rango.",
                  "Las señales de tendencia (cruces de medias, MACD) fallan más en rango: priorizar osciladores.",
                  "Una ruptura vale solo con cierre fuera del rango y volumen; si vuelve adentro, es trampa."]
    return {"titulo": f"Canal {ch['tipo']}", "texto": base, "reglas": reglas}


# ------------------------------------------------------------------------------------------- figuras
def zigzag(d: pd.DataFrame, k_atr: float = 1.5) -> list[tuple[int, float, str]]:
    """Pivotes alternados (índice, precio, 'H'|'L'): un máximo se confirma cuando el precio cae k_atr × ATR desde
    él (y al revés para los mínimos)."""
    hi, lo = d["High"].to_numpy(float), d["Low"].to_numpy(float)
    n, thr = len(d), k_atr * _atr(d)
    piv: list[tuple[int, float, str]] = []
    last = None
    ch_i, ch_v, cl_i, cl_v = 0, hi[0], 0, lo[0]  # máximo y mínimo candidatos desde el último pivote
    for i in range(1, n):
        if hi[i] >= ch_v:
            ch_i, ch_v = i, hi[i]
        if lo[i] <= cl_v:
            cl_i, cl_v = i, lo[i]
        if last != "H" and ch_i < i and ch_v - lo[i] >= thr and (last is None or ch_i > piv[-1][0]):
            piv.append((ch_i, float(ch_v), "H"))
            last = "H"
            seg = lo[ch_i + 1:i + 1]
            cl_i, cl_v = ch_i + 1 + int(np.argmin(seg)), float(seg.min())
            ch_i, ch_v = i, hi[i]
        elif last != "L" and cl_i < i and hi[i] - cl_v >= thr and (last is None or cl_i > piv[-1][0]):
            piv.append((cl_i, float(cl_v), "L"))
            last = "L"
            seg = hi[cl_i + 1:i + 1]
            ch_i, ch_v = cl_i + 1 + int(np.argmax(seg)), float(seg.max())
            cl_i, cl_v = i, lo[i]
    return piv


def _line_at(i0, v0, i1, v1, i):
    return v0 + (v1 - v0) * (i - i0) / ((i1 - i0) or 1)


def patterns(d: pd.DataFrame, lookback: int = 160) -> list[dict]:
    """Figuras recientes en la ventana: lista de dicts con nombre, sesgo, estado, puntos [(fecha, precio)],
    líneas [((fecha, precio), (fecha, precio))], objetivo y texto."""
    w = d.tail(lookback)
    if len(w) < 40:
        return []
    atr = _atr(w)
    pv = zigzag(w)
    idx = w.index
    close = w["Close"].to_numpy(float)
    last_i = len(w) - 1
    out = []
    P = lambda p: (idx[p[0]], float(p[1]))

    def reciente(i_last):
        return i_last >= len(w) * 0.55

    # hombro-cabeza-hombro (5 pivotes) y su inverso
    for j in range(len(pv) - 5, -1, -1):
        a, b, c, e, f = pv[j:j + 5]
        if not reciente(f[0]):
            break
        if [p[2] for p in (a, b, c, e, f)] == ["H", "L", "H", "L", "H"]:
            hs, hd = a[1], f[1]
            if f[0] - a[0] >= 20 and c[1] - max(b[1], e[1]) >= 1.5 * atr \
                    and abs(e[1] - b[1]) <= 0.5 * (c[1] - max(b[1], e[1])) and abs(hs - hd) <= 1.5 * atr and c[1] > max(hs, hd) + 0.3 * atr and abs(hs - hd) <= max(1.0 * atr, 0.25 * (c[1] - min(b[1], e[1]))):
                neck = lambda i: _line_at(b[0], b[1], e[0], e[1], i)
                brk = next((i for i in range(f[0] + 1, last_i + 1) if close[i] < neck(i)), None)
                end = brk if brk is not None else min(last_i, f[0] + (f[0] - a[0]) // 2)
                tgt = neck(end) - (c[1] - neck(c[0]))
                conf = brk is not None
                hecho = conf and close[brk:].min() <= tgt
                out.append({"nombre": "Hombro-cabeza-hombro", "sesgo": "bajista",
                            "estado": "objetivo alcanzado" if hecho else "confirmada" if conf else "en formación",
                            "puntos": [P(a), P(b), P(c), P(e), P(f)],
                            "lineas": [(P(b), (idx[end], neck(end)))], "objetivo": float(tgt),
                            "texto": "Techo de tendencia: la ruptura de la línea clavicular confirma la figura y "
                                     "proyecta una caída igual a la altura de la cabeza."})
                break
        if [p[2] for p in (a, b, c, e, f)] == ["L", "H", "L", "H", "L"]:
            hs, hd = a[1], f[1]
            if f[0] - a[0] >= 20 and min(b[1], e[1]) - c[1] >= 1.5 * atr \
                    and abs(e[1] - b[1]) <= 0.5 * (min(b[1], e[1]) - c[1]) and abs(hs - hd) <= 1.5 * atr and c[1] < min(hs, hd) - 0.3 * atr and abs(hs - hd) <= max(1.0 * atr, 0.25 * (max(b[1], e[1]) - c[1])):
                neck = lambda i: _line_at(b[0], b[1], e[0], e[1], i)
                brk = next((i for i in range(f[0] + 1, last_i + 1) if close[i] > neck(i)), None)
                end = brk if brk is not None else min(last_i, f[0] + (f[0] - a[0]) // 2)
                tgt = neck(end) + (neck(c[0]) - c[1])
                conf = brk is not None
                hecho = conf and close[brk:].max() >= tgt
                out.append({"nombre": "Hombro-cabeza-hombro invertido", "sesgo": "alcista",
                            "estado": "objetivo alcanzado" if hecho else "confirmada" if conf else "en formación",
                            "puntos": [P(a), P(b), P(c), P(e), P(f)],
                            "lineas": [(P(b), (idx[end], neck(end)))], "objetivo": float(tgt),
                            "texto": "Suelo de tendencia: la ruptura al alza de la línea clavicular confirma la "
                                     "figura y proyecta una subida igual a la profundidad de la cabeza."})
                break

    # doble techo / doble suelo (3 pivotes)
    if len(pv) >= 3:
        a, b, c = pv[-3:]
        if reciente(c[0]) and c[0] - a[0] >= 10:
            if [p[2] for p in (a, b, c)] == ["H", "L", "H"] and abs(a[1] - c[1]) <= 0.6 * atr \
                    and min(a[1], c[1]) - b[1] >= 2 * atr:
                conf = close[-1] < b[1]
                out.append({"nombre": "Doble techo", "sesgo": "bajista", "estado": "confirmada" if conf else "en formación",
                            "puntos": [P(a), P(b), P(c)],
                            "lineas": [((idx[b[0]], b[1]), (idx[last_i], b[1]))],
                            "objetivo": float(b[1] - (max(a[1], c[1]) - b[1])),
                            "texto": "Dos máximos similares: la pérdida del mínimo intermedio confirma el techo."})
            if [p[2] for p in (a, b, c)] == ["L", "H", "L"] and abs(a[1] - c[1]) <= 0.6 * atr \
                    and b[1] - max(a[1], c[1]) >= 2 * atr:
                conf = close[-1] > b[1]
                out.append({"nombre": "Doble suelo", "sesgo": "alcista", "estado": "confirmada" if conf else "en formación",
                            "puntos": [P(a), P(b), P(c)],
                            "lineas": [((idx[b[0]], b[1]), (idx[last_i], b[1]))],
                            "objetivo": float(b[1] + (b[1] - min(a[1], c[1]))),
                            "texto": "Dos mínimos similares: la superación del máximo intermedio confirma el suelo."})

    # triple techo / triple suelo (5 pivotes, tres extremos similares)
    if len(pv) >= 5 and not out:
        a, b, c, e, f = pv[-5:]
        tipos = [p[2] for p in (a, b, c, e, f)]
        if reciente(f[0]) and f[0] - a[0] >= 20:
            ext3 = [a[1], c[1], f[1]]
            if tipos == ["H", "L", "H", "L", "H"] and max(ext3) - min(ext3) <= 0.8 * atr \
                    and min(ext3) - max(b[1], e[1]) >= 1.5 * atr:
                sop = min(b[1], e[1])
                conf = close[-1] < sop
                out.append({"nombre": "Triple techo", "sesgo": "bajista", "estado": "confirmada" if conf else "en formación",
                            "puntos": [P(a), P(b), P(c), P(e), P(f)],
                            "lineas": [((idx[b[0]], sop), (idx[last_i], sop))],
                            "objetivo": float(sop - (max(ext3) - sop)),
                            "texto": "Tres máximos similares: la resistencia rechaza el precio tres veces; perder el "
                                     "soporte intermedio confirma la reversión."})
            if tipos == ["L", "H", "L", "H", "L"] and max(ext3) - min(ext3) <= 0.8 * atr \
                    and min(b[1], e[1]) - max(ext3) >= 1.5 * atr:
                res = max(b[1], e[1])
                conf = close[-1] > res
                out.append({"nombre": "Triple suelo", "sesgo": "alcista", "estado": "confirmada" if conf else "en formación",
                            "puntos": [P(a), P(b), P(c), P(e), P(f)],
                            "lineas": [((idx[b[0]], res), (idx[last_i], res))],
                            "objetivo": float(res + (res - min(ext3))),
                            "texto": "Tres mínimos similares: el soporte resiste tres veces; superar la resistencia "
                                     "intermedia confirma la reversión."})

    # triángulos (últimos 2 máximos y 2 mínimos)
    hs_ = [p for p in pv if p[2] == "H"][-2:]
    ls_ = [p for p in pv if p[2] == "L"][-2:]
    if len(hs_) == 2 and len(ls_) == 2 and reciente(max(hs_[-1][0], ls_[-1][0])) and not out:
        dh, dl = hs_[1][1] - hs_[0][1], ls_[1][1] - ls_[0][1]
        flat = 0.5 * atr
        nombre = None
        if dh < -flat and dl > flat:
            nombre, sesgo = "Triángulo simétrico", "neutral"
        elif abs(dh) <= flat and dl > flat:
            nombre, sesgo = "Triángulo ascendente", "alcista"
        elif dh < -flat and abs(dl) <= flat:
            nombre, sesgo = "Triángulo descendente", "bajista"
        elif dh > flat and dl > flat and dl > dh * 1.15:  # ambas suben y convergen
            nombre, sesgo = "Cuña ascendente", "bajista"
        elif dh < -flat and dl < -flat and dh < dl * 1.15:  # ambas bajan y convergen
            nombre, sesgo = "Cuña descendente", "alcista"
        if nombre:
            up = lambda i: _line_at(hs_[0][0], hs_[0][1], hs_[1][0], hs_[1][1], i)
            dn = lambda i: _line_at(ls_[0][0], ls_[0][1], ls_[1][0], ls_[1][1], i)
            est = ("ruptura alcista" if close[-1] > up(last_i) else "ruptura bajista" if close[-1] < dn(last_i)
                   else "en formación")
            alt = hs_[0][1] - ls_[0][1]
            tgt = (up(last_i) + alt) if est == "ruptura alcista" else (dn(last_i) - alt) if est == "ruptura bajista" else None
            pts = sorted(hs_ + ls_, key=lambda p: p[0])
            cuna = nombre.startswith("Cuña")
            out.append({"nombre": nombre, "sesgo": sesgo, "estado": est, "puntos": [P(p) for p in pts],
                        "lineas": [(P(hs_[0]), (idx[last_i], up(last_i))), (P(ls_[0]), (idx[last_i], dn(last_i)))],
                        "objetivo": None if tgt is None else float(tgt),
                        "texto": ("Dos líneas que se inclinan en el mismo sentido y convergen: el impulso se agota; "
                                  "suele romper en contra de la inclinación." if cuna else
                                  "Compresión del precio entre dos líneas convergentes: la ruptura con volumen marca la "
                                  "dirección; el objetivo es la altura inicial del triángulo.")})

    # bandera / banderín: impulso fuerte (≥ 4 ATR en ≤ 12 velas) y consolidación corta y estrecha en contra
    if not out and len(w) >= 30:
        for L in range(5, 16):
            j = last_i - L  # fin del impulso
            k0 = max(0, j - 12)
            seg = close[k0:j + 1]
            imp = close[j] - seg.min() if close[j] - seg.min() >= seg.max() - close[j] else close[j] - seg.max()
            if abs(imp) < 4 * atr:
                continue
            cons = w.iloc[j + 1:]
            rng = float(cons["High"].max() - cons["Low"].min())
            pend = float(np.polyfit(np.arange(len(cons)), cons["Close"].to_numpy(float), 1)[0]) * len(cons)
            if rng <= 0.5 * abs(imp) and pend * np.sign(imp) <= 0.15 * abs(imp):
                alc = imp > 0
                hi_c, lo_c = float(cons["High"].max()), float(cons["Low"].min())
                brk = close[-1] > hi_c if alc else close[-1] < lo_c
                i0 = int(np.argmin(seg) if alc else np.argmax(seg)) + k0
                out.append({"nombre": "Bandera alcista" if alc else "Bandera bajista", "sesgo": "alcista" if alc else "bajista",
                            "estado": "confirmada" if brk else "en formación",
                            "puntos": [P((i0, close[i0])), P((j, close[j])), P((last_i, close[last_i]))],
                            "lineas": [((idx[j + 1], hi_c), (idx[last_i], hi_c)), ((idx[j + 1], lo_c), (idx[last_i], lo_c))],
                            "objetivo": float((hi_c if alc else lo_c) + imp),
                            "texto": "Pausa estrecha tras un impulso fuerte: la ruptura en el sentido del impulso "
                                     "proyecta un recorrido similar al mástil."})
                break
    return out[:2]
