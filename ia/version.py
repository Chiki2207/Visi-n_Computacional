"""
Versión del motor: r19 — siempre la misma, se arranque como se arranque.

Los valores de la versión están en un solo lugar: config/configurar_r19.ps1.
Al importar `ia` se leen de ese archivo y se fijan, se haya ejecutado o no el .ps1
en la consola. Antes, si se abría el programa sin cargar el .ps1, corría con los valores
de fábrica del código (un solo modelo, sin RetinaFace…): otra versión, sin avisar.

Si el archivo falta, el programa se detiene con un aviso en vez de correr con otra versión.

Solo para pruebas de laboratorio: con IA_PRUEBAS=1 se respetan las variables que ya
estén puestas en la consola (lo que falte se completa con r19).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

NOMBRE = "r19"
ARCHIVO = Path(__file__).resolve().parent.parent / "config" / f"configurar_{NOMBRE}.ps1"

# Variables que leen los módulos de ia/ y que la versión NO fija: valen lo que dice el código.
# Si quedaron puestas en la consola (por ejemplo, de una versión anterior), se quitan.
DE_FABRICA = (
    "ARCHIVO_ADAFACE", "ARCHIVO_EDGEFACE", "ARCHIVO_IR101", "DEG_PX", "DET_SCORE_MATCH",
    "DET_SCORE_REGISTRO", "DET_UMBRAL", "DM_DIFERENCIA", "DM_MARGEN_COLUMNA", "DM_MARGEN_FILA",
    "DOBLE_MARGEN", "ENSAMBLE", "FILTRO_FALSAS", "GAFAS_MIN_FRAC", "MALLA_LADO_MIN",
    "MULTI_MAX_EXTRA", "MULTI_SCORE_OK", "MULTI_SIGMAS", "MULTI_UMBRAL", "PENA_DEGRADADA",
    "PENA_SINTETICA", "PIRAMIDE", "PIRAMIDE_ANCHO", "PIRAMIDE_LADO", "PIRAMIDE_REEMPLAZA",
    "REGISTRO_ANCHO", "REGISTRO_DUENO", "REGISTRO_FOTO_MIN", "REGISTRO_LADO", "REGISTRO_SCORE",
    "REG_AUG", "REG_DEGRADADAS", "REG_GAFAS", "USAR_DEGRADADAS", "USAR_SINTETICAS",
    "VARIANTES_REG", "VERIF_CONSENSO", "VERIF_DET_OK", "VERIF_MIN_PX", "VERIF_NMS",
)


def valores() -> dict[str, str]:
    """Lee del .ps1 las líneas  $env:NOMBRE = "valor"."""
    try:
        texto = ARCHIVO.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise RuntimeError(
            f"Falta la configuración de la versión {NOMBRE}: {ARCHIVO}\n"
            "Sin ese archivo el programa correría con otra versión, así que no arranca."
        ) from error
    leidos = dict(re.findall(r'^[ \t]*\$env:(\w+)[ \t]*=[ \t]*"([^"]*)"', texto, re.M))
    if "UMBRAL_RECONOCIMIENTO" not in leidos or "PESOS_FUSION" not in leidos:
        raise RuntimeError(f"{ARCHIVO} no tiene los valores de la versión {NOMBRE}.")
    return leidos


def aplicar() -> None:
    """Deja en el entorno los valores de r19. Se llama una vez, al importar `ia`."""
    de_r19 = valores()
    if os.environ.get("IA_PRUEBAS") == "1":
        for nombre, valor in de_r19.items():
            os.environ.setdefault(nombre, valor)
        return
    for nombre in DE_FABRICA:
        os.environ.pop(nombre, None)
    os.environ.update(de_r19)
