# Secuencia del motor de IA

Orden exacto del procesamiento (paquete `ia/`):

1. **Abrir imagen** → OpenCV (`leer_imagen.py`)
2. **Detectar caras** → YuNet por **OpenCV DNN** + detección **multi-escala** (`detectar_caras.py`)
3. **Filtrar falsos** → verificar caras + **RetinaFace-R50** + anti-spoof MiniFASNet (`verificar_caras.py`, `retina_caras.py`)
4. **Alinear** → MediaPipe / mezcla (`forma_facial.py`)
5. **Huella (embedding 1536)** → fusión **EdgeFace + AdaFace IR-50 + AdaFace IR-101** (`reconocedor_onnx.py`, pesos 0.18 / 0.12 / 0.70)
6. **Comparar** → similitud coseno vs galería, umbral ~0.37 (`comparar.py`)
7. **Asignar lista** → 1 cara = 1 persona + k-recíproco (`comparar.py` / `motor_facial.py`)
8. **Caras tapadas por un monitor** → las que quedaron sin nombre y ya tenían un candidato claro se vuelven a comparar solo con la parte de arriba de la cara (frente, ojos y nariz) contra el registro tapado igual (`cara_tapada.py`). No baja el umbral: la media cara tiene que llegar al mismo 0.37 y ganarle claro al segundo.

Entrada pública recomendada para explicar: `ia/motor_facial.py` → `MotorFacial`.
