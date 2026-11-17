"""
Huella de una cara con modelos ONNX (EdgeFace y AdaFace).

Entrada de los tres:
  cara alineada 112×112 con los 5 puntos (ojos, nariz, boca)
  normalizada (pixel − 127.5) / 127.5

Cada uno devuelve 512 números. ReconocedorTrio los pega: 1536.
Se ejecutan con onnxruntime: en la GPU dedicada si la hay (mismos números, verificado
al cargar; ver ia/acelerador.py) y si no en la CPU.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from ia import acelerador
from ia import forma_facial as _forma

# Plantilla estándar de 5 puntos para una cara de 112×112
PLANTILLA_ARCFACE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _normalizar(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norma = np.linalg.norm(vector)
    return vector / norma if norma > 0 else vector


class ReconocedorOnnx:
    """
    Imita la interfaz de cv2.FaceRecognizerSF (alignCrop + feature)
    para que el resto del código no cambie.
    """

    def __init__(self, ruta_modelo: str, entrada_rgb: bool = True, hilos: int = 0) -> None:
        hilos = hilos or int(os.environ.get("ORT_HILOS", "0"))
        # GPU dedicada si la hay y da los mismos números; si no, CPU con estos hilos.
        self.red = acelerador.Red(
            ruta_modelo, hilos, control=acelerador.CONTROL_CARA, denormales_a_cero=True
        )
        self.nombre_entrada = self.red.entrada
        self.entrada_rgb = entrada_rgb
        self.dimension = int(self.sesion.get_outputs()[0].shape[-1])

    @property
    def sesion(self):
        return self.red.sesion

    @property
    def en_gpu(self) -> bool:
        return self.red.en_gpu

    def alignCrop(self, imagen: np.ndarray, fila_cara: np.ndarray) -> np.ndarray:  # noqa: N802
        if _forma.ALINEACION != "5p":
            fila_cara = _forma.fila_realineada(imagen, fila_cara)
        return self._alinear(imagen, fila_cara)

    def _alinear(self, imagen: np.ndarray, fila_cara: np.ndarray) -> np.ndarray:
        """Alinea la cara a 112×112.

        Si la caja es chica (< 48 px), primero recorta con margen, la agranda
        con interpolación cúbica hasta ~64 px de lado y recién ahí hace el warp.
        Así la red no recibe una cara de 14 px estirada a 112 (queda menos
        cuadriculada). En selfies grandes no cambia nada.
        """
        x, y, w, h = [float(v) for v in fila_cara[:4]]
        puntos = np.asarray(fila_cara[4:14], dtype=np.float32).reshape(5, 2)
        lado = min(w, h)
        trabajo = imagen
        if 0 < lado < 48:
            pad = 0.35
            x0 = max(0, int(x - pad * w))
            y0 = max(0, int(y - pad * h))
            x1 = min(imagen.shape[1], int(x + w * (1.0 + pad)))
            y1 = min(imagen.shape[0], int(y + h * (1.0 + pad)))
            recorte = imagen[y0:y1, x0:x1]
            if recorte.size:
                factor = min(4.0, 64.0 / lado)
                trabajo = cv2.resize(
                    recorte, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC
                )
                origen = np.float32([x0, y0])
                puntos = (puntos - origen) * factor
                x, y, w, h = (x - x0) * factor, (y - y0) * factor, w * factor, h * factor
        matriz, _ = cv2.estimateAffinePartial2D(puntos, PLANTILLA_ARCFACE, method=cv2.LMEDS)
        if matriz is None:
            origen = np.float32([[x, y], [x + w, y], [x, y + h]])
            destino = np.float32([[0, 0], [112, 0], [0, 112]])
            matriz = cv2.getAffineTransform(origen, destino)
        return cv2.warpAffine(trabajo, matriz, (112, 112), borderValue=0)

    def features(self, caras: list[np.ndarray]) -> np.ndarray:
        """Cara 112×112 → 512 números (la huella).

        Esos 512 no se leen uno por uno. Al comparar, se multiplican
        por los 512 de la otra foto y se suman: sale un solo número
        entre -1 y 1. Cerca de 1 es la misma persona; cerca de 0, otra.
        """
        lote = np.stack(
            [cv2.cvtColor(c, cv2.COLOR_BGR2RGB) if self.entrada_rgb else c for c in caras]
        ).astype(np.float32)
        lote = ((lote - 127.5) / 127.5).transpose(0, 3, 1, 2)
        salida = self.red.correr_lote(lote)
        return salida / np.linalg.norm(salida, axis=1, keepdims=True)

    def feature(self, cara_alineada: np.ndarray) -> np.ndarray:
        return self.features([cara_alineada])[0:1]

    def embedding_espejo(self, imagen: np.ndarray, fila_cara: np.ndarray) -> np.ndarray:
        """Cara + su espejo, promediados (más estable).

        Si la caja es muy chica (< 24 px), también mete una versión un poco
        borrosa: en el salón esas caras salen movidas y se parece más al registro
        (el registro ya guarda plantillas achicadas/borrosas).
        """
        cara = self.alignCrop(imagen, fila_cara)
        lote = [cara, cv2.flip(cara, 1)]
        if min(float(fila_cara[2]), float(fila_cara[3])) < 24:
            lote.append(cv2.GaussianBlur(cara, (0, 0), 1.2))
        vectores = self.features(lote)
        return _normalizar(vectores.sum(axis=0))

    def embeddings_espejo(self, imagen: np.ndarray, filas: list[np.ndarray]) -> list[np.ndarray]:
        """embedding_espejo de varias caras de una misma foto.

        Cada cara da la misma huella que pidiéndola sola; lo que cambia es la espera.
        En la GPU todas las caras van en un solo lote. En la CPU van una por una, como siempre:
        ahí los lotes grandes rinden menos (medido: el doble de espera con 20 caras).
        """
        if len(filas) == 0:
            return []
        if not self.en_gpu:
            return [self.embedding_espejo(imagen, fila) for fila in filas]
        # Misma regla que embedding_espejo: cara chica (< 24 px) también con blur.
        lotes_por_cara: list[list[np.ndarray]] = []
        for fila in filas:
            cara = self.alignCrop(imagen, fila)
            versions = [cara, cv2.flip(cara, 1)]
            if min(float(fila[2]), float(fila[3])) < 24:
                versions.append(cv2.GaussianBlur(cara, (0, 0), 1.2))
            lotes_por_cara.append(versions)
        plano = [v for versions in lotes_por_cara for v in versions]
        vectores = self.features(plano)
        out = []
        k = 0
        for versions in lotes_por_cara:
            n = len(versions)
            out.append(_normalizar(vectores[k:k + n].sum(axis=0)))
            k += n
        return out


class ReconocedorTrio(ReconocedorOnnx):
    """Tres huellas pegadas: EdgeFace + AdaFace IR-50 + AdaFace IR-101.

    Cada modelo devuelve 512 números. features() los guarda juntos,
    512 + 512 + 512 = 1536, en este orden: EdgeFace, IR-50, IR-101.
    No se comparan como un solo saco de 1536. comparar.py los separa
    otra vez y saca una nota por modelo. La nota final es
    0.18·EdgeFace + 0.12·IR-50 + 0.70·IR-101 (PESOS_FUSION).
    """

    def __init__(self, ruta_edge: str, ruta_ada: str, ruta_ir101: str, entrada_rgb: bool = True, hilos: int = 0) -> None:
        from concurrent.futures import ThreadPoolExecutor

        # Hilos de CPU por red. IR-101 es la más pesada y recibe más. El resultado no cambia con los hilos.
        h50 = int(os.environ.get("ORT_HILOS_IR50", "0")) or hilos
        h101 = int(os.environ.get("ORT_HILOS_IR101", "0")) or hilos
        # Las tres redes se cargan a la vez, cada una en su hilo: el arranque espera a la más lenta, no a la suma.
        with ThreadPoolExecutor(2) as carga:
            tarea_50 = carga.submit(ReconocedorOnnx, ruta_ada, False, h50)        # AdaFace: entrada BGR
            tarea_101 = carga.submit(ReconocedorOnnx, ruta_ir101, False, h101)    # AdaFace IR-101: entrada BGR
            super().__init__(ruta_edge, entrada_rgb, hilos)
            self.ada = tarea_50.result()
            self.ir101 = tarea_101.result()
        self.dimension = 3 * int(self.sesion.get_outputs()[0].shape[-1])
        self.partes = 3
        self._aparte = None

    @property
    def en_gpu(self) -> bool:
        return self.red.en_gpu and self.ada.red.en_gpu and self.ir101.red.en_gpu

    def _edge_y_ir50(self, caras: list[np.ndarray]):
        return ReconocedorOnnx.features(self, caras), self.ada.features(caras)

    def features(self, caras: list[np.ndarray]) -> np.ndarray:
        # a, b, c: 512 números cada uno. Juntos = 1536, sin mezclar los bloques.
        if self.en_gpu:
            # En la GPU van una tras otra: la tarjeta ya reparte el trabajo por dentro.
            a = ReconocedorOnnx.features(self, caras)   # EdgeFace
            b = self.ada.features(caras)                # AdaFace IR-50
            c = self.ir101.features(caras)              # AdaFace IR-101
            return np.concatenate([a, b, c], axis=1) / np.sqrt(3.0)
        # En CPU, EdgeFace e IR-50 corren en otro hilo mientras IR-101 corre en este: mismos números, menos espera.
        if self._aparte is None:
            from concurrent.futures import ThreadPoolExecutor

            self._aparte = ThreadPoolExecutor(1)
        tarea = self._aparte.submit(self._edge_y_ir50, caras)
        c = self.ir101.features(caras)    # AdaFace IR-101
        a, b = tarea.result()             # EdgeFace, AdaFace IR-50
        return np.concatenate([a, b, c], axis=1) / np.sqrt(3.0)
