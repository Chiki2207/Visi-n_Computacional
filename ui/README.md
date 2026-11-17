# ui/ — interfaz de escritorio

## Arranque

```powershell
cd D:\Vision_Computacional_Final
. .\config\configurar_r19.ps1
.\.venv\Scripts\python.exe lanzar_ui.py
```

## Uso

1. **Excel de clase…** → `datos/clases/<Clase>/estudiantes.xlsx` (si hay `foto_grupal.webp` al lado, se carga sola)
2. **Foto grupal…** (si hace falta otra)
3. **Pasar lista**
4. Clic en la lista → ficha; **👁 Ver foto** → selfie grande; presente → marca en la grupal

### Aviso "repetir selfie de: …"

Sale cuando un alumno quedó reconocido de cerca (cara de 35 px o más) pero con nota baja (menos de 0.65):
su selfie se parece poco a como se ve en clase. Esos alumnos son los primeros que quedan sin nombre cuando
están lejos (en las pruebas: 45 % de sus caras lejanas con nombre, contra 86 % de los que tienen buena selfie).
En el Excel de la lista aparece como motivo `repetir_selfie`. No cambia quién queda presente.

Cómo tomar la selfie nueva: de frente, cara completa (sin cortar la frente), luz pareja sin contraluz,
**sin filtro de belleza**, sin la mano en la cara, y como va a clase (con las gafas si las usa).
Reemplazar el archivo de la carpeta `fotos/` con el mismo nombre.

### «¿revisar?» — caras lejanas sugeridas

Ninguna cara chica queda ignorada. Si una cara del fondo (menos de 20 px) quedó sin nombre pero se
parece a un alumno que no apareció (nota 0.20 o más), ese alumno sale en la lista como **¿revisar?**
(fondo amarillo) y su cara se marca en **naranja** en la foto al elegirlo. Sigue ausente hasta que
usted lo confirme: compare la cara con la selfie (👁 Ver foto) y, si es, **Poner presente**.
En el Excel queda como ausente con motivo `revisar_cara_lejana:<nota>` (o `manual_presente` si se confirmó).

En el banco de pruebas: 104 sugerencias, 99 correctas (95 %); las otras 5 eran otro alumno (2)
o una persona no registrada (3). Por eso no se ponen presentes solas: usted confirma.

El motor no les pone nombre solo porque a ese tamaño una persona parecida llega a 0.32. Lo que hace
que salgan solas es más resolución: la foto **como documento** (WhatsApp → adjuntar → Documento;
no se comprime) o tomada más cerca. Si la foto tiene solo 1600 px de lado, el aviso lo dice.

### Fotos enviadas como documento

Se abren JPG, PNG, WebP y **HEIC** (iPhone). La foto original del celular suele venir acostada con
una marca de giro (EXIF): el programa la endereza igual para reconocer y para dibujar las cajas.
Una foto grande tarda más (una de 3088 px tardó 105 s) pero trae unas 2,5 veces más píxeles por cara.
