"""Crea una carpeta de clase con Excel + carpeta fotos/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.excel_clase import crear_plantilla_clase


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nombre", default="Clase_Ejemplo", help="Nombre de la carpeta/clase")
    ap.add_argument(
        "--donde",
        type=Path,
        default=ROOT / "datos" / "clases",
        help="Carpeta padre de clases",
    )
    args = ap.parse_args()
    excel = crear_plantilla_clase(args.donde, args.nombre)
    print(f"[OK] Plantilla creada: {excel}")
    print(f"     Fotos → {excel.parent / 'fotos'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
