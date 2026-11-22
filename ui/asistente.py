"""
Asistente de la ventana. No llama al motor de caras.

Para explicarlo, son cuatro pasos y nada más:

1. normalizar: minúsculas y sin tildes, para que «Sebastián» y «sebastian» sean lo mismo.
2. interpretar: de la frase saca la acción (pasar, presente, ausente, agregar, quitar) y los nombres.
3. resolver_nombres: busca en la lista. Si hay dos con el mismo nombre, no elige; pide apellido o id.
4. La ventana ejecuta esa acción con los mismos botones de siempre y responde «Listo».
"""

from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import tkinter as tk

_UI = Path(__file__).resolve().parent
_HABLAR = _UI / "hablar.ps1"
_OIR = _UI / "oir.ps1"
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Orden:
    accion: str
    nombres: list[str]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[¿?¡!.,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _partir_nombres(trozo: str) -> list[str]:
    trozo = re.sub(r"^(a|al|los|las|el|la)\s+", "", trozo.strip())
    trozo = re.sub(r"\s+e\s+(?=[ie])", ", ", trozo)
    trozo = re.sub(r"\s+y\s+", ", ", trozo)
    nombres = []
    for parte in trozo.split(","):
        n = re.sub(r"^(a|al|de|el|la)\s+", "", parte.strip())
        n = re.sub(r"\s+(por favor)$", "", n).strip()
        if n and n not in {"presente", "presentes", "ausente", "ausentes", "estudiante", "alumno", "alumna"}:
            nombres.append(n)
    return nombres


def interpretar(texto: str) -> Orden:
    """De una frase saca la acción y los nombres. Si no la entiende, accion='no'."""
    t = normalizar(texto)
    t = re.sub(r"^(oye |hola |buenas |por favor |quiero que |puedes |puede |me )+", "", t)
    t = re.sub(r"\b(pongas|ponga|ponme|pongan|poner)\b", "pon", t)
    t = re.sub(r"\b(marques|marque|marcar)\b", "marca", t)
    t = re.sub(r"\b(quites|quite|quitar)\b", "quita", t)
    t = re.sub(r"\b(agregues|agregue|agregar|anades|anade|anadir|registra|registrar|mete|meter|crea|crear)\b", "agrega", t)
    t = re.sub(r"\b(elimina|elimines|elimine|eliminar|borra|borrar|saca|sacar)\b", "quita", t)
    t = re.sub(r"\b(pases|pase|pasar|toma|tomar|haz|hacer)\b", "pasa", t)

    if t in {"ayuda", "que puedes hacer", "que sabes hacer", "que haces", "comandos"}:
        return Orden("ayuda", [])
    if re.fullmatch(r"pasa( la| el)? (lista|asistencia)", t):
        return Orden("pasar", [])

    # El orden importa: «quita el estudiante» es borrar de la clase;
    # «quita a Ana» es solo quitarle el presente.
    patrones = [
        ("quitar", r"(?:quita) (?:al |el |la |a )?(?:estudiante|alumno|alumna) (.+)"),
        ("quitar", r"(?:quita) (?:a )?(.+?) (?:de la clase|del curso|de la lista de clase)"),
        ("agregar", r"(?:agrega) (?:al |a la |el |la |un |una |a )?(?:estudiante |alumno |alumna )?(.+)"),
        ("ausente", r"(?:quita) (?:el |los )?presentes? (?:de |a )?(.+)"),
        ("ausente", r"(?:quita) (?:a )?(.+)"),
        ("ausente", r"(?:pon|marca|coloca|deja) (?:a |al |los |las )?(.+?) (?:como )?ausentes?"),
        ("ausente", r"(.+?) (?:ya no esta|no vino|falto|faltaron|estan ausentes|esta ausente)"),
        ("presente", r"(?:pon|marca|coloca|deja|anota) (?:como )?presentes? (?:a |al |los |las )?(.+)"),
        ("presente", r"(?:pon|marca|coloca|deja|anota) (?:a |al |los |las )?(.+?) (?:como )?presentes?"),
        ("presente", r"(.+?) (?:estan|esta|quedaron|queda|son) presentes?"),
    ]
    for accion, patron in patrones:
        m = re.fullmatch(patron, t)
        if not m:
            continue
        nombres = _partir_nombres(m.group(1))
        if accion == "agregar" and any(x in nombres for x in ("presente", "ausente")):
            continue
        if not nombres or nombres == ["estas personas"] or set(nombres) <= {"estas", "ellos", "ellas"}:
            return Orden("falta_nombre", [])
        return Orden(accion, nombres)
    return Orden("no", [])


def _numero_id(token: str) -> int | None:
    m = re.fullmatch(r"e(\d{1,4})", token)
    return int(m.group(1)) if m else None


def _id_persona(persona: dict) -> int | None:
    return _numero_id(normalizar(str(persona.get("id") or "")))


def _texto_opciones(candidatos: list[dict]) -> str:
    mostrados = candidatos[:8]
    lista = "; ".join(f"{p['nombre']} ({p['id']})" for p in mostrados)
    if len(candidatos) > len(mostrados):
        lista += f"; y {len(candidatos) - len(mostrados)} más"
    return lista


def _candidatos(pedido: str, personas: list[dict]) -> tuple[list[dict], str | None, str]:
    """Busca un pedido dentro de la lista.

    Devuelve (coincidencias, error, modo). modo es "", "par" (los dos) o "todos".
    Si el pedido trae un id, ese id gana. Si el nombre lo comparten varias personas, devuelve todas.
    """
    q = normalizar(pedido)
    modo = ""
    if re.match(r"^(?:los dos|las dos|ambos|ambas)\b", q):
        modo = "par"
        q = re.sub(r"^(?:los dos|las dos|ambos|ambas)\s+", "", q).strip()
    elif re.match(r"^(?:todos los|todas las|todos|todas)\b", q):
        modo = "todos"
        q = re.sub(r"^(?:todos los|todas las|todos|todas)\s+", "", q).strip()
    if not q:
        return [], "Dime el nombre o el id.", modo
    tokens = [tok for tok in q.split() if tok not in {"el", "la", "id", "numero", "número"}]
    numeros = [n for n in (_numero_id(tok) for tok in tokens) if n is not None]
    if len(numeros) > 1:
        return [], "Dime un id a la vez.", modo
    if numeros:
        quien = [p for p in personas if _id_persona(p) == numeros[0]]
        if not quien:
            return [], f"No hay nadie con el id E{numeros[0]:03d}.", modo
        resto = [tok for tok in tokens if _numero_id(tok) is None]
        persona = quien[0]
        palabras = normalizar(persona["nombre"]).split()
        if resto and not all(tok in palabras for tok in resto):
            return [], f"El {persona['id']} es {persona['nombre']}. No coincide con ese nombre.", modo
        return [persona], None, modo
    exactos = [p for p in personas if normalizar(p["nombre"]) == q]
    if exactos:
        return exactos, None, modo
    candidato = [
        p for p in personas
        if all(tok in normalizar(p["nombre"]).split() for tok in tokens)
    ]
    return candidato, None, modo


def resolver_nombres(pedidos: list[str], personas: list[dict]) -> tuple[list[dict], str | None, list[dict]]:
    """Cada pedido tiene que coincidir sin duda. El tercer valor son las opciones si hubo empate.

    Si uno de los nombres es ambiguo, no devuelve a nadie: no marca al parecido.
    """
    if not personas:
        return [], "No hay estudiantes cargados.", []
    elegidos: list[dict] = []
    vistos: set[str] = set()
    for pedido in pedidos:
        candidato, err, modo = _candidatos(pedido, personas)
        if err:
            return [], err, []
        if not candidato:
            return [], f"No encontré a {pedido}.", []
        if modo == "par" and len(candidato) != 2:
            lista = _texto_opciones(candidato)
            return [], f"De «{pedido}» hay {len(candidato)}, no dos: {lista}. Dime el id. No cambié a nadie.", candidato
        if len(candidato) > 1 and modo != "todos" and modo != "par":
            lista = _texto_opciones(candidato)
            return [], (
                f"«{pedido}» hay {len(candidato)}: {lista}. "
                "Dime el apellido o el id. No cambié a nadie."
            ), candidato
        for persona in candidato:
            pid = str(persona["id"])
            if pid not in vistos:
                elegidos.append(persona)
                vistos.add(pid)
    return elegidos, None, []


def decir(texto: str) -> subprocess.Popen | None:
    """Lo dice en voz alta, sin frenar la ventana. None si no hay voz."""
    if not texto or not _HABLAR.is_file():
        return None
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-File", str(_HABLAR)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_SIN_VENTANA,
        )
    except OSError:
        return None
    assert proc.stdin is not None
    proc.stdin.write(texto.encode("utf-8"))
    proc.stdin.close()
    return proc


def escuchar() -> tuple[str, str | None]:
    """(texto, error). error='sin_oido' si Windows no tiene reconocedor de voz."""
    if not _OIR.is_file():
        return "", "sin_oido"
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-File", str(_OIR)],
            capture_output=True,
            timeout=20,
            creationflags=_SIN_VENTANA,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", "No pude usar el micrófono."
    err = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode == 2 or "SIN_RECONOCEDOR" in err:
        return "", "sin_oido"
    if proc.returncode != 0:
        return "", "No pude oír. Revisa el micrófono o escríbelo."
    return proc.stdout.decode("utf-8", errors="replace").strip(), None


class CaraAsistente(tk.Canvas):
    """Carita negra con ojos y boca. Parpadea, y la boca se mueve al hablar."""

    def __init__(self, master) -> None:
        super().__init__(master, width=92, height=78, bg="#f4f4f4", highlightthickness=0)
        self._fase = 0
        self._parpadeo = 0
        self.modo = "idle"  # idle | oye | habla
        self._tick()

    def poner(self, modo: str) -> None:
        self.modo = modo

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        self._fase = (self._fase + 1) % 28
        if self._parpadeo > 0:
            self._parpadeo -= 1
        elif self._fase == 0 and self.modo != "habla":
            self._parpadeo = 2
        self.delete("all")
        self.create_oval(26, 8, 66, 70, fill="#161616", outline="#161616")
        ojos_y = 30
        alto = 3 if self._parpadeo else (16 if self.modo == "oye" else 14)
        for cx in (38, 54):
            self.create_oval(cx - 5, ojos_y, cx + 5, ojos_y + alto, fill="#f5f5f5", outline="#f5f5f5")
        if self.modo == "habla" and (self._fase // 3) % 2 == 0:
            self.create_oval(40, 50, 52, 60, fill="#f5f5f5", outline="#f5f5f5")
        else:
            self.create_arc(36, 46, 56, 62, start=200, extent=140, style=tk.ARC, outline="#f5f5f5", width=2)
        self.after(140, self._tick)


AYUDA = (
    "Puedo pasar la lista, poner presente, quitar un presente, "
    "agregar un estudiante o quitarlo de la clase. "
    "Por ejemplo: pon a Ana como presente."
)


def _demo() -> int:
    frases = [
        ("pon a ana lopez como presente", "presente", ["ana lopez"]),
        ("marca presente a ana y luis", "presente", ["ana", "luis"]),
        ("quita el presente de ana", "ausente", ["ana"]),
        ("quita a ana", "ausente", ["ana"]),
        ("pon a ana como ausente", "ausente", ["ana"]),
        ("agrega al estudiante maria lopez", "agregar", ["maria lopez"]),
        ("quita el estudiante pedro diaz", "quitar", ["pedro diaz"]),
        ("elimina a juan de la clase", "quitar", ["juan"]),
        ("pasa la lista", "pasar", []),
        ("hola que tal", "no", []),
    ]
    mal = 0
    for frase, accion, nombres in frases:
        o = interpretar(frase)
        if o.accion != accion or o.nombres != nombres:
            print("MAL", frase, "->", o)
            mal += 1
    personas = [
        {"id": "E001", "nombre": "Ana López"},
        {"id": "E002", "nombre": "Luis Gómez"},
        {"id": "E003", "nombre": "Ana Díaz"},
    ]
    ok, err, opts = resolver_nombres(["luis"], personas)
    if err or ok[0]["id"] != "E002":
        print("MAL resolver luis", ok, err, opts)
        mal += 1
    ok, err, opts = resolver_nombres(["ana"], personas)
    if ok or len(opts) != 2:
        print("MAL ana deberia ser ambigua", ok, err, opts)
        mal += 1
    ok, err, opts = resolver_nombres(["ana lopez"], personas)
    if err or ok[0]["id"] != "E001":
        print("MAL ana lopez", ok, err)
        mal += 1
    ok, err, opts = resolver_nombres(["e003"], personas)
    if err or ok[0]["id"] != "E003":
        print("MAL id", ok, err)
        mal += 1
    ok, err, opts = resolver_nombres(["los dos ana"], personas)
    if err or [p["id"] for p in ok] != ["E001", "E003"]:
        print("MAL los dos", ok, err)
        mal += 1
    personas.append({"id": "E004", "nombre": "Ana López"})
    ok, err, opts = resolver_nombres(["ana lopez"], personas)
    if ok or len(opts) != 2:
        print("MAL nombre identico", ok, err, opts)
        mal += 1
    print("fallos", mal)
    return mal


if __name__ == "__main__":
    sys.exit(_demo())
