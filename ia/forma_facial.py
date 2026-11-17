"""
Ronda 4 — Forma de la cara 2D/3D (tipo NEC NeoFace) con MediaPipe Face Landmarker
(Apache-2.0, 478 puntos 3D + matriz de pose). Todo opcional, por variables de entorno.

  ALINEACION = 5p (YuNet, por defecto) | denso (5 puntos re-estimados con la malla densa)
               | mezcla (promedio YuNet + malla)
  POSE_AUG   = 0 | N  -> en el REGISTRO añade vistas giradas ±yaw (grados) por malla 3D
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

ALINEACION = os.environ.get("ALINEACION", "mezcla").strip().lower()
LADO_MIN = float(os.environ.get("MALLA_LADO_MIN", "0"))  # ancho mínimo de cara (px) para usar la malla
_RUTA = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"
_lm = None

OJO_I = [33, 133, 159, 145, 160, 144, 158, 153]
OJO_D = [362, 263, 386, 374, 387, 373, 385, 380]
NARIZ, BOCA_I, BOCA_D = 1, 61, 291


def disponible() -> bool:
    if not _RUTA.exists():
        return False
    try:
        import mediapipe  # noqa: F401
    except Exception:  # sin mediapipe → se usa YuNet 5 puntos
        return False
    return True


def _detector():
    global _lm
    if _lm is None:
        from mediapipe.tasks.python import BaseOptions, vision

        op = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(_RUTA)),
            output_facial_transformation_matrixes=True,
            num_faces=3,
            min_face_detection_confidence=0.3,
            min_face_presence_confidence=0.3,
        )
        _lm = vision.FaceLandmarker.create_from_options(op)
    return _lm


def malla(imagen: np.ndarray, fila_cara: np.ndarray):
    """Devuelve (puntos 478x3 en coords de la imagen, matriz 4x4 de pose) o None."""
    import mediapipe as mp

    alto, ancho = imagen.shape[:2]
    x, y, w, h = [float(v) for v in fila_cara[:4]]
    pad = 0.7 * max(w, h)
    x1, y1 = int(max(0, x - pad)), int(max(0, y - pad))
    x2, y2 = int(min(ancho, x + w + pad)), int(min(alto, y + h + pad))
    roi = imagen[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    s = 256.0 / max(roi.shape[:2])
    roi = cv2.resize(roi, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    rgb = np.ascontiguousarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
    r = _detector().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not r.face_landmarks:
        return None
    cx, cy = (x + w / 2 - x1) * s, (y + h / 2 - y1) * s
    H, W = roi.shape[:2]
    mejor = None
    for k, lms in enumerate(r.face_landmarks):
        p = np.array([[l.x * W, l.y * H, l.z * W] for l in lms], np.float32)
        d = np.hypot(p[:, 0].mean() - cx, p[:, 1].mean() - cy)
        if mejor is None or d < mejor[0]:
            mejor = (d, p, k)
    d, p, k = mejor
    if d > 0.5 * w * s:
        return None
    p[:, 0] = p[:, 0] / s + x1
    p[:, 1] = p[:, 1] / s + y1
    p[:, 2] = p[:, 2] / s
    M = np.array(r.facial_transformation_matrixes[k]) if r.facial_transformation_matrixes else None
    return p, M


def cinco_puntos(p: np.ndarray) -> np.ndarray:
    return np.array([p[OJO_I, :2].mean(0), p[OJO_D, :2].mean(0), p[NARIZ, :2], p[BOCA_I, :2], p[BOCA_D, :2]], np.float32)


def pose_grados(M) -> tuple[float, float, float]:
    """(yaw, pitch, roll) en grados a partir de la matriz de MediaPipe."""
    if M is None:
        return 0.0, 0.0, 0.0
    R = np.asarray(M)[:3, :3]
    yaw = np.degrees(np.arctan2(-R[2, 0], np.hypot(R[2, 1], R[2, 2])))
    pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
    roll = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    return float(yaw), float(pitch), float(roll)


def fila_realineada(imagen: np.ndarray, fila_cara: np.ndarray, modo: str | None = None):
    """Fila YuNet con los 5 puntos reemplazados según ALINEACION (o la original)."""
    modo = modo or ALINEACION
    if modo == "5p" or not disponible() or float(fila_cara[2]) < LADO_MIN:
        return fila_cara
    m = malla(imagen, fila_cara)
    if m is None:
        return fila_cara
    cinco = cinco_puntos(m[0])
    f = np.array(fila_cara, np.float32).copy()
    yu = f[4:14].reshape(5, 2)
    nuevo = cinco if modo == "denso" else (yu + cinco) / 2
    f[4:14] = nuevo.reshape(-1)
    return f
