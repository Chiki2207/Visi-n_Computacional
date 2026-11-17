"""
Paso 0 — Leer la imagen

La foto llega como bytes (archivo subido).
OpenCV necesita una matriz de píxeles (alto × ancho × colores BGR).

Fotos enviadas como documento (sin comprimir): conservan la marca EXIF de giro del celular
(la foto se guarda acostada y la marca dice "girar 90°"). Se gira aquí, siempre igual, sin
depender de la versión de OpenCV. La ventana usa esta misma función, así que las cajas
caen sobre la cara correcta. Las fotos HEIC/HEIF (iPhone) se abren con pillow-heif.
"""

from __future__ import annotations

import io

import cv2
import numpy as np

EXTENSIONES = (".webp", ".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".tif", ".tiff")

# Marca EXIF de orientación (1..8) → cómo dejar la foto derecha (sin perder píxeles).
_GIROS = {
    2: lambda a: cv2.flip(a, 1),
    3: lambda a: cv2.rotate(a, cv2.ROTATE_180),
    4: lambda a: cv2.flip(a, 0),
    5: lambda a: cv2.transpose(a),
    6: lambda a: cv2.rotate(a, cv2.ROTATE_90_CLOCKWISE),
    7: lambda a: cv2.flip(cv2.transpose(a), -1),
    8: lambda a: cv2.rotate(a, cv2.ROTATE_90_COUNTERCLOCKWISE),
}


def registrar_heif() -> bool:
    """Deja que Pillow abra HEIC/HEIF. False si pillow-heif no está instalado."""
    try:
        import pillow_heif
    except ImportError:
        return False
    pillow_heif.register_heif_opener()
    return True


def _orientacion(datos: bytes) -> int:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(datos)) as im:
            return int(im.getexif().get(0x0112, 1) or 1)
    except Exception:
        return 1


def _con_pillow(datos: bytes) -> np.ndarray | None:
    """Formatos que OpenCV no abre (HEIC/HEIF del iPhone, …)."""
    try:
        from PIL import Image, ImageOps

        registrar_heif()
        with Image.open(io.BytesIO(datos)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def bytes_a_imagen(datos: bytes) -> np.ndarray:
    """
    Convierte bytes de un archivo (webp/jpg/png/heic) a imagen OpenCV, ya derecha.

    Returns:
        Imagen en formato BGR (Blue-Green-Red), que es el que usa OpenCV.
    """
    if not datos:
        raise ValueError("El archivo de imagen está vacío")

    # 1) bytes → array de números
    buffer = np.frombuffer(datos, dtype=np.uint8)

    # 2) array → imagen decodificada (sin girar) y giro según la marca EXIF
    imagen = cv2.imdecode(buffer, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if imagen is not None:
        girar = _GIROS.get(_orientacion(datos))
        if girar is not None:
            imagen = np.ascontiguousarray(girar(imagen))
    else:
        imagen = _con_pillow(datos)

    if imagen is None:
        heic = datos[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypmsf1", b"ftyphevc")
        if heic and not registrar_heif():
            raise ValueError(
                "La foto es HEIC (iPhone) y falta pillow-heif: "
                ".venv\\Scripts\\python.exe -m pip install pillow-heif"
            )
        raise ValueError("No se pudo leer la imagen. ¿Formato válido? (jpg, png, webp, heic)")

    return imagen


def abrir_rgb(ruta):
    """La misma imagen que ve el motor, como PIL RGB (para mostrarla en la ventana)."""
    from PIL import Image

    with open(ruta, "rb") as f:
        bgr = bytes_a_imagen(f.read())
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
