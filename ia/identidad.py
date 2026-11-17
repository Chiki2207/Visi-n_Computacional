"""
Paso 3 — Huella de identidad

Una cara no se guarda como la foto completa para comparar.
Se convierte en un vector de números (embedding).

Mejora IA:
  TTA = promediar embeddings de varias versiones leves
  de la misma cara (luz) → más estable.

En fotos grupales / unidas:
  cada cara se recorta y se vuelve a analizar como si fuera
  una foto individual (mismo camino que el registro).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ia.detectar_caras import calidad_de_cara, detectar_caras, ordenar_por_calidad
from ia.mejoras import embedding_con_tta, embedding_registro_aumentado, embeddings_sinteticos, embeddings_degradados
import os as _os

# Plantillas degradadas en el registro (1 = activo)
REG_DEGRADADAS = __import__("os").environ.get("REG_DEGRADADAS", "1") == "1"
# Registro con variantes sintéticas de gafas (1 = activo)
REG_GAFAS = _os.environ.get("REG_GAFAS", "1") == "1"


def normalizar(vector: np.ndarray) -> np.ndarray:
    """Deja el vector con longitud 1 para poder usar producto punto como similitud."""
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norma = np.linalg.norm(vector)
    if norma > 0:
        vector = vector / norma
    return vector


def cara_a_embedding(
    imagen: np.ndarray,
    fila_cara: np.ndarray,
    reconocedor: cv2.FaceRecognizerSF,
    usar_tta: bool = True,
) -> np.ndarray:
    """
    1) Alinea/recorta la cara
    2) la fusión de 1536 números (o el modelo ONNX que esté cargado)
    3) Normaliza el vector
    """
    if usar_tta:
        return embedding_con_tta(imagen, fila_cara, reconocedor)

    cara_alineada = reconocedor.alignCrop(imagen, fila_cara)
    features = reconocedor.feature(cara_alineada)
    return normalizar(features)


def _retrato_aislado(
    imagen: np.ndarray,
    fila_cara: np.ndarray,
) -> np.ndarray:
    """Recorta la cara con margen y la centra en un lienzo cuadrado (como foto sola)."""
    alto, ancho = imagen.shape[:2]
    x, y, w, h = [float(v) for v in fila_cara[:4]]
    pad = 0.5 * max(w, h)
    x1 = max(0, int(x - pad))
    y1 = max(0, int(y - pad))
    x2 = min(ancho, int(x + w + pad))
    y2 = min(alto, int(y + h + pad))
    roi = imagen[y1:y2, x1:x2]
    if roi.size == 0:
        return imagen

    lado = int(max(roi.shape[0], roi.shape[1], 420))
    fondo = int(np.median(roi.reshape(-1, 3), axis=0).mean())
    lienzo = np.full((lado, lado, 3), fondo, dtype=np.uint8)
    oy = (lado - roi.shape[0]) // 2
    ox = (lado - roi.shape[1]) // 2
    lienzo[oy : oy + roi.shape[0], ox : ox + roi.shape[1]] = roi
    return lienzo


def embedding_cara_en_grupo(
    imagen: np.ndarray,
    fila_cara: np.ndarray,
    detector: cv2.FaceDetectorYN,
    reconocedor: cv2.FaceRecognizerSF,
) -> np.ndarray:
    """
    Embedding robusto para foto grupal o collage.

    1) Embedding directo sobre la imagen completa (landmarks originales)
    2) Aísla la cara en un retrato cuadrado, re-detecta y embebe
       (mismo tratamiento que cuando la foto va sola)
    3) Devuelve el promedio normalizado de ambos (más estable)
    """
    directo = cara_a_embedding(imagen, fila_cara, reconocedor, usar_tta=True)

    retrato = _retrato_aislado(imagen, fila_cara)
    caras = detectar_caras(retrato, detector)
    if caras is None or caras.shape[0] == 0:
        return directo

    aislado = cara_a_embedding(
        retrato,
        ordenar_por_calidad(caras)[0],
        reconocedor,
        usar_tta=True,
    )
    return normalizar(0.5 * (directo + aislado))


def describir_cara(
    imagen: np.ndarray,
    fila_cara: np.ndarray,
    reconocedor: cv2.FaceRecognizerSF,
    para_registro: bool = True,
    variantes: bool = True,
) -> dict[str, Any]:
    """
    Empaqueta recuadro + huella + scores para la lista.

    para_registro=True → huella aumentada (ver mejoras.py), pensada
    para compararse luego con las caras del salón.
    """
    x, y, w, h = [float(v) for v in fila_cara[:4]]
    nombres_sint: list[str] = []
    if para_registro:
        embedding = embedding_registro_aumentado(imagen, fila_cara, reconocedor)
        if variantes and REG_GAFAS and getattr(reconocedor, "partes", 1) == 3:
            # Muestras sintéticas (quitar/poner gafas) pegadas al final del vector:
            # [base | var1 | var2 ...] (cada bloque = dimensión del modelo). comparar.py las separa.
            extra = embeddings_sinteticos(imagen, fila_cara, reconocedor)
            if extra:
                nombres_sint = [n for n, _ in extra]
                embedding = np.concatenate([embedding] + [e for _, e in extra])
            if REG_DEGRADADAS:
                # Ronda 17: + 5 plantillas degradadas al final → [base | gafas(1-2) | d18 d24j d30n d24b dosc]
                deg = embeddings_degradados(imagen, fila_cara, reconocedor)
                embedding = np.concatenate([embedding] + deg)
                nombres_sint += ["degradadas"]
    else:
        embedding = cara_a_embedding(imagen, fila_cara, reconocedor, usar_tta=True)

    return {
        "embedding": embedding.astype(float).tolist(),
        "bbox": [x, y, x + w, y + h],
        "det_score": float(fila_cara[14]),
        "quality": calidad_de_cara(fila_cara),
        "synthetic": nombres_sint,
    }
