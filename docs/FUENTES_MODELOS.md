# Modelos que usa la lista

Están en `models/`. El programa no los descarga: solo los lee del disco.

| Archivo | Red | Para qué |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet | Encontrar caras |
| `retinaface_r50.onnx` | RetinaFace R50 | Confirmar cajas dudosas |
| `minifasnet_v2_2.7_80x80.onnx` | MiniFASNet v2 | Cara real o foto de una foto |
| `minifasnet_v1se_4.0_80x80.onnx` | MiniFASNet v1se | Lo mismo, a otra escala |
| `face_landmarker.task` | MediaPipe Face Landmarker | 478 puntos y la pose |
| `edgeface_base.onnx` | EdgeFace | 512 números de identidad |
| `adaface_ir_50.onnx` | AdaFace IR-50 | otros 512 |
| `adaface_ir_101.onnx` | AdaFace IR-101 | otros 512 (pesa 0.70 en la nota) |
| `face_parsing_resnet18.onnx` | Face parsing | Gafas, al registrar |

Los tres de identidad se pegan: 1536 números. La comparación los vuelve a separar.

Origen de referencia (no hace falta Internet para pasar lista):

- YuNet: [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo), carpeta `face_detection_yunet`.
- EdgeFace: [yakhyo/uniface-weights](https://huggingface.co/yakhyo/uniface-weights), archivo `edgeface_base.onnx`.
- AdaFace IR-50 e IR-101: pesos AdaFace exportados a ONNX (entrada BGR, 112×112).
- RetinaFace R50, MiniFASNet y el parser de gafas: los `.onnx` que ya están en `models/`.
- Face Landmarker: paquete de tareas de MediaPipe, archivo `face_landmarker.task`.
