# Vision_Computacional_Final

Motor de IA en Python + Excel por clase. Corre en esta PC: sin web y sin base de datos.

## Dos formas de usarlo (los mismos Excel de `datos/`)

| | Cómo se abre | Para qué |
|---|---|---|
| **Ventana de Python** | `.\.venv\Scripts\python.exe lanzar_ui.py` → elegir el Excel de la clase y la foto | en esta PC, como siempre |
| **Web** | `powershell -ExecutionPolicy Bypass -File .\web\iniciar_local.ps1` → http://localhost:3000 | en un servidor: login de docentes, clases, registrar estudiantes con la cámara, pasar lista |

Lo que se agrega en la web (estudiantes, listas) queda en los mismos `estudiantes.xlsx`, `fotos/` y
`datos/listas/` que usa la ventana, y al revés. Detalles de la web: `web/README.md`.

```
ia/       → detección y reconocimiento
models/   → redes .onnx / .tflite / .task
app/      → Excel + pasar lista
datos/    → clases reales + listas generadas
ui/       → ventana (lista + ver foto)
config/   → variables de la versión actual
```

## Datos (todo aquí)

```
datos/clases/primera prueba/
datos/clases/segunda prueba/
datos/clases/clase_computacional2/
datos/listas/
```

Cada clase: `estudiantes.xlsx` + `fotos/` + `fotos_grupales/` + `foto_grupal.webp`.

## Uso

```powershell
cd D:\Vision_Computacional_Final
. .\config\configurar_r19.ps1

# Consola
.\.venv\Scripts\python.exe app\pasar_lista.py `
  --clase "datos\clases\primera prueba\estudiantes.xlsx" `
  --foto "datos\clases\primera prueba\foto_grupal.webp"

# Ventana
.\.venv\Scripts\python.exe lanzar_ui.py
```

Secuencia IA: `docs/SECUENCIA_IA.md`
