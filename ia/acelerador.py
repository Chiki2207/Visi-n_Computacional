"""
Dónde corren las redes ONNX: en la GPU dedicada si la hay; si no, en la CPU.

Las redes de identidad (EdgeFace, AdaFace IR-50 e IR-101) se llevan casi todo el tiempo de
una lista. En la GPU (DirectML, tarjeta NVIDIA o AMD) dan los mismos números que en la CPU
hasta el quinto decimal, en la octava parte del tiempo. Es la misma versión, más rápida.

Para que la velocidad nunca cambie el resultado:
  1) Solo se usa una GPU dedicada (NVIDIA o AMD con memoria propia). La gráfica integrada
     de Intel no se usa: es más lenta que la CPU y con EdgeFace dio números distintos.
  2) Cada red se prueba al cargarla con una imagen fija. Si la GPU no da lo que da la CPU
     (la firma guardada en FIRMAS), esa red se queda en la CPU.
  3) Si la GPU falla a mitad de una lista (sin memoria, controlador), la red pasa a la CPU
     y la lista sigue.

IA_GPU=0 obliga a usar solo la CPU.
Firmas de un modelo nuevo:  python -m ia.acelerador
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

# Firma de cada red en la CPU: (tamaño del archivo en bytes, 8 números de control).
# Si el archivo cambia, no hay firma con qué comparar y esa red corre en la CPU.
FIRMAS: dict[str, tuple[int, tuple[float, ...]]] = {
    "edgeface_base.onnx": (73084333, (0.10794, 0.40973, -0.01045, 0.22301, -0.95152, -0.11072, 0.38360, 0.19570)),
    "adaface_ir_50.onnx": (174396180, (-0.29607, -0.07326, -0.22907, -0.09379, -0.07345, -0.28382, -2.18284, -0.38446)),
    "adaface_ir_101.onnx": (260704652, (1.00765, -0.46323, 0.18710, -0.33265, 0.10131, -0.24469, 0.42062, 0.19263)),
    "retinaface_r50.onnx": (109110500, (-0.06250, -0.11040, 0.17106, -0.16085, -0.18887, -0.48771, -0.24895, -0.22108)),
}

TOLERANCIA = 0.02
# En la GPU cada tamaño de lote nuevo se prepara aparte (unos 0.3 s la primera vez).
# Se usan solo estos dos tamaños; lo que falte para completar se rellena y se descarta.
TANDAS = (6, 16)

_candado = threading.Lock()
# La GPU atiende una sola cosa a la vez: dos redes corriendo en ella desde hilos distintos
# la dejan colgada (DirectML la da por perdida). Todo lo que la toca pasa por este candado.
_turno_gpu = threading.Lock()
_gpu: tuple[int, str] | None | bool = False   # False = todavía no se ha buscado
_avisado = False


def _adaptadores() -> list[tuple[int, str, int, int, bool]]:
    """Adaptadores de video en el orden de DXGI: (índice, nombre, fabricante, MB propios, es de software)."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    class LUID(ctypes.Structure):
        _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.LONG)]

    class DESC1(ctypes.Structure):
        _fields_ = [
            ("Description", wintypes.WCHAR * 128), ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
            ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT), ("DedicatedVideoMemory", ctypes.c_size_t),
            ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
            ("AdapterLuid", LUID), ("Flags", wintypes.UINT),
        ]

    def metodo(objeto, indice, tipo, *argumentos):
        tabla = ctypes.cast(objeto, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(tipo, ctypes.c_void_p, *argumentos)(tabla[indice])

    dxgi = ctypes.WinDLL("dxgi")
    dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    dxgi.CreateDXGIFactory1.restype = ctypes.c_long
    iid = GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    fabrica = ctypes.c_void_p()
    if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(fabrica)) != 0 or not fabrica:
        return []
    lista = []
    try:
        enumerar = metodo(fabrica, 12, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))  # EnumAdapters1
        i = 0
        while True:
            adaptador = ctypes.c_void_p()
            if enumerar(fabrica, i, ctypes.byref(adaptador)) != 0 or not adaptador:
                break
            d = DESC1()
            if metodo(adaptador, 10, ctypes.c_long, ctypes.POINTER(DESC1))(adaptador, ctypes.byref(d)) == 0:  # GetDesc1
                lista.append((i, d.Description, d.VendorId, d.DedicatedVideoMemory // (1024 * 1024), bool(d.Flags & 2)))
            metodo(adaptador, 2, wintypes.ULONG)(adaptador)  # Release
            i += 1
    finally:
        metodo(fabrica, 2, wintypes.ULONG)(fabrica)
    return lista


def gpu_dedicada() -> tuple[int, str] | None:
    """(índice DXGI, nombre) de la primera GPU NVIDIA o AMD con memoria propia; None si no hay o no se puede usar."""
    global _gpu
    with _candado:
        if _gpu is False:
            _gpu = None
            try:
                import onnxruntime as ort

                if os.environ.get("IA_GPU", "auto").strip() != "0" and "DmlExecutionProvider" in ort.get_available_providers():
                    for indice, nombre, fabricante, mb, software in _adaptadores():
                        if fabricante in (0x10DE, 0x1002) and mb >= 1500 and not software:
                            _gpu = (indice, nombre)
                            break
            except Exception:  # sin DirectML o sin DXGI: CPU
                _gpu = None
        return _gpu


def entrada_control(forma: tuple[int, int, int, int], amplitud: float = 1.0) -> np.ndarray:
    """Imágenes fijas hechas con senos (no salen de ninguna foto). Sirven para comparar GPU y CPU."""
    n, canales, alto, ancho = forma
    y, x = np.meshgrid(np.arange(alto, dtype=np.float32), np.arange(ancho, dtype=np.float32), indexing="ij")
    lote = np.empty(forma, np.float32)
    for k in range(n):
        for c in range(canales):
            lote[k, c] = np.sin(0.11 * (c + 1) * x + 0.07 * (k + 1) * y + c) * np.cos(0.05 * (k + 2) * y - 0.03 * x)
    return lote * amplitud


def firma(salida: np.ndarray) -> np.ndarray:
    """Ocho números que resumen una salida. Si la salida cambia, cambian."""
    v = np.asarray(salida, np.float64).reshape(-1)
    v = v / (np.linalg.norm(v) or 1.0)
    i = np.arange(v.size, dtype=np.float64)
    return np.array([float(v @ np.cos(0.37 * k * i + k)) for k in range(1, 9)])


class Red:
    """Una red ONNX. correr(x) devuelve sus salidas, desde la GPU si pasó la prueba y si no desde la CPU."""

    def __init__(
        self,
        ruta: str | Path,
        hilos: int = 0,
        control: tuple[tuple[int, int, int, int], float] | None = None,
        sin_arena: bool = False,
        denormales_a_cero: bool = False,
    ) -> None:
        self.ruta = Path(ruta)
        self._hilos = hilos
        self._sin_arena = sin_arena
        self._denormales = denormales_a_cero
        self.en_gpu = False
        self.sesion = None
        gpu = gpu_dedicada() if control is not None else None
        if gpu is not None:
            self._probar_gpu(gpu, control)
        if self.sesion is None:
            self.sesion = self._crear_cpu()
        self.entrada = self.sesion.get_inputs()[0].name

    def _crear_cpu(self):
        import onnxruntime as ort

        opciones = ort.SessionOptions()
        opciones.log_severity_level = 3
        if self._denormales:
            # Sin esto, los pesos grandes dejan la CPU mucho más lenta.
            opciones.add_session_config_entry("session.set_denormal_as_zero", "1")
        if self._sin_arena:
            opciones.enable_cpu_mem_arena = False
        if self._hilos:
            opciones.intra_op_num_threads = self._hilos
        return ort.InferenceSession(str(self.ruta), opciones, providers=["CPUExecutionProvider"])

    def _probar_gpu(self, gpu: tuple[int, str], control) -> None:
        global _avisado
        import onnxruntime as ort

        guardada = FIRMAS.get(self.ruta.name)
        try:
            if guardada is None or guardada[0] != self.ruta.stat().st_size:
                raise RuntimeError("no hay firma de CPU para este archivo")
            opciones = ort.SessionOptions()
            opciones.log_severity_level = 3
            opciones.enable_mem_pattern = False                       # lo pide DirectML
            opciones.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            forma, amplitud = control
            with _turno_gpu:
                sesion = ort.InferenceSession(
                    str(self.ruta), opciones,
                    providers=[("DmlExecutionProvider", {"device_id": str(gpu[0])}), "CPUExecutionProvider"],
                )
                salida = sesion.run(None, {sesion.get_inputs()[0].name: entrada_control(forma, amplitud)})[0]
            if float(np.abs(firma(salida) - np.asarray(guardada[1])).max()) > TOLERANCIA:
                raise RuntimeError("la GPU no dio los mismos números que la CPU")
            self.sesion, self.en_gpu = sesion, True
            with _candado:
                if not _avisado:
                    _avisado = True
                    print(f"[IA] Redes en la GPU: {gpu[1]} (mismos números que en CPU, verificado)")
        except Exception as error:
            print(f"[IA] {self.ruta.name} corre en CPU ({str(error)[:120]})")

    def correr(self, entrada: np.ndarray) -> list[np.ndarray]:
        if not self.en_gpu:
            return self.sesion.run(None, {self.entrada: entrada})
        try:
            with _turno_gpu:
                return self.sesion.run(None, {self.entrada: entrada})
        except Exception as error:
            print(f"[IA] La GPU falló con {self.ruta.name} ({str(error)[:120]}); sigue en CPU")
            self.sesion, self.en_gpu = self._crear_cpu(), False
            return self.sesion.run(None, {self.entrada: entrada})

    def correr_lote(self, lote: np.ndarray) -> np.ndarray:
        """Primera salida para un lote de cualquier tamaño, por tandas (así la memoria no crece con la foto).

        Cada imagen da lo mismo vaya en la tanda que vaya. En GPU las tandas son de tamaño fijo
        (se rellenan repitiendo la última imagen y lo sobrante se descarta); en CPU, de hasta 16.
        """
        partes = []
        i = 0
        while i < len(lote):
            falta = len(lote) - i
            if self.en_gpu:
                tanda = TANDAS[0] if falta <= TANDAS[0] else TANDAS[1]
            else:
                tanda = min(falta, TANDAS[1])
            trozo = lote[i:i + tanda]
            if len(trozo) < tanda:
                trozo = np.concatenate([trozo, np.repeat(trozo[-1:], tanda - len(trozo), axis=0)])
            partes.append(self.correr(trozo)[0][:min(tanda, falta)])
            i += tanda
        return partes[0] if len(partes) == 1 else np.concatenate(partes, axis=0)


# Con qué imagen fija se prueba cada red: (forma, amplitud de los valores de entrada)
CONTROL_CARA = ((TANDAS[0], 3, 112, 112), 1.0)       # caras alineadas, valores entre -1 y 1
CONTROL_RETINA = ((1, 3, 320, 320), 100.0)           # foto sin normalizar (BGR menos la media)


if __name__ == "__main__":
    # Imprime las firmas de CPU de las redes de models/ para pegarlas en FIRMAS.
    carpeta = Path(__file__).resolve().parent.parent / "models"
    for nombre, control in (
        ("edgeface_base.onnx", CONTROL_CARA), ("adaface_ir_50.onnx", CONTROL_CARA),
        ("adaface_ir_101.onnx", CONTROL_CARA), ("retinaface_r50.onnx", CONTROL_RETINA),
    ):
        ruta = carpeta / nombre
        if not ruta.exists():
            continue
        red = Red(ruta)  # sin control: siempre CPU
        salida = red.correr(entrada_control(*control))[0]
        numeros = ", ".join(f"{v:.5f}" for v in firma(salida))
        print(f'    "{nombre}": ({ruta.stat().st_size}, ({numeros})),')
