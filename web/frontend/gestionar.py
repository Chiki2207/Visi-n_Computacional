"""
Docentes que pueden entrar a la web (web/usuarios.json, claves cifradas con PBKDF2).

  python web\\frontend\\gestionar.py crear-usuario --usuario profe --nombre "Nombre Apellido"   (pide la clave)
  python web\\frontend\\gestionar.py cambiar-clave --usuario profe
  python web\\frontend\\gestionar.py desactivar --usuario profe
  python web\\frontend\\gestionar.py usuarios

Los cambios valen al instante (el servidor lee el archivo en cada inicio de sesión).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from servidor import _usuarios, guardar_usuarios, hash_clave  # noqa: E402


def _clave(dada: str | None) -> str:
    c = dada or getpass.getpass("Clave (mínimo 8): ")
    if not dada and c != getpass.getpass("Repita la clave: "):
        sys.exit("Las claves no coinciden")
    if len(c) < 8:
        sys.exit("La clave debe tener al menos 8 caracteres")
    return c


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="Docentes de la web de asistencia")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("crear-usuario"); p.add_argument("--usuario", required=True); p.add_argument("--nombre", required=True); p.add_argument("--clave")
    p = sub.add_parser("cambiar-clave"); p.add_argument("--usuario", required=True); p.add_argument("--clave")
    p = sub.add_parser("desactivar"); p.add_argument("--usuario", required=True)
    sub.add_parser("usuarios")
    a = ap.parse_args()
    us = _usuarios()
    if a.cmd == "usuarios":
        for k, v in sorted(us.items()):
            print(f"{k:20s} {v['nombre']:40s} {'activo' if v.get('activo', True) else 'desactivado'}")
        return
    usuario = a.usuario.strip().lower()
    if a.cmd == "crear-usuario":
        if usuario in us:
            sys.exit(f"Ya existe el usuario {usuario}")
        us[usuario] = {"nombre": a.nombre.strip(), "clave": hash_clave(_clave(a.clave)), "activo": True}
    elif usuario not in us:
        sys.exit("No existe ese usuario")
    elif a.cmd == "cambiar-clave":
        us[usuario].update(clave=hash_clave(_clave(a.clave)), activo=True)
    else:
        us[usuario]["activo"] = False
    guardar_usuarios(us)
    print(f"Listo: {a.cmd} {usuario}")


if __name__ == "__main__":
    main()
