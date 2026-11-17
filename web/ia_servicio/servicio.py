"""
Servicio de IA (puerto 8001 por defecto).

El motor r19 tal cual, detrás de HTTP. No guarda nada: recibe fotos y huellas, devuelve resultados.
Solo lo llama el servidor web (clave IA_TOKEN en la cabecera X-IA-Token); no se publica a internet.

Usa las mismas funciones que la ventana de escritorio (app/asistencia_core.py):
  huella_de_selfie  → registro de una selfie
  quien_esta_y_quien_no + armar_lista → la lista (presente / «¿revisar?» / ausente)
así la web y la ventana dan el mismo resultado con la misma foto.

Arranque:  .venv\\Scripts\\python.exe web\\ia_servicio\\servicio.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]          # D:\Vision_Computacional_Final
WEB = RAIZ / "web"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _leer_env(ruta: Path) -> None:
    """Lee web/.env (NOMBRE=valor). Lo que ya esté en el entorno manda."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_leer_env(WEB / ".env")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

import ia  # noqa: E402,F401  (fija la versión r19 del motor)
from app.asistencia_core import (  # noqa: E402
    armar_lista,
    aviso_foto,
    es_revisar,
    huella_de_selfie,
    obtener_motor,
)
from ia import comparar  # noqa: E402
from ia import version as ia_version  # noqa: E402
from ia.leer_imagen import bytes_a_imagen  # noqa: E402

IA_TOKEN = os.environ.get("IA_TOKEN", "").strip()
IA_HOST = os.environ.get("IA_HOST", "127.0.0.1")
IA_PUERTO = int(os.environ.get("IA_PUERTO", "8001"))
IA_MAX_MB = float(os.environ.get("IA_MAX_MB", "40"))

# Los datos de la clase (huellas de todos los alumnos) llegan como campo de texto "datos" y, con
# muchos alumnos, pasan de 1 MB: el límite que Starlette pone por defecto a cada campo del formulario
# ("Part exceeded maximum size of 1024KB"). Se sube ese límite al mismo tamaño máximo de la foto.
from starlette.requests import Request as _Request  # noqa: E402

_form_original = _Request.form


def _form_sin_limite_1mb(self, *, max_files=1000, max_fields=1000, max_part_size=int(IA_MAX_MB * 1024 * 1024)):
    return _form_original(self, max_files=max_files, max_fields=max_fields, max_part_size=max_part_size)


_Request.form = _form_sin_limite_1mb
VISTA_SELFIE_PX = 640


def _version_huella() -> str:
    """Cambia si cambia cualquier cosa que pueda mover una huella: código de ia/, config r19 o modelos.
    El servidor web recuerda esta marca con cada huella y la vuelve a pedir si no coincide."""
    h = hashlib.sha256()
    h.update(ia_version.ARCHIVO.read_bytes())
    for p in sorted((RAIZ / "ia").glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    for p in sorted((RAIZ / "models").iterdir()):
        if p.is_file() and p.suffix.lower() in (".onnx", ".task", ".tflite"):   # solo modelos (no README)
            h.update(f"{p.name}:{p.stat().st_size}".encode())
    return f"{ia_version.NOMBRE}-{h.hexdigest()[:12]}"


VERSION_HUELLA = _version_huella()
_cerrojo = threading.Lock()
_log = logging.getLogger("ia_servicio")      # un trabajo a la vez: el motor usa toda la CPU


@asynccontextmanager
async def _vida(_app: FastAPI):
    if not IA_TOKEN:
        raise RuntimeError("Falta IA_TOKEN (web/.env): el servicio de IA no arranca sin clave.")
    obtener_motor()              # cargar modelos una vez, al arrancar
    yield


app = FastAPI(title="Asistencia · servicio de IA", version=VERSION_HUELLA, lifespan=_vida,
              docs_url=None, redoc_url=None, openapi_url=None)


def _exigir_clave(x_ia_token: str = Header(default="")) -> None:
    if not IA_TOKEN or not hmac.compare_digest(x_ia_token.encode(), IA_TOKEN.encode()):
        raise HTTPException(401, "Clave del servicio de IA inválida")


async def _leer(foto: UploadFile) -> bytes:
    datos = await foto.read(int(IA_MAX_MB * 1024 * 1024) + 1)
    if not datos:
        raise HTTPException(422, "El archivo está vacío")
    if len(datos) > IA_MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"La foto supera {IA_MAX_MB:g} MB")
    return datos


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _jpg(imagen: np.ndarray, calidad: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", imagen, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not ok:
        raise RuntimeError("No se pudo codificar la imagen")
    return buf.tobytes()


def _limpio(x: Any) -> Any:
    """numpy → tipos de JSON."""
    if isinstance(x, dict):
        return {str(k): _limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpio(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return x


@app.get("/salud")
def salud() -> dict:
    return {"ok": True, "version": ia_version.NOMBRE, "version_huella": VERSION_HUELLA,
            "ocupado": _cerrojo.locked()}


@app.post("/registro", dependencies=[Depends(_exigir_clave)])
async def registro(foto: UploadFile = File(...)) -> dict:
    """Selfie → huella (1536 números, float64 en base64), cara alineada (PNG) y vista para mostrar."""
    datos = await _leer(foto)
    t0 = time.perf_counter()
    def trabajo():
        with _cerrojo:
            motor = obtener_motor()
            reg = huella_de_selfie(motor, datos)
            # La huella de la cara en blanco y negro (caras lejanas, ver REALCE_GRIS): se saca aquí una vez
            # y la web la guarda con la normal, así pasar lista no la tiene que calcular.
            gris = comparar.huella_gris_registro(reg["cara"], motor.reconocedor_onnx) if comparar.REALCE_GRIS else None
            return reg, gris, bytes_a_imagen(datos)

    try:
        reg, gris, imagen = await run_in_threadpool(trabajo)
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    except Exception as ex:  # noqa: BLE001  (que el servidor web vea el motivo, no un 500 mudo)
        _log.exception("Falló /registro")
        raise HTTPException(500, f"Error de la IA: {type(ex).__name__}: {ex}") from ex
    ok, png = cv2.imencode(".png", reg["cara"])
    if not ok:
        raise HTTPException(500, "No se pudo guardar la cara alineada")
    alto, ancho = imagen.shape[:2]
    escala = min(1.0, VISTA_SELFIE_PX / max(alto, ancho))
    vista = cv2.resize(imagen, (round(ancho * escala), round(alto * escala)), interpolation=cv2.INTER_AREA) if escala < 1 else imagen
    huella = np.asarray(reg["embedding"], dtype="<f8")
    return {
        "version_huella": VERSION_HUELLA,
        "huella": _b64(huella.tobytes()),
        "dim": int(huella.size),
        "cara_png": _b64(png.tobytes()),
        "huella_gris": _b64(np.asarray(gris, dtype="<f8").tobytes()) if gris is not None else None,
        "caras_en_foto": reg["caras_en_foto"],
        "vista_jpg": _b64(_jpg(vista, 88)),
        "segundos": round(time.perf_counter() - t0, 2),
    }


@app.post("/pasar-lista", dependencies=[Depends(_exigir_clave)])
async def pasar_lista(foto: UploadFile = File(...), datos: str = Form(...)) -> dict:
    """Foto grupal + alumnos registrados → la lista, igual que la ventana.

    datos (JSON): {"alumnos": [{"id", "nombre", "huella", "cara_png", "huella_gris" (opcional), "version_huella"}],
                   "fallos": [{"id", "nombre", "motivo"}], "umbral": null}
    """
    foto_bytes = await _leer(foto)
    try:
        pedido = json.loads(datos)
    except json.JSONDecodeError as ex:
        raise HTTPException(422, "datos no es JSON") from ex
    personas, estudiantes = [], []
    for a in pedido.get("alumnos") or []:
        if a.get("version_huella") != VERSION_HUELLA:
            raise HTTPException(409, f"La huella de {a.get('nombre')} es de otra versión del motor: hay que registrarla de nuevo")
        emb = np.frombuffer(base64.b64decode(a["huella"]), dtype="<f8").tolist()
        cara = cv2.imdecode(np.frombuffer(base64.b64decode(a["cara_png"]), np.uint8), cv2.IMREAD_UNCHANGED)
        if cara is None or len(emb) != 1536:
            raise HTTPException(422, f"Registro dañado de {a.get('nombre')}")
        persona = {"id": str(a["id"]), "name": a["nombre"], "embeddings": [emb], "cara": cara}
        if a.get("huella_gris"):  # sin ella (o dañada) el motor la calcula de la cara: mismo resultado, más lento
            gris = np.frombuffer(base64.b64decode(a["huella_gris"]), dtype="<f8")
            if gris.size == 1536 and np.isfinite(gris).all():
                persona["huella_gris"] = gris
        personas.append(persona)
        estudiantes.append(SimpleNamespace(id=str(a["id"]), nombre=a["nombre"], ruta_imagen=None))
    fallos = []
    for f in pedido.get("fallos") or []:
        fallos.append({"id": str(f["id"]), "nombre": f["nombre"], "estado": "ausente", "similitud": None,
                       "motivo": f.get("motivo") or "sin_registro", "bbox": None, "foto": "", "origen": "ai"})
        estudiantes.append(SimpleNamespace(id=str(f["id"]), nombre=f["nombre"], ruta_imagen=None))
    umbral = pedido.get("umbral")
    t0 = time.perf_counter()
    def trabajo():
        with _cerrojo:
            return (obtener_motor().quien_esta_y_quien_no(foto_bytes, personas, umbral=umbral),
                    bytes_a_imagen(foto_bytes))

    try:
        resultado, imagen = await run_in_threadpool(trabajo)
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    except Exception as ex:  # noqa: BLE001
        _log.exception("Falló /pasar-lista")
        raise HTTPException(500, f"Error de la IA: {type(ex).__name__}: {ex}") from ex
    lista = armar_lista(estudiantes, fallos, resultado)
    alto, ancho = imagen.shape[:2]
    filas = lista["filas"]
    por_revisar = sum(1 for f in filas if es_revisar(f))
    return _limpio({
        "version_huella": VERSION_HUELLA,
        "rostros": int(resultado.get("faces_detected") or 0),
        "umbral": float(resultado.get("threshold") or 0),
        "lado_foto": int(max(alto, ancho)),
        "ancho": int(ancho),
        "alto": int(alto),
        "filas": filas,
        "detecciones": lista["detecciones"],
        "repetir_selfie": lista["repetir_selfie"],
        "sugerencias": list(lista["sugeridas"].values()),
        "aviso_foto": aviso_foto(por_revisar, int(max(alto, ancho))),
        "vista_jpg": _b64(_jpg(imagen, 90)),
        "segundos": round(time.perf_counter() - t0, 1),
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=IA_HOST, port=IA_PUERTO, workers=1, log_level="info")
