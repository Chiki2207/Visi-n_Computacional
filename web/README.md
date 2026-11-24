# web/ — versión web (para servidor)

Dos servicios, cada uno en su puerto. **Sin base de datos**: todo se guarda en los mismos Excel y carpetas
que usa la ventana de escritorio, así que lo que se hace en la web lo ve la ventana y al revés.
El motor de IA (`ia/`, `models/`, `config/`) se usa tal cual, sin cambios.

```
 navegador ──► web :3000 (web/frontend) ──► IA :8001 (web/ia_servicio)
               página + lee/escribe Excel       motor r19, no guarda nada
                        │
                        ▼
               datos/clases/<clase>/estudiantes.xlsx   alumnos (id, nombre, ruta_imagen)
               datos/clases/<clase>/fotos/             selfies   (E021_Nombre_Apellido.jpg)
               datos/clases/<clase>/fotos_grupales/    fotos de clase subidas para pasar lista
               datos/listas/lista_<clase>_<fecha>.xlsx listas (lista / meta / detecciones, como la ventana,
                                                       + hojas "cajas" y "web" para dibujar las caras)
```

| Servicio | Carpeta | Puerto | Publicar a internet |
|---|---|---|---|
| Web (página + Excel) | `web/frontend/` | 3000 | sí (con HTTPS) |
| IA | `web/ia_servicio/` | 8001 | **no** (solo la usa la web, con la clave `IA_TOKEN`) |

## Cómo se usa la página

1. **Iniciar sesión** (docente): usuario y contraseña. Mismo estilo que el proyecto Vision_Computaciona_completo
   (logo de la Universidad de la Amazonia, verde institucional).
2. **Tus clases**: entrar a una o crear una nueva.
3. En la clase, tres pestañas:
   - **Pasar lista**: «Tomar foto» del salón (cámara del celular o del computador) o «Galería / Archivo» → *Pasar lista*.
   - **Estudiantes**: «Tomar foto» del estudiante + nombre (el código se pone solo) → *Registrar estudiante*.
     La IA revisa que la foto tenga una cara antes de guardarla.
   - **Historial**: todas las listas (también las hechas con la ventana de Python).
4. En una lista: la foto con las caras marcadas, **«¿Están en la foto?»** (cara lejana dudosa al lado de su foto:
   *Sí, está* / *No*), y la lista con *Poner presente* / *Poner ausente*. *Descargar Excel*.

La cámara dentro de la página funciona en `localhost` y, en el servidor, solo con **HTTPS** (regla de los navegadores).
En el celular, «Tomar foto» abre la cámara del teléfono.

## Qué hace cada acción (igual que a mano)

- **Agregar alumno**: la IA revisa que la selfie tenga una cara; se guarda en `fotos/<código>_<Nombre>.<ext>`
  y se agrega la fila `id, nombre, ruta_imagen` al `estudiantes.xlsx` de la clase. La hoja `info` no se toca.
- **Cambiar selfie / nombre**: se actualiza la fila; la selfie anterior va a `fotos/_borradas/`.
- **Quitar alumno**: se quita la fila; la selfie va a `fotos/_borradas/` (no se elimina).
- **Nueva clase**: carpeta `datos/clases/<nombre>/` con `estudiantes.xlsx` (hojas estudiantes + info), `fotos/` y `fotos_grupales/`.
- **Pasar lista**: la foto queda en `fotos_grupales/` y la lista en `datos/listas/`, con la misma función que la
  ventana (`app/excel_clase.guardar_lista`) y el mismo resultado (probado con las mismas fotos).
- **Corregir a mano / confirmar «¿revisar?»**: se escribe en el Excel de esa lista (estado, motivo `manual_…`, origen `manual`).
- **Borrar lista**: va a `datos/listas/_borradas/`.
- El historial muestra también las listas hechas con la ventana.

Si un Excel está abierto en Microsoft Excel, la web no puede guardarlo y lo avisa ("ciérrelo").
**Huellas:** al subir la foto de un estudiante la web responde de una ("Foto subida con éxito") y el servidor saca
la huella por dentro; queda guardada en `fotos/_huellas/` y solo se rehace si cambia la foto o la versión del motor.
Al arrancar el servidor, al entrar a una clase y antes de cada lista se crean las que falten. Si una foto no tiene
cara, el estudiante sale en rojo "La foto no sirve: tome otra".

## Primera vez

```powershell
cd D:\Vision_Computacional_Final
.\.venv\Scripts\python.exe -m pip install -r web\ia_servicio\requisitos.txt        # IA (entorno del motor)
python -m venv web\frontend\.venv                                                    # web (entorno aparte)
web\frontend\.venv\Scripts\python.exe -m pip install -r web\frontend\requisitos.txt
copy web\.env.ejemplo web\.env          # y poner una clave larga en IA_TOKEN
web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py crear-usuario --usuario profe --nombre "Su Nombre"
```

## Arrancar

```powershell
powershell -ExecutionPolicy Bypass -File .\web\iniciar_local.ps1      # abre las dos ventanas
# o a mano, cada uno en su terminal:
.\.venv\Scripts\python.exe web\ia_servicio\servicio.py                 # IA  :8001 (tarda ~20 s en cargar)
web\frontend\.venv\Scripts\python.exe web\frontend\servidor.py         # web :3000
```

Abrir http://localhost:3000.

## Producción

- **Linux: librerías del sistema obligatorias** (el detector de rostros usa gráficos aunque no haya pantalla;
  sin ellas cada huella falla). Debian/Ubuntu:
  `sudo apt-get install -y libgl1 libegl1 libgles2 libglib2.0-0`
  Comprobar: `.venv/bin/python -c "import mediapipe, cv2, onnxruntime; print('ok')"` y subir una foto de prueba.
- Hacia internet solo el puerto **443** (y 80 para el certificado), con un proxy HTTPS (Caddy o nginx) que
  pase todo a `127.0.0.1:3000`. Los puertos 3000 y 8001 quedan cerrados en el firewall.
- `IA_TOKEN` nueva y larga en `web/.env`. `DATOS` apunta a la carpeta de datos (por defecto `datos/`).
- Un solo proceso de la web (ya lo hace `servidor.py`): la cola de listas y las sesiones viven en él.
  Si se reinicia a mitad de una lista, esa lista se pierde (la foto queda en `fotos_grupales/`) y se vuelve a subir.
- Copia de seguridad diaria de `datos/` (selfies = datos biométricos) y de `web/usuarios.json`.

Ejemplo de Caddy (sin probar; ajustar el dominio):

```
asistencia.su-dominio {
    request_body { max_size 30MB }
    reverse_proxy 127.0.0.1:3000
}
```

## Docentes

```powershell
web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py usuarios
web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py crear-usuario --usuario otro --nombre "Otro Docente"
web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py cambiar-clave --usuario profe
web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py desactivar --usuario profe
```

## Chat (lenguaje natural + Gemini opcional)

El chat de la página usa reglas en `web/frontend/asistente.js`. Si una frase no encaja, el
servidor puede preguntar a Gemini (`web/frontend/chat_llm.py`) solo para interpretar; la
asistencia ejecuta la orden con las APIs de siempre. Hace falta `GEMINI_API_KEY` en `web/.env`
(ver `web/.env.ejemplo`). Sin esa clave el chat sigue funcionando solo con reglas.

Explicación completa al final del `README.md` del proyecto.
