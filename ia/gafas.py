"""
Ronda 16 — Gafas: registro robusto con o sin gafas (todo sobre la cara ALINEADA 112×112).

Con UNA foto de registro, el alumno puede llegar a clase con o sin gafas. Generamos versiones
sintéticas de la cara registrada y las guardamos como muestras extra:
  - si la foto tiene gafas  → versión SIN gafas (se borra el marco con inpainting)
  - si no tiene gafas       → versiones CON gafas dibujadas (metal fino / pasta negra)
La segmentación de gafas usa BiSeNet face-parsing (yakhyo/face-parsing, código MIT,
clase 6 = eye_g de CelebAMask-HQ). Si el modelo no está, solo se dibujan gafas.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

_RUTA_PARSING = Path(__file__).resolve().parent.parent / "models" / "face_parsing_resnet18.onnx"
_sesion = None
# fracción mínima de la cara marcada como "gafas" para decir que las tiene
GAFAS_MIN_FRAC = float(os.environ.get("GAFAS_MIN_FRAC", "0.02"))
OJO_I = (38.2946, 51.6963)
OJO_D = (73.5318, 51.5014)


def _parser():
    global _sesion
    if _sesion is None:
        import onnxruntime as ort

        op = ort.SessionOptions()
        op.log_severity_level = 3
        _sesion = ort.InferenceSession(str(_RUTA_PARSING), op, providers=["CPUExecutionProvider"])
    return _sesion


def disponible() -> bool:
    return _RUTA_PARSING.exists()


def poner_gafas(cara: np.ndarray, estilo: str = "metal") -> np.ndarray:
    """Dibuja gafas sintéticas sobre la cara alineada (plantilla ArcFace: ojos fijos)."""
    S = 4  # dibujar a 448 px y bajar (antialias)
    g = cv2.resize(cara, (112 * S, 112 * S), interpolation=cv2.INTER_CUBIC)
    capa = g.copy()
    if estilo == "negra":
        color, grosor, aw, ah = (25, 25, 25), 3 * S, 15, 10
    elif estilo == "dorada":
        color, grosor, aw, ah = (60, 150, 190), 1 * S, 14, 10
    else:  # metal plateado fino (como las de registro de Luis)
        color, grosor, aw, ah = (170, 170, 175), 1 * S, 14, 10
    cy = 0.5 * (OJO_I[1] + OJO_D[1]) + 1
    for ex in (OJO_I[0], OJO_D[0]):
        x1, y1, x2, y2 = int((ex - aw) * S), int((cy - ah) * S), int((ex + aw) * S), int((cy + ah) * S)
        r = 4 * S
        # rectángulo redondeado
        cv2.line(capa, (x1 + r, y1), (x2 - r, y1), color, grosor, cv2.LINE_AA)
        cv2.line(capa, (x1 + r, y2), (x2 - r, y2), color, grosor, cv2.LINE_AA)
        cv2.line(capa, (x1, y1 + r), (x1, y2 - r), color, grosor, cv2.LINE_AA)
        cv2.line(capa, (x2, y1 + r), (x2, y2 - r), color, grosor, cv2.LINE_AA)
        for (cx_, cy_, a0) in ((x1 + r, y1 + r, 180), (x2 - r, y1 + r, 270), (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90)):
            cv2.ellipse(capa, (cx_, cy_), (r, r), a0, 0, 90, color, grosor, cv2.LINE_AA)
    # puente y patillas
    yb = int((cy - ah + 3) * S)
    cv2.line(capa, (int((OJO_I[0] + aw) * S), yb), (int((OJO_D[0] - aw) * S), yb), color, grosor, cv2.LINE_AA)
    cv2.line(capa, (int((OJO_I[0] - aw) * S), yb), (0, yb + S), color, grosor, cv2.LINE_AA)
    cv2.line(capa, (int((OJO_D[0] + aw) * S), yb), (112 * S - 1, yb + S), color, grosor, cv2.LINE_AA)
    # reflejo leve en los lentes
    lentes = np.zeros(g.shape[:2], np.uint8)
    for ex in (OJO_I[0], OJO_D[0]):
        cv2.ellipse(lentes, (int(ex * S), int(cy * S)), (int((aw - 1) * S), int((ah - 1) * S)), 0, 0, 360, 255, -1)
    tinte = capa.astype(np.float32)
    tinte[lentes > 0] = 0.9 * tinte[lentes > 0] + 0.1 * np.array([235, 215, 200], np.float32)
    return cv2.resize(tinte.clip(0, 255).astype(np.uint8), (112, 112), interpolation=cv2.INTER_AREA)


def contraluz(cara: np.ndarray) -> np.ndarray:
    """Cara oscura y lavada (luz detrás): gamma alto + menos contraste + algo de ruido."""
    x = cara.astype(np.float32) / 255.0
    x = 0.65 * x ** 1.6 + 0.04
    return (x * 255).clip(0, 255).astype(np.uint8)


def variantes(cara: np.ndarray, modo: str = "gafas") -> list[tuple[str, np.ndarray]]:
    """Versiones sintéticas de la cara de registro (sin incluir la original)."""
    out: list[tuple[str, np.ndarray]] = []
    con = False
    if disponible():
        m = mascara_gafas(cara)
        con = float((m > 0).mean()) >= GAFAS_MIN_FRAC
        if con:
            out.append(("sin_gafas", quitar_gafas(cara, m)))
    if not con:
        out.append(("gafas_metal", poner_gafas(cara, "metal")))
        out.append(("gafas_negra", poner_gafas(cara, "negra")))
    if "luz" in modo:
        out.append(("contraluz", contraluz(cara)))
    return out


# --- alineación "holgada" (más contexto) para segmentar mejor las gafas ---
_K, _LADO_H = 1.25, 256
_OFF = (_LADO_H - 112 * _K) / 2.0


def _recorte_holgado(imagen: np.ndarray, puntos5: np.ndarray) -> np.ndarray:
    from ia.reconocedor_onnx import PLANTILLA_ARCFACE

    dst = PLANTILLA_ARCFACE * _K + _OFF
    M, _ = cv2.estimateAffinePartial2D(np.asarray(puntos5, np.float32).reshape(5, 2), dst, method=cv2.LMEDS)
    if M is None:
        return None
    return cv2.warpAffine(imagen, M, (_LADO_H, _LADO_H), borderMode=cv2.BORDER_REPLICATE)


def _holgado_a_112(h: np.ndarray) -> np.ndarray:
    A = np.float32([[1 / _K, 0, -_OFF / _K], [0, 1 / _K, -_OFF / _K]])
    return cv2.warpAffine(h, A, (112, 112), flags=cv2.INTER_AREA, borderValue=0)


def mascara_holgada(h: np.ndarray) -> np.ndarray:
    s = _parser()
    x = cv2.resize(cv2.cvtColor(h, cv2.COLOR_BGR2RGB), (512, 512), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    y = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    m = (y.argmax(0) == 6).astype(np.uint8) * 255
    return cv2.resize(m, (_LADO_H, _LADO_H), interpolation=cv2.INTER_NEAREST)


def _quitar_holgado(h: np.ndarray, m: np.ndarray) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    borde = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, k)
    fino = cv2.subtract(m, cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))))
    banda = cv2.dilate(cv2.bitwise_or(borde, fino), np.ones((3, 3), np.uint8))
    hsv = cv2.cvtColor(h, cv2.COLOR_BGR2HSV)
    dentro = (m > 0) & (banda == 0)
    hsv[..., 1][dentro] = (hsv[..., 1][dentro] * 0.6).astype(np.uint8)
    return cv2.inpaint(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR), banda, 5, cv2.INPAINT_TELEA)


def analizar_registro(imagen: np.ndarray, puntos5: np.ndarray, cara112: np.ndarray):
    """Devuelve (fracción de gafas, cara112 sin gafas o None)."""
    if not disponible():
        return 0.0, None
    h = _recorte_holgado(imagen, puntos5)
    if h is None:
        return 0.0, None
    m = mascara_holgada(h)
    # solo cuenta la zona central (cara), no el fondo
    c0, c1 = int(_OFF), int(_OFF + 112 * _K)
    frac = float((m[c0:c1, c0:c1] > 0).mean())
    if frac < GAFAS_MIN_FRAC:
        return frac, None
    return frac, _holgado_a_112(_quitar_holgado(h, m))
