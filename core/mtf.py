"""Análisis multi-temporalidad (MTF).

Cada temporalidad elegida arrastra otras dos mayores (operativa · contexto · tendencia mayor). Sus pesos NO son fijos:
dependen del horizonte de la operación (días hasta el vencimiento de la opción, o el plazo natural de la temporalidad
en el análisis de la acción). Cada temporalidad tiene un plazo natural H_tf; su peso es un núcleo log-normal

    w_tf ∝ exp( −(ln(H / H_tf))² / (2·σ²) ),  σ = 1, normalizado a 100 %

así que a menor horizonte más pesan las temporalidades menores (las mayores quedan como soportes y resistencias de
segundo nivel) y a mayor horizonte dominan las mayores (las menores solo afinan el punto de entrada).

Niveles: se unen los soportes y resistencias de las tres temporalidades (más los nodos del VRVP), se agrupan a menos
de medio ATR y su fuerza = Σ toques × rango de la temporalidad (operativa 1, contexto 2, mayor 3) + 2 por coincidir
con el VRVP. El objetivo y la invalidación salen de los niveles de las temporalidades dominantes para ese horizonte.
"""
from __future__ import annotations

import math

import numpy as np

TRIADAS = {"10m": ("10m", "1h", "4h"), "30m": ("30m", "4h", "1D"), "1h": ("1h", "4h", "1D"),
           "4h": ("4h", "1D", "1W"), "1D": ("1D", "1W", "1M"), "1W": ("1W", "1M", "1M"), "1M": ("1M", "1M", "1M")}
# plazo natural (en días de calendario) para el que cada temporalidad es más informativa
PLAZO = {"10m": 0.3, "30m": 0.8, "1h": 1.5, "4h": 5.0, "1D": 25.0, "1W": 90.0, "1M": 365.0}
# horizonte por defecto de una operación en el análisis de la acción, según la temporalidad elegida
HORIZONTE_TF = {"10m": 0.5, "30m": 1.5, "1h": 5.0, "4h": 12.0, "1D": 30.0, "1W": 120.0, "1M": 365.0}
SIGMA = 1.0
ROLES = ("Operativa", "Contexto", "Mayor")


def triada(tf: str) -> list[str]:
    """Temporalidades únicas de la tríada, en orden de menor a mayor."""
    out = []
    for t in TRIADAS.get(tf, (tf,)):
        if t not in out:
            out.append(t)
    return out


def pesos(horizonte_dias: float, tfs: list[str]) -> dict[str, float]:
    """Pesos (suman 1) de cada temporalidad para un horizonte en días."""
    h = max(float(horizonte_dias), 0.1)
    raw = {t: math.exp(-(math.log(h / PLAZO[t]) ** 2) / (2 * SIGMA ** 2)) for t in tfs}
    s = sum(raw.values()) or 1.0
    return {t: v / s for t, v in raw.items()}


def _niveles_tf(A: dict, rango: int) -> list[dict]:
    plan = A.get("plan") or {}
    out = []
    for p, n in (plan.get("soportes") or []) + (plan.get("resistencias") or []):
        out.append({"precio": float(p), "toques": int(n), "rango": rango, "vrvp": False})
    vp = A.get("vprofile") or {}
    for k in ("poc", "vah", "val"):
        if vp.get(k):
            out.append({"precio": float(vp[k]), "toques": 1, "rango": rango, "vrvp": True, "nodo": k.upper()})
    return out


PESO_FUND_MAX, HORIZONTE_FUND = 0.4, 180  # el fundamental llega a su peso máximo a 6 meses


def combinar(analisis: dict[str, dict], horizonte_dias: float, tf_operativa: str) -> dict:
    """analisis: {tf: resultado de full_analysis} de la tríada. Devuelve puntaje, alineación y niveles fuertes."""
    tfs = [t for t in triada(tf_operativa) if t in analisis]
    w = pesos(horizonte_dias, tfs)
    A0 = analisis[tf_operativa]
    spot = float(A0["df"]["Close"].iloc[-1])
    atr = float(A0["plan"].get("atr") or A0["df"]["ATR"].iloc[-1])
    filas, score, num, den = [], 0.0, 0.0, 0.0
    for i, t in enumerate(tfs):
        A = analisis[t]
        # puntaje TÉCNICO de cada temporalidad: el fundamental es el mismo en todas y, sumado en cada una,
        # fabricaba una alineación falsa (las tres heredaban el mismo sesgo). Entra una sola vez, abajo.
        sc = float((A.get("tech") or {}).get("score", A.get("combinado") or 0))
        con = ((A.get("metodo") or {}).get("consolidado") or {})
        adx = ((A.get("metodo") or {}).get("adx") or {})
        score += w[t] * sc
        s = 1 if sc >= 15 else -1 if sc <= -15 else 0
        num += w[t] * s
        den += w[t] * abs(s)
        filas.append({"tf": t, "rol": ROLES[min(i, 2)], "peso": w[t], "puntaje": sc,
                      "escenario": con.get("escenario_base") or ("Alcista" if s > 0 else "Bajista" if s < 0 else "Neutral"),
                      "adx": adx.get("adx"), "regimen": adx.get("regimen")})
    # fundamental: una sola vez, con peso según el horizonte (casi nada en días, hasta 40 % a 6 meses o más)
    fs = (A0.get("fscore") or {}).get("score")
    w_f = PESO_FUND_MAX * min(1.0, horizonte_dias / HORIZONTE_FUND) if fs is not None else 0.0
    tecnico = score
    score = (1 - w_f) * tecnico + w_f * float(fs or 0)
    alineacion = abs(num) / den if den else 0.0  # 1 = las temporalidades con sesgo apuntan al mismo lado
    sentido = 1 if score >= 0 else -1
    # conflicto: peso de las temporalidades que van en contra del puntaje combinado
    contra = [f for f in filas if (f["puntaje"] >= 15 and sentido < 0) or (f["puntaje"] <= -15 and sentido > 0)]
    peso_contra = sum(f["peso"] for f in contra)
    lateral = all(f["regimen"] == "rango" for f in filas if f["regimen"])
    if lateral:
        estado = "Lateral"
    elif not contra and all(abs(f["puntaje"]) >= 15 for f in filas):
        estado = "Alineado"
    elif contra and filas[0] not in contra and contra[-1]["rol"] == "Mayor":
        estado = "Rebote contra la tendencia mayor"
    elif contra and filas[0] in contra:
        estado = "Operativa en contra"
    else:
        estado = "Mixto"
    niveles = fuertes(analisis, tfs, spot, atr, w)
    return {"tfs": tfs, "pesos": w, "horizonte_dias": horizonte_dias, "filas": filas, "puntaje": score,
            "puntaje_tecnico": tecnico, "fundamental": {"puntaje": fs, "peso": w_f},
            "alineacion": alineacion, "estado": estado, "peso_en_contra": peso_contra, "niveles": niveles,
            "limites": limites(niveles, spot, sentido, w, tfs), "spot": spot, "atr": atr}


def fuertes(analisis: dict, tfs: list[str], spot: float, atr: float, w: dict) -> list[dict]:
    """Niveles agrupados (a < ½ ATR) con su fuerza y la temporalidad más alta que los respalda."""
    crudos = []
    for i, t in enumerate(tfs):
        for n in _niveles_tf(analisis[t], i + 1):
            n["tf"] = t
            crudos.append(n)
    crudos.sort(key=lambda n: n["precio"])
    grupos: list[list[dict]] = []
    for n in crudos:
        if grupos and n["precio"] - grupos[-1][-1]["precio"] <= 0.5 * atr:
            grupos[-1].append(n)
        else:
            grupos.append([n])
    out = []
    for g in grupos:
        f = sum(n["toques"] * n["rango"] for n in g if not n["vrvp"]) + (2 if any(n["vrvp"] for n in g) else 0)
        top = max(g, key=lambda n: n["rango"])
        precio = float(np.average([n["precio"] for n in g], weights=[n["toques"] * n["rango"] for n in g]))
        out.append({"precio": precio, "fuerza": f, "tf": top["tf"], "rango": top["rango"],
                    "peso_tf": w.get(top["tf"], 0.0), "vrvp": any(n["vrvp"] for n in g),
                    "tipo": "R" if precio > spot else "S", "tfs": sorted({n["tf"] for n in g}, key=tfs.index)})
    return out


def limites(niveles: list[dict], spot: float, sentido: int, w: dict, tfs: list[str]) -> dict:
    """Objetivo e invalidación con los niveles de las temporalidades dominantes para el horizonte; entrada con los
    de la operativa; y el siguiente nivel de una temporalidad mayor como «segundo nivel»."""
    dom = {t for t, p in w.items() if p >= 0.25} or {max(w, key=w.get)}
    fav = [n for n in niveles if (n["precio"] > spot if sentido > 0 else n["precio"] < spot) and n["fuerza"] >= 2]
    opu = [n for n in niveles if (n["precio"] < spot if sentido > 0 else n["precio"] > spot) and n["fuerza"] >= 2]
    key = (lambda n: n["precio"]) if sentido > 0 else (lambda n: -n["precio"])
    key_o = (lambda n: -n["precio"]) if sentido > 0 else (lambda n: n["precio"])
    fav_dom = sorted([n for n in fav if any(t in dom for t in n["tfs"])], key=key)
    opu_dom = sorted([n for n in opu if any(t in dom for t in n["tfs"])], key=key_o)
    mayor = tfs[-1]
    seg = sorted([n for n in fav if mayor in n["tfs"]], key=key)
    ent = sorted([n for n in opu if tfs[0] in n["tfs"]], key=key_o)
    entrada = ent[0] if ent else None
    # la invalidación es un nivel más allá de la entrada (perderla confirma que el escenario falló)
    inv = next((n for n in opu_dom if not entrada or abs(n["precio"] - entrada["precio"]) > 1e-9), None)
    return {"objetivo": fav_dom[0] if fav_dom else None, "invalidacion": inv,
            "segundo_nivel": seg[0] if seg and (not fav_dom or seg[0]["precio"] != fav_dom[0]["precio"]) else None,
            "entrada": entrada, "dominantes": sorted(dom, key=tfs.index)}


def etiqueta(n: dict | None) -> str:
    return "—" if not n else f"{n['tipo']} {n['tf']} ${n['precio']:,.2f}"


def confianza_ajustada(conf: float | None, sentido_plan: int, R: dict) -> float | None:
    """Ajuste de ±10 puntos máximo: suma si el puntaje multi-temporalidad respalda la dirección del plan (en la
    medida de su alineación) y resta si la contradice."""
    if conf is None:
        return None
    a = R["alineacion"]
    s = 1 if R["puntaje"] >= 0 else -1
    return float(np.clip(conf + (10 * a if s == sentido_plan else -10 * a), 1, 99))


def resumen_ia(R: dict) -> dict:
    """Bloque compacto para el JSON que recibe la IA."""
    L = R["limites"]
    return {"horizonte_dias": R["horizonte_dias"], "estado": R["estado"], "puntaje": round(R["puntaje"], 1),
            "puntaje_tecnico": round(R.get("puntaje_tecnico", R["puntaje"]), 1),
            "fundamental": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in (R.get("fundamental") or {}).items()},
            "alineacion": round(R["alineacion"], 2),
            "temporalidades": [{"tf": f["tf"], "rol": f["rol"], "peso": round(f["peso"], 2), "puntaje": round(f["puntaje"], 1),
                                "escenario": f["escenario"], "adx": f["adx"]} for f in R["filas"]],
            "objetivo": etiqueta(L["objetivo"]), "invalidacion": etiqueta(L["invalidacion"]),
            "segundo_nivel": etiqueta(L["segundo_nivel"]), "entrada": etiqueta(L["entrada"]),
            "regla": "pesos según el horizonte: corto → temporalidades menores; largo → mayores (las menores solo para la "
                     "entrada). Cada temporalidad aporta solo su puntaje técnico; el fundamental entra una vez, con peso "
                     "creciente con el horizonte (máx. 40 % a 6 meses)"}


def lineas_grafico(R: dict, evitar: list[float] | None = None) -> list[dict]:
    """Niveles a dibujar: objetivo, invalidación y segundo nivel (con la temporalidad que los respalda). Se omiten los
    que coinciden (±0.3 ATR) con niveles que el gráfico ya marca, como la entrada o el stop del plan."""
    L, out = R["limites"], []
    tol = 0.3 * R.get("atr", 0)
    for clave, rol in (("objetivo", "Objetivo MTF"), ("invalidacion", "Invalidación MTF"), ("segundo_nivel", "2.º nivel")):
        n = L.get(clave)
        if n and not any(abs(n["precio"] - v) <= tol for v in (evitar or []) if v):
            out.append({"precio": n["precio"], "texto": f"{rol} · {n['tipo']} {n['tf']} {n['precio']:,.2f}", "rol": clave})
    return out


def tarjeta_html(R: dict, conf_base: float | None = None, conf_aj: float | None = None) -> str:
    """Tarjeta «Multi-temporalidad» (HTML) para las vistas de análisis y opciones."""
    import html as _h
    E = _h.escape
    G, Rr, N = "#26A69A", "#EF5350", "#58A6FF"
    col = {"Alineado": G, "Lateral": N, "Mixto": N}.get(R["estado"], "#D29922")
    filas = "".join(
        f"<tr><td>{E(f['tf'])}</td><td>{E(f['rol'])}</td><td class='n'>{f['peso'] * 100:.0f}%</td>"
        f"<td class='n' style='color:{G if f['puntaje'] >= 15 else Rr if f['puntaje'] <= -15 else N}'>"
        f"{'▲' if f['puntaje'] >= 15 else '▼' if f['puntaje'] <= -15 else '◆'} {f['puntaje']:+.0f}</td>"
        f"<td class='n'>{'—' if f['adx'] is None else f['adx']}</td></tr>" for f in R["filas"])
    FU = R.get("fundamental") or {}
    if FU.get("puntaje") is not None:
        fp = float(FU["puntaje"])
        filas += (f"<tr><td>Fund.</td><td>Valor y calidad</td><td class='n'>{FU['peso'] * 100:.0f}%</td>"
                  f"<td class='n' style='color:{G if fp >= 15 else Rr if fp <= -15 else N}'>"
                  f"{'▲' if fp >= 15 else '▼' if fp <= -15 else '◆'} {fp:+.0f}</td><td class='n'>—</td></tr>")
    L = R["limites"]
    lim = "".join(
        f"<div class='x-dl2'><span>{E(t)}</span><b class='num'>{E(etiqueta(L.get(k)))}</b></div>"
        for k, t in (("objetivo", "Objetivo (temporalidades dominantes)"), ("invalidacion", "Invalidación"),
                     ("segundo_nivel", "Segundo nivel (temporalidad mayor)"), ("entrada", "Entrada fina (operativa)")))
    conf = (f"<div class='x-dl2'><span>Confianza ajustada por alineación</span><b class='num'>"
            f"{conf_base:.0f}% → {conf_aj:.0f}%</b></div>" if conf_base is not None and conf_aj is not None else "")
    return (f"<div class='x-plan'><div class='x-ph'><span>Multi-temporalidad</span>"
            f"<span class='x-badge' style='color:{col};border-color:{col}66;background:{col}14'>{E(R['estado'])}</span></div>"
            f"<div class='mp-s'>Horizonte {R['horizonte_dias']:g} días · pesos según el horizonte · puntaje técnico "
            f"<b class='num'>{R.get('puntaje_tecnico', R['puntaje']):+.0f}</b> · con fundamental "
            f"<b class='num'>{R['puntaje']:+.0f}</b> · alineación <b class='num'>{R['alineacion'] * 100:.0f}%</b></div>"
            f"<table class='x-mtf'><tr><th>TF</th><th>Rol</th><th>Peso</th><th>Puntaje</th><th>ADX</th></tr>{filas}</table>"
            f"{lim}{conf}</div>")
