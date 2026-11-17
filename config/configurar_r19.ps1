# Variables de la versión actual del motor de IA.
# No arranca web. Uso desde la raiz:
#   . .\config\configurar_r19.ps1
#   .\.venv\Scripts\python.exe lanzar_ui.py

$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$env:ALINEACION = "mezcla"
$env:DETECCION = "multi"
$env:MODELO_RECONOCIMIENTO = "edgeface"
$env:FUSION_ADAFACE = "1"
$env:FUSION_IR101 = "1"
$env:PESOS_FUSION = "0.18,0.12,0.70"
$env:UMBRAL_RECONOCIMIENTO = "0.37"
# Sin pasada por debajo de 0.37: un desconocido no entra solo porque “gana claro” a 0.33.
$env:DIFERENCIA_PISO = "0"
$env:PISO_EDGE = "0.20"
$env:PISO_ADA = "0.14"
$env:PISO_IR101 = "0.25"
$env:EXTRA_DUDOSA = "9"
$env:DET_SCORE_DUDOSA = "0.50"
$env:BONO_PX = "0.09"
$env:BONO_MIN_PX = "48"
# Caras del fondo: si YuNet (0.80 o más) y RetinaFace (0.5 o más) dicen que es una cara,
# se compara sin importar el tamaño. Si solo la ve YuNet, se compara desde 12 px.
# Las de menos de 32 px solo llevan nombre con esa confirmación de los dos detectores.
# Una cara de menos de 48 px confirmada por YuNet y RetinaFace usa el mismo
# umbral 0.37 (CHICA_EXTRA=0). Sin esa confirmación sigue pidiendo 0.49.
# Medido: un impostor en caras de 12–16 px no pasó de ~0.31 con los pisos.
$env:CARA_MIN_PX = "0"
$env:CARA_MIN_MATCH_PX = "12"
$env:CARA_MIN_2DET_PX = "0"
$env:CASTIGO_CHICA = "0"
$env:CHICA_PX = "24"
$env:CHICA_2DET_PX = "32"
$env:CHICA_DET = "0.80"
$env:CHICA_EXTRA = "0"
# Caras de menos de 20 px que no llegan a 0.37: entran si la nota es 0.33 o más
# y le ganan al segundo por 0.18 o más. Medido con 3.539 pruebas de impostor:
# 32 nombres más y 0 equivocados. Nota 0.32 ya deja pasar un parecido de otra persona.
# De 20 a 32 px no se aplica: ahí dos parecidos llegaron a 0.344 y 0.337 (24 y 25 px).
$env:SEGUNDO_NIVEL = "1"
$env:SEGUNDO_NOTA = "0.33"
$env:SEGUNDO_MARGEN = "0.18"
$env:SEGUNDO_MAX_PX = "20"
# Caras de menos de 32 px: también se compara la cara con contraste local (CLAHE) y se usa, por modelo y
# por alumno, la nota más alta de las dos. No inventa rasgos. Medido con el motor completo en las 73
# fotos-escala del banco (2026-11-17): 704 -> 707 nombres (+3 caras lejanas de 11-13 px), 0 equivocados,
# 0 perdidos; contra las listas de otras clases y contra la lista sin los presentes, 0 nombres nuevos.
$env:REALCE_CLAHE = "1"
$env:REALCE_PX = "32"
# Las mismas caras chicas también en BLANCO Y NEGRO contra la foto de registro en blanco y negro (quita el
# tinte de la luz y las paredes del salón); por modelo y por alumno, la nota más alta. Medido con el motor
# completo (2026-11-17), sobre lo de arriba: 707 -> 713 nombres (+6 caras lejanas de 10-17 px), 0
# equivocados, 0 perdidos; contra las listas de otras clases y sin los presentes, 0 nombres nuevos.
$env:REALCE_GRIS = "1"
$env:VERIFICAR_CARAS = "1"
$env:KR_CONSENSO = "1"
# Mismo piso que el umbral: la pasada de los 3 modelos no baja el listón.
$env:KR_T3 = "0.37"
$env:KR_M = "0.12"
$env:KR_MC = "0.04"
$env:KR_PX = "20"
$env:FAS_ACTIVO = "1"
$env:FAS_PX = "80"
$env:FAS_UMBRAL = "0.5"
# Anti-logo general: geometría YuNet + veto de matches flojos chicos/sin malla
$env:GEO_VETO = "1"
$env:GEO_VETO_PX = "48"
$env:GEO_VETO_EXTRA = "0.12"
$env:GEO_VETO_MALLA = "1"
$env:REGISTRO_MEDIAPIPE = "1"
$env:RETINA_VERIF = "1"
$env:RETINA_CONS = "0.5"
$env:RETINA_MODELO = "retinaface_r50.onnx"
# Hilos de CPU. Solo cambian el tiempo; los números que salen son los mismos.
$env:ORT_HILOS = "2"
$env:ORT_HILOS_IR50 = "3"
$env:ORT_HILOS_IR101 = "4"
$env:RETINA_HILOS = "6"
$env:CAL_DET = "0.80"
$env:CAL_DET_BONO = "0.06"
# Caras tapadas por un monitor (sentados al fondo): segunda oportunidad comparando solo la
# parte de arriba de la cara (ia/cara_tapada.py). No baja el umbral: solo confirma al alumno
# que ya iba primero con la cara completa (nota 0.25 o más), si con media cara vuelve a ganar
# con 0.37 o más, 0.20 de ventaja sobre el segundo y z de 5.5 o más. Caras de 18 a 70 px.
# Medido en 73 fotos de prueba: 5 caras más con nombre y ningún nombre cambiado ni perdido.
$env:RESCATE_TAPADA = "1"
$env:TAPADA_Y0 = "76"
$env:TAPADA_NOTA_NORMAL = "0.25"
$env:TAPADA_NOTA = "0.37"
$env:TAPADA_MARGEN = "0.20"
$env:TAPADA_Z = "5.5"
$env:TAPADA_MIN_PX = "18"
$env:TAPADA_MAX_PX = "70"
$env:PYTHONPATH = $Root

Write-Host "[IA] Entorno r19 listo en $Root" -ForegroundColor Green
