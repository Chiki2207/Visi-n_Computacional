"""
Caras tapadas por abajo — segunda oportunidad con "media cara"

En un salón de computadores, a quien está sentado al fondo el monitor le tapa la boca y el
mentón. La huella de la cara completa mezcla entonces cara y monitor, y la nota cae a
0.27–0.34 aunque la persona esté en la lista: queda sin nombre.

Aquí se compara solo la parte de arriba (frente, ojos y nariz):

  1) la cara de la foto, ya alineada a 112×112, se pone en negro de la fila Y0 hacia abajo;
  2) la cara de registro de cada alumno se tapa igual (nítida y también achicada al tamaño
     de la cara de la foto, con JPEG) y se saca su huella;
  3) se comparan esas dos "medias caras" con los mismos tres modelos y los mismos pesos.

No baja el umbral ni se usa sola. Una cara solo recibe nombre por esta vía si:

  • quedó sin nombre en la comparación normal y no es dudosa (los dos detectores la ven);
  • con la cara completa ya iba primero ese mismo alumno, con nota ≥ NOTA_NORMAL, en los
    tres modelos, y ese alumno no está puesto en otra cara de la foto;
  • con media cara vuelve a ir primero el mismo alumno en los tres modelos, con nota ≥ NOTA
    (el mismo 0.37 de siempre), con ventaja ≥ MARGEN sobre el segundo y separado del resto
    de la lista (z ≥ Z).

Solo cuesta tiempo cuando alguna cara cumple la primera parte; si no, no corre ninguna red.
RESCATE_TAPADA=0 lo apaga.
"""

from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np

ACTIVO = os.environ.get("RESCATE_TAPADA", "0") == "1"
# Fila de corte en la cara alineada de 112 (ojos ≈ 52, punta de la nariz ≈ 72, boca ≈ 92).
Y0 = int(os.environ.get("TAPADA_Y0", "76"))
NOTA_NORMAL = float(os.environ.get("TAPADA_NOTA_NORMAL", "0.25"))  # nota mínima con la cara completa
NOTA = float(os.environ.get("TAPADA_NOTA", "0.37"))                # nota mínima con media cara
MARGEN = float(os.environ.get("TAPADA_MARGEN", "0.20"))            # ventaja sobre el segundo, con media cara
Z = float(os.environ.get("TAPADA_Z", "5.5"))                       # separación del resto de la lista
# Ancho de cara (px) en que se usa. Por debajo de 18 px media cara ya no alcanza para distinguir
# (medido: un parecido de 14 px llegó a 0.38); por encima de 70 px no se midió.
MIN_PX = float(os.environ.get("TAPADA_MIN_PX", "18"))
MAX_PX = float(os.environ.get("TAPADA_MAX_PX", "70"))
MIN_RIVALES = 5        # con menos alumnos en la lista no hay "resto" contra el cual medir la separación
LADOS = (24, 32, 40)   # tamaños a los que se achica la cara de registro (lado ≈ 1.5 × ancho de la cara en la foto)


def _partes(v: np.ndarray) -> np.ndarray:
    """1536 números → 3 bloques de 512, cada uno con longitud 1."""
    v = np.asarray(v, dtype=np.float32).reshape(3, -1)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def _tapar(cara: np.ndarray) -> np.ndarray:
    media = cara.copy()
    media[Y0:] = 0
    return media


def _achicar(cara: np.ndarray, lado: int) -> np.ndarray:
    """La cara de registro como se vería lejos: `lado` px, JPEG 75 y de vuelta a 112 como lo hace el motor."""
    chica = cv2.resize(cara, (lado, lado), interpolation=cv2.INTER_AREA)
    chica = cv2.imdecode(cv2.imencode(".jpg", chica, [cv2.IMWRITE_JPEG_QUALITY, 75])[1], cv2.IMREAD_COLOR)
    factor = min(4.0, 96.0 / lado)
    media = cv2.resize(chica, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    return cv2.resize(media, (112, 112), interpolation=cv2.INTER_LINEAR)


def _lado_para(ancho: float) -> int:
    """Tamaño de registro que corresponde a una cara de `ancho` px (0 = solo la nítida)."""
    if 1.5 * ancho > 46:
        return 0
    return min(LADOS, key=lambda lado: abs(lado - 1.5 * ancho))


def _huellas(reconocedor, caras: list[np.ndarray]) -> list[np.ndarray]:
    """Huella (3×512) de cada cara: la cara y su espejo, sumadas."""
    lote = [x for c in caras for x in (c, cv2.flip(c, 1))]
    e = np.concatenate([reconocedor.features(lote[i:i + 6]) for i in range(0, len(lote), 6)])
    return [_partes(e[2 * i] + e[2 * i + 1]) for i in range(len(caras))]


def _plantillas(reconocedor, personas: list[dict[str, Any]], lado: int) -> np.ndarray:
    """Media cara de registro de cada alumno, (N, 3, 512). Se guarda en el alumno para la siguiente cara."""
    for tam in ((0, lado) if lado else (0,)):
        faltan = [p for p in personas if tam not in p.setdefault("_tapadas", {})]
        if faltan:
            caras = [_tapar(_achicar(p["cara"], tam) if tam else p["cara"]) for p in faltan]
            for p, h in zip(faltan, _huellas(reconocedor, caras)):
                p["_tapadas"][tam] = h
    if not lado:
        return np.stack([p["_tapadas"][0] for p in personas])
    suma = np.stack([p["_tapadas"][0] + p["_tapadas"][lado] for p in personas])
    return suma / np.maximum(np.linalg.norm(suma, axis=2, keepdims=True), 1e-9)


def _primero(notas: np.ndarray) -> tuple[int, float, float, float]:
    """(quién va primero, su nota, ventaja sobre el segundo, z contra el resto)."""
    orden = np.argsort(-notas)
    k = int(orden[0])
    resto = np.delete(notas, k)
    z = (notas[k] - resto.mean()) / max(float(resto.std()), 1e-6)
    return k, float(notas[k]), float(notas[k] - notas[orden[1]]), float(z)


def rescatar(
    imagen: np.ndarray,
    orden: list,
    entradas: list[dict[str, Any]],
    asignaciones: list[tuple],
    por_modelo: list,
    dudosas: set[int],
    dos_det: list[bool],
    reconocedor,
    personas: list[dict[str, Any]],
    galeria: dict[str, dict[str, Any]],
    pesos: list[float],
) -> list[tuple]:
    """Devuelve las asignaciones con las caras tapadas que se pudieron confirmar con media cara."""
    ids = list(galeria.keys())
    por_id = {p["id"]: p for p in personas}
    if len(ids) < MIN_RIVALES + 1 or any(por_id.get(i, {}).get("cara") is None for i in ids):
        return asignaciones
    w3 = np.asarray(pesos, dtype=np.float32)
    w3 = w3 / w3.sum()
    usados = {a[0] for a in asignaciones if a[0] is not None}

    # 1) Con la cara completa: caras sin nombre cuyo primer candidato está libre y es el mismo en los tres modelos.
    candidatas = []
    for i, asig in enumerate(asignaciones):
        if asig[0] is not None or por_modelo[i] is None or i in dudosas or not dos_det[i]:
            continue
        ancho = float(orden[i][2])
        if not (MIN_PX <= ancho <= MAX_PX):
            continue
        notas3 = np.array([[por_modelo[i][0][k][p] for p in ids] for k in range(3)], dtype=np.float32)
        k0, nota0, _, _ = _primero(w3 @ notas3)
        if nota0 < NOTA_NORMAL or ids[k0] in usados or not (notas3.argmax(axis=1) == k0).all():
            continue
        candidatas.append((i, k0, ancho))
    if not candidatas:
        return asignaciones

    # 2) Con media cara: tiene que volver a ganar el mismo alumno, y claro.
    confirmadas = []
    for i, k0, ancho in candidatas:
        cara = reconocedor.alignCrop(imagen, orden[i])
        sonda = _huellas(reconocedor, [_tapar(cara)])[0]
        plantillas = _plantillas(reconocedor, [por_id[p] for p in ids], _lado_para(ancho))
        notas3 = np.einsum("nkd,kd->kn", plantillas, sonda)
        k1, nota1, margen1, z1 = _primero(w3 @ notas3)
        if k1 != k0 or nota1 < NOTA or margen1 < MARGEN or z1 < Z:
            continue
        if not (notas3.argmax(axis=1) == k0).all():
            continue
        confirmadas.append((nota1, i, ids[k0], margen1))

    salida = list(asignaciones)
    for nota1, i, pid, margen1 in sorted(confirmadas, reverse=True):
        if pid in usados:
            continue
        salida[i] = (pid, galeria[pid]["name"], nota1, margen1)
        entradas[i]["via"] = "media_cara"
        usados.add(pid)
    return salida
