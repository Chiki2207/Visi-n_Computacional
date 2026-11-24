"""Pruebas del respaldo del chat (Gemini simulado, sin internet ni clave real).
Correr:  python web/frontend/prueba_chat_llm.py     (la página no sirve este archivo)"""
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chat_llm  # noqa: E402

ok = mal = 0


def prueba(nombre, fn):
    global ok, mal
    try:
        asyncio.run(fn()) if asyncio.iscoroutinefunction(fn) else fn()
        ok += 1
        print("  ok   " + nombre)
    except Exception as e:  # noqa: BLE001
        mal += 1
        print(f"  MAL  {nombre}\n       {type(e).__name__}: {e}")


def con_falso(manejador):
    it = chat_llm.Interprete()
    it._cliente = httpx.AsyncClient(transport=httpx.MockTransport(manejador))
    return it


def respuesta(obj, status=200):
    return httpx.Response(status, json={"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]})


os.environ["GEMINI_API_KEY"] = "clave-de-prueba"
os.environ["GEMINI_MODELO"] = "gemini-2.5-flash-lite"


async def sin_clave():
    os.environ.pop("GEMINI_API_KEY")
    try:
        r = await chat_llm.Interprete().interpretar("hola", [])
        assert r["motivo"] == "no_disponible" and r["ok"] is False
    finally:
        os.environ["GEMINI_API_KEY"] = "clave-de-prueba"


async def bien():
    vistos = []

    def h(req):
        vistos.append(json.loads(req.content))
        assert req.headers["x-goog-api-key"] == "clave-de-prueba"
        return respuesta({"accion": "presente", "nombres": ["Luis Enrique Avendaño Ortiz"], "confianza": 0.9})

    it = con_falso(h)
    r = await it.interpretar("el Luis Enrique araña sí llegó", ["Luis Enrique Avendaño Ortiz", "Ana Pérez"])
    assert r["ok"] and r["accion"] == "presente" and r["nombres"] == ["Luis Enrique Avendaño Ortiz"], r
    g = vistos[0]["generationConfig"]
    assert g["thinkingConfig"] == {"thinkingBudget": 0} and g["responseMimeType"] == "application/json"
    r2 = await it.interpretar("el Luis Enrique araña sí llegó", ["Luis Enrique Avendaño Ortiz", "Ana Pérez"])
    assert r2.get("memoria") and len(vistos) == 1          # la misma frase otra vez: sin volver a Google


async def tarda():
    os.environ["GEMINI_TIMEOUT"] = "0.5"
    try:
        async def h(req):
            await asyncio.sleep(2)
            return respuesta({"accion": "ayuda", "nombres": [], "confianza": 1})

        r = await con_falso(h).interpretar("algo", [])
        assert r == {"ok": False, "accion": "no", "motivo": "tiempo"}, r
    finally:
        os.environ.pop("GEMINI_TIMEOUT")


async def error_google():
    r = await con_falso(lambda req: httpx.Response(403, json={"error": {}})).interpretar("algo", [])
    assert r["ok"] is False and r["motivo"] == "error"


async def basura():
    r = await con_falso(lambda req: httpx.Response(200, text="no es json")).interpretar("algo", [])
    assert r["ok"] is False


def validar():
    v = chat_llm.validar
    assert v({"accion": "borrar_todo", "nombres": [], "confianza": 1})["ok"] is False
    assert v({"accion": "quitar", "nombres": ["X"], "confianza": 0.2})["ok"] is False      # poca confianza
    assert v({"accion": "entrar", "nombres": [], "confianza": 0.9})["ok"] is False        # entrar sin destino
    r = v({"accion": "entrar", "nombres": [], "codigo": "48 21", "tipo": "ninguno", "confianza": 0.9})
    assert r["ok"] and r["codigo"] == "4821" and r["tipo"] == ""
    assert v("hola")["ok"] is False


def modelos():
    assert chat_llm._pensar("gemini-2.5-flash") == {"thinkingBudget": 0}
    assert chat_llm._pensar("gemini-3.5-flash-lite") == {"thinkingLevel": "minimal"}


print("Respaldo del chat (Gemini simulado):")
prueba("sin GEMINI_API_KEY: «no disponible» y no llama a nadie", sin_clave)
prueba("frase rara: orden válida, sin pensar, JSON, y memoria de frases repetidas", bien)
prueba("si Google tarda más que GEMINI_TIMEOUT: responde «tiempo» sin esperar más", tarda)
prueba("si Google da error (p. ej. 403): ok=false", error_google)
prueba("si Google responde basura: ok=false", basura)
prueba("solo pasan órdenes bien formadas y con confianza", validar)
prueba("apaga el «pensar» según el modelo", modelos)
print(f"\n{ok} bien, {mal} mal")
sys.exit(1 if mal else 0)
