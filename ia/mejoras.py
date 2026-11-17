"""
Tecnicas de IA para endurecer el reconocimiento:

1) TTA (luz + CLAHE) — más estable en collage / fotos unidas
2) Fusion galeria (max + centroide)
3) Embedding de REGISTRO aumentado: la foto de registro suele ser nitida,
   pero en la foto del salon la cara sale chica / borrosa. Promediamos el
   embedding de la cara original + espejo + versiones achicadas y borrosas,
   asi el vector guardado "se parece" tambien a la cara degradada.
   (Banco de pruebas: menos faltantes sin subir falsos positivos.)
"""

from __future__ import annotations

import os

import cv2
import numpy as np


def _normalizar(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norma = np.linalg.norm(vector)
    if norma > 0:
        vector = vector / norma
    return vector


def _clahe_bgr(cara_bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(cara_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l2 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l)
    return cv2.cvtColor(cv2.merge([l2, a, b]), cv2.COLOR_LAB2BGR)


def _augmentos_cara(cara_bgr: np.ndarray) -> list[np.ndarray]:
    outs = [cara_bgr, _clahe_bgr(cara_bgr)]
    outs.append(cv2.convertScaleAbs(cara_bgr, alpha=1.08, beta=8))
    outs.append(cv2.convertScaleAbs(cara_bgr, alpha=0.92, beta=-8))
    return outs


def _huellas(reconocedor, versiones: list[np.ndarray]) -> list[np.ndarray]:
    """Las mismas huellas que feature() una por una, en un solo lote."""
    if hasattr(reconocedor, "features"):
        lote = reconocedor.features(versiones)
        return [_normalizar(lote[i]) for i in range(len(versiones))]
    return [_normalizar(reconocedor.feature(v)) for v in versiones]


def embedding_con_tta(
    imagen: np.ndarray,
    fila_cara: np.ndarray,
    reconocedor,
) -> np.ndarray:
    cara = reconocedor.alignCrop(imagen, fila_cara)
    vectores = _huellas(reconocedor, _augmentos_cara(cara))
    return _normalizar(np.mean(np.stack(vectores, axis=0), axis=0))


def _achicar(cara_bgr: np.ndarray, lado: int) -> np.ndarray:
    """Simula una cara lejana: baja a `lado` px y vuelve a 112×112."""
    alto, ancho = cara_bgr.shape[:2]
    chica = cv2.resize(cara_bgr, (lado, lado), interpolation=cv2.INTER_AREA)
    return cv2.resize(chica, (ancho, alto), interpolation=cv2.INTER_LINEAR)


def _degradadas_fuertes(cara: np.ndarray) -> list[np.ndarray]:
    rng = np.random.default_rng(0)
    c36 = _achicar(cara, 36)
    ruido = np.clip(c36.astype(np.float32) + rng.normal(0, 8, c36.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", _achicar(cara, 30), [cv2.IMWRITE_JPEG_QUALITY, 35])
    jpg = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    oscura = np.clip(255.0 * (c36 / 255.0) ** 1.8 * 0.8, 0, 255).astype(np.uint8)
    k = np.zeros((7, 7), np.float32); k[3, :] = 1 / 7
    mov = cv2.filter2D(_achicar(cara, 40), -1, k)
    return [
        _achicar(cara, 16), _achicar(cara, 20),
        _achicar(cv2.GaussianBlur(cara, (0, 0), 2.0), 28),
        ruido, jpg, oscura, mov,
    ]


def embedding_registro_aumentado(
    imagen: np.ndarray,
    fila_cara: np.ndarray,
    reconocedor,
) -> np.ndarray:
    """Huella para guardar al registrar (el mismo espacio que la comparación)."""
    return embedding_registro_de_cara(reconocedor.alignCrop(imagen, fila_cara), reconocedor)


def embedding_registro_de_cara(cara: np.ndarray, reconocedor) -> np.ndarray:
    """Lo mismo, partiendo de la cara ya alineada a 112×112."""
    # Incluye 16 y 20 px: el registro "se parece" también a caras del fondo del salón.
    versiones = [
        cara,
        cv2.flip(cara, 1),
        _achicar(cara, 16),
        _achicar(cara, 20),
        _achicar(cara, 24),
        _achicar(cara, 36),
        _achicar(cara, 52),
        cv2.GaussianBlur(cara, (0, 0), 1.5),
    ]
    if os.environ.get("REG_AUG", "normal").lower() == "fuerte":
        # Ronda 5 — más plantillas degradadas (muy chica, blur+chica, ruido, JPEG, poca luz, movimiento)
        versiones += _degradadas_fuertes(cara)
    vectores = _huellas(reconocedor, versiones)
    return _normalizar(np.sum(np.stack(vectores, axis=0), axis=0))


def score_contra_galeria(
    sonda: np.ndarray,
    vectores_persona: list[np.ndarray],
) -> float:
    if not vectores_persona:
        return -1.0
    sims = [float(np.dot(sonda, v)) for v in vectores_persona]
    sim_max = max(sims)
    centro = _normalizar(np.mean(np.stack(vectores_persona, axis=0), axis=0))
    sim_avg = float(np.dot(sonda, centro))
    # Más peso al mejor sample (multi-foto ayuda; un sample malo no arrastra tanto)
    return 0.65 * sim_max + 0.35 * sim_avg


def _std6(cara: np.ndarray) -> list[np.ndarray]:
    return [cara, cv2.flip(cara, 1), _achicar(cara, 24), _achicar(cara, 36), _achicar(cara, 52),
            cv2.GaussianBlur(cara, (0, 0), 1.5)]


# Ronda 16: qué variantes sintéticas se guardan al registrar (sin_gafas / gafas_metal / gafas_negra / contraluz)
VARIANTES_REG = tuple(v.strip() for v in os.environ.get("VARIANTES_REG", "sin_gafas,gafas_metal,gafas_negra").split(",") if v.strip())


def embeddings_sinteticos(imagen: np.ndarray, fila_cara: np.ndarray, reconocedor) -> list[tuple[str, np.ndarray]]:
    """Ronda 16 — variantes de la cara de registro: si tiene gafas → sin gafas; si no → con gafas dibujadas.
    Cada variante se embebe igual que el registro (6 versiones sumadas)."""
    from ia import forma_facial as _forma, gafas

    fila = _forma.fila_realineada(imagen, fila_cara) if _forma.ALINEACION != "5p" else fila_cara
    cara = reconocedor._alinear(imagen, fila)
    frac, sin = gafas.analizar_registro(imagen, np.asarray(fila[4:14], np.float32), cara)
    V: list[tuple[str, np.ndarray]] = []
    if sin is not None:
        V.append(("sin_gafas", sin))
    else:
        V.append(("gafas_metal", gafas.poner_gafas(cara, "metal")))
        V.append(("gafas_negra", gafas.poner_gafas(cara, "negra")))
    V.append(("contraluz", gafas.contraluz(cara)))
    V = [(n, c) for n, c in V if n in VARIANTES_REG]
    if not V:
        return []
    lote = [x for _, c in V for x in _std6(c)]
    E = reconocedor.features(lote)
    return [(n, _normalizar(E[6 * j:6 * j + 6].sum(axis=0))) for j, (n, _) in enumerate(V)]


# Ronda 17: plantillas DEGRADADAS del registro (cara lejana simulada), guardadas aparte (no promediadas).
# comparar.py las usa solo con caras de la foto < DEG_PX px y con castigo PENA_DEGRADADA.
NOMBRES_DEGRADADAS = ("d18", "d24j", "d30n", "d24b", "dosc")


def _variantes_degradadas(c: np.ndarray) -> list[np.ndarray]:
    def sm(l):
        return cv2.resize(c, (l, l), interpolation=cv2.INTER_AREA)

    def up(x):
        return cv2.resize(x, (112, 112), interpolation=cv2.INTER_LINEAR)

    def jpg(x, q):
        return cv2.imdecode(cv2.imencode(".jpg", x, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)

    def ruido(x, s, seed):
        return np.clip(x.astype(np.float32) + np.random.default_rng(seed).normal(0, s, x.shape), 0, 255).astype(np.uint8)

    return [
        up(sm(18)),
        up(jpg(sm(24), 45)),
        up(jpg(ruido(sm(30), 7, 1), 40)),
        up(cv2.resize(cv2.GaussianBlur(c, (0, 0), 1.5), (24, 24), interpolation=cv2.INTER_AREA)),
        up(ruido(np.clip(255 * (sm(30) / 255.0) ** 1.8 * 0.7, 0, 255).astype(np.uint8), 6, 2)),
    ]


def embeddings_degradados(imagen: np.ndarray, fila_cara: np.ndarray, reconocedor) -> list[np.ndarray]:
    from ia import forma_facial as _forma

    fila = _forma.fila_realineada(imagen, fila_cara) if _forma.ALINEACION != "5p" else fila_cara
    cara = reconocedor._alinear(imagen, fila)
    V = _variantes_degradadas(cara)
    lote = [x for v in V for x in (v, cv2.flip(v, 1))]
    E = reconocedor.features(lote)
    return [_normalizar(E[2 * j:2 * j + 2].sum(axis=0)) for j in range(len(V))]
