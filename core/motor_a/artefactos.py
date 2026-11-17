"""Guardar y leer el modelo y el reporte del Motor A.

Se guardan en disco (datos/motor_a/) y, si hay credenciales de Supabase, en Supabase Storage (bucket privado
«modelos»), que es de donde la app en producción los lee. El entrenamiento corre fuera de Render (GitHub Actions).
"""
from __future__ import annotations

import json
import os

import requests

from ..store import secret
from .dataset import CACHE_DIR

BUCKET = "modelos"
PREFIJO = "motor_a"
ARCHIVOS = ("reporte.json", "modelo.txt")


def _sb():
    url = (os.environ.get("SUPABASE_URL") or secret("SUPABASE_URL")).rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or secret("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return None, None
    h = {"apikey": key}
    if key.startswith("eyJ"):  # clave JWT antigua; las nuevas (sb_secret_…) van solo en apikey
        h["Authorization"] = f"Bearer {key}"
    return url, h


def nombre_reporte(objetivo: str, H: int) -> str:
    """El experimento principal (dirección a 10 sesiones) es «reporte.json»; los demás llevan sufijo."""
    return "reporte.json" if (objetivo, H) == ("direccion", 10) else f"reporte_{objetivo}_H{H}.json"


def guardar_local(reporte: dict, modelo_txt: str | None, nombre: str = "reporte.json") -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / nombre).write_text(json.dumps(reporte, ensure_ascii=False, indent=1, default=float))
    if modelo_txt:
        (CACHE_DIR / "modelo.txt").write_text(modelo_txt)


def subir(reporte: dict, modelo_txt: str | None, nombre: str = "reporte.json") -> bool:
    url, h = _sb()
    if not url:
        return False
    requests.post(f"{url}/storage/v1/bucket", headers=h, json={"id": BUCKET, "name": BUCKET, "public": False},
                  timeout=30)  # ya existe → 400/409, no importa
    datos = {nombre: (json.dumps(reporte, ensure_ascii=False, default=float).encode(), "application/json")}
    if modelo_txt:
        datos["modelo.txt"] = (modelo_txt.encode(), "text/plain")
    ok = True
    for nombre, (cuerpo, tipo) in datos.items():
        r = requests.post(f"{url}/storage/v1/object/{BUCKET}/{PREFIJO}/{nombre}", data=cuerpo, timeout=120,
                          headers={**h, "Content-Type": tipo, "x-upsert": "true"})
        ok = ok and r.status_code < 300
    return ok


def listar() -> list[str]:
    """Nombres de los reportes disponibles (reporte.json primero)."""
    nombres = set()
    url, h = _sb()
    if url:
        try:
            r = requests.post(f"{url}/storage/v1/object/list/{BUCKET}", headers=h, timeout=20,
                              json={"prefix": PREFIJO + "/", "limit": 100})
            if r.status_code == 200:
                nombres |= {x["name"] for x in r.json() if x.get("name", "").startswith("reporte")}
        except Exception:
            pass
    if CACHE_DIR.exists():
        nombres |= {p.name for p in CACHE_DIR.glob("reporte*.json")}
    return sorted(nombres, key=lambda n: (n != "reporte.json", n))


def leer_reporte(nombre: str = "reporte.json") -> dict | None:
    """Reporte más reciente: primero Supabase Storage, si no el disco local."""
    url, h = _sb()
    if url:
        try:
            r = requests.get(f"{url}/storage/v1/object/{BUCKET}/{PREFIJO}/{nombre}", headers=h, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    p = CACHE_DIR / nombre
    return json.loads(p.read_text()) if p.exists() else None
