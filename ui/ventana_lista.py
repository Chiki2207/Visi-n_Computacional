"""
Interfaz de escritorio: Excel + foto grupal → lista, y ver en la foto
dónde está cada presente / cada rostro detectado (como en la web).
"""

from __future__ import annotations

import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.asistencia_core import ResultadoAsistencia, es_revisar, orden_estado, pasar_lista  # noqa: E402
from ia.leer_imagen import abrir_rgb  # noqa: E402  (misma foto, ya derecha, que ve el motor)
from ui.asistente import (  # noqa: E402
    AYUDA,
    CaraAsistente,
    decir,
    escuchar,
    interpretar,
    resolver_nombres,
)


class VentanaLista(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Presencia Facial — Pasar lista (Python)")
        self.geometry("1180x720")
        self.minsize(960, 600)

        self.excel_path: Path | None = None
        self.foto_path: Path | None = None
        self.resultado: ResultadoAsistencia | None = None
        self._img_orig: Image.Image | None = None
        self._img_tk: ImageTk.PhotoImage | None = None
        self._focus_bbox: list[float] | None = None
        self._focus_label = ""
        self._det_index = 0
        self._busy = False
        self._oyendo = False
        self._asistente_espera = False
        self._aclaracion: dict | None = None
        self._foto_alumno_tk: ImageTk.PhotoImage | None = None
        self._rutas_foto: dict[str, Path] = {}

        self._build()
        self.after(100, self._redibujar_foto)

    def _build(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Button(top, text="1. Excel de clase…", command=self._elegir_excel).pack(
            side=tk.LEFT, padx=4
        )
        self.lbl_excel = ttk.Label(top, text="(sin Excel)", foreground="#666")
        self.lbl_excel.pack(side=tk.LEFT, padx=8)

        ttk.Button(top, text="2. Foto grupal…", command=self._elegir_foto).pack(
            side=tk.LEFT, padx=4
        )
        self.lbl_foto = ttk.Label(top, text="(sin foto)", foreground="#666")
        self.lbl_foto.pack(side=tk.LEFT, padx=8)

        self.btn_pasar = ttk.Button(
            top, text="3. Pasar lista", command=self._pasar_lista
        )
        self.btn_pasar.pack(side=tk.RIGHT, padx=4)

        self.lbl_estado = ttk.Label(self, text="Elige Excel y foto grupal.", padding=6)
        self.lbl_estado.pack(fill=tk.X)
        # Los avisos largos (selfie / foto) bajan de renglón en vez de cortarse.
        self.lbl_estado.bind(
            "<Configure>", lambda e: self.lbl_estado.config(wraplength=max(e.width - 12, 200))
        )

        mid = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # --- Foto ---
        left = ttk.Frame(mid)
        mid.add(left, weight=3)
        self.canvas = tk.Canvas(left, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redibujar_foto())

        nav = ttk.Frame(left)
        nav.pack(fill=tk.X, pady=4)
        ttk.Button(nav, text="◀ Anterior rostro", command=self._det_prev).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(nav, text="Siguiente rostro ▶", command=self._det_next).pack(
            side=tk.LEFT, padx=2
        )
        self.lbl_det = ttk.Label(nav, text="")
        self.lbl_det.pack(side=tk.LEFT, padx=10)
        ttk.Button(nav, text="Quitar marca", command=self._quitar_marca).pack(
            side=tk.RIGHT, padx=2
        )

        # --- Lista ---
        right = ttk.Frame(mid, padding=4)
        mid.add(right, weight=2)
        self._panel_asistente(right)
        ttk.Label(right, text="Lista de asistencia", font=("", 11, "bold")).pack(
            anchor=tk.W
        )
        cols = ("id", "nombre", "estado", "sim")
        self.tree = ttk.Treeview(
            right, columns=cols, show="headings", selectmode="browse"
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("nombre", text="Nombre")
        self.tree.heading("estado", text="Estado")
        self.tree.heading("sim", text="Sim.")
        self.tree.column("id", width=52, anchor=tk.CENTER)
        self.tree.column("nombre", width=160)
        self.tree.column("estado", width=78, anchor=tk.CENTER)
        self.tree.column("sim", width=58, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_fila)
        self.tree.bind("<Double-1>", lambda _e: self._ampliar_foto_alumno())

        ficha = ttk.LabelFrame(right, text="Ficha del alumno", padding=6)
        ficha.pack(fill=tk.X, pady=6)
        self.lbl_preview = ttk.Label(
            ficha, text="(elige alguien de la lista)", cursor="hand2"
        )
        self.lbl_preview.pack(side=tk.LEFT, padx=4)
        self.lbl_preview.bind("<Button-1>", lambda _e: self._ampliar_foto_alumno())
        self.lbl_ficha_txt = ttk.Label(
            ficha, text="", foreground="#333", wraplength=160, justify=tk.LEFT
        )
        self.lbl_ficha_txt.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        ttk.Button(
            right, text="👁 Ver foto", command=self._ampliar_foto_alumno
        ).pack(fill=tk.X, pady=2)
        self.btn_manual = ttk.Button(
            right, text="Poner presente", command=self._toggle_manual
        )
        self.btn_manual.pack(fill=tk.X, pady=2)

        ttk.Label(
            right,
            text="Presentes arriba · ausentes abajo.\n"
            "👁 Ver foto = selfie grande. "
            "Poner presente/ausente = manual.\n"
            "Al asistente: «pon a Ana como presente».",
            foreground="#555",
            wraplength=300,
        ).pack(anchor=tk.W, pady=4)

    def _panel_asistente(self, parent: ttk.Frame) -> None:
        caja = ttk.LabelFrame(parent, text="Asistente", padding=4)
        caja.pack(fill=tk.X, pady=(0, 6))
        fila = ttk.Frame(caja)
        fila.pack(fill=tk.X)
        self.cara = CaraAsistente(fila)
        self.cara.pack(side=tk.LEFT, padx=(0, 6))
        self.lbl_asistente = ttk.Label(
            fila,
            text="Escríbeme o pulsa el micrófono. " + AYUDA,
            wraplength=230,
            justify=tk.LEFT,
        )
        self.lbl_asistente.pack(side=tk.LEFT, fill=tk.X, expand=True)
        pedido = ttk.Frame(caja)
        pedido.pack(fill=tk.X, pady=(4, 0))
        self.ent_asistente = ttk.Entry(pedido)
        self.ent_asistente.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ent_asistente.bind("<Return>", lambda _e: self._enviar_asistente())
        ttk.Button(pedido, text="Enviar", command=self._enviar_asistente).pack(side=tk.LEFT, padx=3)
        self.btn_oir = ttk.Button(pedido, text="Mic", command=self._oir_asistente)
        self.btn_oir.pack(side=tk.LEFT)

    def _decir_asistente(self, texto: str, hablar: bool = False) -> None:
        self.lbl_asistente.config(text=texto)
        if not hablar:
            return
        self.cara.poner("habla")
        proc = decir(texto)

        def vigilar() -> None:
            if not self.winfo_exists():
                return
            if proc is None or proc.poll() is not None:
                if self.cara.modo == "habla":
                    self.cara.poner("idle")
                return
            self.after(200, vigilar)

        self.after(200, vigilar)

    def _enviar_asistente(self, texto: str | None = None) -> None:
        if texto is None:
            texto = self.ent_asistente.get().strip()
            self.ent_asistente.delete(0, tk.END)
        else:
            texto = texto.strip()
            self.ent_asistente.delete(0, tk.END)
            self.ent_asistente.insert(0, texto)
        if not texto:
            return
        self._decir_asistente(self._ejecutar_orden(texto), hablar=True)

    def _oir_asistente(self) -> None:
        if self._oyendo:
            return
        self._oyendo = True
        self.btn_oir.config(state=tk.DISABLED)
        self.cara.poner("oye")
        self.lbl_asistente.config(text="Te escucho…")

        def trabajo() -> None:
            dicho, err = escuchar()
            self.after(0, lambda: self._recibir_voz(dicho, err))

        threading.Thread(target=trabajo, daemon=True).start()

    def _recibir_voz(self, texto: str, err: str | None) -> None:
        self._oyendo = False
        self.btn_oir.config(state=tk.NORMAL)
        self.cara.poner("idle")
        if err == "sin_oido":
            self._decir_asistente(
                "Este Windows no tiene reconocedor de voz. Escríbeme el pedido en la casilla.",
                hablar=True,
            )
            return
        if err:
            self._decir_asistente(err, hablar=True)
            return
        if not texto:
            self._decir_asistente("No oí nada. Intenta otra vez o escríbelo.", hablar=True)
            return
        self._enviar_asistente(texto)

    def _ejecutar_orden(self, texto: str) -> str:
        orden = interpretar(texto)
        if self._aclaracion and orden.accion in {"no", "falta_nombre"}:
            return self._responder_aclaracion(texto)
        self._aclaracion = None
        if orden.accion == "ayuda":
            return AYUDA
        if orden.accion == "falta_nombre":
            return "Dime el nombre. Por ejemplo: pon a Ana como presente."
        if orden.accion == "pasar":
            return self._asistente_pasar()
        if orden.accion == "presente":
            return self._asistente_estado(orden.nombres, "presente")
        if orden.accion == "ausente":
            return self._asistente_estado(orden.nombres, "ausente")
        if orden.accion == "agregar":
            return self._asistente_agregar(orden.nombres)
        if orden.accion == "quitar":
            return self._asistente_quitar(orden.nombres)
        return "No entendí. " + AYUDA

    def _responder_aclaracion(self, texto: str) -> str:
        from ui.asistente import normalizar

        pendiente = self._aclaracion or {}
        t = normalizar(texto)
        pide_par = bool(re.match(r"^(los dos|las dos|ambos|ambas)\b", t))
        pide_todos = bool(re.match(r"^(todos|todas)\b", t))
        if pide_par or pide_todos:
            grupo = list(pendiente.get("opciones") or [])
            if pide_par and len(grupo) != 2:
                return f"Hay {len(grupo)}, no dos. Dime el id."
            elegidos, err, opciones = grupo, None, []
        else:
            elegidos, err, opciones = resolver_nombres([texto], pendiente.get("opciones") or [])
        if opciones:
            self._aclaracion = {**pendiente, "opciones": opciones}
            return err or "Sigo sin saber cuál."
        if err:
            return err
        if not elegidos:
            return "No quedó nadie para cambiar."
        self._aclaracion = None
        if pendiente.get("accion") == "quitar":
            return self._quitar_elegidos(elegidos)
        return self._aplicar_elegidos(elegidos, pendiente.get("estado") or "presente")

    def _asistente_pasar(self) -> str:
        if self._busy:
            return "Sigo pasando la lista."
        if not self.excel_path or not self.foto_path:
            return "Primero elige el Excel de la clase y la foto grupal."
        self._aclaracion = None
        self._asistente_espera = True
        self._pasar_lista()
        return "Estoy pasando la lista."

    def _personas_lista(self) -> list[dict]:
        if not self.resultado:
            return []
        return [{"id": f["id"], "nombre": f["nombre"]} for f in self.resultado.filas]

    def _asistente_estado(self, nombres: list[str], estado: str) -> str:
        if not self.resultado:
            return "Primero pasa la lista. Di: pasa la lista."
        elegidos, err, opciones = resolver_nombres(nombres, self._personas_lista())
        if opciones:
            self._aclaracion = {"accion": "estado", "estado": estado, "opciones": opciones}
            return err or "Dime cuál."
        if err:
            return err
        return self._aplicar_elegidos(elegidos, estado)

    def _aplicar_elegidos(self, elegidos: list[dict], estado: str) -> str:
        if not self.resultado:
            return "Primero pasa la lista. Di: pasa la lista."
        por_id = {str(f["id"]): f for f in self.resultado.filas}
        if any(str(p["id"]) not in por_id for p in elegidos):
            return "Ese estudiante no está en la lista que ya pasé."
        for persona in elegidos:
            self._fijar_estado_fila(por_id[str(persona["id"])], estado)
        if estado == "ausente":
            self._focus_bbox = None
            self._focus_label = ""
            self._redibujar_foto()
        else:
            ultima = por_id[str(elegidos[-1]["id"])]
            if ultima.get("bbox"):
                self._marcar_en_grupal(ultima)
        self._llenar_lista(seleccionar=str(elegidos[-1]["id"]))
        self._mostrar_preview_alumno(por_id[str(elegidos[-1]["id"])])
        self._guardar_lista_actual()
        self.lbl_estado.config(text=self._conteo() + self._aviso_selfies() + self._aviso_foto())
        quienes = " y ".join(f"{p['nombre']} ({p['id']})" for p in elegidos)
        verbo = "presente" if estado == "presente" else "ausente"
        if len(elegidos) > 1:
            verbo += "s"
            return f"Listo. {quienes} quedaron {verbo}."
        return f"Listo. {quienes} quedó {verbo}."

    def _asistente_agregar(self, nombres: list[str]) -> str:
        if not self.excel_path:
            return "Primero elige el Excel de la clase."
        if len(nombres) != 1:
            return "Agrega a uno por uno, porque cada estudiante lleva su foto."
        nombre = " ".join(p.capitalize() for p in nombres[0].split())
        ruta = filedialog.askopenfilename(
            title=f"Selfie de {nombre}",
            filetypes=[
                ("Imágenes", "*.webp *.jpg *.jpeg *.png *.heic *.heif"),
                ("Todos", "*.*"),
            ],
        )
        if not ruta:
            return "No lo agregué: falta la foto."
        from app.excel_clase import agregar_estudiante, cargar_estudiantes

        try:
            est = agregar_estudiante(self.excel_path, nombre, Path(ruta))
        except Exception as ex:
            return str(ex)
        if self.resultado:
            self.resultado.filas.append(
                {
                    "id": est.id,
                    "nombre": est.nombre,
                    "estado": "ausente",
                    "similitud": None,
                    "motivo": "recien_agregado",
                    "bbox": None,
                    "foto": str(est.ruta_imagen),
                    "origen": "manual",
                }
            )
            self._llenar_lista(seleccionar=est.id)
            self._guardar_lista_actual()
            self.lbl_estado.config(text=self._conteo() + self._aviso_selfies() + self._aviso_foto())
        from ui.asistente import normalizar

        iguales = [
            e for e in cargar_estudiantes(self.excel_path)
            if normalizar(e.nombre) == normalizar(est.nombre) and e.id != est.id
        ]
        aviso = ""
        if iguales:
            aviso = " Ya hay otro con ese nombre: " + ", ".join(f"{e.nombre} ({e.id})" for e in iguales) + ". Para no confundirlos, dime el id."
        return f"Listo. Agregué a {est.nombre} con el id {est.id}.{aviso}"

    def _asistente_quitar(self, nombres: list[str]) -> str:
        if not self.excel_path:
            return "Primero elige el Excel de la clase."
        if len(nombres) != 1:
            return "Quita a un estudiante por vez."
        from app.excel_clase import cargar_estudiantes

        try:
            personas = [{"id": e.id, "nombre": e.nombre} for e in cargar_estudiantes(self.excel_path)]
        except Exception as ex:
            return str(ex)
        elegidos, err, opciones = resolver_nombres(nombres, personas)
        if opciones:
            self._aclaracion = {"accion": "quitar", "opciones": opciones}
            return err or "Dime cuál."
        if err:
            return err
        return self._quitar_elegidos(elegidos)

    def _quitar_elegidos(self, elegidos: list[dict]) -> str:
        from app.excel_clase import quitar_estudiante

        if not self.excel_path:
            return "Primero elige el Excel de la clase."
        quitados = []
        for persona in elegidos:
            try:
                quien = quitar_estudiante(self.excel_path, str(persona["id"]))
            except Exception as ex:
                return str(ex)
            quitados.append(f"{quien} ({persona['id']})")
            if self.resultado:
                self.resultado.filas = [
                    f for f in self.resultado.filas if str(f.get("id")) != str(persona["id"])
                ]
        if self.resultado:
            self._focus_bbox = None
            self._focus_label = ""
            self._redibujar_foto()
            self._llenar_lista()
            self._guardar_lista_actual()
            self.lbl_estado.config(text=self._conteo() + self._aviso_selfies() + self._aviso_foto())
        return "Listo. Quité a " + " y ".join(quitados) + " de la clase. La foto sigue en la carpeta."

    def _elegir_excel(self) -> None:
        ini = ROOT / "datos" / "clases"
        path = filedialog.askopenfilename(
            title="Excel de la clase",
            initialdir=str(ini if ini.is_dir() else ROOT),
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")],
        )
        if path:
            self.excel_path = Path(path)
            self.lbl_excel.config(text=self.excel_path.name, foreground="#0b6b3a")
            # Si hay foto_grupal.webp al lado del Excel, sugerirla
            sug = self.excel_path.parent / "foto_grupal.webp"
            if sug.is_file() and self.foto_path is None:
                self.foto_path = sug
                self.lbl_foto.config(text=sug.name, foreground="#0b6b3a")
                self._cargar_imagen(sug)

    def _elegir_foto(self) -> None:
        if self.excel_path is not None:
            ini = self.excel_path.parent
            alt = self.excel_path.parent / "fotos_grupales"
            if alt.is_dir():
                ini = alt
        else:
            ini = ROOT / "datos" / "clases"
        path = filedialog.askopenfilename(
            title="Foto grupal",
            initialdir=str(ini if Path(ini).is_dir() else ROOT),
            filetypes=[
                ("Imágenes", "*.webp *.jpg *.jpeg *.png *.heic *.heif"),
                ("Todos", "*.*"),
            ],
        )
        if path:
            self.foto_path = Path(path)
            self.lbl_foto.config(text=self.foto_path.name, foreground="#0b6b3a")
            self._cargar_imagen(self.foto_path)

    def _cargar_imagen(self, path: Path) -> None:
        try:
            self._img_orig = abrir_rgb(path)
            self._focus_bbox = None
            self._focus_label = ""
            self._redibujar_foto()
        except Exception as ex:
            messagebox.showerror("Foto", f"No se pudo abrir la imagen:\n{ex}")

    def _pasar_lista(self) -> None:
        if self._busy:
            return
        if not self.excel_path or not self.foto_path:
            messagebox.showwarning(
                "Falta algo", "Elige el Excel de clase y la foto grupal."
            )
            return
        self._busy = True
        self.btn_pasar.config(state=tk.DISABLED)
        self.lbl_estado.config(text="Pasando lista… (puede tardar)")

        def trabajo() -> None:
            try:
                res = pasar_lista(
                    self.excel_path,
                    self.foto_path,
                    on_progreso=lambda m: self.after(
                        0, lambda: self.lbl_estado.config(text=m)
                    ),
                )
                self.after(0, lambda: self._aplicar_resultado(res))
            except Exception as ex:
                self.after(0, lambda err=ex: self._error_pasar(err))

        threading.Thread(target=trabajo, daemon=True).start()

    def _error_pasar(self, ex: Exception) -> None:
        self._busy = False
        self.btn_pasar.config(state=tk.NORMAL)
        self.lbl_estado.config(text="Error al pasar lista")
        if self._asistente_espera:
            self._asistente_espera = False
            self._decir_asistente("No pude pasar la lista. " + str(ex), hablar=True)
        messagebox.showerror("Error", str(ex))

    def _aplicar_resultado(self, res: ResultadoAsistencia) -> None:
        self._busy = False
        self.btn_pasar.config(state=tk.NORMAL)
        self.resultado = res
        self._cargar_imagen(res.foto_grupal)
        self._llenar_lista()
        self._det_index = 0
        self.lbl_estado.config(
            text=(
                self._conteo()
                + (f" · guardado {res.excel_salida.name}" if res.excel_salida else "")
                + self._aviso_selfies()
                + self._aviso_foto()
            )
        )
        if res.detecciones:
            self._mostrar_deteccion(0)
        if self._asistente_espera:
            self._asistente_espera = False
            self._decir_asistente(
                "Listo. La lista ya fue realizada. " + self._conteo(),
                hablar=True,
            )

    def _llenar_lista(self, seleccionar: str | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rutas_foto.clear()
        if not self.resultado:
            return
        # Presentes primero, luego "¿revisar?" (caras lejanas sugeridas), ausentes al final
        filas = sorted(
            self.resultado.filas,
            key=lambda f: (
                orden_estado(f),
                str(f.get("nombre") or "").lower(),
                str(f.get("id") or ""),
            ),
        )
        self.resultado.filas = filas
        for f in filas:
            sim = f.get("similitud")
            sim_txt = "" if sim is None else f"{float(sim):.3f}"
            sid = str(f["id"])
            origen = f.get("origen") or "ai"
            estado_txt = f["estado"]
            tag = f["estado"]
            if origen == "manual" and estado_txt == "presente":
                estado_txt = "presente*"
            if es_revisar(f):
                estado_txt, tag = "¿revisar?", "revisar"
                if f.get("sugerencia") is not None:
                    sim_txt = f"¿{float(f['sugerencia']):.3f}"
            self.tree.insert(
                "",
                tk.END,
                iid=sid,
                values=(sid, f["nombre"], estado_txt, sim_txt),
                tags=(tag,),
            )
            foto = f.get("foto") or ""
            if foto:
                self._rutas_foto[sid] = Path(foto)
        self.tree.tag_configure("presente", background="#e6f6ec")
        self.tree.tag_configure("ausente", background="#fdecea")
        self.tree.tag_configure("revisar", background="#fff4d6")
        if seleccionar and seleccionar in self.tree.get_children():
            self.tree.selection_set(seleccionar)
            self.tree.see(seleccionar)
        self._actualizar_btn_manual()

    def _actualizar_btn_manual(self) -> None:
        fila = self._fila_seleccionada()
        if not fila:
            self.btn_manual.config(text="Poner presente", state=tk.DISABLED)
            return
        self.btn_manual.config(state=tk.NORMAL)
        if fila.get("estado") == "presente":
            self.btn_manual.config(text="Poner ausente")
        else:
            self.btn_manual.config(text="Poner presente")

    def _fijar_estado_fila(self, fila: dict, estado: str) -> None:
        """La misma corrección manual de siempre: presente o ausente, sin tocar la IA."""
        fila["estado"] = estado
        fila["origen"] = "manual"
        fila["motivo"] = "manual_presente" if estado == "presente" else "manual_ausente"

    def _toggle_manual(self) -> None:
        """Como en la web: el docente corrige a mano presente ↔ ausente."""
        if not self.resultado:
            return
        fila = self._fila_seleccionada()
        if not fila:
            messagebox.showinfo("Manual", "Elige un alumno de la lista.")
            return
        sid = str(fila["id"])
        if fila.get("estado") == "presente":
            self._fijar_estado_fila(fila, "ausente")
            # no borramos bbox por si vuelve a marcarse; la marca en foto se quita
            self._focus_bbox = None
            self._focus_label = ""
            self._redibujar_foto()
        else:
            self._fijar_estado_fila(fila, "presente")
            if fila.get("bbox"):
                self._marcar_en_grupal(fila)
        self._llenar_lista(seleccionar=sid)
        self._mostrar_preview_alumno(fila)
        self._guardar_lista_actual()
        self.lbl_estado.config(
            text=(
                self._conteo()
                + (
                    f" · {self.resultado.excel_salida.name}"
                    if self.resultado.excel_salida
                    else ""
                )
                + self._aviso_selfies()
                + self._aviso_foto()
            )
        )

    def _sigue_por_revisar(self, sid: str) -> bool:
        """El alumno sigue marcado «¿revisar?» (el docente todavía no lo confirmó ni lo descartó)."""
        if not self.resultado:
            return False
        return any(str(f.get("id")) == sid and es_revisar(f) for f in self.resultado.filas)

    def _conteo(self) -> str:
        r = self.resultado
        rev = r.por_revisar
        aus = r.ausentes - rev
        return (
            f"{r.clase}: {r.faces_detected} rostros · {r.presentes} presentes"
            + (f" · {rev} por revisar" if rev else "")
            + f" · {aus} ausentes"
        )

    def _aviso_foto(self) -> str:
        """Caras lejanas con pinta de alumno que quedaron sin nombre por chicas."""
        txt = getattr(self.resultado, "aviso_foto", "") or ""
        return f"\n{txt}" if txt else ""

    def _aviso_selfies(self) -> str:
        """Alumnos reconocidos de cerca con nota baja: con otra selfie se reconocen mejor de lejos."""
        lista = getattr(self.resultado, "repetir_selfie", None) or []
        if not lista:
            return ""
        return " · repetir selfie de: " + ", ".join(str(d.get("nombre") or d.get("id")) for d in lista)

    def _guardar_lista_actual(self) -> None:
        if not self.resultado or not self.resultado.excel_salida:
            return
        from app.excel_clase import guardar_lista

        guardar_lista(
            self.resultado.excel_salida,
            clase=self.resultado.clase,
            foto_grupal=str(self.resultado.foto_grupal),
            umbral=float(self.resultado.umbral),
            faces_detected=int(self.resultado.faces_detected),
            filas=self.resultado.filas,
            detecciones=self.resultado.detecciones,
        )

    def _fila_seleccionada(self) -> dict | None:
        if not self.resultado:
            return None
        sel = self.tree.selection()
        if not sel:
            return None
        sid = sel[0]
        return next((f for f in self.resultado.filas if f["id"] == sid), None)

    def _mostrar_preview_alumno(self, fila: dict) -> None:
        sid = str(fila.get("id") or "")
        nombre = fila.get("nombre") or ""
        estado = fila.get("estado") or ""
        sim = fila.get("similitud")
        sim_txt = f"\nsim {float(sim):.3f}" if sim is not None else ""
        aviso = (
            "\nSelfie floja: tomarle otra (de frente, luz pareja, sin filtro, como va a clase)"
            if fila.get("motivo") == "repetir_selfie"
            else ""
        )
        if es_revisar(fila):
            aviso = (
                "\nPosible cara lejana (naranja en la foto): compárela con la selfie;"
                " si es, «Poner presente»"
            )
        self.lbl_ficha_txt.config(text=f"{nombre}\nID {sid}\n{estado}{sim_txt}{aviso}")
        ruta = self._rutas_foto.get(sid)
        if not ruta or not ruta.is_file():
            self._foto_alumno_tk = None
            self.lbl_preview.config(image="", text="(sin foto)")
            return
        try:
            im = abrir_rgb(ruta)
            im.thumbnail((96, 96), Image.Resampling.LANCZOS)
            self._foto_alumno_tk = ImageTk.PhotoImage(im)
            self.lbl_preview.config(image=self._foto_alumno_tk, text="")
        except Exception:
            self._foto_alumno_tk = None
            self.lbl_preview.config(image="", text="(foto ilegible)")

    def _on_select_fila(self, _evt=None) -> None:
        fila = self._fila_seleccionada()
        if not fila:
            return
        self._mostrar_preview_alumno(fila)
        self._actualizar_btn_manual()
        if (fila.get("estado") == "presente" or es_revisar(fila)) and fila.get("bbox"):
            self._marcar_en_grupal(fila)

    def _marcar_en_grupal(self, fila: dict) -> None:
        bbox = fila.get("bbox")
        if not bbox or len(bbox) < 4:
            return
        sid = str(fila.get("id") or "")
        self._focus_bbox = [float(x) for x in bbox[:4]]
        sim = fila.get("similitud")
        extra = f"  sim={float(sim):.3f}" if sim is not None else ""
        self._focus_label = f"{fila.get('nombre')}{extra}"
        if es_revisar(fila):
            nota = fila.get("sugerencia")
            self._focus_label = f"¿{fila.get('nombre')}? revisar" + (f"  nota={float(nota):.3f}" if nota is not None else "")
        if self.resultado:
            for i, d in enumerate(self.resultado.detecciones):
                sug = d.get("sugerido") or {}
                if str(d.get("person_id") or "") == sid or (es_revisar(fila) and str(sug.get("id") or "") == sid):
                    self._det_index = i
                    break
        self._actualizar_lbl_det()
        self._redibujar_foto()

    def _ampliar_foto_alumno(self) -> None:
        """Como en la web: abre la selfie a tamaño grande."""
        fila = self._fila_seleccionada()
        if not fila:
            messagebox.showinfo("Ver foto", "Elige un alumno de la lista.")
            return
        sid = str(fila.get("id") or "")
        ruta = self._rutas_foto.get(sid)
        if not ruta or not ruta.is_file():
            messagebox.showinfo("Ver foto", "Ese alumno no tiene selfie.")
            return
        if fila.get("estado") == "presente" and fila.get("bbox"):
            self._marcar_en_grupal(fila)

        try:
            im = abrir_rgb(ruta)
        except Exception as ex:
            messagebox.showerror("Ver foto", f"No se pudo abrir la foto:\n{ex}")
            return

        win = tk.Toplevel(self)
        win.title(f"{fila.get('nombre')} · {sid}")
        win.transient(self)
        # Encajar en pantalla dejando margen
        sw = max(self.winfo_screenwidth() - 80, 400)
        sh = max(self.winfo_screenheight() - 120, 400)
        nw, nh = im.size
        scale = min(sw / nw, sh / nh, 1.0)
        # Si es muy chica, ampliar hasta ~720 px de lado
        if max(nw, nh) < 720:
            scale = max(scale, min(720 / max(nw, nh), sw / nw, sh / nh))
        dw, dh = max(1, int(nw * scale)), max(1, int(nh * scale))
        vis = im.resize((dw, dh), Image.Resampling.LANCZOS)
        foto_tk = ImageTk.PhotoImage(vis)
        win._foto_tk = foto_tk  # evitar GC
        lbl = ttk.Label(win, image=foto_tk)
        lbl.pack(padx=8, pady=8)
        meta = f"{fila.get('nombre')}  ·  ID {sid}  ·  {fila.get('estado')}"
        ttk.Label(win, text=meta).pack(pady=(0, 4))
        ttk.Button(win, text="Cerrar", command=win.destroy).pack(pady=(0, 8))
        win.bind("<Escape>", lambda _e: win.destroy())
        win.focus_set()

    def _det_prev(self) -> None:
        if not self.resultado or not self.resultado.detecciones:
            return
        n = len(self.resultado.detecciones)
        self._det_index = (self._det_index - 1) % n
        self._mostrar_deteccion(self._det_index)

    def _det_next(self) -> None:
        if not self.resultado or not self.resultado.detecciones:
            return
        n = len(self.resultado.detecciones)
        self._det_index = (self._det_index + 1) % n
        self._mostrar_deteccion(self._det_index)

    def _mostrar_deteccion(self, i: int) -> None:
        if not self.resultado or not self.resultado.detecciones:
            return
        d = self.resultado.detecciones[i]
        bb = d.get("bbox")
        if not bb or len(bb) < 4:
            return
        self._det_index = i
        self._focus_bbox = [float(x) for x in bb[:4]]
        sug = d.get("sugerido") or {}
        if d.get("matched") and d.get("name"):
            sim = d.get("similarity")
            extra = f"  sim={float(sim):.3f}" if sim is not None else ""
            self._focus_label = f"{d['name']}{extra}"
        elif sug and self._sigue_por_revisar(str(sug.get("id"))):
            self._focus_label = f"¿{sug.get('nombre')}? revisar  nota={float(sug.get('nota') or 0):.3f}"
        else:
            self._focus_label = f"Rostro {i + 1} · no reconocido"
        self._actualizar_lbl_det()
        self._redibujar_foto()
        # Seleccionar en lista si está matched (o si es la cara sugerida de alguien por revisar)
        pid = d.get("person_id") or (sug.get("id") if sug and self._sigue_por_revisar(str(sug.get("id"))) else None)
        if pid and str(pid) in self.tree.get_children():
            self.tree.selection_set(str(pid))
            self.tree.see(str(pid))

    def _actualizar_lbl_det(self) -> None:
        if not self.resultado or not self.resultado.detecciones:
            self.lbl_det.config(text="")
            return
        n = len(self.resultado.detecciones)
        self.lbl_det.config(text=f"Rostro {self._det_index + 1} / {n}")

    def _quitar_marca(self) -> None:
        self._focus_bbox = None
        self._focus_label = ""
        self._redibujar_foto()

    def _redibujar_foto(self) -> None:
        if self._img_orig is None:
            self.canvas.delete("all")
            return
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        img = self._img_orig.copy()
        nw, nh = img.size
        scale = min(cw / nw, ch / nh)
        dw, dh = max(1, int(nw * scale)), max(1, int(nh * scale))
        vis = img.resize((dw, dh), Image.Resampling.BILINEAR)
        ox = (cw - dw) // 2
        oy = (ch - dh) // 2

        if self._focus_bbox and len(self._focus_bbox) >= 4:
            draw = ImageDraw.Draw(vis, "RGBA")
            x1, y1, x2, y2 = self._focus_bbox
            # Atenuar fuera del bbox
            overlay = Image.new("RGBA", vis.size, (0, 0, 0, 110))
            mask = Image.new("L", vis.size, 0)
            md = ImageDraw.Draw(mask)
            rx1 = int(x1 * scale)
            ry1 = int(y1 * scale)
            rx2 = int(x2 * scale)
            ry2 = int(y2 * scale)
            pad = max(2, int(min(rx2 - rx1, ry2 - ry1) * 0.06))
            md.rectangle(
                [rx1 - pad, ry1 - pad, rx2 + pad, ry2 + pad], fill=255
            )
            # donde mask=255 no oscurecer
            from PIL import ImageChops

            inv = ImageChops.invert(mask)
            dark = Image.composite(
                overlay, Image.new("RGBA", vis.size, (0, 0, 0, 0)), inv
            )
            vis = Image.alpha_composite(vis.convert("RGBA"), dark)
            draw = ImageDraw.Draw(vis)
            # Verde: reconocido. Naranja: sin nombre o sugerencia por revisar.
            matched = "no reconocido" not in self._focus_label and not self._focus_label.startswith("¿")
            color = (11, 107, 58, 255) if matched else (180, 120, 20, 255)
            draw.rectangle(
                [rx1 - pad, ry1 - pad, rx2 + pad, ry2 + pad],
                outline=color,
                width=3,
            )
            if self._focus_label:
                ty = max(0, ry1 - pad - 18)
                tw = min(vis.size[0] - (rx1 - pad), 10 + 7 * len(self._focus_label))
                draw.rectangle(
                    [rx1 - pad, ty, rx1 - pad + tw, ty + 16],
                    fill=color,
                )
                draw.text((rx1 - pad + 4, ty + 2), self._focus_label, fill=(255, 255, 255, 255))
            vis = vis.convert("RGB")

        self._img_tk = ImageTk.PhotoImage(vis)
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, anchor=tk.NW, image=self._img_tk)


def main() -> None:
    app = VentanaLista()
    app.mainloop()


if __name__ == "__main__":
    main()
