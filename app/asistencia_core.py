"""Núcleo compartido: Excel + MotorFacial → filas de lista + detecciones."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.excel_clase import Estudiante, cargar_estudiantes, guardar_lista
from ia.motor_facial import MotorFacial

ROOT = Path(__file__).resolve().parent.parent


def _embedding_usable(emb: list | None) -> bool:
    if not isinstance(emb, list) or len(emb) < 64:
        return False
    return sum(float(v) * float(v) for v in emb) > 1e-12


def _huella_de_preparada(motor: MotorFacial, preparada: dict) -> list:
    """Paso 2 del registro: la huella (los primeros 1536 números; las variantes no se calculan)."""
    out = motor.huella_registro(preparada)
    emb = out["face"]["embedding"]
    dim = 1536
    if isinstance(emb, list) and len(emb) > dim and len(emb) % dim == 0:
        emb = emb[:dim]
    if not _embedding_usable(emb):
        raise ValueError("embedding vacío o inválido")
    return emb


def huella_de_selfie(motor: MotorFacial, datos: bytes) -> dict:
    """Selfie → {embedding, cara (112×112 alineada), caras_en_foto}. Igual que registrar_galeria."""
    preparada = motor.preparar_registro(datos)
    return {
        "embedding": _huella_de_preparada(motor, preparada),
        "cara": preparada["cara"],
        "caras_en_foto": int(preparada["face_count"]),
    }


def registrar_galeria(
    motor: MotorFacial, estudiantes: list[Estudiante]
) -> tuple[list[dict], list[dict]]:
    personas = []
    fallos = []
    # Un hilo aparte lee cada selfie, busca la cara y la alinea. Este hilo saca las huellas.
    # Así, mientras las redes trabajan en una selfie, la siguiente ya se está preparando.
    # No se guarda nada entre una lista y otra.
    aparte = ThreadPoolExecutor(1)
    preparadas = {
        i: aparte.submit(lambda ruta=est.ruta_imagen: motor.preparar_registro(ruta.read_bytes()))
        for i, est in enumerate(estudiantes)
        if est.ruta_imagen.is_file()
    }
    aparte.shutdown(wait=False)
    for i, est in enumerate(estudiantes):
        if i not in preparadas:
            fallos.append(
                {
                    "id": est.id,
                    "nombre": est.nombre,
                    "estado": "ausente",
                    "similitud": None,
                    "motivo": f"sin_foto:{est.ruta_imagen}",
                    "bbox": None,
                    "foto": str(est.ruta_imagen) if est.ruta_imagen else "",
                    "origen": "ai",
                }
            )
            continue
        try:
            # La lista solo usa los primeros 1536 números; las variantes no se calculan.
            preparada = preparadas[i].result()
            emb = _huella_de_preparada(motor, preparada)
            # "cara": la cara de registro alineada (112×112). La usa la comparación de caras
            # tapadas por un monitor (ia/cara_tapada.py); el resto de la lista no la toca.
            personas.append(
                {"id": est.id, "name": est.nombre, "embeddings": [emb], "cara": preparada["cara"]}
            )
        except Exception as ex:
            fallos.append(
                {
                    "id": est.id,
                    "nombre": est.nombre,
                    "estado": "ausente",
                    "similitud": None,
                    "motivo": f"registro_fallo:{ex}",
                    "bbox": None,
                    "foto": str(est.ruta_imagen) if est.ruta_imagen else "",
                    "origen": "ai",
                }
            )
    return personas, fallos


# Selfie que calza poco con la cara real del alumno: salió reconocido con la cara grande
# (SELFIE_PX o más de ancho) pero con nota baja (menos de SELFIE_NOTA).
# Medido en las fotos de prueba: de cerca, una selfie buena da 0.66–0.87; las flojas (luz quemada,
# borrosa, con filtro, la mano en la cara, sin las gafas que usa en clase) 0.52–0.65.
# Esos alumnos son los que primero quedan sin nombre cuando están lejos: con caras de menos de 20 px
# salieron con nombre el 45 % de las veces, contra 86 % los de selfie buena. Tomarles otra selfie
# (de frente, luz pareja, sin filtro, como van a clase) es lo que más sube el acierto de lejos.
# Solo es un aviso: no cambia quién queda presente o ausente.
SELFIE_PX = 35
SELFIE_NOTA = 0.65


def selfies_por_repetir(matches: list[dict]) -> list[dict]:
    """Alumnos reconocidos de cerca con nota baja: su selfie conviene repetirla.

    No cuenta las caras reconocidas por la parte de arriba (tapadas por un monitor):
    ahí la nota baja es por lo tapado, no por la selfie.
    """
    salida: dict[str, dict] = {}
    for m in matches or []:
        if not (m.get("matched") and m.get("person_id")) or m.get("via"):
            continue
        bb, sim = m.get("bbox"), m.get("similarity")
        if sim is None or not isinstance(bb, (list, tuple)) or len(bb) < 4:
            continue
        ancho = float(bb[2]) - float(bb[0])
        if ancho >= SELFIE_PX and float(sim) < SELFIE_NOTA:
            pid = str(m["person_id"])
            salida[pid] = {"id": pid, "nombre": m.get("name"), "similitud": float(sim), "ancho": round(ancho)}
    return sorted(salida.values(), key=lambda d: d["similitud"])


# Sugerencias para revisar a mano. Una cara lejana (lado menor de menos de SUGERIR_PX) que quedó
# SIN nombre, cuyo candidato (el alumno sin cara asignada con la nota más alta) llega a SUGERIR_NOTA.
# El motor no le pone nombre solo porque a ese tamaño un parecido llega a 0.32; aquí no se pone nadie
# presente: la lista muestra "¿revisar?" y la caja en naranja, y el docente confirma con
# "Poner presente". Así ninguna cara chica queda ignorada sin arriesgar un nombre equivocado.
# Medido con el motor real en el banco (73 fotos-escala, 2026-11-16, tmp/lab_lejos/x/correr_sug.py):
# 104 sugerencias, 99 correctas (95 %); 2 sugerían a otro alumno y 3 eran personas no registradas.
# Con nota 0.25: 74, todas correctas, pero quedan fuera 25 caras de alumnos. Ninguna decisión del
# motor cambió (mismos nombres en las 73).
SUGERIR_PX = 20
SUGERIR_NOTA = 0.20
MOTIVO_REVISAR = "revisar_cara_lejana"
FOTO_COMPRIMIDA_PX = 1600   # WhatsApp normal deja la foto en 1600 px de lado mayor


def sugerencias_lejanas(matches: list[dict]) -> list[dict]:
    """Una sugerencia por alumno (la cara con más nota): {id, nombre, bbox, nota, lado}."""
    salida: dict[str, dict] = {}
    for m in matches or []:
        if m.get("matched") or not m.get("candidate_id"):
            continue
        bb, nota = m.get("bbox"), m.get("candidate_score")
        if nota is None or not isinstance(bb, (list, tuple)) or len(bb) < 4:
            continue
        lado = min(float(bb[2]) - float(bb[0]), float(bb[3]) - float(bb[1]))
        if lado >= SUGERIR_PX or float(nota) < SUGERIR_NOTA:
            continue
        pid = str(m["candidate_id"])
        if pid not in salida or float(nota) > salida[pid]["nota"]:
            salida[pid] = {
                "id": pid,
                "nombre": m.get("candidate_name"),
                "bbox": [float(v) for v in bb[:4]],
                "nota": float(nota),
                "lado": round(lado),
            }
    return sorted(salida.values(), key=lambda d: -d["nota"])


def lado_mayor_foto(ruta: Path) -> int | None:
    try:
        from PIL import Image

        from ia.leer_imagen import registrar_heif

        registrar_heif()
        with Image.open(ruta) as im:
            return int(max(im.size))
    except Exception:
        return None


def es_revisar(f: dict) -> bool:
    return f.get("estado") == "ausente" and str(f.get("motivo") or "").startswith(MOTIVO_REVISAR)


def orden_estado(f: dict) -> int:
    """0 presente, 1 revisar a mano, 2 ausente."""
    if f.get("estado") == "presente":
        return 0
    return 1 if es_revisar(f) else 2


def aviso_foto(por_revisar: int, lado: int | None) -> str:
    """Texto para la ventana y la consola ("" si no hay nada que avisar)."""
    if por_revisar <= 0:
        return ""
    if por_revisar == 1:
        txt = "1 cara lejana parece de un alumno pero es muy chica para ponerle nombre seguro"
    else:
        txt = f"{por_revisar} caras lejanas parecen de alumnos pero son muy chicas para ponerles nombre seguro"
    txt += ": revise las marcadas «¿revisar?» y confirme con «Poner presente»"
    if lado is not None and lado <= FOTO_COMPRIMIDA_PX:
        txt += f". La foto tiene solo {lado} px (llegó comprimida)"
    return txt + ". Para que salgan solas: foto como documento (sin comprimir) o tomada más cerca."


@dataclass
class ResultadoAsistencia:
    clase: str
    foto_grupal: Path
    excel_clase: Path
    faces_detected: int
    umbral: float
    filas: list[dict] = field(default_factory=list)
    detecciones: list[dict] = field(default_factory=list)
    excel_salida: Path | None = None
    repetir_selfie: list[dict] = field(default_factory=list)   # ver selfies_por_repetir
    sugerencias: list[dict] = field(default_factory=list)      # ver sugerencias_lejanas
    lado_foto: int | None = None                               # lado mayor de la foto grupal (px)

    @property
    def por_revisar(self) -> int:
        return sum(1 for f in self.filas if es_revisar(f))

    @property
    def aviso_foto(self) -> str:
        return aviso_foto(self.por_revisar, self.lado_foto)

    @property
    def presentes(self) -> int:
        return sum(1 for f in self.filas if f.get("estado") == "presente")

    @property
    def ausentes(self) -> int:
        return sum(1 for f in self.filas if f.get("estado") == "ausente")


def armar_lista(estudiantes: list, fallos: list[dict], resultado: dict, prog: Any = None) -> dict:
    """De la respuesta del motor (quien_esta_y_quien_no) a la lista: presente / «¿revisar?» / ausente.

    La usan la ventana, la consola y el servicio web: misma regla en todos.
    estudiantes: objetos con .id, .nombre y .ruta_imagen (puede ser None).
    """
    prog = prog or (lambda _m: None)
    presentes = {p["id"] for p in resultado.get("present", [])}
    bboxes: dict[str, list] = {}
    sims: dict[str, float] = {}
    for match in resultado.get("matches") or []:
        if match.get("matched") and match.get("person_id"):
            pid = str(match["person_id"])
            sims[pid] = match.get("similarity")
            if isinstance(match.get("bbox"), (list, tuple)) and len(match["bbox"]) >= 4:
                bboxes[pid] = list(match["bbox"])
    repetir = selfies_por_repetir(resultado.get("matches") or [])
    ids_repetir = {d["id"] for d in repetir}
    if repetir:
        prog("Conviene repetir la selfie de: " + ", ".join(f"{d['nombre']} ({d['similitud']:.2f})" for d in repetir))
    sugeridas = {
        d["id"]: d for d in sugerencias_lejanas(resultado.get("matches") or []) if d["id"] not in presentes
    }
    if sugeridas:
        prog("Revisar a mano (caras lejanas): " + ", ".join(f"{d['nombre']} ({d['nota']:.2f})" for d in sugeridas.values()))

    filas = list(fallos)
    ids_fallo = {f["id"] for f in fallos}
    for est in estudiantes:
        if est.id in ids_fallo:
            continue
        foto_rel = str(est.ruta_imagen) if est.ruta_imagen else ""
        if est.id in presentes:
            filas.append(
                {
                    "id": est.id,
                    "nombre": est.nombre,
                    "estado": "presente",
                    "similitud": sims.get(est.id),
                    "motivo": "repetir_selfie" if est.id in ids_repetir else "",
                    "bbox": bboxes.get(est.id),
                    "foto": foto_rel,
                    "origen": "ai",
                }
            )
        elif est.id in sugeridas:
            # Sigue ausente hasta que el docente lo confirme; bbox = la cara sugerida.
            sug = sugeridas[est.id]
            filas.append(
                {
                    "id": est.id,
                    "nombre": est.nombre,
                    "estado": "ausente",
                    "similitud": None,
                    "motivo": f"{MOTIVO_REVISAR}:{sug['nota']:.2f}",
                    "bbox": sug["bbox"],
                    "sugerencia": sug["nota"],
                    "foto": foto_rel,
                    "origen": "ai",
                }
            )
        else:
            filas.append(
                {
                    "id": est.id,
                    "nombre": est.nombre,
                    "estado": "ausente",
                    "similitud": None,
                    "motivo": "no_reconocido",
                    "bbox": None,
                    "foto": foto_rel,
                    "origen": "ai",
                }
            )

    # Presentes primero, luego los de revisar a mano, ausentes al final
    filas.sort(
        key=lambda f: (
            orden_estado(f),
            str(f.get("nombre") or "").lower(),
            str(f.get("id") or ""),
        )
    )

    caja_sugerida = {tuple(d["bbox"]): d for d in sugeridas.values()}
    detecciones = []
    for match in resultado.get("matches") or []:
        bb = match.get("bbox")
        sug = caja_sugerida.get(tuple(float(v) for v in bb[:4])) if isinstance(bb, (list, tuple)) and len(bb) >= 4 else None
        detecciones.append(
            {
                "bbox": bb,
                "matched": bool(match.get("matched")),
                "person_id": match.get("person_id"),
                "name": match.get("name"),
                "similarity": match.get("similarity"),
                "sugerido": None if sug is None else {"id": sug["id"], "nombre": sug["nombre"], "nota": sug["nota"]},
            }
        )

    return {"filas": filas, "detecciones": detecciones, "repetir_selfie": repetir, "sugeridas": sugeridas}


_motor: MotorFacial | None = None


def obtener_motor() -> MotorFacial:
    global _motor
    if _motor is None:
        _motor = MotorFacial()
        _motor.cargar()
    return _motor


def pasar_lista(
    excel_clase: Path,
    foto_grupal: Path,
    *,
    umbral: float | None = None,
    guardar_excel: bool = True,
    salida: Path | None = None,
    motor: MotorFacial | None = None,
    on_progreso: Any = None,
) -> ResultadoAsistencia:
    """Misma lógica que la web: registra huellas del Excel y reconoce en la foto grupal."""
    excel_clase = excel_clase.resolve()
    foto_grupal = foto_grupal.resolve()
    if not foto_grupal.is_file():
        raise FileNotFoundError(f"No existe la foto grupal: {foto_grupal}")

    def prog(msg: str) -> None:
        if on_progreso:
            on_progreso(msg)

    estudiantes = cargar_estudiantes(excel_clase)
    prog(f"Clase: {len(estudiantes)} estudiantes en Excel")
    m = motor or obtener_motor()
    prog("Generando huellas desde fotos del Excel…")
    personas, fallos = registrar_galeria(m, estudiantes)
    prog(f"Huellas OK={len(personas)}  fallos={len(fallos)}")
    prog("Analizando foto grupal…")
    resultado = m.quien_esta_y_quien_no(
        foto_grupal.read_bytes(), personas, umbral=umbral
    )

    lista = armar_lista(estudiantes, fallos, resultado, prog)
    filas, detecciones = lista["filas"], lista["detecciones"]
    repetir, sugeridas = lista["repetir_selfie"], lista["sugeridas"]
    lado = lado_mayor_foto(foto_grupal)

    out_path = None
    if guardar_excel:
        if salida is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = (
                ROOT / "datos" / "listas" / f"lista_{excel_clase.parent.name}_{stamp}.xlsx"
            )
        else:
            out_path = salida.resolve()
        guardar_lista(
            out_path,
            clase=excel_clase.parent.name,
            foto_grupal=str(foto_grupal),
            umbral=float(resultado.get("threshold") or 0),
            faces_detected=int(resultado.get("faces_detected") or 0),
            filas=filas,
            detecciones=detecciones,
        )
        prog(f"Lista guardada: {out_path}")

    return ResultadoAsistencia(
        clase=excel_clase.parent.name,
        foto_grupal=foto_grupal,
        excel_clase=excel_clase,
        faces_detected=int(resultado.get("faces_detected") or 0),
        umbral=float(resultado.get("threshold") or 0),
        filas=filas,
        detecciones=detecciones,
        excel_salida=out_path,
        repetir_selfie=repetir,
        sugerencias=list(sugeridas.values()),
        lado_foto=lado,
    )
