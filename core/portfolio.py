"""Portafolio simulado: operaciones registradas desde el Plan de ejecución (sin bróker, sin dinero real).

Se guarda en los ajustes del usuario (technical_settings["portafolio"]["ops"]), en Supabase o en la config
local, igual que las configuraciones de indicadores. El estado se evalúa con velas diarias desde el registro:
una entrada Limit se llena cuando el precio toca la entrada; luego gana el primer nivel tocado (stop o TP).
"""
import copy
import uuid
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from . import profiles

MAX_OPS = 200


def _settings() -> dict:
    return profiles.merge_settings(st.session_state.get("technical_settings"))


def ops() -> list[dict]:
    return list((_settings().get("portafolio") or {}).get("ops") or [])


def _save(lst: list[dict]) -> None:
    S = _settings()
    S["portafolio"] = {"ops": lst[-MAX_OPS:]}
    profiles.save_user_view(settings=S)


def registrar(ticker: str, plan: dict, tf: str, precio: float) -> dict:
    """Registra la operación del plan activo. Devuelve la operación guardada."""
    op = {
        "id": uuid.uuid4().hex[:10],
        "ticker": ticker,
        "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tf": tf,
        "largo": "COMPRA" in str(plan.get("direccion", "")).upper(),
        "modo": plan.get("modo_entrada", "market"),
        "entrada": float(plan["entrada"]),
        "precio_registro": float(precio),
        "stop": float(plan["stop"]),
        "tp1": float(plan["objetivo_1"]),
        "tp2": float(plan["objetivo_2"]),
        "acciones": float(plan.get("acciones") or 0),
        "riesgo": float(plan.get("riesgo_monetario") or 0),
        "cierre": None,
        "fecha_cierre": None,
    }
    _save(ops() + [op])
    return op


def cerrar(op_id: str, precio: float) -> None:
    lst = ops()
    for o in lst:
        if o["id"] == op_id and o.get("cierre") is None:
            o["cierre"] = float(precio)
            o["fecha_cierre"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save(lst)


def eliminar(op_id: str) -> None:
    _save([o for o in ops() if o["id"] != op_id])


def evaluar(op: dict, df: pd.DataFrame | None) -> dict:
    """Estado y resultado de una operación con las velas diarias desde su registro."""
    o = copy.deepcopy(op)
    s = 1 if o["largo"] else -1
    last = float(df["Close"].iloc[-1]) if df is not None and len(df) else o["precio_registro"]
    o["ultimo"] = last
    if o.get("cierre") is not None:
        o["estado"], salida = "Cerrada (manual)", o["cierre"]
    else:
        estado, salida, lleno, tp1 = "Pendiente", None, o["modo"] != "limit", False
        if df is not None and len(df):
            t0 = pd.Timestamp(o["fecha"]).tz_convert(None).normalize() if pd.Timestamp(o["fecha"]).tzinfo else \
                pd.Timestamp(o["fecha"]).normalize()
            idx = df.index.tz_localize(None) if getattr(df.index, "tz", None) else df.index
            barras = df[idx >= t0]
            for _, b in barras.iterrows():
                hi, lo = float(b["High"]), float(b["Low"])
                if not lleno:
                    if (lo <= o["entrada"]) if o["largo"] else (hi >= o["entrada"]):
                        lleno = True
                    else:
                        continue
                toca_stop = (lo <= o["stop"]) if o["largo"] else (hi >= o["stop"])
                toca_tp2 = (hi >= o["tp2"]) if o["largo"] else (lo <= o["tp2"])
                toca_tp1 = (hi >= o["tp1"]) if o["largo"] else (lo <= o["tp1"])
                if toca_stop:  # si en la misma vela tocó stop y objetivo, se asume lo peor
                    estado, salida = ("Stop tras TP1" if tp1 else "Cerrada (stop)"), o["stop"]
                    break
                if toca_tp2:
                    estado, salida = "Cerrada (TP2)", o["tp2"]
                    break
                if toca_tp1:
                    tp1 = True
            else:
                estado = ("TP1 alcanzado" if tp1 else "Abierta") if lleno else "Pendiente"
        o["estado"] = estado
    abierta = salida is None and o["estado"] != "Pendiente"
    ref = salida if salida is not None else (last if abierta else None)
    o["resultado"] = None if ref is None else (ref - o["entrada"]) * s * o["acciones"]
    o["resultado_R"] = None if ref is None or not o["riesgo"] else o["resultado"] / o["riesgo"]
    o["abierta"] = abierta or o["estado"] == "Pendiente"
    return o
