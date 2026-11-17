# Pasar lista con varias fotos (guardado, no activo)

La app pasa lista con **una sola foto**. Esta es una opción que se probó el 14 de noviembre de 2026
y se dejó guardada por si algún día sirve.

## Qué hace

Se eligen 2 o 3 fotos del salón de la misma clase. Cada foto pasa por el motor por separado,
con las mismas reglas de siempre (no se afloja nada). Al final se juntan los nombres:
está presente quien sale reconocido en al menos una de las fotos.

Las fotos no se conectan entre sí: no hace falta saber que una cara de la foto 1 es la misma
de la foto 2. La lista es de alumnos, así que si alguien sale en las dos cuenta una sola vez.
En la ventana, al elegir un alumno se muestra la foto donde salió con la nota más alta.

## Lo que se midió

| Prueba | Mejor foto sola | Dos fotos juntas |
|---|---|---|
| Banco de pruebas, clase al 40 % del tamaño (caras de ~13–20 px) | 83 % con nombre | 88 % |
| Banco de pruebas, clase al 30 % del tamaño (caras de ~10–15 px) | 52 % con nombre | 57 % |
| Fotos reales del 12 nov (clase_computacional2), 9:19 sola vs 9:05 + 9:19 | 14 presentes | 15 presentes |

Ningún ausente salió marcado. En la foto real, el que se suma es E019, que solo sale reconocido
en la foto de las 9:05 (por la comparación de media cara, la de los monitores).

Rinde más si las fotos son desde puntos o momentos distintos: quien sale tapado o muy chico
en una puede salir bien en la otra. Dos fotos seguidas desde el mismo punto casi no suman.

## Cómo activarlo

Los cambios están en `varias_fotos.patch` (en esta misma carpeta). Desde la raíz del proyecto:

```powershell
cd D:\Vision_Computacional_Final
git apply docs\varias_fotos\varias_fotos.patch
```

Toca `app/asistencia_core.py`, `app/excel_clase.py`, `app/pasar_lista.py`, `ui/ventana_lista.py`
y los README. Con una sola foto, el resultado es el mismo de siempre.

Después de activarlo:

- **Ventana:** en "2. Foto(s) grupal(es)…" se eligen varias fotos con Ctrl+clic.
- **Consola:** `--foto foto1.jpg foto2.jpg`.
- **Excel de la lista:** columna `foto_grupal` con la foto donde salió cada presente.

Si en el futuro esos archivos cambian, el parche puede no aplicar tal cual (`git apply --check`
lo dice antes de tocar nada). En ese caso hay que rehacer los cambios a mano a partir del parche.

## Pruebas que se usaron

En `tmp/lab_lejos/x/` (laboratorio, no forman parte del programa):

- `varias_fotos.py`: la medición del banco (sin redes).
- `probar_varias.py`: prueba de la unión con un motor de mentira.
- `probar_ventana.py`: prueba de la ventana con un resultado de dos fotos.
