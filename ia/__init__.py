"""
Paquete de inteligencia artificial del proyecto.

Aquí vive el reconocimiento de caras, en local y sin web:
  1) Leer imagen
  2) Detectar caras (YuNet)
  3) Convertir cada cara en una huella de 1536 números
  4) Comparar esas huellas y armar presentes / ausentes
"""

from ia import version

# Antes que nada: fijar la versión r19. Los demás módulos leen sus valores al importarse.
version.aplicar()

from ia.motor_facial import MotorFacial  # noqa: E402

__all__ = ["MotorFacial", "version"]
