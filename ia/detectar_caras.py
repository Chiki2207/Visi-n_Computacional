"""
Paso 2 — Detectar caras (YuNet)

Entrada: una foto completa
Salida: lista de caras con:
  - posición (x, y, ancho, alto)
  - puntos de ojos / nariz / boca (landmarks)
  - score de confianza

Tip: la foto se AGRANDA (x2, hasta 4096 px de ancho) antes de detectar.
YuNet pierde caras de menos de ~20 px; al agrandar, las caras lejanas
o pequeñas de una foto de salón pasan a ser detectables.
(Banco de pruebas: recall de detección 0.79 → 1.00 en fotos 4K con caras de 22–40 px.)
"""

from __future__ import annotations

import os

import cv2
import numpy as np

# Agrandamos la foto antes de detectar (caras chicas / lejanas)
FACTOR_AUMENTO = 2.0
# Tope de ancho de trabajo (más grande = más lento en CPU)
ANCHO_MAXIMO = 4096


# Ronda 7 — detección multi-suavizado para fotos oscuras/ruidosas/llenas.
# DETECCION=normal (por defecto) | multi
DETECCION = os.environ.get("DETECCION", "normal").strip().lower()
MULTI_SIGMAS = tuple(float(v) for v in os.environ.get("MULTI_SIGMAS", "1.5,2.5,3.5").split(","))
MULTI_UMBRAL = float(os.environ.get("MULTI_UMBRAL", "0.1"))
MULTI_SCORE_OK = float(os.environ.get("MULTI_SCORE_OK", "0.5"))
MULTI_MAX_EXTRA = int(os.environ.get("MULTI_MAX_EXTRA", "150"))


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _suavizar_gamma(imagen: np.ndarray, sigma: float) -> np.ndarray:
    if sigma > 0:
        imagen = cv2.GaussianBlur(imagen, (0, 0), sigma)
    media = max(1.0, float(cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY).mean()))
    g = float(np.clip(np.log(100 / 255) / np.log(media / 255), 0.3, 1.0))
    lut = np.clip(255 * (np.arange(256) / 255.0) ** g, 0, 255).astype(np.uint8)
    return cv2.LUT(imagen, lut)


def _detectar_multi(imagen, detector, base: np.ndarray) -> np.ndarray:
    """Une las caras normales con las halladas tras suavizar (σ) + gamma; una cara extra se acepta
    si la ven >=2 versiones o su score >= MULTI_SCORE_OK. Las extra llevan score real (<0.8 → 'dudosas')."""
    umbral_orig = float(detector.getScoreThreshold())
    detector.setScoreThreshold(MULTI_UMBRAL)
    filas = []
    try:
        for k, sg in enumerate(MULTI_SIGMAS):
            for r in _detectar_basico(_suavizar_gamma(imagen, sg), detector):
                filas.append((k, r))
    finally:
        detector.setScoreThreshold(umbral_orig)
    filas.sort(key=lambda t: -t[1][14])
    grupos: list[dict] = []
    for k, r in filas:
        for g in grupos:
            if _iou(r, g["r"]) > 0.35:
                g["ks"].add(k)
                break
        else:
            grupos.append({"r": r, "ks": {k}})
    salida = [r for r in base]
    extra = []
    for g in grupos:
        if len(g["ks"]) >= 2 or g["r"][14] >= MULTI_SCORE_OK:
            if all(_iou(g["r"], o) < 0.3 for o in salida) and all(_iou(g["r"], o) < 0.3 for o in extra):
                extra.append(g["r"])
    extra = extra[:MULTI_MAX_EXTRA]
    return np.array(salida + extra, dtype=np.float32).reshape(-1, 15)


# PIRÁMIDE: YuNet ve mal las caras MUY grandes (selfie / primer plano): al agrandar ×2 la cara
# pasa de ~250 px de lado y salen cajas corridas con score <0.5 (la persona queda "dudosa" → ausente).
# Pasada extra con la foto achicada a PIRAMIDE_ANCHO px: si allí aparece una cara GRANDE (lado en la escala
# de trabajo > PIRAMIDE_LADO px) con mejor score, reemplaza a las cajas que la pisan. Las caras chicas
# (fotos de salón) no se tocan → mismo resultado que r15 en los bancos.
PIRAMIDE = os.environ.get("PIRAMIDE", "1") == "1"
PIRAMIDE_ANCHO = int(os.environ.get("PIRAMIDE_ANCHO", "640"))
PIRAMIDE_LADO = float(os.environ.get("PIRAMIDE_LADO", "300"))
# solo reemplaza si las cajas originales que la pisan son malas (score < esto)
PIRAMIDE_REEMPLAZA = float(os.environ.get("PIRAMIDE_REEMPLAZA", "0.80"))


def _solapa(a, b) -> float:
    """intersección / área de la caja más chica"""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    m = min(a[2] * a[3], b[2] * b[3])
    return inter / m if m > 0 else 0.0


def _escala_trabajo(ancho: int, ancho_maximo: int = ANCHO_MAXIMO, factor_aumento: float = FACTOR_AUMENTO) -> float:
    a = min(max(int(ancho * factor_aumento), 640), max(ancho_maximo, ancho))
    return a / ancho


def _detectar_piramide(imagen, detector, base: np.ndarray) -> np.ndarray:
    alto, ancho = imagen.shape[:2]
    esc_base = _escala_trabajo(ancho)
    if ancho <= PIRAMIDE_ANCHO * 0.9:
        return base
    W = PIRAMIDE_ANCHO; H = max(1, int(round(alto * W / ancho))); f = ancho / W
    detector.setInputSize((W, H))
    _, c = detector.detect(cv2.resize(imagen, (W, H), interpolation=cv2.INTER_AREA))
    if c is None:
        return base
    c = c.copy(); c[:, 0:14] *= f
    grandes = [r for r in c if float(r[2]) * esc_base > PIRAMIDE_LADO]
    if not grandes:
        return base
    filas = [r for r in base]
    for g in grandes:
        pisa = [r for r in filas if _iou(g, r) > 0.3 or _solapa(g, r) > 0.5]
        if pisa and max(float(r[14]) for r in pisa) >= min(float(g[14]), PIRAMIDE_REEMPLAZA):
            continue
        filas = [r for r in filas if not any(r is q for q in pisa)] + [g]
    return np.array(filas, dtype=np.float32).reshape(-1, 15)


def detectar_caras(
    imagen: np.ndarray,
    detector: cv2.FaceDetectorYN,
    ancho_maximo: int = ANCHO_MAXIMO,
    factor_aumento: float = FACTOR_AUMENTO,
) -> np.ndarray:
    base = _detectar_basico(imagen, detector, ancho_maximo, factor_aumento)
    if DETECCION == "multi" and imagen.shape[1] >= 1000:
        base = _detectar_multi(imagen, detector, base)
    if PIRAMIDE:
        base = _detectar_piramide(imagen, detector, base)
    return base


def _detectar_basico(
    imagen: np.ndarray,
    detector: cv2.FaceDetectorYN,
    ancho_maximo: int = ANCHO_MAXIMO,
    factor_aumento: float = FACTOR_AUMENTO,
) -> np.ndarray:
    """
    Busca todas las caras en la imagen.

    Returns:
        Matriz N×15 (una fila por cara). Si no hay caras → vacío.
        Columnas importantes:
          0..3  → x, y, ancho, alto del recuadro
          4..13 → landmarks (ojos, nariz, comisuras)
          14    → score de detección (0..1)
    """
    alto_original, ancho_original = imagen.shape[:2]

    # Agrandamos (x2) pero sin pasar del tope; nunca menos de 640
    ancho_deseado = int(ancho_original * factor_aumento)
    ancho_trabajo = min(max(ancho_deseado, 640), max(ancho_maximo, ancho_original))
    alto_trabajo = int(alto_original * (ancho_trabajo / ancho_original))

    detector.setInputSize((ancho_trabajo, alto_trabajo))

    if (ancho_trabajo, alto_trabajo) != (ancho_original, alto_original):
        interpolacion = (
            cv2.INTER_CUBIC if ancho_trabajo > ancho_original else cv2.INTER_AREA
        )
        imagen_trabajo = cv2.resize(
            imagen, (ancho_trabajo, alto_trabajo), interpolation=interpolacion
        )
    else:
        imagen_trabajo = imagen

    _, caras = detector.detect(imagen_trabajo)

    if caras is None:
        return np.empty((0, 15), dtype=np.float32)

    # Las coordenadas salieron en tamaño "trabajo".
    # Las devolvemos al tamaño real de la foto original.
    escala_x = ancho_original / ancho_trabajo
    escala_y = alto_original / alto_trabajo
    caras = caras.copy()

    caras[:, 0] *= escala_x  # x
    caras[:, 1] *= escala_y  # y
    caras[:, 2] *= escala_x  # ancho
    caras[:, 3] *= escala_y  # alto

    # landmarks: pares (x, y)
    for i in range(4, 14, 2):
        caras[:, i] *= escala_x
        caras[:, i + 1] *= escala_y

    return caras


# Geometría para descartar logos, brazos y ruido que YuNet marca como cara.
CARA_MIN_MATCH_PX = float(os.environ.get("CARA_MIN_MATCH_PX", os.environ.get("CARA_MIN_PX", "48")))
# Brazos/codos suelen venir con score ~0.55-0.65; caras reales de salon >0.85
DET_SCORE_MATCH = float(os.environ.get("DET_SCORE_MATCH", "0.72"))


def parece_cara_humana(fila_cara: np.ndarray) -> bool:
    """True si el recuadro parece una cara real (tamano, score, landmarks)."""
    x, y, w, h = [float(v) for v in fila_cara[:4]]
    score = float(fila_cara[14])
    if min(w, h) < CARA_MIN_MATCH_PX:
        return False
    if score < DET_SCORE_MATCH:
        return False
    ar = w / max(h, 1.0)
    if ar < 0.55 or ar > 1.75:
        return False
    for i in range(4, 14, 2):
        lx, ly = float(fila_cara[i]), float(fila_cara[i + 1])
        if lx < x - 0.25 * w or lx > x + w + 0.25 * w:
            return False
        if ly < y - 0.25 * h or ly > y + h + 0.25 * h:
            return False
    le_x, le_y = float(fila_cara[4]), float(fila_cara[5])
    re_x, re_y = float(fila_cara[6]), float(fila_cara[7])
    nose_x, nose_y = float(fila_cara[8]), float(fila_cara[9])
    ml_y, mr_y = float(fila_cara[11]), float(fila_cara[13])
    eye = abs(le_x - re_x)
    if eye < 0.28 * w or eye > 0.85 * w:
        return False
    if abs(le_y - re_y) > 0.35 * max(eye, 1.0):
        return False
    mid_eye_y = 0.5 * (le_y + re_y)
    mouth_y = 0.5 * (ml_y + mr_y)
    if not (mid_eye_y + 0.04 * h < nose_y < mouth_y - 0.02 * h):
        return False
    if mouth_y - mid_eye_y < 0.22 * h:
        return False
    if nose_x < min(le_x, re_x) - 0.15 * w or nose_x > max(le_x, re_x) + 0.15 * w:
        return False
    return True


def filtrar_caras_creibles(caras: np.ndarray) -> np.ndarray:
    """Quita falsos positivos (logos, texturas) antes de reconocer / contar."""
    if caras is None or caras.size == 0:
        return np.empty((0, 15), dtype=np.float32)
    keep = [caras[i] for i in range(caras.shape[0]) if parece_cara_humana(caras[i])]
    if not keep:
        return np.empty((0, 15), dtype=np.float32)
    return np.array(keep, dtype=np.float32).reshape(-1, 15)


def _geometria_cara_ok(fila_cara: np.ndarray, min_score: float) -> bool:
    x, y, w, h = [float(v) for v in fila_cara[:4]]
    score = float(fila_cara[14])
    if min(w, h) < 40:
        return False
    if score < min_score:
        return False
    ar = w / max(h, 1.0)
    if ar < 0.55 or ar > 1.75:
        return False
    for i in range(4, 14, 2):
        lx, ly = float(fila_cara[i]), float(fila_cara[i + 1])
        if lx < x - 0.25 * w or lx > x + w + 0.25 * w:
            return False
        if ly < y - 0.25 * h or ly > y + h + 0.25 * h:
            return False
    le_x, le_y = float(fila_cara[4]), float(fila_cara[5])
    re_x, re_y = float(fila_cara[6]), float(fila_cara[7])
    nose_x, nose_y = float(fila_cara[8]), float(fila_cara[9])
    ml_y, mr_y = float(fila_cara[11]), float(fila_cara[13])
    eye = abs(le_x - re_x)
    if eye < 0.28 * w or eye > 0.85 * w:
        return False
    if abs(le_y - re_y) > 0.35 * max(eye, 1.0):
        return False
    mid_eye_y = 0.5 * (le_y + re_y)
    mouth_y = 0.5 * (ml_y + mr_y)
    if not (mid_eye_y + 0.04 * h < nose_y < mouth_y - 0.02 * h):
        return False
    if mouth_y - mid_eye_y < 0.22 * h:
        return False
    if nose_x < min(le_x, re_x) - 0.15 * w or nose_x > max(le_x, re_x) + 0.15 * w:
        return False
    return True


_lm_global = None


def _landmarker_global():
    """Un solo MediaPipe para elegir la selfie. Mismas opciones de siempre."""
    global _lm_global
    if _lm_global is None:
        from ia import forma_facial as ff
        from mediapipe.tasks.python import BaseOptions, vision

        _lm_global = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ff._RUTA)),
            num_faces=1,
            min_face_detection_confidence=0.4,
            min_face_presence_confidence=0.4,
        ))
    return _lm_global


def _bbox_mediapipe_global(imagen: np.ndarray):
    try:
        from ia import forma_facial as ff
        import mediapipe as mp
    except Exception:
        return None
    if not ff.disponible():
        return None
    alto, ancho = imagen.shape[:2]
    escala = 1280.0 / max(alto, ancho)
    if escala < 1.0:
        ch, cw = int(alto * escala), int(ancho * escala)
        small = cv2.resize(imagen, (cw, ch), interpolation=cv2.INTER_AREA)
    else:
        escala = 1.0
        small = imagen
        ch, cw = alto, ancho
    rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    r = _landmarker_global().detect(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    )
    if not r.face_landmarks:
        return None
    lms = r.face_landmarks[0]
    xs = [l.x * cw / escala for l in lms]
    ys = [l.y * ch / escala for l in lms]
    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    return float(x1), float(y1), float(x2 - x1), float(y2 - y1)


def _iou_xywh(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def elegir_cara_registro(imagen: np.ndarray, caras: np.ndarray) -> np.ndarray:
    if caras is None or caras.size == 0:
        raise ValueError("No se detecto ninguna cara. Usa una foto frontal y nitida.")
    alto, ancho = imagen.shape[:2]
    cx, cy = ancho * 0.5, alto * 0.5
    min_score = float(os.environ.get("DET_SCORE_REGISTRO", "0.35"))
    mp_box = _bbox_mediapipe_global(imagen)
    try:
        from ia import forma_facial as ff
        mp_ok = ff.disponible()
    except Exception:
        ff = None  # type: ignore
        mp_ok = False
    confirmadas = []
    geometricas = []
    for i in range(caras.shape[0]):
        fila = caras[i]
        geo = _geometria_cara_ok(fila, min_score)
        # Cabeza ladeada: la revisión de geometría la rechaza, pero si YuNet la da por segura
        # y MediaPipe le encuentra la malla, es una cara y sirve (al alinear se endereza).
        fuerte = float(fila[14]) >= REGISTRO_SCORE and min(float(fila[2]), float(fila[3])) >= 40
        if not geo and not (fuerte and mp_ok):
            continue
        x, y, w, h = [float(v) for v in fila[:4]]
        area_rel = (w * h) / max(float(ancho * alto), 1.0)
        fcx, fcy = x + 0.5 * w, y + 0.5 * h
        dist = ((fcx - cx) / max(ancho, 1.0)) ** 2 + ((fcy - cy) / max(alto, 1.0)) ** 2
        score = float(fila[14])
        nota = 0.35 * score + 0.35 * min(area_rel / 0.12, 1.0) + 0.15 * (1.0 - min(dist, 1.0))
        if mp_box is not None:
            nota += 0.35 * _iou_xywh((x, y, w, h), mp_box)
        if geo:
            geometricas.append((nota, fila))
        if mp_ok and ff is not None:
            try:
                if ff.malla(imagen, fila) is not None:
                    confirmadas.append((nota + 0.5, fila))
            except Exception:
                pass
    if confirmadas:
        # El dueño de la selfie es la cara más cercana a la cámara. Si atrás sale otra persona,
        # su cara mide bastante menos y se descarta (menos del 60 % del ancho de la mayor).
        ancho_mayor = max(float(f[2]) for _, f in confirmadas)
        confirmadas = [(n, f) for n, f in confirmadas if float(f[2]) >= REGISTRO_DUENO * ancho_mayor]
    pool = confirmadas or geometricas
    if not pool:
        for i in range(caras.shape[0]):
            fila = caras[i]
            if _geometria_cara_ok(fila, 0.25):
                pool.append((calidad_de_cara(fila), fila))
    if not pool:
        raise ValueError("No se encontro una cara usable para registrar. Usa un selfie frontal claro (ojos y boca visibles).")
    pool.sort(key=lambda t: t[0], reverse=True)
    return pool[0][1]


# Registro: en una selfie la cara ya es grande, no hace falta agrandar la foto.
# Se busca con la foto a REGISTRO_ANCHO px de ancho (el mismo tamaño de la pasada PIRAMIDE).
# Si ahí no sale una cara clara, se hace la búsqueda completa de detectar_caras.
REGISTRO_ANCHO = int(os.environ.get("REGISTRO_ANCHO", "640"))
REGISTRO_SCORE = float(os.environ.get("REGISTRO_SCORE", "0.80"))
REGISTRO_LADO = float(os.environ.get("REGISTRO_LADO", "80"))  # ancho mínimo de la cara, en esa escala
REGISTRO_FOTO_MIN = int(os.environ.get("REGISTRO_FOTO_MIN", "1000"))  # fotos más angostas van por la búsqueda completa
REGISTRO_DUENO = float(os.environ.get("REGISTRO_DUENO", "0.60"))  # una cara más angosta que esta fracción de la mayor es de otra persona


def _tiene_malla(imagen: np.ndarray, fila: np.ndarray) -> bool:
    """True si MediaPipe encuentra la malla de la cara en esa caja."""
    try:
        from ia import forma_facial as ff

        return ff.disponible() and ff.malla(imagen, fila) is not None
    except Exception:
        return False


def detectar_caras_registro(imagen: np.ndarray, detector: cv2.FaceDetectorYN) -> np.ndarray:
    alto, ancho = imagen.shape[:2]
    if ancho < REGISTRO_FOTO_MIN:
        # foto chica: la búsqueda completa ya es rápida y se deja tal cual
        return detectar_caras(imagen, detector)
    # 640 px sirve para la selfie normal. Si la cara salió lejos se prueba a 1280 px,
    # y si llena casi toda la foto, a 320 px. Ninguno agranda la foto.
    for W in (REGISTRO_ANCHO, 2 * REGISTRO_ANCHO, REGISTRO_ANCHO // 2):
        if W > ancho:
            continue
        H = max(1, int(round(alto * W / ancho)))
        f = ancho / W
        chica = cv2.resize(imagen, (W, H), interpolation=cv2.INTER_AREA)
        detector.setInputSize((W, H))
        _, c = detector.detect(chica)
        if c is None:
            continue
        c = c.copy()
        c[:, 0:14] *= f
        if any(
            float(r[14]) >= REGISTRO_SCORE
            and float(r[2]) / f >= REGISTRO_LADO
            and (_geometria_cara_ok(r, REGISTRO_SCORE) or _tiene_malla(imagen, r))
            for r in c
        ):
            return c
    try:
        return detectar_caras(imagen, detector)
    except cv2.error:
        # sin memoria para agrandar la foto: se busca en su tamaño real
        return detectar_caras(imagen, detector, factor_aumento=1.0)


def calidad_de_cara(fila_cara: np.ndarray) -> float:
    """
    Nota rápida de calidad (0..1 aprox).

    Mezcla:
      - confianza del detector
      - tamaño de la cara (caras muy chicas suelen fallar al reconocer)
    """
    ancho = float(fila_cara[2])
    alto = float(fila_cara[3])
    confianza = float(fila_cara[14])

    area = max(ancho * alto, 1.0)
    # Referencia: cara de ~120×120 px se considera "bien de tamaño"
    nota_tamano = min(area / (120.0 * 120.0), 1.0)

    return round(0.55 * confianza + 0.45 * nota_tamano, 4)


def ordenar_por_calidad(caras: np.ndarray) -> list[np.ndarray]:
    """Primero las caras más nítidas / grandes (mejor para reconocer)."""
    lista = [caras[i] for i in range(caras.shape[0])]
    lista.sort(key=calidad_de_cara, reverse=True)
    return lista
