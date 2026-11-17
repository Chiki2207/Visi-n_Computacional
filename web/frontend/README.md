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
