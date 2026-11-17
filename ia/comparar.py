"""
Paso 4 — Comparar identidades (foto grupal / collage)

Lista cerrada de asistencia, pero SIN forzar cupos 1–1
(eso inventaría presentes = falso positivo).

1) Embedding por cara (aislado + directo)
2) Asignación global por score
3) Umbral principal estricto + pasada piso solo con margen claro
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ia.detectar_caras import calidad_de_cara, ordenar_por_calidad
from ia.identidad import cara_a_embedding, embedding_cara_en_grupo, normalizar
from ia.mejoras import score_contra_galeria
from ia.modelos import UMBRAL_POR_DEFECTO

import os as _os
# Piso = umbral − DIFERENCIA_PISO. Con 0 no hay pasada genérica por debajo del umbral
# (un desconocido no entra solo porque gana claro a 0.33 contra el resto de la clase).
# La excepción medida está más abajo: SEGUNDO_NIVEL, solo caras de menos de 20 px.
DIFERENCIA_PISO = float(_os.environ.get("DIFERENCIA_PISO", "0"))
# Margen exigido bajo el umbral principal (evita “casi empatados”)
MARGEN_MINIMO = 0.03
# Solo aplica si DIFERENCIA_PISO > 0.
MARGEN_PISO = float(_os.environ.get("MARGEN_PISO", "0.12"))
CALIDAD_MINIMA = 0.20
# Caras "dudosas" (detector poco seguro: cara cortada, de perfil, tapada
# o una cabeza del fondo): solo se aceptan con score alto y NUNCA en la
# pasada piso. En el banco de pruebas casi todos los falsos positivos
# venían de caras con det_score < 0.80; las genuinas suelen tener > 0.86.
DET_SCORE_DUDOSA = float(_os.environ.get("DET_SCORE_DUDOSA", "0.80"))
# Con la fusión de tres modelos esta pasada extra queda apagada.
DOBLE_MARGEN = _os.environ.get("DOBLE_MARGEN", "0" if _os.environ.get("FUSION_ADAFACE", "0") == "1" else "1") == "1"
DM_DIFERENCIA = float(_os.environ.get("DM_DIFERENCIA", "0.08"))
DM_MARGEN_FILA = float(_os.environ.get("DM_MARGEN_FILA", "0.12"))
DM_MARGEN_COLUMNA = float(_os.environ.get("DM_MARGEN_COLUMNA", "0.10"))
# Cada modelo tiene que superar su piso. Si uno falla, esa cara no entra.
PISO_EDGE = float(_os.environ.get("PISO_EDGE", "0"))      # normal 0.27 / difícil 0.32
PISO_ADA = float(_os.environ.get("PISO_ADA", "0"))        # normal 0.18 / difícil 0.14
PISO_IR101 = float(_os.environ.get("PISO_IR101", "0"))
# Cuánto cuenta cada modelo en la nota final: EdgeFace 18 %, IR-50 12 %, IR-101 70 %.
# IR-101 pesa más porque en caras chicas y con mala luz acertaba más.
PESOS_FUSION = [float(x) for x in _os.environ.get("PESOS_FUSION", "0.18,0.12,0.70").split(",")]
CARA_MIN_PX = float(_os.environ.get("CARA_MIN_PX", "0"))  # más angosta que esto (px) = dudosa
BONO_PX = float(_os.environ.get("BONO_PX", "0"))          # 0.06 → +0.06·(50−px)/50 si px<50
# No bonificar cajas minúsculas (logos ~40 px): el bono solo aplica si ancho >= BONO_MIN_PX
BONO_MIN_PX = float(_os.environ.get("BONO_MIN_PX", "48"))
# Ancho mínimo para EMBEDDER/reconocer. Logos/texturas suelen ser <48 px; caras de salón típicas >=60.
# Separado de CARA_MIN_PX (dudosa). Si no se fija, usa CARA_MIN_PX si >0; si no, 48 (anti-logo).
_cm_env = _os.environ.get("CARA_MIN_MATCH_PX")
if _cm_env is not None and _cm_env.strip() != "":
    CARA_MIN_MATCH_PX = float(_cm_env)
else:
    _cmin = float(_os.environ.get("CARA_MIN_PX", "0") or "0")
    CARA_MIN_MATCH_PX = _cmin if _cmin > 0 else 48.0
FILTRO_FALSAS = _os.environ.get("FILTRO_FALSAS", "1") == "1"
USAR_SINTETICAS = _os.environ.get("USAR_SINTETICAS", "1") == "1"  # muestras de gafas del registro
PENA_SINTETICA = float(_os.environ.get("PENA_SINTETICA", "0.02"))
# Castigo a caras más angostas que CHICA_PX.
CASTIGO_CHICA = float(_os.environ.get("CASTIGO_CHICA", "0"))
CHICA_PX = float(_os.environ.get("CHICA_PX", "24"))
# Caras del fondo (lado menor < CHICA_2DET_PX): solo llevan nombre si los dos detectores dicen que es una cara,
# YuNet con CHICA_DET o más y RetinaFace con RETINA_CONS o más. Sin RetinaFace no llevan nombre.
# Ejemplo medido: un logo de camiseta de 23 px pasó YuNet con 0.55 y RetinaFace le dio 0;
# las caras reales de 18 a 32 px dieron 0.85 o más en YuNet y 0.97 o más en RetinaFace.
CHICA_2DET_PX = float(_os.environ.get("CHICA_2DET_PX", "32"))
CHICA_DET = float(_os.environ.get("CHICA_DET", "0.80"))
# Tamaño mínimo para comparar una cara que los dos detectores confirman. Si no se fija, es CARA_MIN_MATCH_PX.
CARA_MIN_2DET_PX = float(_os.environ.get("CARA_MIN_2DET_PX", str(CARA_MIN_MATCH_PX)))
# Extra sobre el umbral para caras < GEO_VETO_PX confirmadas por los dos detectores.
# 0 = mismo listón 0.37 que las grandes. Sin confirmación se sigue pidiendo GEO_VETO_EXTRA.
# Medido: impostor en 12–16 px no pasó de ~0.31 con los pisos de cada modelo.
CHICA_EXTRA = float(_os.environ.get("CHICA_EXTRA", "0"))
USAR_DEGRADADAS = _os.environ.get("USAR_DEGRADADAS", "1") == "1"   # plantillas degradadas del registro
PENA_DEGRADADA = float(_os.environ.get("PENA_DEGRADADA", "0.10"))
DEG_PX = float(_os.environ.get("DEG_PX", "60"))                       # solo caras de la foto más angostas que esto
N_DEGRADADAS = 5
# Pasada k-recíproca: los 3 modelos tienen que coincidir en la misma persona (solo caras aún no asignadas, nunca dudosas):
# el mismo alumno LIBRE es el 1º en EdgeFace, AdaFace-50 e IR-101, la cara es también la mejor de ese alumno
# en los 3 modelos (recíproca), con margen de fila >= KR_M y de columna >= KR_MC en cada modelo,
# score fusionado (sin pisos) >= KR_T3 y cara >= KR_PX px. KR_CONSENSO=0 la apaga.
KR_CONSENSO = _os.environ.get("KR_CONSENSO", "0") == "1"
KR_T3 = float(_os.environ.get("KR_T3", "0.30"))
KR_M = float(_os.environ.get("KR_M", "0.12"))
KR_MC = float(_os.environ.get("KR_MC", "0.04"))
KR_PX = float(_os.environ.get("KR_PX", "20"))
# Caras chicas que se quedaron sin nombre. El umbral de todos sigue en 0.37.
# Si la cara mide menos de 20 px, la nota queda entre 0.33 y 0.37 y le gana al segundo
# por 0.18 o más, entra.
# Medido con 856 caras con verdad y 3.539 pruebas de impostor (quitar a la persona de su
# lista, caras de no registrados, y cada cara contra la lista de las otras clases):
# 32 nombres más (10–13 px 28%→39%, 13–16 px 61%→73%, 16–20 px 91%→95%) y 0 equivocados.
# Bajo 20 px el parecido más alto llegó a 0.320: bajar la nota a 0.32 ya lo deja pasar.
# Entre 20 y 32 px NO se aplica: ahí un parecido llegó a 0.344 (24 px) y otro a 0.337 (25 px),
# los dos con margen de sobra. Con 32 px (como estuvo unas horas) esos dos entraban.
SEGUNDO_NIVEL = _os.environ.get("SEGUNDO_NIVEL", "1") == "1"
SEGUNDO_NOTA = float(_os.environ.get("SEGUNDO_NOTA", "0.33"))
SEGUNDO_MARGEN = float(_os.environ.get("SEGUNDO_MARGEN", "0.18"))
SEGUNDO_MAX_PX = float(_os.environ.get("SEGUNDO_MAX_PX", "20"))

# Caras chicas: también se compara la cara con CONTRASTE LOCAL (CLAHE) y se queda, por modelo y por alumno,
# la nota más alta de las dos. No inventa rasgos (no es restauración con IA). Se activa en la configuración
# de la versión (config/configurar_r19.ps1, con lo medido); sin ella queda apagado.
REALCE_CLAHE = _os.environ.get("REALCE_CLAHE", "0") == "1"
REALCE_PX = float(_os.environ.get("REALCE_PX", "32"))


# Caras chicas: también en blanco y negro, contra la foto de registro en blanco y negro (quita el tinte de
# la luz y las paredes del salón). Por modelo y por alumno, la nota más alta. Lo enciende config r19 (medido ahí).
REALCE_GRIS = _os.environ.get("REALCE_GRIS", "0") == "1"


def _gris(imagen: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)


def huella_gris_registro(cara: np.ndarray, reconocedor) -> np.ndarray:
    """Huella de registro (1536 números) de la cara de registro alineada, en blanco y negro: la misma función
    del registro normal. Cuesta lo mismo que la huella normal (~3 s en CPU) → la web la guarda con ella."""
    from ia.mejoras import embedding_registro_de_cara

    return np.asarray(embedding_registro_de_cara(_gris(np.ascontiguousarray(cara)), reconocedor))[:1536]


# Si no viene guardada (ventana de escritorio), se calcula una vez por alumno mientras el programa siga
# abierto: la cara de registro alineada es la misma en cada lista → la misma plantilla.
_PLANTILLAS_GRIS: dict = {}


def plantilla_gris(cara: np.ndarray, reconocedor, guardada=None) -> list[np.ndarray]:
    if guardada is not None and np.asarray(guardada).size == 1536:
        return _partes(guardada, 3)
    import hashlib

    cara = np.ascontiguousarray(cara)
    clave = (id(reconocedor), cara.shape, hashlib.blake2b(cara.tobytes(), digest_size=16).digest())
    plantilla = _PLANTILLAS_GRIS.get(clave)
    if plantilla is None:
        plantilla = _partes(huella_gris_registro(cara, reconocedor), 3)
        if len(_PLANTILLAS_GRIS) >= 5000:
            _PLANTILLAS_GRIS.clear()
        _PLANTILLAS_GRIS[clave] = plantilla
    return plantilla


def _con_clahe(imagen: np.ndarray) -> np.ndarray:
    lab_ = cv2.cvtColor(imagen, cv2.COLOR_BGR2LAB)
    l_, a_, b_ = cv2.split(lab_)
    l_ = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_)
    return cv2.cvtColor(cv2.merge([l_, a_, b_]), cv2.COLOR_LAB2BGR)
# Anti-logo / anti-textura GENERAL (no por foto / sin overfitting a un logo):
# 1) Caja >= GEO_VETO_PX con geometría YuNet inválida → ni se embebe.
# 2) Caja < GEO_VETO_PX con match flojo (sim < umbral+EXTRA) → se desasigna
#    (logos/texturas chicas suelen colarse justo por encima del umbral).
# 3) Match flojo sin malla MediaPipe → se desasigna (2ª opinión genérica).
GEO_VETO = _os.environ.get("GEO_VETO", "1") == "1"
GEO_VETO_PX = float(_os.environ.get("GEO_VETO_PX", "48"))
GEO_VETO_EXTRA = float(_os.environ.get("GEO_VETO_EXTRA", "0.12"))
GEO_VETO_MALLA = _os.environ.get("GEO_VETO_MALLA", "1") == "1"

# Calibración por calidad: las caras con score de detección bajo (det < CAL_DET) tienen similitudes
# más bajas; se les suma CAL_DET_BONO.
CAL_DET = float(_os.environ.get("CAL_DET", "0.80"))
CAL_DET_BONO = float(_os.environ.get("CAL_DET_BONO", "0"))


def _fusion_partes(sc, w, det=1.0):
    """Junta las tres notas en una sola.

    Nota = 0.18·EdgeFace + 0.12·IR-50 + 0.70·IR-101.
    Para entrar a la lista esa nota tiene que llegar al umbral (0.37)
    y cada modelo tiene que pasar su piso (0.20, 0.14, 0.25).
    Si un modelo queda bajo su piso, a la nota se le resta 1 y no pasa.
    """
    # Bono solo para caras “un poco chicas” pero creíbles (no logos/texturas < BONO_MIN_PX)
    bono = 0.0
    if BONO_PX and w >= BONO_MIN_PX:
        bono = BONO_PX * max(0.0, min(1.0, (50.0 - w) / 50.0))
    if CASTIGO_CHICA and w < CHICA_PX:
        bono -= CASTIGO_CHICA
    if CAL_DET_BONO and det < CAL_DET:
        bono += CAL_DET_BONO
    pisos = (PISO_EDGE, PISO_ADA, PISO_IR101); tot = sum(PESOS_FUSION)
    crudo = {p: sum(PESOS_FUSION[i] * sc[i][p] for i in range(3)) / tot + bono for p in sc[0]}
    fus = {p: crudo[p] - (1.0 if any(sc[i][p] < pisos[i] for i in range(3)) else 0.0) for p in sc[0]}
    return fus, crudo


EXTRA_UMBRAL_DUDOSA = float(_os.environ.get("EXTRA_DUDOSA", "0.10" if _os.environ.get("ENSAMBLE", "0") == "1" else "0.07"))


def armar_galeria_por_persona(
    personas: list[dict[str, Any]],
    dimension: int | None = None,
) -> dict[str, dict[str, Any]]:
    """
    dimension: solo usa huellas de ese largo (1536 = la fusión; 512 = un solo modelo).
    Embeddings de otro modelo no se pueden comparar → se ignoran.
    """
    galeria: dict[str, dict[str, Any]] = {}
    for persona in personas:
        pid = persona["id"]
        vectores = []
        sinteticos = []
        degradados = []
        for emb in persona.get("embeddings", []):
            if dimension is None or len(emb) == dimension:
                vectores.append(normalizar(np.asarray(emb, dtype=np.float32)))
            elif dimension and len(emb) > dimension and len(emb) % dimension == 0:
                # Ronda 16: [base | sintética1 | sintética2 ...] (registro con variantes de gafas)
                bloques = np.asarray(emb, dtype=np.float32).reshape(-1, dimension)
                vectores.append(normalizar(bloques[0]))
                resto = bloques[1:]
                if len(bloques) >= 1 + N_DEGRADADAS:
                    # Ronda 17: [base | gafas(1-2) | 5 degradadas]
                    if USAR_DEGRADADAS:
                        degradados += [normalizar(b) for b in resto[-N_DEGRADADAS:]]
                    resto = resto[:-N_DEGRADADAS]
                if USAR_SINTETICAS:
                    sinteticos += [normalizar(b) for b in resto]
        if not vectores:
            continue
        galeria[pid] = {"name": persona["name"], "vectores": vectores, "sinteticos": sinteticos, "degradados": degradados}
    return galeria


def _partes(v: np.ndarray, k: int) -> list[np.ndarray]:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    h = v.shape[0] // k
    return [normalizar(v[i * h:(i + 1) * h]) for i in range(k)]


def _scores_partes(sonda, galeria, k: int, ancho: float = 1e9):
    """Parte la huella de 1536 en 3 bloques de 512 y compara cada bloque aparte.

    De cada bloque sale un solo número (cerca de 1 = misma persona).
    Esas tres notas son las que después pondera _fusion_partes.
    """
    ss = _partes(sonda, k)
    outs: list[dict[str, float]] = [{} for _ in range(k)]
    for pid, info in galeria.items():
        clave = f"_partes{k}"
        if clave not in info:
            ps = [_partes(v, k) for v in info["vectores"]]
            info[clave] = [[x[i] for x in ps] for i in range(k)]
            sp = [_partes(v, k) for v in info.get("sinteticos", [])]
            info[clave + "s"] = [np.stack([x[i] for x in sp]) for i in range(k)] if sp else None
            dp = [_partes(v, k) for v in info.get("degradados", [])]
            info[clave + "d"] = [np.stack([x[i] for x in dp]) for i in range(k)] if dp else None
        for i in range(k):
            sc = score_contra_galeria(ss[i], info[clave][i])
            if info[clave + "s"] is not None:
                # Ronda 16: la muestra sintética (con/sin gafas) cuenta como otra foto: máximo, por modelo
                sc = max(sc, float((info[clave + "s"][i] @ ss[i]).max()) - PENA_SINTETICA)
            if info[clave + "d"] is not None and ancho < DEG_PX:
                # Ronda 17: cara lejana → también contra las plantillas degradadas (con castigo)
                sc = max(sc, float((info[clave + "d"][i] @ ss[i]).max()) - PENA_DEGRADADA)
            outs[i][pid] = sc
    return outs


def _asignar_caras(
    scores: list[dict[str, float]],
    galeria: dict[str, dict[str, Any]],
    umbral: float,
    dudosas: set[int] | None = None,
    diferencia_piso: float = DIFERENCIA_PISO,
    margen_piso: float = MARGEN_PISO,
) -> list[tuple[str | None, str | None, float | None, float | None]]:
    n = len(scores)
    ids = list(galeria.keys())
    umbral_piso = umbral - diferencia_piso
    dudosas = dudosas or set()
    resultado: list[tuple[str | None, str | None, float | None, float | None]] = [
        (None, None, None, None) for _ in range(n)
    ]
    if not ids or n == 0:
        return resultado

    pares: list[tuple[float, int, str]] = []
    for i, por_persona in enumerate(scores):
        for pid, sc in por_persona.items():
            pares.append((sc, i, pid))
    pares.sort(reverse=True, key=lambda t: t[0])

    caras_usadas: set[int] = set()
    personas_usadas: set[str] = set()

    def margen_de(i: int, pid: str, ignorar: set[str] | None = None) -> float:
        """Margen 1º vs 2º. Por defecto mira toda la galería (anti FP)."""
        ignorar = ignorar or set()
        rivales = [
            s for p, s in scores[i].items() if p != pid and p not in ignorar
        ]
        segundo = max(rivales) if rivales else -1.0
        return scores[i][pid] - segundo

    # Pasada 1 — umbral principal
    for sc, i, pid in pares:
        if i in caras_usadas or pid in personas_usadas:
            continue
        if sc < umbral:
            continue
        if i in dudosas and sc < umbral + EXTRA_UMBRAL_DUDOSA:
            continue
        # Margen solo contra personas aún libres (ya asignadas no compiten)
        mg = margen_de(i, pid, personas_usadas)
        libres = [p for p in ids if p not in personas_usadas]
        if len(libres) > 1 and mg < MARGEN_MINIMO:
            continue
        resultado[i] = (pid, galeria[pid]["name"], sc, mg)
        caras_usadas.add(i)
        personas_usadas.add(pid)

    # Pasada 2 — piso + margen GLOBAL (incluye ya asignados).
    # Evita: “queda 1 cupo → cualquier cara se pega al ausente”.
    for sc, i, pid in pares:
        if i in caras_usadas or pid in personas_usadas:
            continue
        if sc < umbral_piso or i in dudosas:
            continue
        mg_global = margen_de(i, pid, set())
        if mg_global < margen_piso:
            continue
        resultado[i] = (pid, galeria[pid]["name"], sc, mg_global)
        caras_usadas.add(i)
        personas_usadas.add(pid)

    # Pasada 3 — doble margen: cara cuyo 1º candidato queda bajo el umbral pero
    # gana claro en su fila (vs otras personas) Y en su columna (vs otras caras
    # de la misma foto para ese alumno). Nunca dudosas.
    if DOBLE_MARGEN:
        candidatos = []
        for i in range(n):
            if i in caras_usadas or i in dudosas or not scores[i]:
                continue
            pid = max(scores[i], key=scores[i].get)
            sc = scores[i][pid]
            if pid in personas_usadas or sc < umbral - DM_DIFERENCIA:
                continue
            mg = margen_de(i, pid, set())
            if mg < DM_MARGEN_FILA:
                continue
            col = [scores[k][pid] for k in range(n) if k != i and scores[k]]
            mc = sc - (max(col) if col else -1.0)
            if mc < DM_MARGEN_COLUMNA:
                continue
            candidatos.append((sc, i, pid, mg))
        for sc, i, pid, mg in sorted(candidatos, reverse=True):
            if pid in personas_usadas:
                continue
            resultado[i] = (pid, galeria[pid]["name"], sc, mg)
            caras_usadas.add(i)
            personas_usadas.add(pid)

    for i in range(n):
        if resultado[i][0] is not None or not scores[i]:
            continue
        mejor_pid = max(scores[i], key=scores[i].get)
        sc = scores[i][mejor_pid]
        mg = margen_de(i, mejor_pid, set())
        resultado[i] = (None, None, sc, mg)

    return resultado


def _pasada_kreciproca(asignaciones, por_modelo, entradas, dudosas, galeria):
    """Ronda 18: acepta caras no asignadas con consenso recíproco de los 3 modelos (ver KR_*)."""
    n = len(asignaciones)
    usados = {a[0] for a in asignaciones if a[0] is not None}
    validas = [i for i in range(n) if por_modelo[i] is not None]
    candidatos = []
    for i in validas:
        if asignaciones[i][0] is not None or i in dudosas:
            continue
        if (entradas[i]["bbox"][2] - entradas[i]["bbox"][0]) < KR_PX:
            continue
        sc, crudo = por_modelo[i]
        pid = max(crudo, key=crudo.get)
        if pid in usados or crudo[pid] < KR_T3:
            continue
        ok = True
        for k in range(3):
            fila = sc[k]
            rivales = [v for p, v in fila.items() if p != pid]
            if fila[pid] < max(fila.values()) or (rivales and fila[pid] - max(rivales) < KR_M):
                ok = False
                break
            col = [por_modelo[j][0][k][pid] for j in validas if j != i]
            if col and (fila[pid] < max(col) or fila[pid] - max(col) < KR_MC):
                ok = False
                break
        if ok:
            candidatos.append((crudo[pid], i, pid))
    salida = list(asignaciones)
    for s_, i, pid in sorted(candidatos, reverse=True):
        if pid in usados:
            continue
        sc, crudo = por_modelo[i]
        rivales = [v for p, v in crudo.items() if p != pid]
        salida[i] = (pid, galeria[pid]["name"], crudo[pid], crudo[pid] - (max(rivales) if rivales else -1.0))
        usados.add(pid)
    return salida


def _pasada_margen_chica(asignaciones, scores, entradas, dudosas, galeria):
    """Acepta una cara de menos de 20 px sin nombre si la nota llega a 0.33 y el margen a 0.18.

    No baja el umbral del resto. Una cara dudosa (detector flojo, o de menos de
    32 px vista por un solo detector) no entra. El margen se mide contra toda
    la lista, también contra quien ya tiene otra cara: si no, un hueco libre
    se llenaría con el parecido que quedaba segundo.
    """
    if not SEGUNDO_NIVEL:
        return asignaciones
    n = len(asignaciones)
    usados = {a[0] for a in asignaciones if a[0] is not None}
    candidatos = []
    for i in range(n):
        if asignaciones[i][0] is not None or i in dudosas or not scores[i]:
            continue
        ancho = min(
            entradas[i]["bbox"][2] - entradas[i]["bbox"][0],
            entradas[i]["bbox"][3] - entradas[i]["bbox"][1],
        )
        if ancho >= SEGUNDO_MAX_PX:
            continue
        pid = max(scores[i], key=scores[i].get)
        sc = scores[i][pid]
        if pid in usados or sc < SEGUNDO_NOTA:
            continue
        rivales = [v for p, v in scores[i].items() if p != pid]
        mg = sc - (max(rivales) if rivales else -1.0)
        if mg < SEGUNDO_MARGEN:
            continue
        candidatos.append((sc, i, pid, mg))
    salida = list(asignaciones)
    for sc, i, pid, mg in sorted(candidatos, reverse=True):
        if pid in usados:
            continue
        salida[i] = (pid, galeria[pid]["name"], sc, mg)
        usados.add(pid)
    return salida


def comparar_foto_grupal(
    imagen: np.ndarray,
    caras: np.ndarray,
    reconocedor,
    personas: list[dict[str, Any]],
    umbral: float = UMBRAL_POR_DEFECTO,
    detector=None,
    diferencia_piso: float = DIFERENCIA_PISO,
    margen_piso: float = MARGEN_PISO,
    devolver_embeddings: bool = False,
) -> dict[str, Any]:
    galeria = armar_galeria_por_persona(
        personas, getattr(reconocedor, "dimension", 128)
    )
    if FILTRO_FALSAS and EXTRA_UMBRAL_DUDOSA >= 1 and caras.shape[0]:  # solo si las dudosas nunca se reconocen
        # Ronda 16: detecciones de baja confianza (techo, lámpara, texturas) no cuentan como caras.
        # Con EXTRA_DUDOSA=9 nunca podían ser reconocidas → quitarlas no cambia presentes/ausentes.
        caras = caras[caras[:, 14] >= DET_SCORE_DUDOSA]
    from ia import verificar_caras as _vc0
    _vc0.preparar_retina(imagen, caras)
    if GEO_VETO and caras is not None and getattr(caras, "shape", (0,))[0]:
        # Descarta logos/escudos/brazos con geometría inválida (tamaño >= GEO_VETO_PX).
        from ia.detectar_caras import parece_cara_humana

        keep_geo = []
        for i in range(int(caras.shape[0])):
            w_i = float(caras[i, 2])
            h_i = float(caras[i, 3])
            if min(w_i, h_i) >= GEO_VETO_PX and not parece_cara_humana(caras[i]):
                continue
            keep_geo.append(i)
        if keep_geo:
            caras = caras[np.asarray(keep_geo, dtype=np.int32)]
        else:
            caras = caras[:0]
    orden = ordenar_por_calidad(caras)

    entradas: list[dict[str, Any]] = []
    con_huella: list[int] = []  # caras que se comparan (las demás son muy chicas o de mala calidad)

    # dos_det[i]: YuNet y RetinaFace coinciden en que la caja i es una cara
    dos_det = [
        float(fila[14]) >= CHICA_DET and _vc0._retina_score(fila) >= _vc0.RETINA_CONS
        if min(float(fila[2]), float(fila[3])) < GEO_VETO_PX else True
        for fila in orden
    ]

    for i_cara, fila_cara in enumerate(orden):
        x, y, w, h = [float(v) for v in fila_cara[:4]]
        calidad = calidad_de_cara(fila_cara)
        entrada: dict[str, Any] = {
            "bbox": [x, y, x + w, y + h],
            "det_score": float(fila_cara[14]),
            "quality": calidad,
            "similarity": None,
            "margin": None,
            "person_id": None,
            "name": None,
            "matched": False,
        }
        entradas.append(entrada)

        # Cajas demasiado chicas (logos, escudos, texturas): no embeber → menos FP y menos CPU.
        # Si los dos detectores dicen que es una cara, se compara desde CARA_MIN_2DET_PX (0 = sin mínimo).
        minimo = CARA_MIN_2DET_PX if dos_det[i_cara] else CARA_MIN_MATCH_PX
        if min(w, h) < minimo or calidad < CALIDAD_MINIMA or not galeria:
            continue
        con_huella.append(i_cara)

    # Huella de cada cara que se compara.
    filas_huella = [orden[i] for i in con_huella]
    if hasattr(reconocedor, "embeddings_espejo") and "embedding_espejo" not in vars(reconocedor):
        # Reconocedor ONNX: cara alineada + espejo, todas las caras de la foto en un solo lote.
        # Da las mismas huellas que pedirlas una por una y espera menos.
        # (Si una prueba reemplazó embedding_espejo en este reconocedor, se usa el suyo, abajo.)
        huellas = reconocedor.embeddings_espejo(imagen, filas_huella)
    elif hasattr(reconocedor, "embedding_espejo"):
        huellas = [reconocedor.embedding_espejo(imagen, fila) for fila in filas_huella]
    elif detector is not None:
        huellas = [embedding_cara_en_grupo(imagen, fila, detector, reconocedor) for fila in filas_huella]
    else:
        huellas = [cara_a_embedding(imagen, fila, reconocedor, usar_tta=True) for fila in filas_huella]

    # Caras chicas: segunda huella con contraste local (ver REALCE_CLAHE).
    realzadas: dict[int, Any] = {}
    if REALCE_CLAHE and getattr(reconocedor, "partes", 2) == 3:
        chicas = [k for k, i in enumerate(con_huella) if min(float(orden[i][2]), float(orden[i][3])) < REALCE_PX]
        if chicas:
            img_r = _con_clahe(imagen)
            filas_r = [filas_huella[k] for k in chicas]
            if hasattr(reconocedor, "embeddings_espejo") and "embedding_espejo" not in vars(reconocedor):
                h_r = reconocedor.embeddings_espejo(img_r, filas_r)
            else:
                h_r = [reconocedor.embedding_espejo(img_r, f) for f in filas_r]
            realzadas = {con_huella[k]: h for k, h in zip(chicas, h_r)}

    # Caras chicas: también en BLANCO Y NEGRO contra la foto de registro en blanco y negro (ver REALCE_GRIS).
    grises: dict[int, Any] = {}
    gris_gal: dict[str, list] = {}
    if REALCE_GRIS and getattr(reconocedor, "partes", 2) == 3 and personas and all(p.get("cara") is not None for p in personas):
        chicas_g = [k for k, i in enumerate(con_huella) if min(float(orden[i][2]), float(orden[i][3])) < REALCE_PX]
        if chicas_g:
            for p in personas:               # la de registro en gris (guardada por la web, o se calcula)
                gris_gal[p["id"]] = plantilla_gris(p["cara"], reconocedor, p.get("huella_gris"))
            img_g = _gris(imagen)
            filas_g = [filas_huella[k] for k in chicas_g]
            if hasattr(reconocedor, "embeddings_espejo") and "embedding_espejo" not in vars(reconocedor):
                h_g = reconocedor.embeddings_espejo(img_g, filas_g)
            else:
                h_g = [reconocedor.embedding_espejo(img_g, f) for f in filas_g]
            grises = {con_huella[k]: _partes(h, 3) for k, h in zip(chicas_g, h_g)}

    scores: list[dict[str, float]] = [{} for _ in orden]
    sondas: list[Any] = [None] * len(orden)      # embedding de cada cara
    por_modelo: list[Any] = [None] * len(orden)  # nota de cada modelo, para la pasada en que los tres tienen que coincidir
    for i_cara, sonda in zip(con_huella, huellas):
        fila_cara = orden[i_cara]
        w = float(fila_cara[2])
        sondas[i_cara] = sonda
        if getattr(reconocedor, "partes", 2) == 3:
            sc = _scores_partes(sonda, galeria, 3, w)
            if i_cara in realzadas:          # por modelo y por alumno, la nota más alta de las dos
                sc2 = _scores_partes(realzadas[i_cara], galeria, 3, w)
                sc = [{p: max(sc[k][p], sc2[k][p]) for p in sc[k]} for k in range(3)]
            if i_cara in grises:             # gris contra gris: también la nota más alta
                sg = grises[i_cara]
                sc = [{p: (max(sc[k][p], float(gris_gal[p][k] @ sg[k])) if p in gris_gal else sc[k][p]) for p in sc[k]}
                      for k in range(3)]
            fus, crudo = _fusion_partes(sc, w, float(fila_cara[14]))
            scores[i_cara] = fus
            por_modelo[i_cara] = (sc, crudo)
        else:
            scores[i_cara] = {
                pid: score_contra_galeria(sonda, info["vectores"])
                for pid, info in galeria.items()
            }

    # Dudosa ≠ “demasiado chica para embeber”: CARA_MIN_MATCH solo salta el embedder;
    # si también las marcáramos dudosas, con EXTRA_DUDOSA=9 nunca se reconocerían
    # caras lejanas reales de 32–45 px (típicas en salón lleno).
    dudosas = {
        i for i, e in enumerate(entradas)
        if e["det_score"] < DET_SCORE_DUDOSA
        or (e["bbox"][2] - e["bbox"][0]) < CARA_MIN_PX
        or (e["bbox"][3] - e["bbox"][1]) < CARA_MIN_PX
    }
    for i, fila in enumerate(orden):
        if min(float(fila[2]), float(fila[3])) < CHICA_2DET_PX and not dos_det[i]:
            dudosas.add(i)
    asignaciones = _asignar_caras(
        scores, galeria, umbral, dudosas, diferencia_piso, margen_piso
    )
    if KR_CONSENSO:
        asignaciones = _pasada_kreciproca(asignaciones, por_modelo, entradas, dudosas, galeria)
    asignaciones = _pasada_margen_chica(asignaciones, scores, entradas, dudosas, galeria)
    if GEO_VETO and asignaciones:
        # Veto post-asignación: no inventar presentes por logos/texturas chicas o sin malla.
        from ia import forma_facial as _ff

        mp_ok = GEO_VETO_MALLA and _ff.disponible()
        for i, asig in enumerate(asignaciones):
            pid, nombre, sim, margen = asig
            if pid is None or sim is None:
                continue
            fila = orden[i]
            w_i = float(fila[2])
            h_i = float(fila[3])
            chica = min(w_i, h_i) < GEO_VETO_PX
            # La pasada de caras chicas ya exigió 0.33 y un margen de 0.18.
            # El veto de "flojo" mira el umbral 0.37 y la borraría.
            if (
                SEGUNDO_NIVEL
                and min(w_i, h_i) < SEGUNDO_MAX_PX
                and float(sim) >= SEGUNDO_NOTA
                and margen is not None
                and float(margen) >= SEGUNDO_MARGEN
            ):
                continue
            extra = CHICA_EXTRA if chica and dos_det[i] else GEO_VETO_EXTRA
            flojo = float(sim) < (umbral + extra)
            if chica and flojo:
                asignaciones[i] = (None, None, sim, margen)
                continue
            if mp_ok and flojo:
                try:
                    if _ff.malla(imagen, fila) is None:
                        asignaciones[i] = (None, None, sim, margen)
                except Exception:
                    pass
    # Caras tapadas por abajo (sentados detrás de un monitor): segunda oportunidad comparando
    # solo la parte de arriba de la cara. Confirma al candidato que ya iba primero; no baja el umbral.
    from ia import cara_tapada as _ct
    if _ct.ACTIVO and asignaciones and getattr(reconocedor, "partes", 2) == 3:
        asignaciones = _ct.rescatar(
            imagen, orden, entradas, asignaciones, por_modelo, dudosas, dos_det,
            reconocedor, personas, galeria, PESOS_FUSION,
        )
    # Candidato de cada cara SIN nombre: el alumno libre (sin cara asignada) con la nota cruda más alta.
    # Solo informa: la lista lo muestra como sugerencia para revisar a mano. No cambia ninguna asignación.
    usados_fin = {a[0] for a in asignaciones if a[0] is not None}
    for i, asig in enumerate(asignaciones):
        if asig[0] is not None or por_modelo[i] is None:
            continue
        libres = [(v, p) for p, v in por_modelo[i][1].items() if p not in usados_fin]
        if libres:
            v, p = max(libres)
            entradas[i]["candidate_id"] = p
            entradas[i]["candidate_name"] = galeria[p]["name"]
            entradas[i]["candidate_score"] = round(float(v), 4)
            entradas[i]["dudosa"] = i in dudosas
            # Giro de la cara (0 = de frente; ±0.3 o más = bastante de lado): nariz respecto al centro de los ojos.
            f = orden[i]
            ojos = max(float(np.hypot(f[6] - f[4], f[7] - f[5])), 1e-6)
            entradas[i]["giro"] = round((float(f[8]) - (float(f[4]) + float(f[6])) / 2) / ojos, 3)
    # Quita manos, ropa y lámparas que YuNet marcó y nadie reconoció.
    # Las reconocidas no se tocan → presentes/ausentes iguales.
    from ia import verificar_caras as _vc
    if _vc.VERIFICAR and entradas:
        keep = _vc.conservar_no_reconocidas(imagen, orden, sondas, [a[0] is not None for a in asignaciones])
        entradas = [e for e, k in zip(entradas, keep) if k]
        sondas = [s for s, k in zip(sondas, keep) if k]
        asignaciones = [a for a, k in zip(asignaciones, keep) if k]
        n_detectadas = len(entradas)
    else:
        n_detectadas = int(caras.shape[0])
    desconocidas = 0

    for entrada, asig in zip(entradas, asignaciones):
        pid, nombre, sim, margen = asig
        if sim is not None:
            entrada["similarity"] = round(float(sim), 4)
        if margen is not None:
            entrada["margin"] = round(float(margen), 4)
        if pid is not None:
            entrada["person_id"] = pid
            entrada["name"] = nombre
            entrada["matched"] = True
        else:
            desconocidas += 1

    ids_presentes = {c["person_id"] for c in entradas if c["matched"]}
    presentes = [
        {"id": p["id"], "name": p["name"]}
        for p in personas
        if p["id"] in ids_presentes
    ]
    ausentes = [
        {"id": p["id"], "name": p["name"]}
        for p in personas
        if p["id"] not in ids_presentes
    ]

    resultado = {
        "faces_detected": n_detectadas,
        "unknown_faces": desconocidas,
        "threshold": umbral,
        "matches": entradas,
        "present": presentes,
        "absent": ausentes,
    }
    if devolver_embeddings:
        # Uso interno de quien pide las huellas.
        resultado["_embeddings"] = [
            None if e is None else [float(v) for v in np.ravel(e)] for e in sondas
        ]
    return resultado
