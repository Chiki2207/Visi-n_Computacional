# Carpeta `ia/` — Inteligencia Artificial (Python puro)

Toda la lógica de detección y reconocimiento. **Sin web.** Corre en esta PC con modelos en `../models/`.

## Entrada para explicar / usar

`motor_facial.py` → clase `MotorFacial` (orquesta todo).

## Secuencia

1. `leer_imagen.py` — abrir foto (OpenCV)  
2. `detectar_caras.py` — YuNet (OpenCV DNN) + multi-escala  
3. `verificar_caras.py` + `retina_caras.py` — filtrar falsos / RetinaFace-R50  
4. `forma_facial.py` — alinear (MediaPipe)  
5. `reconocedor_onnx.py` — huella EdgeFace + AdaFace-50 + AdaFace-101  
6. `comparar.py` — coseno + asignación + k-recíproco  
7. `motor_facial.py` — API de alto nivel  

Detalle: `../docs/SECUENCIA_IA.md`.
