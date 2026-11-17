"""Perfil táctico de opciones: cómo opera el usuario (clases de contrato, salida, meta, corte, días, apetito).

Reglas (en este orden de prioridad):
1. CLASES (ITM / ATM / OTM) — regla maestra. Solo se recomiendan contratos de las clases elegidas, también en el
   modo Default. Si ninguno cumple, el resultado es ESPERAR: nunca un contrato de otra clase.
2. LÍMITES FIJOS (no editables): una meta que exija más de 1.5σ o tenga menos de 15 % de probabilidad se bloquea.
3. APETITO: probabilidad mínima y σ máxima que el usuario acepta.

La clase se mide en σ de la propia acción: ATM = strike a menos de 1/8 de desviación típica del precio a plazo al
vencimiento (|ln(K/F)| ≤ 0.125·σ√T, ≈ delta 0.45–0.55); ITM / OTM a cada lado según el tipo. Si un vencimiento no tiene
ningún strike en esa franja, su strike más cercano cuenta como ATM. Así «OTM» significa lo mismo en SPY que en AMD.

Modo táctico (cierro antes, por ganancia): para cada contrato se simula el camino del precio en los días de
retención, con la theta de cada paso y la IV implícita en la prima, sin ventaja direccional (la dirección la da el
motor técnico). Se mide: precio necesario para la meta, σ y probabilidad de tocarla; probabilidad de llegar a la meta
antes que al corte; probabilidad de que el ruido toque el corte; valor si el precio se queda quieto; días hasta perder
20 % sin movimiento. Modo vencimiento: probabilidad de terminar sobre el breakeven.

Se guarda en technical_settings["opciones_perfil"] = {"*": perfil global, "AMD": perfil de AMD, …}.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from .options import TASA, Z_ATM, bs_price, clase_contrato, moneyness_z

CLASES = ("ITM", "ATM", "OTM")
DEFAULT = {"clases": ["ITM", "ATM", "OTM"], "estilo": "tactico", "meta": 50, "corte": 35, "dias": 5,
           "apetito": "equilibrado", "resultados": "evitar"}
APETITO = {"conservador": {"p": 45, "s": 0.8, "txt": "Muy probable"},
           "equilibrado": {"p": 35, "s": 1.0, "txt": "Equilibrado"},
           "agresivo": {"p": 25, "s": 1.3, "txt": "Acepto apuestas"}}
SIGMA_BLOQUEO, P_BLOQUEO = 1.5, 15.0  # límites fijos
N_SIM, SUB = 1500, 6


# ------------------------------------------------------------------ guardar / leer
def _todos(settings: dict) -> dict:
    return dict((settings or {}).get("opciones_perfil") or {})


def leer(settings: dict, ticker: str) -> tuple[dict | None, str | None]:
    """(perfil, alcance) con alcance 'ticker' o 'todas'; (None, None) si el usuario aún no eligió."""
    P = _todos(settings)
    t = (ticker or "").upper()
    if t in P:
        return normalizar(P[t]), "ticker"
    if "*" in P:
        return normalizar(P["*"]), "todas"
    return None, None


def guardar(settings: dict, ticker: str, perfil: dict, todas: bool) -> dict:
    """Devuelve los ajustes con el perfil guardado (para la acción o para todas). Guardar «para todas» borra el
    perfil propio de esa acción, para que se rija por el global."""
    S = copy.deepcopy(settings or {})
    P = _todos(S)
    p = normalizar(perfil)
    t = (ticker or "").upper()
    if todas:
        P["*"] = p
        P.pop(t, None)
    else:
        P[t] = p
    S["opciones_perfil"] = P
    return S


def normalizar(p: dict | None) -> dict:
    out = {**DEFAULT, **(p or {})}
    out["clases"] = [c for c in CLASES if c in (out.get("clases") or [])] or ["OTM"]
    out["meta"] = int(out["meta"])
    out["corte"] = int(out["corte"])
    out["dias"] = int(min(max(int(out["dias"]), 1), 15))
    if out["apetito"] not in APETITO:
        out["apetito"] = "equilibrado"
    if out["estilo"] not in ("tactico", "vencimiento"):
        out["estilo"] = "tactico"
    return out


def resumen(p: dict) -> list[str]:
    """Etiquetas cortas del perfil para la columna izquierda."""
    cl = p["clases"]
    out = ["Solo " + cl[0] if len(cl) == 1 else " + ".join(cl)]
    if p["estilo"] == "tactico":
        out += ["Cierro antes", f"+{p['meta']} %", f"−{p['corte']} %" if p["corte"] else "sin corte", f"{p['dias']} ses."]
    else:
        out += ["Al vencimiento"]
    out.append(APETITO[p["apetito"]]["txt"])
    return out


def dte_minimo(p: dict) -> int:
    return max(2 * round(p["dias"] * 7 / 5), 7) if p["estilo"] == "tactico" else 1


# ------------------------------------------------------------------ clase de un contrato
def clase(e: dict, spot: float) -> str:
    """ITM / ATM / OTM del contrato evaluado `e` (strike, tipo, iv en %, dte), medido en σ de la acción."""
    return clase_contrato(e["strike"], spot, e["tipo"], max(e["iv"] / 100, 0.01), e["dte"])


def _clases(evs: list[dict], spot: float) -> list[str]:
    """Clase de cada contrato; un vencimiento sin strike ATM toma como ATM al más cercano en σ."""
    cl = [clase(e, spot) for e in evs]
    por_venc: dict = {}
    for i, e in enumerate(evs):
        por_venc.setdefault((e.get("exp_iso"), e["tipo"]), []).append(i)
    for idx in por_venc.values():
        if not any(cl[i] == "ATM" for i in idx):
            j = min(idx, key=lambda i: abs(moneyness_z(evs[i]["strike"], spot, max(evs[i]["iv"] / 100, 0.01),
                                                         evs[i]["dte"])))
            if abs(moneyness_z(evs[j]["strike"], spot, max(evs[j]["iv"] / 100, 0.01), evs[j]["dte"])) <= 2 * Z_ATM:
                cl[j] = "ATM"
    return cl


# ------------------------------------------------------------------ evaluación táctica
def _nivel(K, T, iv, call, objetivo, spot):
    lo, hi = spot * 0.2, spot * 3.0
    for _ in range(70):
        m = (lo + hi) / 2
        v = bs_price(m, K, T, iv, call)
        if (v < objetivo) == call:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def evaluar(e: dict, spot: float, p: dict, z: np.ndarray | None = None) -> dict:
    """Métricas tácticas de un contrato evaluado por options.evaluar (usa strike, tipo, prima, iv %, dte)."""
    call = e["tipo"] == "CALL"
    K, prima, iv, dte = e["strike"], e["prima"], max(e["iv"] / 100, 0.05), max(e["dte"], 1)
    out: dict = {}
    if p["estilo"] == "vencimiento":
        be = e["breakeven"]
        T = dte / 365
        zv = abs(math.log(be / spot)) / (iv * math.sqrt(T))
        out.update(P=float(e["pop"]), z=float(zv), modo="vencimiento", be=float(be))
        return out
    cal = round(p["dias"] * 7 / 5)
    T = max(dte - cal, 0.5) / 365
    s_meta = _nivel(K, T, iv, call, prima * (1 + p["meta"] / 100), spot)
    sig = iv * math.sqrt(p["dias"] / 252)
    zm = abs(math.log(s_meta / spot)) / sig
    p_toca = max(0.0, min(1.0, 2 * (1 - _ncdf(zm)))) * 100
    s_corte = _nivel(K, T, iv, call, prima * (1 - p["corte"] / 100), spot) if p["corte"] else None
    quieto = bs_price(spot, K, T, iv, call) / prima - 1
    dia20 = next((d for d in range(1, dte) if bs_price(spot, K, (dte - d) / 365, iv, call) <= 0.8 * prima), None)
    out.update(modo="tactico", s_meta=float(s_meta), mov_meta=float((s_meta / spot - 1) * 100), z=float(zm),
               P=float(p_toca), s_corte=None if s_corte is None else float(s_corte),
               mov_corte=None if s_corte is None else float((s_corte / spot - 1) * 100),
               quieto=float(quieto * 100), resiste=dia20)
    if z is not None:
        out.update(simular(e, spot, p, z))
    return out


def ruido_normal(n: int = N_SIM, pasos: int = 15 * SUB, seed: int = 7) -> np.ndarray:
    """Números aleatorios comunes a todos los contratos (comparaciones justas y resultados estables)."""
    return np.random.default_rng(seed).standard_normal((n, pasos))


def simular(e: dict, spot: float, p: dict, z: np.ndarray) -> dict:
    """Trayectorias sin tendencia con límite de días: % que toca la meta antes que el corte, % que toca el corte
    (el ruido te saca) y % que no toca ninguno. Meta y corte se miden sobre el valor Black-Scholes de la prima."""
    call = e["tipo"] == "CALL"
    K, prima, iv, dte = e["strike"], e["prima"], max(e["iv"] / 100, 0.05), max(e["dte"], 1)
    pasos = p["dias"] * SUB
    dt = 1 / 252 / SUB
    S = spot * np.exp(np.cumsum(-0.5 * iv * iv * dt + iv * math.sqrt(dt) * z[:, :pasos], axis=1))
    T = np.maximum(dte / 365 - (7 / 5) / SUB / 365 * np.arange(1, pasos + 1), 1e-6)
    sq = iv * np.sqrt(T)
    from scipy.stats import norm
    d1 = (np.log(S / K) + (TASA + 0.5 * iv * iv) * T) / sq
    d2 = d1 - sq
    if call:
        v = S * norm.cdf(d1) - K * np.exp(-TASA * T) * norm.cdf(d2)
    else:
        v = K * np.exp(-TASA * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    r = v / prima - 1
    hit_m = r >= p["meta"] / 100
    hit_c = (r <= -p["corte"] / 100) if p["corte"] else np.zeros_like(hit_m)
    big = pasos + 1
    im = np.where(hit_m.any(1), hit_m.argmax(1), big)
    ic = np.where(hit_c.any(1), hit_c.argmax(1), big)
    n = len(im)
    meta = float((im < ic).sum() / n * 100)
    corte = float((ic < im).sum() / n * 100)
    return {"meta_antes": meta, "ruido_corte": corte, "ninguno": 100 - meta - corte}


def clasificar(t: dict, p: dict) -> tuple[str, str]:
    """(estado, motivo) de un contrato según los límites fijos y el apetito: ok / bloqueado / apetito."""
    ap = APETITO[p["apetito"]]
    if t["z"] > SIGMA_BLOQUEO or t["P"] < P_BLOQUEO:
        return "bloqueado", f"{t['z']:.2f}σ · {t['P']:.0f} % (límite fijo: 1.5σ / 15 %)"
    if t["z"] > ap["s"] or t["P"] < ap["p"]:
        return "apetito", f"{t['P']:.0f} % y {t['z']:.2f}σ (tu perfil: ≥ {ap['p']} % y ≤ {ap['s']}σ)"
    return "ok", ""


def veredicto(t: dict | None, p: dict) -> str:
    if not t:
        return "ESPERAR"
    ap = APETITO[p["apetito"]]
    if t.get("modo") == "tactico" and p["corte"] and t.get("ruido_corte", 0) >= 50:
        return "EXIGENTE"
    return "EXIGENTE" if t["P"] < ap["p"] + 10 else "VIABLE"


def avisos(t: dict, p: dict, e: dict, spot: float) -> list[str]:
    """Advertencias tácticas del contrato elegido."""
    out = []
    if t.get("modo") == "tactico":
        if p["corte"] and t.get("ruido_corte") is not None:
            if t["ruido_corte"] >= 50:
                out.append(f"Tu corte de −{p['corte']} % de la prima equivale a {t['mov_corte']:+.1f} % del precio "
                           f"(${t['s_corte']:,.2f}): con la volatilidad actual el ruido normal lo toca en "
                           f"{t['ruido_corte']:.0f} % de los casos aunque la dirección sea correcta.")
            elif t["ruido_corte"] >= 35:
                out.append(f"El ruido normal toca tu corte en {t['ruido_corte']:.0f} % de los casos: corte ajustado "
                           "para esta volatilidad.")
        if not p["corte"]:
            out.append("Sin corte de pérdida puedes perder la prima entera si el precio se estanca o retrocede.")
        if t["quieto"] <= -15:
            out.append(f"Si el precio se queda quieto {p['dias']} {'sesión' if p['dias'] == 1 else 'sesiones'}, la prima "
                       f"pierde {abs(t['quieto']):.0f} % solo por theta.")
        if e["dte"] < dte_minimo(p):
            out.append(f"Con {p['dias']} {'sesión' if p['dias'] == 1 else 'sesiones'} de retención conviene un vencimiento de ≥ {dte_minimo(p)} días; "
                       f"este vence en {e['dte']}: la theta se acelera dentro de tu ventana.")
    elif p["clases"] == ["OTM"]:
        out.append(f"Solo OTM esperando al vencimiento: la probabilidad de terminar con ganancia es baja "
                   f"({t['P']:.0f} %). La salida anticipada encaja mejor con OTM.")
    return out


def marcar_clases(evs: list[dict], spot: float) -> list[dict]:
    """Solo la clase de cada contrato (modo Default y lado contrario): sin métricas tácticas."""
    return [{**e, "clase": c} for e, c in zip(evs, _clases(evs, spot))]


def motivos(evs: list[dict], money, ventana: int, tier: int, spot: float) -> dict:
    """Cuántos contratos del nivel se descartaron y por qué (para explicar un ESPERAR)."""
    from .options import rango_tier
    lo, hi = rango_tier(ventana, tier)
    out: dict = {}
    for e in evs:
        if lo <= e["dte"] <= hi and e.get("spread_pct", 99) <= 25:
            k = e.get("tac_estado") or "ok"
            out[k] = out.get(k, 0) + 1
    return out


def anotar(evs: list[dict], spot: float, p: dict, res_prox=None, max_sim: int = 40) -> list[dict]:
    """Añade a cada contrato `tac` (métricas), `tac_estado` y `tac_motivo`. Excluye por clase y por resultados
    (si el perfil los evita). Simula solo los `max_sim` mejores por probabilidad de tocar la meta."""
    from datetime import date
    out = []
    for e, cl in zip(evs, _clases(evs, spot)):
        e = dict(e)
        e["clase"] = cl
        if e["clase"] not in p["clases"]:
            e["tac_estado"], e["tac_motivo"] = "fuera", f"{e['clase']} fuera de tus clases"
        elif p["resultados"] == "evitar" and res_prox and e.get("exp_iso") and res_prox <= date.fromisoformat(e["exp_iso"]):
            e["tac_estado"], e["tac_motivo"] = "resultados", "cruza la publicación de resultados"
        else:
            e["tac"] = evaluar(e, spot, p)
            e["tac_estado"], e["tac_motivo"] = clasificar(e["tac"], p)
        out.append(e)
    if p["estilo"] == "tactico":
        z = ruido_normal()
        cand = sorted([e for e in out if e.get("tac") and e["tac_estado"] in ("ok", "apetito")],
                      key=lambda e: -e["tac"]["P"])[:max_sim]
        for e in cand:
            e["tac"].update(simular(e, spot, p, z))
        # los no simulados no compiten: compararlos por «tocar la meta» frente a «meta antes que el corte»
        # favorecería siempre a los que no se simularon
        ids = {id(e) for e in cand}
        for e in out:
            if e.get("tac_estado") in ("ok", "apetito") and id(e) not in ids:
                e["tac_estado"], e["tac_motivo"] = "descartado", "menor probabilidad de tocar la meta que los evaluados"
    return out


def orden(e: dict) -> tuple:
    """Clave de orden del modo táctico: más probabilidad de llegar a la meta antes que al corte, luego menos spread."""
    t = e.get("tac") or {}
    return (-t.get("meta_antes", 0), e.get("spread_pct", 99))
