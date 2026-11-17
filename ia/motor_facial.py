"""
Motor facial — orquestador

Une los pasos en orden:

  leer imagen → detectar caras → huella de 1536 números → comparar
"""

from __future__ import annotations

import os
from typing import Any

import cv2

from ia.comparar import comparar_foto_grupal
from ia.detectar_caras import detectar_caras, detectar_caras_registro, ordenar_por_calidad
from ia.identidad import describir_cara
from ia.leer_imagen import bytes_a_imagen
from ia.modelos import cargar_detector_yunet, cargar_reconocedor_onnx


class MotorFacial:
    """
    Cerebro de IA del proyecto.

    Se crea una vez al arrancar (cargar modelos es lo más lento).
    """

    def __init__(self) -> None:
        self.detector: cv2.FaceDetectorYN | None = None
        self.reconocedor_onnx = None
        self.config_onnx: dict[str, Any] | None = None

    @property
    def nombre_modelo(self) -> str:
        from ia.modelos import MODELO_RECONOCIMIENTO

        return MODELO_RECONOCIMIENTO

    @property
    def listo(self) -> bool:
        return self.detector is not None and self.reconocedor_onnx is not None

    def cargar(self) -> None:
        """Carga YuNet y la fusión EdgeFace + AdaFace (1536 números)."""
        print("[IA] Cargando modelos…")
        self.detector = cargar_detector_yunet()
        self.reconocedor_onnx, self.config_onnx = cargar_reconocedor_onnx()
        if self.reconocedor_onnx is None:
            raise RuntimeError(
                "No hay reconocedor. Hace falta models/edgeface_base.onnx "
                "(y adaface_ir_50.onnx, adaface_ir_101.onnx)."
            )
        print("[IA] Modelos listos: YuNet + fusión EdgeFace / AdaFace")

    def _exigir_listo(self) -> cv2.FaceDetectorYN:
        if not self.listo:
            raise RuntimeError(
                "La IA aún no está cargada. Llama a motor.cargar() al arrancar."
            )
        return self.detector

    def extraer_embedding(self, datos_imagen: bytes, variantes: bool = True) -> dict[str, Any]:
        """
        Caso A — Registro de una persona

        Foto de cara → mejor cara detectada → huella para la lista.
        variantes=False no calcula las muestras de gafas ni las degradadas:
        la lista solo usa los primeros 1536 números, que salen iguales.
        """
        imagen = bytes_a_imagen(datos_imagen)
        n_caras, elegida = self._cara_de_registro(imagen)
        mejor = describir_cara(imagen, elegida, self.reconocedor_onnx, variantes=variantes)

        # La lista solo guarda esta huella. Los otros rectángulos no cambian el parecido.
        return {
            "face_count": n_caras,
            "face": mejor,
            "all_faces": [mejor],
        }

    def _cara_de_registro(self, imagen):
        """Busca las caras de la selfie y elige la del estudiante. Devuelve (cuántas vio, la elegida)."""
        detector = self._exigir_listo()
        caras = detectar_caras_registro(imagen, detector)

        if caras.shape[0] == 0:
            raise ValueError(
                "No se detectó ninguna cara. Usa una foto frontal y nítida."
            )

        from ia import comparar as _cmp
        if _cmp.FILTRO_FALSAS and _cmp.EXTRA_UMBRAL_DUDOSA >= 1 and (caras[:, 14] >= _cmp.DET_SCORE_DUDOSA).any():
            caras = caras[caras[:, 14] >= _cmp.DET_SCORE_DUDOSA]
        elegida = ordenar_por_calidad(caras)[0]
        if os.environ.get("REGISTRO_MEDIAPIPE", "1") == "1":
            try:
                from ia.detectar_caras import elegir_cara_registro
                elegida = elegir_cara_registro(imagen, caras)
            except ValueError:
                pass
        return int(caras.shape[0]), elegida

    # El registro de la lista va en dos pasos para poder hacerlos a la vez con dos selfies distintas:
    # mientras las redes sacan la huella de una, se lee y se alinea la siguiente.
    # El resultado es el mismo de extraer_embedding(..., variantes=False).

    def preparar_registro(self, datos_imagen: bytes) -> dict[str, Any]:
        """Paso 1, sin redes de huella: leer la selfie, elegir la cara y alinearla a 112×112."""
        imagen = bytes_a_imagen(datos_imagen)
        n_caras, elegida = self._cara_de_registro(imagen)
        return {
            "face_count": n_caras,
            "fila": elegida,
            "cara": self.reconocedor_onnx.alignCrop(imagen, elegida),
        }

    def huella_registro(self, preparada: dict[str, Any]) -> dict[str, Any]:
        """Paso 2: la huella de 1536 números de la cara ya alineada."""
        from ia.detectar_caras import calidad_de_cara
        from ia.mejoras import embedding_registro_de_cara

        fila = preparada["fila"]
        x, y, w, h = [float(v) for v in fila[:4]]
        embedding = embedding_registro_de_cara(preparada["cara"], self.reconocedor_onnx)
        mejor = {
            "embedding": embedding.astype(float).tolist(),
            "bbox": [x, y, x + w, y + h],
            "det_score": float(fila[14]),
            "quality": calidad_de_cara(fila),
            "synthetic": [],
        }
        return {"face_count": preparada["face_count"], "face": mejor, "all_faces": [mejor]}

    def quien_esta_y_quien_no(
        self,
        datos_imagen: bytes,
        personas: list[dict[str, Any]],
        umbral: float | None = None,
        devolver_embeddings: bool = False,
    ) -> dict[str, Any]:
        """
        Caso B — Foto grupal

        Detecta caras, las compara con el registro y devuelve
        presentes / ausentes / desconocidas.
        """
        detector = self._exigir_listo()
        imagen = bytes_a_imagen(datos_imagen)
        caras = detectar_caras(imagen, detector)
        cfg = self.config_onnx or {}
        return comparar_foto_grupal(
            imagen=imagen,
            caras=caras,
            reconocedor=self.reconocedor_onnx,
            personas=personas,
            umbral=cfg["umbral"] if umbral is None else umbral,
            detector=detector,
            diferencia_piso=cfg["diferencia_piso"],
            margen_piso=cfg["margen_piso"],
            devolver_embeddings=devolver_embeddings,
        )
