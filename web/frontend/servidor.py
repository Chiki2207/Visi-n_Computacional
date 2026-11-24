"""
Servidor web (puerto 3000 por defecto): la página + una API pequeña que lee y escribe los MISMOS
archivos que la ventana de escritorio. Sin base de datos:

  datos/clases/<clase>/estudiantes.xlsx   alumnos (id, nombre, ruta_imagen)     ← igual que a mano
  datos/clases/<clase>/fotos/             selfies (E001_Nombre_Apellido.ext)
  datos/clases/<clase>/fotos_grupales/    fotos de la clase que se suben para pasar lista
  datos/listas/lista_<clase>_<fecha>.xlsx listas (hojas lista / meta / detecciones, como la ventana)
                                          + hoja "cajas" (dónde está cada cara, para dibujarla en la web)
  datos/codigos_listas.json               código de 4 números de cada clase y lista (para entrar desde el chat).
                                          Archivo aparte: no cambia ningún Excel ni nada del reconocimiento.

Lo que se agrega en la web lo ve la ventana y al revés. El reconocimiento lo hace el servicio de IA
(web/ia_servicio, puerto 8001, solo interno). Docentes: web/usuarios.json (claves cifradas).

Arranque:  web\\frontend\\.venv\\Scripts\\python.exe web\\frontend\\servidor.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

CARPETA = Path(__file__).resolve().parent          # web/frontend
WEB = CARPETA.parent                                # web
RAIZ = WEB.parent                                   # proyecto
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _leer_env(ruta: Path) -> None:
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_leer_env(WEB / ".env")

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.excel_clase import cargar_estudiantes, guardar_lista  # noqa: E402  (los mismos de la ventana)

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # sin HEIC
    pass

HOST = os.environ.get("FRONTEND_HOST", "127.0.0.1")
PUERTO = int(os.environ.get("FRONTEND_PUERTO", "3000"))
IA_URL = os.environ.get("IA_URL", "http://127.0.0.1:8001").rstrip("/")
IA_TOKEN = os.environ.get("IA_TOKEN", "").strip()
_datos = Path(os.environ.get("DATOS", "").strip() or "datos")
DATOS = (_datos if _datos.is_absolute() else RAIZ / _datos).resolve()
CLASES = DATOS / "clases"
LISTAS = DATOS / "listas"
USUARIOS = Path(os.environ.get("USUARIOS", "").strip() or WEB / "usuarios.json")
CODIGOS = Path(os.environ.get("CODIGOS", "").strip() or DATOS / "codigos_listas.json")
MAX_MB = float(os.environ.get("MAX_MB", "25"))
SESION_HORAS = float(os.environ.get("SESION_HORAS", "12"))
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}
RE_LISTA = re.compile(r"^lista_(?P<clase>.+)_(?P<fecha>\d{8}_\d{6})\.xlsx$")
RE_CODIGO = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MOTIVO_REVISAR = "revisar_cara_lejana"

log = logging.getLogger("web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_excel_lock = threading.Lock()          # una escritura de Excel a la vez
_cola = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pasar-lista")
_cola_huellas = ThreadPoolExecutor(max_workers=1, thread_name_prefix="huellas")
_cola_nuevas = ThreadPoolExecutor(max_workers=1, thread_name_prefix="huellas-nuevas")   # fotos recién subidas: primero
_fallos_huella: dict[str, dict] = {}    # selfie → último error del SERVIDOR al sacar su huella (se reintenta solo)
_lock_clase: dict[str, threading.Lock] = {}
_precalentando: set[str] = set()
_trabajos: dict[str, dict] = {}         # listas en proceso o con error (en memoria)
_huellas: dict[tuple, dict] = {}        # (selfie, contenido, versión del motor) → huella (copia en memoria)
_sha_cache: dict[tuple, str] = {}       # (selfie, fecha, tamaño) → sha256 del archivo


# ====================================================================== usuarios y sesiones
def _usuarios() -> dict:
    if not USUARIOS.is_file():
        return {}
    return json.loads(USUARIOS.read_text(encoding="utf-8"))


def guardar_usuarios(u: dict) -> None:
    tmp = USUARIOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(u, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(USUARIOS)


def hash_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, 310_000)
    return f"pbkdf2_sha256$310000${base64.b64encode(sal).decode()}${base64.b64encode(dk).decode()}"


def _clave_ok(clave: str, guardado: str) -> bool:
    try:
        _a, it, sal, dk = guardado.split("$")
        prueba = hashlib.pbkdf2_hmac("sha256", clave.encode(), base64.b64decode(sal), int(it))
        return hmac.compare_digest(prueba, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


_sesiones: dict[str, tuple[str, float]] = {}     # sha256(token) → (usuario, vence)
_fallos: dict[str, list[float]] = {}


def usuario_actual(authorization: str = Header(default="")) -> dict:
    tipo, _, token = authorization.partition(" ")
    if tipo.lower() != "bearer" or not token:
        raise HTTPException(401, "Falta iniciar sesión")
    ses = _sesiones.get(hashlib.sha256(token.strip().encode()).hexdigest())
    if ses is None or ses[1] < time.time():
        raise HTTPException(401, "La sesión venció: vuelva a entrar")
    u = _usuarios().get(ses[0])
    if not u or not u.get("activo", True):
        raise HTTPException(401, "Usuario desactivado")
    return {"usuario": ses[0], "nombre": u["nombre"]}


Usr = Depends(usuario_actual)


# ====================================================================== IA
class IAError(Exception):
    pass


def _ia_post(ruta: str, tiempo: float, **kw) -> dict:
    try:
        r = httpx.post(f"{IA_URL}{ruta}", headers={"X-IA-Token": IA_TOKEN},
                       timeout=httpx.Timeout(tiempo, connect=10), **kw)
    except httpx.HTTPError as ex:
        raise HTTPException(503, f"El servicio de IA no responde ({IA_URL})") from ex
    if r.status_code in (409, 413, 422):
        raise IAError(r.json().get("detail") or r.text)
    if r.status_code != 200:
        try:
            detalle = r.json().get("detail")
        except ValueError:
            detalle = r.text[:300]
        raise HTTPException(503, f"El servicio de IA respondió {r.status_code}: {detalle}")
    return r.json()


_version_cache: list = [None, 0.0]


def _ia_version(maximo_s: float = 0) -> str:
    """Versión del motor (cambia si cambia la IA: entonces las huellas se vuelven a sacar)."""
    if maximo_s and _version_cache[0] and time.time() - _version_cache[1] < maximo_s:
        return _version_cache[0]
    try:
        v = httpx.get(f"{IA_URL}/salud", timeout=5).json()["version_huella"]
    except (httpx.HTTPError, KeyError, ValueError) as ex:
        raise HTTPException(503, f"El servicio de IA no responde ({IA_URL})") from ex
    _version_cache[:] = [v, time.time()]
    return v


def _archivo_huella(ruta: Path) -> Path:
    """La huella vive junto a la selfie: fotos/_huellas/<archivo de la foto>.json (uso interno del servidor)."""
    return ruta.parent / "_huellas" / f"{ruta.name}.json"


def _sha(ruta: Path) -> str:
    st = ruta.stat()
    k = (str(ruta), st.st_mtime_ns, st.st_size)
    if k not in _sha_cache:
        _sha_cache[k] = hashlib.sha256(_reintentar(ruta.read_bytes)).hexdigest()
    return _sha_cache[k]


def _huella_guardada(ruta: Path, version: str) -> dict | None:
    """La huella ya hecha para ESTA foto (mismo contenido) y ESTA versión del motor, o None."""
    sha = _sha(ruta)
    clave = (str(ruta.resolve()), sha, version)
    if clave in _huellas:
        return _huellas[clave]
    a = _archivo_huella(ruta)
    if a.is_file():
        try:
            d = json.loads(a.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if d.get("sha256") == sha and d.get("version_huella") == version:
            _huellas[clave] = d
            return d
    return None


def _huella(ruta: Path, version: str) -> dict:
    """Huella de una selfie (la misma función que la ventana, en el servicio de IA). Se saca UNA vez y se
    guarda; solo se vuelve a sacar si cambia la foto o la versión del motor. Si la foto no tiene cara,
    queda anotado {"error": …} para avisarle al docente."""
    d = _huella_guardada(ruta, version)
    if d is not None:
        return d
    datos = _reintentar(ruta.read_bytes)
    sha = hashlib.sha256(datos).hexdigest()
    try:
        r = _ia_post("/registro", 300, files={"foto": (ruta.name, datos)})
        d = {"sha256": sha, "version_huella": r["version_huella"], "huella": r["huella"], "cara_png": r["cara_png"]}
        if r.get("huella_gris"):  # la de la cara en blanco y negro (caras lejanas): se manda con la normal
            d["huella_gris"] = r["huella_gris"]
    except IAError as ex:
        d = {"sha256": sha, "version_huella": version, "error": str(ex)}
    a = _archivo_huella(ruta)
    a.parent.mkdir(exist_ok=True)
    tmp = a.with_name(f"~{secrets.token_hex(4)}_{a.name}")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    _reintentar(lambda: os.replace(tmp, a))
    _huellas[(str(ruta.resolve()), sha, version)] = d
    return d


def _huella_o_falla(ruta: Path, version: str) -> dict | None:
    """Como _huella, pero si falla el SERVIDOR (IA caída, error interno, disco…) no corta nada: lo anota para
    mostrarlo al docente y escribirlo en el registro; se reintenta solo cada 30 s."""
    try:
        d = _huella(ruta, version)
        _fallos_huella.pop(str(ruta.resolve()), None)
        return d
    except Exception as ex:  # noqa: BLE001
        msg = ex.detail if isinstance(ex, HTTPException) else f"{type(ex).__name__}: {ex}"
        _fallos_huella[str(ruta.resolve())] = {"error": str(msg), "cuando": time.time()}
        log.warning("No se pudo sacar la huella de %s: %s", ruta, msg, exc_info=not isinstance(ex, HTTPException))
        return None


def _huella_en_segundo_plano(ruta: Path) -> None:
    """Apenas se sube la foto: la huella se saca por dentro (el docente no espera), antes que lo demás."""
    def trabajo():
        try:
            version = _ia_version()
        except HTTPException as ex:
            _fallos_huella[str(ruta.resolve())] = {"error": str(ex.detail), "cuando": time.time()}
            log.warning("No se pudo sacar la huella de %s: %s", ruta, ex.detail)
            return
        _huella_o_falla(ruta, version)
    _cola_nuevas.submit(trabajo)


# ====================================================================== clases (carpetas + Excel)
def _carpeta_clase(clase: str) -> Path:
    """Solo carpetas que existen directamente en datos/clases (nada de rutas raras)."""
    if not clase or "/" in clase or "\\" in clase or clase.startswith((".", "_")):
        raise HTTPException(404, "Clase no encontrada")
    c = CLASES / clase
    if not (c / "estudiantes.xlsx").is_file() or c.parent != CLASES:
        raise HTTPException(404, "Clase no encontrada")
    return c


def _nombre_visible(c: Path) -> str:
    try:
        wb = _abrir_excel(c / "estudiantes.xlsx", read_only=True)
        if "info" in wb.sheetnames:
            for k, v in wb["info"].iter_rows(min_row=2, max_col=2, values_only=True):
                if str(k).strip() == "clase" and v:
                    wb.close()
                    return str(v)
        wb.close()
    except Exception:  # noqa: BLE001
        pass
    return c.name


def _alumnos(c: Path) -> list:
    try:
        return cargar_estudiantes(c / "estudiantes.xlsx")
    except ValueError as ex:
        if "No hay estudiantes válidos" in str(ex):
            return []
        raise HTTPException(422, f"Los datos de la clase tienen un problema ({ex}): avise al administrador") from ex


def _listas_de(clase: str) -> list[Path]:
    if not LISTAS.is_dir():
        return []
    out = []
    for p in LISTAS.iterdir():
        m = RE_LISTA.match(p.name)
        if m and m["clase"] == clase:
            out.append(p)
    return sorted(out, key=lambda p: p.name, reverse=True)


def _reintentar(accion, veces: int = 15, espera: float = 0.2):
    """Windows no deja mover/reemplazar un archivo abierto (otra lectura en curso): se reintenta un momento."""
    for i in range(veces):
        try:
            return accion()
        except PermissionError:
            if i == veces - 1:
                raise
            time.sleep(espera)


def _abrir_excel(ruta: Path, **kw):
    """Lee el Excel a memoria y suelta el archivo enseguida."""
    return load_workbook(io.BytesIO(_reintentar(ruta.read_bytes)), **kw)


def _guardar_excel(wb: Workbook, destino: Path) -> None:
    """Escritura segura: a un temporal y luego se reemplaza (nunca queda un Excel a medias)."""
    tmp = destino.with_name(f"~tmp_{secrets.token_hex(4)}_{destino.name}")
    wb.save(tmp)
    try:
        _reintentar(lambda: os.replace(tmp, destino))
    except PermissionError as ex:
        tmp.unlink(missing_ok=True)
        raise HTTPException(409, "El servidor está ocupado guardando: intente de nuevo en un momento") from ex


def _san(texto: str) -> str:
    """Como los nombres de selfie que ya hay: cada carácter raro o espacio → '_'."""
    return re.sub(r"[^A-Za-z0-9]", "_", texto.strip())


def _a_papelera(p: Path, carpeta: Path) -> bool:
    """Mueve el archivo a la carpeta _borradas (nunca se elimina). Si sigue ocupado, se deja donde está."""
    if not p.is_file():
        return True
    carpeta.mkdir(exist_ok=True)
    try:
        _reintentar(lambda: shutil.move(str(p), carpeta / f"{datetime.now():%Y%m%d_%H%M%S}_{p.name}"))
        return True
    except PermissionError:
        log.warning("No se pudo mover %s (ocupado); queda en su lugar", p)
        return False


def _texto(v: str | None, campo: str, largo: int) -> str:
    v = (v or "").strip()
    if not v:
        raise HTTPException(422, f"Falta {campo}")
    if len(v) > largo:
        raise HTTPException(422, f"{campo} muy largo (máximo {largo})")
    return v


async def _leer_subida(f: UploadFile) -> tuple[bytes, str]:
    datos = await f.read(int(MAX_MB * 1024 * 1024) + 1)
    if not datos:
        raise HTTPException(422, "El archivo está vacío")
    if len(datos) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"La foto supera {MAX_MB:g} MB")
    ext = Path(f.filename or "").suffix.lower()
    if ext not in EXTENSIONES:
        raise HTTPException(415, "Formato no permitido (jpg, png, webp, heic)")
    return datos, ext


def _jpeg(ruta: Path, lado: int | None = None) -> Response:
    """Foto derecha (giro EXIF, igual que la IA) en JPEG para el navegador (también HEIC)."""
    try:
        with Image.open(io.BytesIO(_reintentar(ruta.read_bytes))) as im:      # el archivo se suelta enseguida
            im = ImageOps.exif_transpose(im).convert("RGB")
            if lado:
                im.thumbnail((lado, lado), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
    except (OSError, ValueError) as ex:
        raise HTTPException(404, "No se pudo abrir la foto") from ex
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


# ====================================================================== aplicación
def _huellas_al_arrancar() -> None:
    """Al encender el servidor: que todos los estudiantes de todas las clases tengan huella (también los
    agregados a mano en el Excel). Espera a que la IA esté lista."""
    for _ in range(360):
        try:
            _ia_version()
            break
        except HTTPException:
            time.sleep(10)
    else:
        return
    while True:     # al arrancar y luego cada 30 s: crear las huellas que falten (y reintentar las que fallaron)
        if CLASES.is_dir():
            for c in sorted(CLASES.iterdir()):
                if c.is_dir() and not c.name.startswith((".", "_")) and (c / "estudiantes.xlsx").is_file():
                    _precalentar(c)
        time.sleep(30)


@asynccontextmanager
async def _vida(_app):
    threading.Thread(target=_huellas_al_arrancar, daemon=True, name="huellas-inicio").start()
    yield


app = FastAPI(title="Asistencia web", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_vida)

CSP = ("default-src 'self'; connect-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


@app.middleware("http")
async def _cabeceras(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(Exception)
async def _error(_r: Request, ex: Exception):
    log.exception("Error no controlado: %s", ex)
    return JSONResponse({"detail": "Error interno del servidor"}, status_code=500)


_ESTATICOS = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
              "/asistente.js": ("asistente.js", "text/javascript; charset=utf-8"),
              "/estilo.css": ("estilo.css", "text/css; charset=utf-8")}


@app.get("/config.js")
def config_js() -> Response:
    return Response('window.CONFIG = { API_URL: "" };\n', media_type="text/javascript; charset=utf-8",
                    headers={"Cache-Control": "no-cache"})


def _estatico(ruta: str):
    nombre, tipo = _ESTATICOS[ruta]
    return FileResponse(CARPETA / nombre, media_type=tipo, headers={"Cache-Control": "no-cache"})


def _indice() -> Response:
    """La página con la versión de app.js y estilo.css en la dirección (?v=…): si se cambian, el navegador
    (también el del celular) toma la nueva al abrir la página, sin quedarse con la vieja guardada."""
    html = (CARPETA / "index.html").read_text(encoding="utf-8")
    for archivo in ("asistente.js", "app.js", "estilo.css"):
        v = (CARPETA / archivo).stat().st_mtime_ns
        html = html.replace(f'"/{archivo}"', f'"/{archivo}?v={v}"')
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def _pagina():
    return _indice()


@app.get("/index.html", include_in_schema=False)
def _pagina2():
    return _indice()


@app.get("/app.js", include_in_schema=False)
def _js():
    return _estatico("/app.js")


@app.get("/asistente.js", include_in_schema=False)
def _asistente_js():
    return _estatico("/asistente.js")


@app.get("/estilo.css", include_in_schema=False)
def _css():
    return _estatico("/estilo.css")


_MARCA = {"logouniamazonia.webp": "image/webp", "logouniamazonia-sm.webp": "image/webp", "plus-jakarta-sans.woff2": "font/woff2"}


@app.get("/asistente/{archivo}", include_in_schema=False)
def _asistente_sprite(archivo: str):
    """Sprites del asistente en la página. No son parte del reconocimiento de lista."""
    if not re.fullmatch(r"(reposo|boca_[aeioum]|ojos_(centro|izq|der|arriba|abajo|blink|arriba_izq|arriba_der|abajo_izq|abajo_der))\.jpg", archivo):
        raise HTTPException(404)
    ruta = (CARPETA / "asistente" / archivo).resolve()
    if ruta.parent != (CARPETA / "asistente").resolve() or not ruta.is_file():
        raise HTTPException(404)
    return FileResponse(ruta, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@app.get("/marca/{archivo}", include_in_schema=False)
def _marca(archivo: str):
    """Logo de la universidad y la fuente (los mismos del proyecto Vision_Computaciona_completo)."""
    if archivo not in _MARCA:
        raise HTTPException(404)
    return FileResponse(CARPETA / "marca" / archivo, media_type=_MARCA[archivo],
                        headers={"Cache-Control": "public, max-age=604800"})


# ---------------------------------------------------------------------- sesión
class Entrada(BaseModel):
    usuario: str = Field(max_length=80)
    clave: str = Field(max_length=200)


@app.get("/api/salud")
def salud() -> dict:
    try:
        ia = httpx.get(f"{IA_URL}/salud", timeout=5).json()
    except httpx.HTTPError:
        ia = {"ok": False}
    return {"ok": True, "datos": CLASES.is_dir(), "ia": ia}


@app.post("/api/auth/entrar")
def entrar(d: Entrada, request: Request) -> dict:
    llave = f"{request.client.host if request.client else '?'}|{d.usuario.lower()}"
    recientes = [t for t in _fallos.get(llave, []) if time.time() - t < 600]
    if len(recientes) >= 5:
        raise HTTPException(429, "Demasiados intentos: espere 10 minutos")
    usuario = d.usuario.strip().lower()
    u = _usuarios().get(usuario)
    if not u or not u.get("activo", True) or not _clave_ok(d.clave, u["clave"]):
        _fallos[llave] = recientes + [time.time()]
        raise HTTPException(401, "Usuario o clave incorrectos")
    token = secrets.token_urlsafe(32)
    _sesiones[hashlib.sha256(token.encode()).hexdigest()] = (usuario, time.time() + SESION_HORAS * 3600)
    return {"token": token, "usuario": {"usuario": usuario, "nombre": u["nombre"]}}


@app.post("/api/auth/salir")
def salir(authorization: str = Header(default="")) -> dict:
    _sesiones.pop(hashlib.sha256(authorization.partition(" ")[2].strip().encode()).hexdigest(), None)
    return {"ok": True}


# ---------------------------------------------------------------------- códigos de 4 números
# Cada clase y cada lista tiene un código fijo de 4 números (1000-9999) para entrar desde el chat
# («entra a la lista 4821»). Se guardan en un archivo aparte (CODIGOS) como {"clase:<carpeta>": "4821",
# "lista:<archivo>.xlsx": "5930"}. El primer intento sale del nombre (siempre el mismo); si ya está usado,
# se toma el siguiente libre. Una vez dado, no cambia ni se reutiliza (aunque la lista se borre).
_codigos_lock = threading.Lock()
_codigos: dict[str, str] | None = None


def _codigos_cargar() -> dict[str, str]:
    global _codigos
    if _codigos is None:
        try:
            datos = json.loads(CODIGOS.read_text(encoding="utf-8")) if CODIGOS.is_file() else {}
            _codigos = {str(k): str(v) for k, v in datos.items() if re.fullmatch(r"\d{4}", str(v))}
        except Exception as ex:  # noqa: BLE001  (archivo dañado: se guarda aparte y se rehace igual, por el nombre)
            log.warning("No se pudo leer %s (%s): se rehace", CODIGOS, ex)
            try:
                CODIGOS.replace(CODIGOS.with_name(f"{CODIGOS.name}.danado_{datetime.now():%Y%m%d_%H%M%S}"))
            except OSError:
                pass
            _codigos = {}
    return _codigos


def _codigos_guardar(m: dict[str, str]) -> None:
    try:
        CODIGOS.parent.mkdir(parents=True, exist_ok=True)
        tmp = CODIGOS.with_name(CODIGOS.name + ".tmp")
        tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, CODIGOS)
    except OSError as ex:
        log.warning("No se pudo guardar %s: %s (los códigos siguen en memoria)", CODIGOS, ex)


def _codigos_de(claves: list[str]) -> dict[str, str]:
    """Código de cada clave ("clase:<carpeta>" o "lista:<archivo>"); da los que falten y guarda una vez."""
    with _codigos_lock:
        m = _codigos_cargar()
        usados = set(m.values())
        nuevo = False
        for k in claves:
            if k in m:
                continue
            base = int(hashlib.sha1(k.encode("utf-8")).hexdigest(), 16) % 9000
            for i in range(9000):
                c = str(1000 + (base + i) % 9000)
                if c not in usados:
                    m[k] = c
                    usados.add(c)
                    nuevo = True
                    break
        if nuevo:
            _codigos_guardar(m)
        return {k: m.get(k, "") for k in claves}


def _codigo(clave: str) -> str:
    return _codigos_de([clave])[clave]


def _todas_las_claves() -> list[str]:
    claves = []
    if CLASES.is_dir():
        claves += [f"clase:{c.name}" for c in sorted(CLASES.iterdir(), key=lambda p: p.name.lower())
                   if c.is_dir() and not c.name.startswith((".", "_")) and (c / "estudiantes.xlsx").is_file()]
    if LISTAS.is_dir():
        claves += [f"lista:{p.name}" for p in sorted(LISTAS.iterdir()) if RE_LISTA.match(p.name)]
    claves += [f"lista:{a}" for a in list(_trabajos)]
    return claves


# ---------------------------------------------------------------------- clases
def _clase_dict(c: Path) -> dict:
    return {"id": c.name, "nombre": _nombre_visible(c), "estudiantes": len(_alumnos(c)), "listas": len(_listas_de(c.name)),
            "codigo": _codigo(f"clase:{c.name}")}


@app.get("/api/clases")
def clases(_u=Usr) -> list[dict]:
    if not CLASES.is_dir():
        return []
    return [_clase_dict(c) for c in sorted(CLASES.iterdir(), key=lambda p: p.name.lower())
            if c.is_dir() and not c.name.startswith((".", "_")) and (c / "estudiantes.xlsx").is_file()]


class ClaseIn(BaseModel):
    nombre: str = Field(max_length=120)


@app.post("/api/clases", status_code=201)
def crear_clase(d: ClaseIn, _u=Usr) -> dict:
    """Como app/crear_plantilla_clase.py, pero sin filas de ejemplo: carpeta + estudiantes.xlsx + fotos/."""
    nombre = _texto(d.nombre, "el nombre", 120)
    carpeta = re.sub(r"[^\w\- ]", "_", nombre).strip(" ._") or "clase"
    c = CLASES / carpeta
    if c.exists():
        raise HTTPException(409, "Ya existe una clase con ese nombre")
    (c / "fotos").mkdir(parents=True)
    (c / "fotos_grupales").mkdir()
    wb = Workbook()
    ws = wb.active
    ws.title = "estudiantes"
    ws.append(["id", "nombre", "ruta_imagen"])
    info = wb.create_sheet("info")
    info.append(["campo", "valor"])
    info.append(["clase", nombre])
    info.append(["instruccion", "Una fila por alumno: id, nombre y ruta_imagen (fotos/E001_Nombre.webp). "
                                "Se puede editar a mano o desde la web."])
    with _excel_lock:
        _guardar_excel(wb, c / "estudiantes.xlsx")
    return _clase_dict(c)


@app.get("/api/clases/{clase}")
def clase(clase: str, _u=Usr) -> dict:
    c = _carpeta_clase(clase)
    _precalentar(c)        # mientras el docente toma la foto, las huellas ya se van preparando
    return _clase_dict(c)


# ---------------------------------------------------------------------- alumnos
@app.get("/api/clases/{clase}/estudiantes")
def estudiantes(clase: str, _u=Usr) -> list[dict]:
    c = _carpeta_clase(clase)
    try:
        version = _ia_version(60)
    except HTTPException:
        version = None
    out, faltan = [], False
    for e in _alumnos(c):
        existe = e.ruta_imagen.is_file()
        huella, error = "sin_foto", "Falta la foto"
        if existe:
            d = _huella_guardada(e.ruta_imagen, version) if version else None
            falla = _fallos_huella.get(str(e.ruta_imagen.resolve()))
            if d is None and (falla or not version):
                huella, faltan = "error_servidor", True
                error = falla["error"] if falla else "El servicio de IA no responde"
            elif d is None:
                huella, error, faltan = "procesando", None, True
            elif "error" in d:
                huella, error = "sin_cara", d["error"]
            else:
                huella, error = "lista", None
        out.append({
            "id": e.id, "codigo": e.id, "nombre": e.nombre,
            "foto": e.ruta_imagen.relative_to(c).as_posix() if c in e.ruta_imagen.parents else str(e.ruta_imagen),
            "tiene_selfie": existe, "huella": huella, "huella_error": error,
            "actualizado": str(e.ruta_imagen.stat().st_mtime_ns) if existe else "",
        })
    if faltan:
        _precalentar(c)        # ninguna foto se queda sin huella
    return out


def _siguiente_codigo(alumnos: list) -> str:
    nums = [int(m[1]) for a in alumnos if (m := re.fullmatch(r"E(\d+)", a.id))]
    return f"E{(max(nums) + 1 if nums else 1):03d}"


@app.get("/api/clases/{clase}/siguiente-codigo")
def siguiente_codigo(clase: str, _u=Usr) -> dict:
    return {"codigo": _siguiente_codigo(_alumnos(_carpeta_clase(clase)))}


@app.post("/api/clases/{clase}/estudiantes", status_code=201)
async def crear_estudiante(clase: str, nombre: str = Form(...), selfie: UploadFile = File(...),
                           codigo: str = Form(""), _u=Usr) -> dict:
    """Igual que hacerlo a mano: la selfie va a fotos/<código>_<Nombre>.ext y se agrega la fila al Excel.
    Sin código, se usa el siguiente (E021…). Responde enseguida; la huella se saca por dentro."""
    c = _carpeta_clase(clase)
    nombre = _texto(nombre, "el nombre", 160)
    codigo = codigo.strip() or _siguiente_codigo(_alumnos(c))
    codigo = _texto(codigo, "el código", 40)
    if not RE_CODIGO.match(codigo):
        raise HTTPException(422, "El código solo puede tener letras, números, - y _ (ej.: E021)")
    datos, ext = await _leer_subida(selfie)
    with _excel_lock:
        excel = c / "estudiantes.xlsx"
        wb = _abrir_excel(excel)
        ws = wb["estudiantes"] if "estudiantes" in wb.sheetnames else wb.active
        if any(str(r[0]).strip() == codigo for r in ws.iter_rows(min_row=2, max_col=1, values_only=True) if r[0] is not None):
            raise HTTPException(409, f"Ya hay un alumno con el código {codigo} en esta clase")
        archivo = c / "fotos" / f"{codigo}_{_san(nombre)}{ext}"
        if archivo.exists():
            raise HTTPException(409, f"Ya hay un estudiante con el código {codigo}")
        archivo.parent.mkdir(exist_ok=True)
        archivo.write_bytes(datos)
        ws.append([codigo, nombre, f"fotos/{archivo.name}"])
        try:
            _guardar_excel(wb, excel)
        except HTTPException:
            archivo.unlink(missing_ok=True)
            raise
    _huella_en_segundo_plano(archivo)
    return {"codigo": codigo, "nombre": nombre, "foto": f"fotos/{archivo.name}", "huella": "procesando"}


def _fila_de(ws, codigo: str) -> int:
    for i, r in enumerate(ws.iter_rows(min_row=2, max_col=1, values_only=True), start=2):
        if r[0] is not None and str(r[0]).strip() == codigo:
            return i
    raise HTTPException(404, "Alumno no encontrado")


@app.patch("/api/clases/{clase}/estudiantes/{codigo}")
async def editar_estudiante(clase: str, codigo: str, nombre: str | None = Form(None),
                            selfie: UploadFile | None = File(None), _u=Usr) -> dict:
    c = _carpeta_clase(clase)
    datos = ext = None
    if selfie is not None and selfie.filename:
        datos, ext = await _leer_subida(selfie)
    with _excel_lock:
        excel = c / "estudiantes.xlsx"
        wb = _abrir_excel(excel)
        ws = wb["estudiantes"] if "estudiantes" in wb.sheetnames else wb.active
        enc = [str(x.value or "").strip().lower() for x in ws[1]]
        col_nom = next((enc.index(n) for n in ("nombre", "name", "estudiante") if n in enc), 1) + 1
        col_foto = next((enc.index(n) for n in ("ruta_imagen", "foto", "imagen", "ruta", "path") if n in enc), 2) + 1
        i = _fila_de(ws, codigo)
        if nombre is not None:
            ws.cell(i, col_nom).value = _texto(nombre, "el nombre", 160)
        nueva = vieja = temporal = None
        if datos is not None:
            vieja = (c / str(ws.cell(i, col_foto).value)).resolve() if ws.cell(i, col_foto).value else None
            nueva = c / "fotos" / f"{codigo}_{_san(str(ws.cell(i, col_nom).value))}{ext}"
            temporal = nueva.with_name(f"~nueva_{secrets.token_hex(4)}{ext}")
            temporal.write_bytes(datos)               # 1) la nueva, aparte
            ws.cell(i, col_foto).value = f"fotos/{nueva.name}"
        try:
            _guardar_excel(wb, excel)                 # 2) el Excel (si falla, no cambió nada)
        except HTTPException:
            if temporal:
                temporal.unlink(missing_ok=True)
            raise
        if temporal:
            if vieja and vieja.is_file() and c in vieja.parents:
                _a_papelera(vieja, c / "fotos" / "_borradas")   # 3) la vieja a _borradas
            if nueva.exists():
                _a_papelera(nueva, c / "fotos" / "_borradas")
            temporal.replace(nueva)                   # 4) la nueva a su nombre
            _huella_en_segundo_plano(nueva)           # 5) su huella, por dentro
    return {"codigo": codigo, "ok": True}


@app.delete("/api/clases/{clase}/estudiantes/{codigo}")
def borrar_estudiante(clase: str, codigo: str, _u=Usr) -> dict:
    """Quita la fila del Excel. La selfie no se elimina: va a fotos/_borradas/."""
    c = _carpeta_clase(clase)
    with _excel_lock:
        excel = c / "estudiantes.xlsx"
        wb = _abrir_excel(excel)
        ws = wb["estudiantes"] if "estudiantes" in wb.sheetnames else wb.active
        i = _fila_de(ws, codigo)
        enc = [str(x.value or "").strip().lower() for x in ws[1]]
        col_foto = next((enc.index(n) for n in ("ruta_imagen", "foto", "imagen", "ruta", "path") if n in enc), 2) + 1
        rel = ws.cell(i, col_foto).value
        ws.delete_rows(i)
        _guardar_excel(wb, excel)
    if rel:
        foto = (c / str(rel)).resolve()
        if c in foto.parents:
            _a_papelera(foto, c / "fotos" / "_borradas")
    return {"ok": True}


@app.get("/api/clases/{clase}/estudiantes/{codigo}/selfie")
def selfie(clase: str, codigo: str, _u=Usr):
    c = _carpeta_clase(clase)
    e = next((a for a in _alumnos(c) if a.id == codigo), None)
    if e is None or not e.ruta_imagen.is_file():
        raise HTTPException(404, "Sin selfie")
    return _jpeg(e.ruta_imagen, 480)


# ---------------------------------------------------------------------- pasar lista
def _nombre_lista(clase: str) -> str:
    t = datetime.now()
    while True:
        n = f"lista_{clase}_{t:%Y%m%d_%H%M%S}.xlsx"
        if not (LISTAS / n).exists() and n not in _trabajos:
            return n
        t += timedelta(seconds=1)


@app.post("/api/clases/{clase}/asistencias", status_code=202)
async def nueva_asistencia(clase: str, foto: UploadFile = File(...), u=Usr) -> dict:
    c = _carpeta_clase(clase)
    if not _alumnos(c):
        raise HTTPException(422, "La clase no tiene alumnos")
    datos, ext = await _leer_subida(foto)
    archivo = _nombre_lista(c.name)
    sello = RE_LISTA.match(archivo)["fecha"]
    destino = c / "fotos_grupales" / f"{sello}_{_san(Path(foto.filename or 'foto').stem)[:60]}{ext}"
    destino.parent.mkdir(exist_ok=True)
    destino.write_bytes(datos)
    _trabajos[archivo] = {"estado": "procesando", "clase": c.name, "foto": destino, "creada": datetime.now().isoformat(),
                          "nombre_archivo": foto.filename or destino.name, "por": u["usuario"]}
    _cola.submit(_procesar, archivo)
    return {"id": archivo, "estado": "procesando", "codigo": _codigo(f"lista:{archivo}")}


def _procesar(archivo: str) -> None:
    t = _trabajos[archivo]
    try:
        _pasar_lista(archivo, t)
        _trabajos.pop(archivo, None)
    except HTTPException as ex:
        t.update(estado="error", error=ex.detail)
    except IAError as ex:
        t.update(estado="error", error=str(ex))
    except Exception:  # noqa: BLE001
        log.exception("Falló pasar lista %s", archivo)
        t.update(estado="error", error="Error interno al pasar lista")




def _huellas_de_clase(c: Path) -> tuple[list, list]:
    """Huellas de todas las selfies de la clase (las ya calculadas salen de memoria al instante)."""
    with _lock_clase.setdefault(c.name, threading.Lock()):
        estudiantes = cargar_estudiantes(c / "estudiantes.xlsx")
        version = _ia_version()
        alumnos, fallos = [], []
        for est in estudiantes:
            if not est.ruta_imagen.is_file():
                fallos.append({"id": est.id, "nombre": est.nombre, "motivo": f"sin_foto:{est.ruta_imagen}"})
                continue
            h = _huella_o_falla(est.ruta_imagen, version)
            if h is None:
                err = _fallos_huella.get(str(est.ruta_imagen.resolve()), {}).get("error", "error del servidor")
                fallos.append({"id": est.id, "nombre": est.nombre, "motivo": f"registro_fallo:no se pudo sacar la huella ({err})"})
            elif "error" in h:
                fallos.append({"id": est.id, "nombre": est.nombre, "motivo": f"registro_fallo:{h['error']}"})
            else:
                alumnos.append({"id": est.id, "nombre": est.nombre, **h})
        return alumnos, fallos


def _precalentar(c: Path) -> None:
    """Al entrar a una clase: preparar sus huellas en segundo plano, así la lista sale rápido."""
    if c.name in _precalentando:
        return
    _precalentando.add(c.name)

    def trabajo():
        try:
            _huellas_de_clase(c)
        except Exception as ex:  # noqa: BLE001  (si la IA no está, se hará al pasar lista)
            log.info("No se pudieron preparar las huellas de %s: %s", c.name, ex)
        finally:
            _precalentando.discard(c.name)

    _cola_huellas.submit(trabajo)


def _pasar_lista(archivo: str, t: dict) -> None:
    """Lo mismo que app/asistencia_core.pasar_lista: selfies → huellas → foto grupal → lista."""
    c = CLASES / t["clase"]
    alumnos, fallos = _huellas_de_clase(c)
    pedido = {"alumnos": alumnos, "fallos": fallos, "umbral": None}
    foto: Path = t["foto"]
    r = _ia_post("/pasar-lista", 900, files={"foto": (foto.name, foto.read_bytes())}, data={"datos": json.dumps(pedido)})
    # La lista en Excel, con la misma función que la ventana; después se agrega la hoja "cajas".
    LISTAS.mkdir(parents=True, exist_ok=True)
    tmp = LISTAS / f"~tmp_{archivo}"
    try:
        guardar_lista(tmp, clase=c.name, foto_grupal=str(foto), umbral=float(r["umbral"]),
                      faces_detected=int(r["rostros"]), filas=r["filas"], detecciones=r["detecciones"])
        wb = load_workbook(tmp)
        cajas = wb.create_sheet("cajas")
        cajas.append(["id", "x1", "y1", "x2", "y2", "sugerencia"])
        for f in r["filas"]:
            bb = f.get("bbox") or [None] * 4
            cajas.append([f["id"], *bb[:4], f.get("sugerencia")])
        web = wb.create_sheet("web")
        web.append(["campo", "valor"])
        # la foto, relativa a la carpeta de datos (así la lista sirve aunque datos/ se mueva de lugar)
        for k, v in (("foto", foto.resolve().relative_to(DATOS).as_posix()), ("ancho", r["ancho"]), ("alto", r["alto"]),
                     ("lado_foto", r["lado_foto"]), ("aviso_foto", r["aviso_foto"]),
                     ("repetir_selfie", json.dumps(r["repetir_selfie"], ensure_ascii=False)),
                     ("sugeridos", json.dumps([{"i": i, **d["sugerido"]} for i, d in enumerate(r["detecciones"]) if d.get("sugerido")], ensure_ascii=False)),
                     ("nombre_archivo", t["nombre_archivo"]), ("pasada_por", t["por"]), ("segundos", r["segundos"]),
                     ("version_motor", r["version_huella"])):
            web.append([k, v])
        with _excel_lock:
            wb.save(tmp)
            os.replace(tmp, LISTAS / archivo)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------- leer una lista (de la web o de la ventana)
def _ruta_lista(archivo: str) -> Path:
    if not RE_LISTA.match(archivo) or "/" in archivo or "\\" in archivo:
        raise HTTPException(404, "Lista no encontrada")
    p = LISTAS / archivo
    if not p.is_file():
        raise HTTPException(404, "Lista no encontrada")
    return p


def _hoja(wb, nombre) -> list:
    return list(wb[nombre].iter_rows(values_only=True)) if nombre in wb.sheetnames else []


def _leer_lista(archivo: str) -> dict:
    p = _ruta_lista(archivo)
    wb = _abrir_excel(p, read_only=True, data_only=True)
    lista, meta, dets = _hoja(wb, "lista"), dict(r[:2] for r in _hoja(wb, "meta")[1:]), _hoja(wb, "detecciones")
    cajas = {str(r[0]): r for r in _hoja(wb, "cajas")[1:]}
    web = {r[0]: r[1] for r in _hoja(wb, "web")[1:]}
    wb.close()
    m = RE_LISTA.match(archivo)
    detecciones = []
    for r in dets[1:]:
        _i, matched, pid, nombre, sim, x1, y1, x2, y2 = (list(r) + [None] * 9)[:9]
        detecciones.append({"bbox": [x1, y1, x2, y2] if x1 is not None else None, "matched": bool(matched),
                            "codigo": pid or None, "name": nombre or None, "similarity": sim, "sugerido": None})
    for s in json.loads(web.get("sugeridos") or "[]"):
        if 0 <= s["i"] < len(detecciones):
            detecciones[s["i"]]["sugerido"] = {"codigo": s["id"], "nombre": s["nombre"], "nota": s["nota"]}
    caja_det = {str(d["codigo"]): d["bbox"] for d in detecciones if d["matched"] and d["codigo"]}
    registros = []
    for orden, r in enumerate(lista[1:]):
        cod, nombre, estado, sim, motivo, origen = (list(r) + [None] * 6)[:6]
        cod = str(cod)
        cj = cajas.get(cod)
        bbox = [cj[1], cj[2], cj[3], cj[4]] if cj and cj[1] is not None else caja_det.get(cod) if estado == "presente" else None
        sug = cj[5] if cj else None
        if sug is None and str(motivo or "").startswith(MOTIVO_REVISAR + ":"):
            sug = float(str(motivo).split(":", 1)[1])
        registros.append({"id": cod, "codigo": cod, "estudiante_id": cod, "nombre": nombre, "estado": estado,
                          "similitud": sim, "motivo": motivo or "", "origen": origen or "ai", "bbox": bbox,
                          "sugerencia": sug, "orden": orden,
                          "revisar": estado == "ausente" and str(motivo or "").startswith(MOTIVO_REVISAR)})
    pres = sum(r["estado"] == "presente" for r in registros)
    rev = sum(r["revisar"] for r in registros)
    foto_rel = web.get("foto")
    return {
        "id": archivo, "clase_id": m["clase"], "clase": m["clase"], "estado": "lista", "error": None,
        "creada": datetime.strptime(m["fecha"], "%Y%m%d_%H%M%S").isoformat(),
        "nombre_archivo": web.get("nombre_archivo") or Path(str(meta.get("foto_grupal") or "")).name,
        "rostros": meta.get("rostros_detectados"), "umbral": meta.get("umbral"),
        "ancho": web.get("ancho"), "alto": web.get("alto"), "aviso_foto": web.get("aviso_foto") or "",
        "lado_foto": web.get("lado_foto"),
        "repetir_selfie": json.loads(web.get("repetir_selfie") or "[]"), "detecciones": detecciones,
        "registros": registros, "presentes": pres, "por_revisar": rev, "ausentes": len(registros) - pres - rev,
        "foto": foto_rel or meta.get("foto_grupal"), "de_la_ventana": not web,
    }


def _resumen_trabajo(archivo: str, t: dict) -> dict:
    return {"id": archivo, "clase_id": t["clase"], "clase": t["clase"], "estado": t["estado"], "error": t.get("error"),
            "creada": t["creada"], "nombre_archivo": t["nombre_archivo"], "registros": [], "detecciones": [],
            "presentes": 0, "por_revisar": 0, "ausentes": 0}


@app.get("/api/clases/{clase}/asistencias")
def asistencias(clase: str, _u=Usr) -> list[dict]:
    c = _carpeta_clase(clase)
    out = [_resumen_trabajo(a, t) for a, t in _trabajos.items() if t["clase"] == c.name]
    for p in _listas_de(c.name):
        try:
            d = _leer_lista(p.name)
            d.pop("registros"); d.pop("detecciones")
            out.append(d)
        except Exception:  # noqa: BLE001  (un Excel dañado no tumba el historial)
            out.append({"id": p.name, "clase_id": c.name, "estado": "error", "error": "No se pudo leer esta lista",
                        "creada": None, "nombre_archivo": p.name})
    cods = _codigos_de([f"lista:{a['id']}" for a in out])
    for a in out:
        a["codigo"] = cods[f"lista:{a['id']}"]
    return sorted(out, key=lambda a: a["id"], reverse=True)


@app.get("/api/asistencias/{archivo}")
def asistencia(archivo: str, _u=Usr) -> dict:
    if archivo in _trabajos:
        d = _resumen_trabajo(archivo, _trabajos[archivo])
    else:
        d = _leer_lista(archivo)
    d["clase"] = _nombre_visible(CLASES / d["clase_id"]) if (CLASES / d["clase_id"]).is_dir() else d["clase_id"]
    d["codigo"] = _codigo(f"lista:{archivo}")
    return d


@app.get("/api/codigos/{codigo}")
def buscar_codigo(codigo: str, _u=Usr) -> dict:
    """A qué clase o lista lleva un código de 4 números (para «entra a la lista 4821» en el chat)."""
    if not re.fullmatch(r"\d{4}", codigo or ""):
        raise HTTPException(404, "El código son 4 números")

    def buscar() -> str | None:
        with _codigos_lock:
            return next((k for k, v in _codigos_cargar().items() if v == codigo), None)

    clave = buscar()
    if clave is None:                      # por si aún no se había mostrado: se dan todos y se busca otra vez
        _codigos_de(_todas_las_claves())
        clave = buscar()
    if clave:
        tipo, ident = clave.split(":", 1)
        if tipo == "clase":
            try:
                c = _carpeta_clase(ident)
                return {"tipo": "clase", "id": c.name, "clase_id": c.name, "nombre": _nombre_visible(c), "codigo": codigo}
            except HTTPException:
                pass
        elif tipo == "lista" and (ident in _trabajos or (RE_LISTA.match(ident) and (LISTAS / ident).is_file())):
            m = RE_LISTA.match(ident)
            clase_id = _trabajos[ident]["clase"] if ident in _trabajos else m["clase"]
            nombre = _nombre_visible(CLASES / clase_id) if (CLASES / clase_id).is_dir() else clase_id
            return {"tipo": "lista", "id": ident, "clase_id": clase_id, "nombre": nombre, "codigo": codigo,
                    "creada": datetime.strptime(m["fecha"], "%Y%m%d_%H%M%S").isoformat() if m else None}
    raise HTTPException(404, f"No hay ninguna lista ni clase con el código {codigo}")


@app.get("/api/asistencias/{archivo}/foto")
def foto_asistencia(archivo: str, _u=Usr):
    d = _leer_lista(archivo)
    if not d["foto"]:
        raise HTTPException(404, "La lista no dice qué foto usó")
    p = Path(d["foto"])
    p = (p if p.is_absolute() else DATOS / p).resolve()      # web: relativa a datos/; ventana: absoluta
    if DATOS not in p.parents or not p.is_file():     # solo fotos dentro de datos/
        raise HTTPException(404, "La foto de esta lista no está disponible")
    return _jpeg(p)


class CambioEstado(BaseModel):
    estado: str = Field(pattern="^(presente|ausente)$")


@app.patch("/api/asistencias/{archivo}/registros/{codigo}")
def cambiar_registro(archivo: str, codigo: str, d: CambioEstado, _u=Usr) -> dict:
    """Corrección a mano (también confirma una sugerencia «¿revisar?»): se escribe en el Excel de la lista."""
    p = _ruta_lista(archivo)
    with _excel_lock:
        wb = _abrir_excel(p)
        ws = wb["lista"]
        i = _fila_de(ws, codigo)
        if ws.cell(i, 3).value != d.estado:
            ws.cell(i, 3).value = d.estado
            ws.cell(i, 5).value = f"manual_{d.estado}"
            ws.cell(i, 6).value = "manual"
            if "meta" in wb.sheetnames:
                filas = list(ws.iter_rows(min_row=2, values_only=True))
                for fila in wb["meta"].iter_rows(min_row=2):
                    if fila[0].value == "presentes":
                        fila[1].value = sum(1 for f in filas if f[2] == "presente")
                    elif fila[0].value == "ausentes":
                        fila[1].value = sum(1 for f in filas if f[2] == "ausente")
            _guardar_excel(wb, p)
    reg = next(r for r in _leer_lista(archivo)["registros"] if r["codigo"] == codigo)
    return reg


@app.get("/api/asistencias/{archivo}/excel")
def excel(archivo: str, _u=Usr):
    return FileResponse(_ruta_lista(archivo), filename=archivo,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.delete("/api/asistencias/{archivo}")
def borrar_asistencia(archivo: str, _u=Usr) -> dict:
    """La lista no se elimina: va a datos/listas/_borradas/ (la foto grupal se queda en fotos_grupales/)."""
    if archivo in _trabajos:
        if _trabajos[archivo]["estado"] == "procesando":
            raise HTTPException(409, "La lista se está procesando: espere a que termine")
        _trabajos.pop(archivo)
        return {"ok": True}
    with _excel_lock:
        _a_papelera(_ruta_lista(archivo), LISTAS / "_borradas")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    if not IA_TOKEN:
        sys.exit("Falta IA_TOKEN en web/.env")
    print(f"Web en http://{HOST}:{PUERTO}  (datos: {DATOS}; IA: {IA_URL})")
    uvicorn.run(app, host=HOST, port=PUERTO, workers=1, proxy_headers=True, log_level="info")
