"""
Verificación de caras NO reconocidas (quita "caras que no son": manos, ropa, lámparas,
sillas, techo, letras de carteles).

Solo se aplica a las detecciones que NO quedaron asignadas a ningún alumno. Las caras
reconocidas nunca se tocan, así que presentes y ausentes no cambian.

Una detección no reconocida se conserva solo si:
  1) ancho >= VERIF_MIN_PX (14 px), o más angosta si YuNet (>= CHICA_DET) y RetinaFace coinciden
  2) no está montada sobre otra caja ya aceptada
  3) YuNet ya estaba muy seguro (det >= 0.90) o RetinaFace ve la cara (>= RETINA_CONS)
  4) si mide >= FAS_PX, MiniFASNet dice que es una cara real y no impresa o en pantalla
VERIFICAR_CARAS=0 lo apaga.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

VERIFICAR = os.environ.get("VERIFICAR_CARAS", "1") == "1"
VERIF_MIN_PX = float(os.environ.get("VERIF_MIN_PX", "14"))
VERIF_CONSENSO = float(os.environ.get("VERIF_CONSENSO", "0.30"))
VERIF_DET_OK = float(os.environ.get("VERIF_DET_OK", "0.90"))
VERIF_NMS = float(os.environ.get("VERIF_NMS", "0.30"))
CHICA_DET = float(os.environ.get("CHICA_DET", "0.80"))  # YuNet seguro; con RetinaFace de acuerdo, la caja se conserva aunque sea angosta

# Anti-spoofing (caras impresas / posters / pantallas) SOLO para NO reconocidas grandes:
# MiniFASNetV2 (2.7x) + MiniFASNetV1SE (4.0x) de Silent-Face-Anti-Spoofing (minivision, Apache-2.0), 80x80.
FAS_ACTIVO = os.environ.get("FAS_ACTIVO", "0") == "1"
FAS_PX = float(os.environ.get("FAS_PX", "80"))
FAS_UMBRAL = float(os.environ.get("FAS_UMBRAL", "0.5"))

_MODELOS = Path(__file__).resolve().parent.parent / "models"
_RUTAS_FAS = [(2.7, _MODELOS / "minifasnet_v2_2.7_80x80.onnx"), (4.0, _MODELOS / "minifasnet_v1se_4.0_80x80.onnx")]
_fas = None

# RetinaFace como juez de las cajas que nadie reconoció.
# Se corre una vez por foto, en teselas de 1024 px.
RETINA_VERIF = os.environ.get("RETINA_VERIF", "0") == "1"
RETINA_CONS = float(os.environ.get("RETINA_CONS", "0.5"))
RETINA_DET = None      # detecciones RetinaFace de la foto actual (N×15)

_yunet = None


def preparar_retina(imagen, caras_yunet=None):
    global RETINA_DET
    RETINA_DET = None
    if not RETINA_VERIF:
        return
    try:
        from ia import retina_caras
        RETINA_DET = retina_caras.detectar_teselas(imagen, 1.0, umbral=0.2)
    except Exception as e:  # sin el archivo, se sigue solo con YuNet
        print(f"[IA] RetinaFace no disponible ({e})")
        RETINA_DET = None


def _retina_score(fila) -> float:
    if RETINA_DET is None or not len(RETINA_DET):
        return 0.0
    return float(max([r[14] for r in RETINA_DET if _iou(r, fila) >= 0.4] or [0.0]))


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _contencion(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    m = min(a[2] * a[3], b[2] * b[3])
    return inter / m if m > 0 else 0.0


def _recorte(imagen, fila, pad, lado):
    alto, ancho = imagen.shape[:2]
    x, y, w, h = [float(v) for v in fila[:4]]
    s = max(w, h); p = pad * s
    x1, y1 = int(max(0, x - p)), int(max(0, y - p))
    x2, y2 = int(min(ancho, x + w + p)), int(min(alto, y + h + p))
    c = imagen[y1:y2, x1:x2]
    if c.size == 0:
        return None, None
    k = lado / max(1.0, s)
    nw, nh = max(8, int(c.shape[1] * k)), max(8, int(c.shape[0] * k))
    c = cv2.resize(c, (nw, nh), interpolation=cv2.INTER_CUBIC if k > 1 else cv2.INTER_AREA)
    return c, [(x - x1) * k, (y - y1) * k, w * k, h * k]


def _yunet_zoom(imagen, fila) -> float:
    """Sin RetinaFace: YuNet otra vez sobre un recorte ampliado (cara a ~96 px)."""
    global _yunet
    if _yunet is None:
        from ia.modelos import cargar_detector_yunet
        _yunet = cargar_detector_yunet()
        _yunet.setScoreThreshold(0.2)
    c, caja = _recorte(imagen, fila, 0.8, 96)
    if c is None:
        return 0.0
    _yunet.setInputSize((c.shape[1], c.shape[0]))
    _, d = _yunet.detect(c)
    if d is None:
        return 0.0
    return float(max([r[14] for r in d if _iou(r, caja) > 0.4] or [0.0]))


def _fas_sesiones():
    global _fas
    if _fas is None:
        _fas = []
        try:
            import onnxruntime as ort
            so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.log_severity_level = 3
            for esc, ruta in _RUTAS_FAS:
                if ruta.exists():
                    _fas.append((esc, ort.InferenceSession(str(ruta), so, providers=["CPUExecutionProvider"])))
        except Exception as e:
            print(f"[IA] Anti-spoofing no disponible ({e})")
        if not _fas:
            print("[IA] Anti-spoofing: modelos MiniFASNet no encontrados; se omite")
    return _fas


def _recorte_fas(imagen, fila, escala):
    """Igual que CropImage de Silent-Face: caja escalada (sin salirse de la foto) → 80x80 BGR."""
    alto, ancho = imagen.shape[:2]
    x, y, w, h = [float(v) for v in fila[:4]]
    w = max(1.0, int(w)); h = max(1.0, int(h)); x = int(x); y = int(y)
    escala = min((alto - 1) / h, min((ancho - 1) / w, escala))
    nw, nh = w * escala, h * escala; cx, cy = w / 2 + x, h / 2 + y
    x1, y1, x2, y2 = cx - nw / 2, cy - nh / 2, cx + nw / 2, cy + nh / 2
    if x1 < 0: x2 -= x1; x1 = 0
    if y1 < 0: y2 -= y1; y1 = 0
    if x2 > ancho - 1: x1 -= x2 - ancho + 1; x2 = ancho - 1
    if y2 > alto - 1: y1 -= y2 - alto + 1; y2 = alto - 1
    c = imagen[int(y1): int(y2) + 1, int(x1): int(x2) + 1]
    return cv2.resize(c, (80, 80)) if c.size else None


def prob_cara_real(imagen, fila) -> float | None:
    """Prob. (0..1) de que la cara sea real y no impresa/pantalla. None si no hay modelos."""
    ses = _fas_sesiones()
    if not ses:
        return None
    ps = []
    for esc, s in ses:
        c = _recorte_fas(imagen, fila, esc)
        if c is None:
            continue
        z = s.run(None, {s.get_inputs()[0].name: c.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
        e = np.exp(z - z.max()); ps.append(float(e[1] / e.sum()))
    return float(np.mean(ps)) if ps else None


def conservar_no_reconocidas(imagen, filas: list, sondas: list, asignadas: list[bool]) -> list[bool]:
    """Devuelve, por detección, si se conserva. Las asignadas siempre se conservan."""
    n = len(filas)
    if not VERIFICAR or n == 0:
        return [True] * n
    dets = np.array([float(f[14]) for f in filas]); anchos = np.array([float(f[2]) for f in filas])
    keep = [bool(a) for a in asignadas]
    # primero las reconocidas, luego el resto por score de detección
    orden = [i for i in range(n) if asignadas[i]] + sorted((i for i in range(n) if not asignadas[i]), key=lambda i: -dets[i])
    aceptadas = [i for i in range(n) if asignadas[i]]
    for i in orden:
        if asignadas[i]:
            continue
        f = filas[i]
        if anchos[i] < VERIF_MIN_PX and not (
            RETINA_VERIF and RETINA_DET is not None and dets[i] >= CHICA_DET and _retina_score(f) >= RETINA_CONS
        ):
            continue   # muy angosta y sin que los dos detectores la confirmen
        if any(_contencion(f, filas[j]) > VERIF_NMS for j in aceptadas):
            continue
        if RETINA_VERIF and RETINA_DET is not None:
            if dets[i] < VERIF_DET_OK and _retina_score(f) < RETINA_CONS:
                continue
        elif dets[i] < VERIF_DET_OK and _yunet_zoom(imagen, f) < VERIF_CONSENSO:
            continue
        if FAS_ACTIVO and anchos[i] >= FAS_PX:
            pr = prob_cara_real(imagen, f)
            if pr is not None and pr < FAS_UMBRAL:
                continue   # cara impresa, póster o pantalla
        keep[i] = True
        aceptadas.append(i)
    return keep
