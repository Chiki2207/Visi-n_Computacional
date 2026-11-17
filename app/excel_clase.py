"""
Leer / escribir Excel de clase y de lista de asistencia.

Formato estudiantes (una hoja "estudiantes"):
  id | nombre | ruta_imagen

ruta_imagen puede ser:
  - relativa al Excel (recomendado): fotos/E001.webp
  - absoluta: D:\\...\\E001.webp
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook, load_workbook


@dataclass
class Estudiante:
    id: str
    nombre: str
    ruta_imagen: Path


def _celda(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def cargar_estudiantes(excel: Path) -> list[Estudiante]:
    excel = excel.resolve()
    if not excel.is_file():
        raise FileNotFoundError(f"No existe el Excel de clase: {excel}")

    wb = load_workbook(excel, read_only=True, data_only=True)
    ws = wb["estudiantes"] if "estudiantes" in wb.sheetnames else wb.active
    filas = list(ws.iter_rows(values_only=True))
    wb.close()
    if not filas:
        raise ValueError("El Excel está vacío")

    encabezado = [_celda(c).lower() for c in filas[0]]
    # Acepta nombres de columna flexibles
    def idx(*nombres: str) -> int:
        for n in nombres:
            if n in encabezado:
                return encabezado.index(n)
        raise ValueError(
            f"Falta columna {nombres[0]!r} en {excel.name}. "
            f"Encabezados: {encabezado}"
        )

    i_id = idx("id", "codigo", "código")
    i_nom = idx("nombre", "name", "estudiante")
    i_foto = idx("ruta_imagen", "foto", "imagen", "ruta", "path")

    base = excel.parent
    out: list[Estudiante] = []
    vistos: set[str] = set()
    for row in filas[1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        eid = _celda(row[i_id] if i_id < len(row) else "")
        nombre = _celda(row[i_nom] if i_nom < len(row) else "")
        rel = _celda(row[i_foto] if i_foto < len(row) else "")
        if not eid or not nombre or not rel:
            continue
        if eid in vistos:
            raise ValueError(f"Id duplicado en Excel: {eid}")
        vistos.add(eid)
        ruta = Path(rel)
        if not ruta.is_absolute():
            ruta = (base / ruta).resolve()
        out.append(Estudiante(id=eid, nombre=nombre, ruta_imagen=ruta))
    if not out:
        raise ValueError(f"No hay estudiantes válidos en {excel}")
    return out


def guardar_lista(
    salida: Path,
    *,
    clase: str,
    foto_grupal: str,
    umbral: float,
    faces_detected: int,
    filas: list[dict],
    detecciones: list[dict] | None = None,
) -> Path:
    """
    filas: [{id, nombre, estado, similitud, motivo}]
    detecciones opcionales: cajas de la IA para revisión.
    """
    salida = salida.resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "lista"
    ws.append(["id", "nombre", "estado", "similitud", "motivo", "origen"])
    for f in filas:
        sim = f.get("similitud")
        ws.append(
            [
                f.get("id"),
                f.get("nombre"),
                f.get("estado"),
                None if sim is None else round(float(sim), 4),
                f.get("motivo") or "",
                f.get("origen") or "ai",
            ]
        )

    meta = wb.create_sheet("meta")
    meta.append(["campo", "valor"])
    meta.append(["clase", clase])
    meta.append(["foto_grupal", foto_grupal])
    meta.append(["umbral", umbral])
    meta.append(["rostros_detectados", faces_detected])
    meta.append(["presentes", sum(1 for f in filas if f.get("estado") == "presente")])
    meta.append(["ausentes", sum(1 for f in filas if f.get("estado") == "ausente")])

    if detecciones:
        wd = wb.create_sheet("detecciones")
        wd.append(["i", "matched", "id", "nombre", "similitud", "x1", "y1", "x2", "y2"])
        for i, d in enumerate(detecciones, 1):
            bb = d.get("bbox") or [None, None, None, None]
            wd.append(
                [
                    i,
                    bool(d.get("matched")),
                    d.get("person_id") or "",
                    d.get("name") or "",
                    d.get("similarity"),
                    bb[0],
                    bb[1],
                    bb[2],
                    bb[3],
                ]
            )

    wb.save(salida)
    return salida


def crear_plantilla_clase(carpeta: Path, nombre_clase: str = "Clase_Ejemplo") -> Path:
    """
    Crea:
      carpeta/nombre_clase/estudiantes.xlsx
      carpeta/nombre_clase/fotos/   (vacía, listo para poner E001.webp…)
    """
    root = (carpeta / nombre_clase).resolve()
    fotos = root / "fotos"
    fotos.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "estudiantes"
    ws.append(["id", "nombre", "ruta_imagen"])
    # Filas de ejemplo (el usuario reemplaza / agrega fotos reales)
    ejemplos = [
        ("E001", "Estudiante Uno", "fotos/E001.webp"),
        ("E002", "Estudiante Dos", "fotos/E002.webp"),
        ("E003", "Estudiante Tres", "fotos/E003.webp"),
    ]
    for row in ejemplos:
        ws.append(list(row))

    info = wb.create_sheet("info")
    info.append(["campo", "valor"])
    info.append(["clase", nombre_clase])
    info.append(
        [
            "instruccion",
            "Pon la selfie de cada alumno en fotos/ con el nombre del id "
            "(E001.webp). Luego edita id/nombre/ruta_imagen. "
            "Varias clases = varias carpetas con su Excel.",
        ]
    )

    excel = root / "estudiantes.xlsx"
    wb.save(excel)

    # README corto en la carpeta de la clase
    (root / "LEEME.txt").write_text(
        f"Clase: {nombre_clase}\n\n"
        "1) Coloca una foto frontal por alumno en la carpeta fotos/\n"
        "   Ejemplo: fotos/E001.webp\n"
        "2) Edita estudiantes.xlsx (id, nombre, ruta_imagen)\n"
        "3) Pasa lista:\n"
        "   python app/pasar_lista.py --clase datos/clases/"
        f"{nombre_clase}/estudiantes.xlsx "
        "--foto datos/fotos_grupales/TU_FOTO.webp\n",
        encoding="utf-8",
    )
    return excel
