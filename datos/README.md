# datos/ — datasets del proyecto (un solo lugar)

```
datos/
  clases/
    primera prueba/          ← Amazonia (9 alumnos)
      estudiantes.xlsx
      fotos/                 ← selfies
      fotos_grupales/        ← todas las grupales de la clase
      foto_grupal.webp       ← la recomendada para probar
    segunda prueba/          ← Ouven (28)
    clase_computacional2/    ← Computacional 2 (12)
  listas/                    ← salidas de pasar_lista
```

## Pasar lista (consola)

```powershell
cd D:\Vision_Computacional_Final
. .\config\configurar_r19.ps1

.\.venv\Scripts\python.exe app\pasar_lista.py `
  --clase "datos\clases\primera prueba\estudiantes.xlsx" `
  --foto "datos\clases\primera prueba\foto_grupal.webp"
```

## Ventana

```powershell
.\.venv\Scripts\python.exe lanzar_ui.py
```

El diálogo de Excel/foto abre por defecto en `datos/clases/`.
