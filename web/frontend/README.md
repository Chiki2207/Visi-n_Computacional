# web/frontend — la web (puerto 3000)

`servidor.py` sirve la página (`index.html`, `app.js`, `estilo.css`, `marca/`: logo y fuente) y una API pequeña que lee y escribe los
mismos Excel de `datos/` que la ventana de escritorio (usa `app/excel_clase.py`: `cargar_estudiantes`,
`guardar_lista`). Sin base de datos. El reconocimiento lo pide al servicio de IA (`web/ia_servicio`).

```powershell
python -m venv web\frontend\.venv                                                    # una vez
web\frontend\.venv\Scripts\python.exe -m pip install -r web\frontend\requisitos.txt  # una vez
web\frontend\.venv\Scripts\python.exe web\frontend\servidor.py
web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py crear-usuario --usuario profe --nombre "Nombre"
```

Docentes en `web/usuarios.json` (claves cifradas). Ver `web/README.md`.

## Chat / procesamiento de lenguaje natural

El asistente flotante (abajo a la derecha) entiende texto y voz. **No llama al motor de caras.**

1. **Reglas** en `asistente.js` (igual idea que `ui/asistente.py`): normalizar → interpretar →
   resolver nombres → `app.js` ejecuta con las rutas que ya tenía (presente, ausente, quitar…).
2. **Respaldo Gemini** solo si las reglas no entendieron: `app.js` llama
   `POST /api/chat/interpretar` → `chat_llm.py` (clave `GEMINI_API_KEY` en `web/.env`).
   Gemini no marca asistencia solo: devuelve una orden y la página la aplica con el mismo
   camino (nombres contra la lista real; eliminar pide confirmación).

Sin clave o si Gemini falla/tarda, el chat queda igual que solo con reglas. Detalle en el
README raíz, sección «Procesamiento de lenguaje natural».
