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

## Procesamiento de lenguaje natural (chat del asistente)

No usa spaCy, NLTK ni un modelo propio. El chat entiende órdenes en español con **reglas**
(expresiones regulares) y, solo en la web, un **respaldo con la API de Gemini** si las reglas
no entendieron la frase. **No toca el reconocimiento de caras** ni reentrena nada.

### Cómo se explica (cuatro pasos)

1. **Normalizar** — minúsculas y sin tildes («Sebastián» = «sebastian»).
2. **Interpretar** — de la frase saca la acción (`presente`, `ausente`, `quitar`, `agregar`,
   `pasar`, `entrar`…) y los nombres.
3. **Resolver nombres** — busca en la lista real. Si hay dos iguales, no adivina: pide apellido,
   id o el número de la opción.
4. **Ejecutar** — la ventana o la página hacen el cambio con los mismos botones/APIs de siempre
   y responden «Listo».

### Dónde está el código

| Pieza | Archivo |
|---|---|
| Reglas (escritorio) | `ui/asistente.py` |
| Reglas + chat web | `web/frontend/asistente.js` |
| Respaldo Gemini (solo servidor) | `web/frontend/chat_llm.py` → `POST /api/chat/interpretar` |
| Conectar el chat a las APIs | `web/frontend/app.js` |

### Gemini (solo web, solo si hace falta)

1. Primero corren las **reglas** (rápido, sin internet).
2. Si la acción sale `no` («no entendí»), el navegador pide al servidor
   `POST /api/chat/interpretar`.
3. El servidor llama a **Gemini** (`GEMINI_API_KEY` en `web/.env`). Gemini solo devuelve una
   orden del mismo tipo (JSON). Los nombres vuelven a pasar por el buscador de la lista;
   eliminar sigue pidiendo «sí / no».
4. Si no hay clave, Gemini tarda o falla, el chat responde «No entendí» como antes.

Variables en `web/.env` (ver `web/.env.ejemplo`):

- `GEMINI_API_KEY` — clave de Google AI Studio (solo en el servidor; no va en git ni en el JS).
- `GEMINI_MODELO` — por defecto `gemini-2.5-flash-lite`.
- `GEMINI_TIMEOUT` — segundos máximos (por defecto 2.5).

La ventana de escritorio (`lanzar_ui.py`) sigue solo con reglas; no usa Gemini.
