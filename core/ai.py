"""
Síntesis con IA (Claude vía API de Anthropic). Recibe la evidencia cuantitativa
(técnico, fundamental, probabilidad histórica, backtest, plan, noticias) y devuelve
un veredicto estructurado. Si no hay API key, se usa una síntesis por reglas.
"""
from __future__ import annotations

import json
import math
import re

MODELOS = {
    "Claude Sonnet 5.5 (rápido)": "claude-sonnet-5-5",
    "Claude Opus 5.5 (máxima calidad)": "claude-opus-5-5",
    "Claude Haiku 5.5 (económico)": "claude-haiku-5-5",
}

SYSTEM = """Eres un analista cuantitativo y trader profesional de acciones de EE.UU. con 20 años de experiencia.
Tu trabajo es emitir una evaluación OBJETIVA basada solo en la evidencia entregada (no inventes datos).
Reglas:
- Pondera: tendencia y momento técnico, probabilidad histórica (triple barrera) y backtest, calidad y valoración fundamental, noticias,
  y los datos de Finviz (short float, propiedad/transacciones de insiders e institucionales, cambios de rating, fecha de resultados).
- Si hay resultados (earnings) dentro del horizonte de la operación, menciónalo como riesgo de gap.
- La probabilidad histórica es tu ancla principal; solo ajústala ±10 puntos con justificación explícita.
- Si la evidencia es contradictoria o débil, dilo y recomienda ESPERAR.
- Los niveles de entrada/stop/objetivos propuestos vienen del ATR y soportes/resistencias; respétalos salvo razón técnica clara.
- Relación riesgo/beneficio mínima aceptable 1.5:1.
- Responde en español, SOLO con un JSON válido con esta forma:
{"veredicto": "COMPRAR" | "ESPERAR" | "EVITAR" | "VENDER EN CORTO",
 "confianza": 0-100,
 "probabilidad_ajustada": 0-1,
 "horizonte": "texto (p.ej. 2-4 semanas)",
 "entrada": número, "stop": número, "objetivo_1": número, "objetivo_2": número,
 "tesis": "3-5 frases",
 "factores_a_favor": ["..."], "riesgos": ["..."],
 "invalidacion": "qué evento/precio invalida la tesis",
 "catalizadores": ["..."]}"""


def _clean(o):
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 4)
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def build_payload(ticker, tech, fund_metrics, fund_score, pio, prob, bt, plan, news, finviz=None) -> dict:
    finviz = finviz or {}
    return _clean({
        "ticker": ticker,
        "tecnico": {"score": tech["score"], "señales": tech["señales"]},
        "fundamental": {"score": fund_score.get("score") if fund_score else None,
                        "bloques": fund_score.get("bloques") if fund_score else None,
                        "metricas": fund_metrics, "piotroski": pio},
        "probabilidad_historica": prob,
        "backtest_senal": {k: v for k, v in (bt or {}).items() if k != "trades"},
        "plan_propuesto": {k: v for k, v in plan.items() if k not in ("fibonacci",)},
        "fibonacci": plan.get("fibonacci"),
        "noticias_recientes": [n["titulo"] for n in (news or [])],
        "finviz": {"metricas_extra": finviz.get("extras"), "senales": finviz.get("signals"),
                   "cambios_rating_analistas": finviz.get("ratings")},
    })


def analyze(payload: dict, api_key: str, model: str = "claude-sonnet-5-5") -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": "Evidencia (JSON):\n" + json.dumps(payload, ensure_ascii=False)}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("La IA no devolvió JSON: " + text[:300])
    out = json.loads(m.group(0))
    out["_modelo"] = model
    return out


def rule_based(payload: dict) -> dict:
    """Síntesis determinista cuando no hay IA disponible."""
    t = payload["tecnico"]["score"] or 0
    f = payload["fundamental"]["score"]
    p = payload["probabilidad_historica"]["probabilidad"]
    ev = payload["probabilidad_historica"]["valor_esperado_R"]
    plan = payload["plan_propuesto"]
    comb = 0.6 * t + 0.4 * (f if f is not None else 0)
    if ev > 0.2 and comb > 20:
        v = "COMPRAR"
    elif comb < -30 and ev < 0:
        v = "EVITAR"
    else:
        v = "ESPERAR"
    favor = [s["Indicador"] + ": " + s["Lectura"] for s in payload["tecnico"]["señales"] if s["Señal"] > 0.3][:5]
    contra = [s["Indicador"] + ": " + s["Lectura"] for s in payload["tecnico"]["señales"] if s["Señal"] < -0.3][:5]
    return {
        "veredicto": v,
        "confianza": int(min(90, abs(comb) * 0.6 + abs(ev) * 30)),
        "probabilidad_ajustada": p,
        "horizonte": "hasta 20 sesiones",
        "entrada": plan["entrada"], "stop": plan["stop"],
        "objetivo_1": plan["objetivo_1"], "objetivo_2": plan["objetivo_2"],
        "tesis": f"Puntaje combinado {comb:.0f}/100 (técnico {t:.0f}, fundamental {f if f is not None else 'n/d'}). "
                 f"Históricamente, configuraciones similares alcanzaron el objetivo antes que el stop "
                 f"{p*100:.0f}% de las veces (valor esperado {ev:+.2f}R).",
        "factores_a_favor": favor, "riesgos": contra,
        "invalidacion": f"Cierre por debajo de {plan['stop']:.2f}",
        "catalizadores": [],
        "_modelo": "reglas (sin IA)",
    }
