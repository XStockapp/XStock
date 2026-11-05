"""Orquesta el análisis completo de una acción."""
from __future__ import annotations

from . import data
from . import fundamental as F
from . import probability as P
from .levels import trade_plan
from .technical import compute_all, explain_last, score_series


def full_analysis(ticker: str, tp=3.0, sl=1.5, horizon=20, account=10_000.0, risk_pct=1.0,
                  av_key: str | None = None, provider: str = "yahoo") -> dict:
    raw = data.history(ticker, "5y", provider, av_key or "")
    d = compute_all(raw)
    s = score_series(d)
    tech = explain_last(d)
    cur = tech["score"]
    direction = "long" if cur >= -20 else "short"

    out_l = P.barrier_outcomes(d, tp, sl, horizon, direction)
    sc = s if direction == "long" else -s
    cs = P.conditional_stats(sc, out_l, cur if direction == "long" else -cur, P.DEFAULTS["band"])
    p = P.shrunk_probability(cs["wins"], cs["n"], cs["base_rate"], P.DEFAULTS["prior_strength"])
    prob = {
        "direccion": direction,
        "probabilidad": p,
        "valor_esperado_R": P.expected_R(p, tp, sl),
        "casos_similares": cs["n"],
        "tasa_base_accion": cs["base_rate"],
        "R_promedio_similares": cs["avg_R"],
        "dias_promedio_salida": cs["dias_prom"],
        "parametros": f"Objetivo {tp}×ATR, stop {sl}×ATR, horizonte {horizon} sesiones",
    }
    bt = P.backtest_signal(d, s, 40.0, tp, sl, horizon, direction)

    info = data.info(ticker, av_key, provider)
    fv = {"snapshot": {}, "info": {}, "extras": {}, "ratings": [], "news": [], "signals": []}
    if not data._demo():
        try:
            from .finviz import bundle
            fv = bundle(ticker)
        except Exception:
            pass
    # Finviz completa los datos que falten en Yahoo / Alpha Vantage
    for k, v in fv["info"].items():
        if v is not None and info.get(k) is None:
            info[k] = v
    metrics = F.extract_metrics(info)
    fscore = F.score_fundamentals(metrics)
    pio = F.piotroski(*data.statements(ticker))
    plan = trade_plan(d, direction, sl, tp, account, risk_pct)
    news = data.news(ticker, av_key=av_key or "")
    seen = {n["titulo"] for n in news}
    news += [n for n in fv["news"] if n["titulo"] not in seen][: max(0, 12 - len(news))]
    comb = 0.6 * cur + 0.4 * (fscore["score"] if fscore["score"] is not None else 0)
    return {"ticker": ticker, "df": d, "tech": tech, "prob": prob, "bt": bt, "metrics": metrics,
            "fscore": fscore, "piotroski": pio, "plan": plan, "news": news, "combinado": comb,
            "finviz": fv}
