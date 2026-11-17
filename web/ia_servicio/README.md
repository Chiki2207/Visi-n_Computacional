# web/ia_servicio — servicio de IA (puerto 8001)

El motor r19 del proyecto (`ia/`, `models/`, `config/configurar_r19.ps1`) detrás de HTTP. **No guarda nada.**
Solo lo llama el servidor web (`web/frontend/servidor.py`), con la cabecera `X-IA-Token` = `IA_TOKEN` de `web/.env`. No publicarlo a internet.

```powershell
.\.venv\Scripts\python.exe -m pip install -r web\ia_servicio\requisitos.txt   # una vez
.\.venv\Scripts\python.exe web\ia_servicio\servicio.py
```

| Ruta | Qué hace |
|---|---|
| `GET /salud` | `version_huella`: versión del motor (cambia si cambia el código de `ia/`, la config r19 o los modelos) |
| `POST /registro` (foto) | selfie → huella (1536 números), cara alineada, vista JPEG |
| `POST /pasar-lista` (foto + datos) | foto grupal + huellas → la lista (presente / «¿revisar?» / ausente), cajas, avisos, vista JPEG |

Usa las mismas funciones que la ventana de escritorio (`app/asistencia_core.py`), así que da el mismo
resultado con la misma foto. Atiende un trabajo a la vez (el motor ocupa toda la CPU); los demás esperan.
Si una huella llega de otra versión del motor, responde 409 (el servidor web pide la huella de nuevo).
