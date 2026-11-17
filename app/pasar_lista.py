"""
Pasar lista con Excel de clase + foto grupal (mismo motor ia/ r19, sin web).

Uso:
  . .\config\configurar_r19.ps1
  python app/pasar_lista.py --clase "datos/clases/primera prueba/estudiantes.xlsx" --foto "datos/clases/primera prueba/foto_grupal.webp"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.asistencia_core import pasar_lista  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Pasar lista (Excel + foto grupal)")
    ap.add_argument("--clase", type=Path, required=True)
    ap.add_argument("--foto", type=Path, required=True)
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--umbral", type=float, default=None)
    args = ap.parse_args()

    excel_clase = args.clase if args.clase.is_absolute() else (ROOT / args.clase)
    foto = args.foto if args.foto.is_absolute() else (ROOT / args.foto)
    if not foto.is_file():
        print(f"[ERROR] No existe la foto grupal: {foto}")
        return 1

    print(f"[CLASE] {excel_clase}")
    res = pasar_lista(
        excel_clase,
        foto,
        umbral=args.umbral,
        salida=args.salida,
        on_progreso=print,
    )
    print(
        f"[OK] rostros={res.faces_detected}  "
        f"presentes={res.presentes}  ausentes={res.ausentes}"
    )
    for d in res.repetir_selfie:
        print(f"[AVISO] Repetir la selfie de {d['id']} {d['nombre']}: de cerca ({d['ancho']} px) sacó solo {d['similitud']:.2f}")
    if res.aviso_foto:
        print(f"[AVISO] {res.aviso_foto}")
    if res.excel_salida:
        print(f"[OK] Lista guardada en: {res.excel_salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
