"""
Modelos locales en models/.

  • YuNet                          → dónde hay caras
  • EdgeFace + AdaFace IR-50 + IR-101 → quién es (1536 números)

No se descarga nada al pasar lista. El origen de cada archivo está en docs/FUENTES_MODELOS.md.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2

from ia.reconocedor_onnx import ReconocedorOnnx

CARPETA_MODELOS = Path(__file__).resolve().parent.parent / "models"

ARCHIVO_YUNET = "face_detection_yunet_2023mar.onnx"

# Nota mínima de la fusión (coseno). La configuración actual usa 0.37.
UMBRAL_POR_DEFECTO = 0.37


def _ruta_modelo(nombre_archivo: str) -> Path:
    ruta = CARPETA_MODELOS / nombre_archivo
    if not ruta.exists() or ruta.stat().st_size < 10_000:
        raise FileNotFoundError(
            f"Falta el modelo local: {ruta}\n"
            f"Debe existir en models/. "
            f"Ver docs/FUENTES_MODELOS.md si necesitas reponerlo."
        )
    return ruta


def cargar_detector_yunet() -> cv2.FaceDetectorYN:
    """
    Carga YuNet desde disco.

    Parámetros del create():
      - score_threshold 0.6 → confianza mínima
      - nms_threshold 0.3   → evita recuadros duplicados
      - top_k 5000          → máximo de candidatos
    """
    ruta = _ruta_modelo(ARCHIVO_YUNET)
    print(f"[IA] Cargando YuNet desde {ruta}")

    return cv2.FaceDetectorYN.create(
        str(ruta),
        "",
        (640, 640),
        float(os.environ.get("DET_UMBRAL", "0.6")),
        0.3,
        5000,
    )


# EdgeFace (RGB) + las dos AdaFace (BGR). Juntos: 1536 números.
MODELOS_ONNX = {
    "edgeface": {
        "archivo": "edgeface_base.onnx",
        "rgb": True,
        "umbral": 0.37,
        # 0 = no hay pasada por debajo del umbral. Con 0.04 (antes) una cara ajena
        # podía salir presente con 0.33 si el margen contra el resto era grande.
        "diferencia_piso": float(os.environ.get("DIFERENCIA_PISO", "0")),
        "margen_piso": float(os.environ.get("MARGEN_PISO", "0.12")),
    },
}
MODELO_RECONOCIMIENTO = os.environ.get("MODELO_RECONOCIMIENTO", "edgeface").strip().lower()


def cargar_reconocedor_onnx(nombre: str = MODELO_RECONOCIMIENTO):
    """Devuelve (ReconocedorTrio, config) o (None, None) si falta EdgeFace."""
    config = MODELOS_ONNX.get(nombre)
    if config is None:
        return None, None
    ruta = CARPETA_MODELOS / config["archivo"]
    if os.environ.get("ARCHIVO_EDGEFACE"):
        ruta = Path(os.environ["ARCHIVO_EDGEFACE"])
    if not ruta.exists() or ruta.stat().st_size < 10_000:
        print(f"[IA] No está {ruta.name} (ver docs/FUENTES_MODELOS.md)")
        return None, None
    if os.environ.get("FUSION_ADAFACE", "0") == "1" and os.environ.get("FUSION_IR101", "0") == "1":
        ruta_ada = Path(os.environ.get("ARCHIVO_ADAFACE", str(CARPETA_MODELOS / "adaface_ir_50.onnx")))
        ruta_101 = Path(os.environ.get("ARCHIVO_IR101", str(CARPETA_MODELOS / "adaface_ir_101.onnx")))
        from ia.reconocedor_onnx import ReconocedorTrio
        config = dict(config, umbral=float(os.environ.get("UMBRAL_RECONOCIMIENTO", "0.37")))
        print(f"[IA] Cargando FUSIÓN x3 {ruta.name} + {ruta_ada.name} + {ruta_101.name}")
        return ReconocedorTrio(str(ruta), str(ruta_ada), str(ruta_101), entrada_rgb=config["rgb"]), config
    if os.environ.get("UMBRAL_RECONOCIMIENTO"):
        config = dict(config, umbral=float(os.environ["UMBRAL_RECONOCIMIENTO"]))
    print(f"[IA] Cargando {nombre} desde {ruta}")
    return ReconocedorOnnx(str(ruta), entrada_rgb=config["rgb"]), config
