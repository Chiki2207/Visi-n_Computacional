"""Respaldo del chat con Gemini: SOLO interpreta frases que las reglas del asistente no entendieron.

No toca el reconocimiento de caras ni ningún dato. Recibe la frase y los nombres de la clase abierta
(para corregir nombres mal oídos) y devuelve una orden del MISMO tipo que las reglas
(entrar, presente, ausente, quitar, agregar, pasar, ayuda, no). La página la ejecuta con lo de siempre
(los nombres vuelven a pasar por el buscador aproximado y eliminar sigue pidiendo «sí / no»).

Variables en web/.env (si falta la clave, el chat queda exactamente como sin respaldo):
  GEMINI_API_KEY   clave de Google AI Studio (solo en el servidor; nunca en el código ni en git)
  GEMINI_MODELO    modelo (por defecto gemini-2.5-flash-lite)
  GEMINI_TIMEOUT   segundos máximos de espera (por defecto 2.5); si se pasa, el chat responde como antes
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict

import httpx

log = logging.getLogger("web.chat_llm")

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
ACCIONES = ["entrar", "presente", "ausente", "quitar", "agregar", "pasar", "ayuda", "no"]
MAX_NOMBRES = 400          # nombres de la clase que se mandan (solo para comparar)
MAX_TEXTO = 300
CONFIANZA_MIN = 0.5

SISTEMA = (
    "Interpretas órdenes cortas en español de Colombia para un chat de asistencia de una clase. "
    "Responde solo el JSON. Acciones: "
    "entrar = abrir una lista o clase (codigo de 4 cifras o destino con el nombre de la clase; tipo lista o clase); "
    "presente = marcar presentes; ausente = marcar ausentes o quitarles el presente; "
    "quitar = eliminar o borrar estudiantes de la clase; agregar = registrar un estudiante nuevo (un nombre); "
    "pasar = pasar o tomar asistencia; ayuda = qué puede hacer el asistente; no = otra cosa o no está claro. "
    "En nombres pon a quién se refiere. Si la frase trae un nombre mal oído o mal escrito, "
    "pon el nombre completo de la lista de estudiantes que más se le parezca. "
    "Números de 4 cifras dichos en palabras van como cifras en codigo. "
    "confianza entre 0 y 1."
)

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "accion": {"type": "STRING", "enum": ACCIONES},
        "nombres": {"type": "ARRAY", "items": {"type": "STRING"}},
        "codigo": {"type": "STRING"},
        "destino": {"type": "STRING"},
        "tipo": {"type": "STRING", "enum": ["lista", "clase", "ninguno"]},
        "confianza": {"type": "NUMBER"},
    },
    "required": ["accion", "nombres", "confianza"],
    "propertyOrdering": ["accion", "nombres", "codigo", "destino", "tipo", "confianza"],
}

NO_DISPONIBLE = {"ok": False, "accion": "no", "motivo": "no_disponible"}


def _config() -> tuple[str, str, float]:
    clave = os.environ.get("GEMINI_API_KEY", "").strip()
    modelo = os.environ.get("GEMINI_MODELO", "").strip() or "gemini-2.5-flash-lite"
    try:
        tiempo = float(os.environ.get("GEMINI_TIMEOUT", "2.5"))
    except ValueError:
        tiempo = 2.5
    return clave, modelo, max(0.5, min(tiempo, 10.0))


def disponible() -> bool:
    return bool(_config()[0])


def _pensar(modelo: str) -> dict:
    """Sin «pensar»: es lo que más tarda. Cada familia lo apaga distinto."""
    m = modelo.lower()
    if m.startswith("gemini-2.5"):
        return {"thinkingBudget": 0}
    if m.startswith("gemini-3"):
        return {"thinkingLevel": "minimal"}
    return {}


def cuerpo(texto: str, nombres: list[str], modelo: str) -> dict:
    lista = "\n".join(nombres) if nombres else "(no hay clase abierta)"
    gen = {
        "temperature": 0,
        "maxOutputTokens": 160,
        "responseMimeType": "application/json",
        "responseSchema": ESQUEMA,
    }
    pensar = _pensar(modelo)
    if pensar:
        gen["thinkingConfig"] = pensar
    return {
        "systemInstruction": {"parts": [{"text": SISTEMA}]},
        "contents": [{"role": "user", "parts": [{"text": f"Estudiantes:\n{lista}\n\nFrase: {texto}"}]}],
        "generationConfig": gen,
    }


def _limpio(s: object, largo: int = 120) -> str:
    s = "".join(ch for ch in str(s or "") if unicodedata.category(ch)[0] != "C")
    return re.sub(r"\s+", " ", s).strip()[:largo]


def validar(datos: object) -> dict:
    """Solo pasa una orden bien formada; cualquier cosa rara queda como «no entendí»."""
    if not isinstance(datos, dict):
        return {"ok": False, "accion": "no", "motivo": "formato"}
    accion = datos.get("accion")
    if accion not in ACCIONES:
        return {"ok": False, "accion": "no", "motivo": "formato"}
    try:
        confianza = float(datos.get("confianza", 0))
    except (TypeError, ValueError):
        confianza = 0.0
    nombres = datos.get("nombres") or []
    if not isinstance(nombres, list):
        nombres = []
    nombres = [n for n in (_limpio(x) for x in nombres[:20]) if n]
    codigo = re.sub(r"\D", "", str(datos.get("codigo") or ""))
    codigo = codigo if len(codigo) == 4 else ""
    destino = _limpio(datos.get("destino"), 80)
    tipo = datos.get("tipo") if datos.get("tipo") in ("lista", "clase") else ""
    if accion == "no" or confianza < CONFIANZA_MIN:
        return {"ok": False, "accion": "no", "motivo": "no_entendio", "confianza": confianza}
    if accion == "entrar" and not (codigo or destino):
        return {"ok": False, "accion": "no", "motivo": "no_entendio", "confianza": confianza}
    return {"ok": True, "accion": accion, "nombres": nombres, "codigo": codigo, "destino": destino,
            "tipo": tipo, "confianza": round(confianza, 2)}


class Interprete:
    """Un cliente HTTP que se queda abierto (sin abrir conexión nueva en cada frase) y una memoria corta
    de frases repetidas."""

    def __init__(self) -> None:
        self._cliente: httpx.AsyncClient | None = None
        self._memo: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def _cli(self) -> httpx.AsyncClient:
        if self._cliente is None or self._cliente.is_closed:
            self._cliente = httpx.AsyncClient(
                http2=False,
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8, keepalive_expiry=120),
                headers={"Content-Type": "application/json"},
            )
        return self._cliente

    async def calentar(self) -> None:
        """Deja abierta la conexión con Google (TLS listo) para que la primera frase no espere."""
        clave, modelo, _t = _config()
        if not clave:
            return
        try:
            await self._cli().get(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}",
                                  headers={"x-goog-api-key": clave}, timeout=5)
        except httpx.HTTPError:
            pass

    async def cerrar(self) -> None:
        if self._cliente is not None:
            await self._cliente.aclose()
            self._cliente = None

    def _memo_get(self, k: str) -> dict | None:
        with self._lock:
            v = self._memo.get(k)
            if not v or v[0] < time.time():
                self._memo.pop(k, None)
                return None
            self._memo.move_to_end(k)
            return v[1]

    def _memo_put(self, k: str, r: dict) -> None:
        with self._lock:
            self._memo[k] = (time.time() + 600, r)
            while len(self._memo) > 300:
                self._memo.popitem(last=False)

    async def interpretar(self, texto: str, nombres: list[str]) -> dict:
        clave, modelo, tiempo = _config()
        if not clave:
            return dict(NO_DISPONIBLE)
        texto = _limpio(texto, MAX_TEXTO)
        if not texto:
            return {"ok": False, "accion": "no", "motivo": "vacio"}
        nombres = [n for n in (_limpio(x, 120) for x in (nombres or [])[:MAX_NOMBRES]) if n]
        k = hashlib.sha256(json.dumps([modelo, texto.lower(), nombres], ensure_ascii=False).encode()).hexdigest()
        hecho = self._memo_get(k)
        if hecho is not None:
            return {**hecho, "memoria": True}
        t0 = time.perf_counter()
        try:
            # tope TOTAL (httpx solo pone tope a cada paso): pase lo que pase, a los GEMINI_TIMEOUT s se suelta
            r = await asyncio.wait_for(
                self._cli().post(URL.format(modelo=modelo), headers={"x-goog-api-key": clave},
                                 json=cuerpo(texto, nombres, modelo),
                                 timeout=httpx.Timeout(tiempo, connect=min(tiempo, 1.5))),
                timeout=tiempo)
            ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code != 200:
                log.warning("Gemini respondió %s en %s ms", r.status_code, ms)
                return {"ok": False, "accion": "no", "motivo": "error"}
            partes = r.json()["candidates"][0]["content"]["parts"]
            salida = validar(json.loads("".join(p.get("text", "") for p in partes)))
        except (httpx.TimeoutException, asyncio.TimeoutError):
            log.info("Gemini tardó más de %.1f s: el chat responde sin él", tiempo)
            return {"ok": False, "accion": "no", "motivo": "tiempo"}
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as ex:
            log.warning("Gemini no sirvió: %s", type(ex).__name__)
            return {"ok": False, "accion": "no", "motivo": "error"}
        salida["ms"] = ms
        self._memo_put(k, salida)
        return salida


interprete = Interprete()
