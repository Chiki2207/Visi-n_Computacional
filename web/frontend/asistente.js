/* Asistente de la página. No llama al reconocimiento de caras.
   Son los mismos cuatro pasos que ui/asistente.py:

   1. normalizar: minúsculas y sin tildes.
   2. interpretar: saca la acción y los nombres.
   3. resolverNombres: busca en la lista. Si hay dos iguales, no elige.
   4. La página ejecuta esa acción con las rutas que ya tenía (presente, ausente, agregar, quitar).
*/
(function (raiz) {
  "use strict";

  const AYUDA = "Puedo pasar la lista, poner presente, quitar un presente, agregar un estudiante o quitarlo de la clase. Por ejemplo: pon a Ana como presente.";

  function normalizar(texto) {
    return String(texto || "").trim().toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[¿?¡!.,;:]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }

  function partirNombres(trozo) {
    let t = trozo.trim().replace(/^(a|al|los|las|el|la)\s+/, "");
    t = t.replace(/\s+e\s+(?=[ie])/g, ", ").replace(/\s+y\s+/g, ", ");
    const fuera = new Set(["presente", "presentes", "ausente", "ausentes", "estudiante", "alumno", "alumna"]);
    return t.split(",").map((parte) => parte.trim()
      .replace(/^(a|al|de|el|la)\s+/, "")
      .replace(/\s+por favor$/, "")).filter((n) => n && !fuera.has(n));
  }

  function interpretar(texto) {
    let t = normalizar(texto)
      .replace(/^(oye |hola |buenas |por favor |quiero que |puedes |puede |me )+/, "")
      .replace(/\b(pongas|ponga|ponme|pongan|poner)\b/g, "pon")
      .replace(/\b(marques|marque|marcar)\b/g, "marca")
      .replace(/\b(quites|quite|quitar)\b/g, "quita")
      .replace(/\b(agregues|agregue|agregar|anades|anade|anadir|registra|registrar|mete|meter|crea|crear)\b/g, "agrega")
      .replace(/\b(elimina|elimines|elimine|eliminar|borra|borrar|saca|sacar)\b/g, "quita")
      .replace(/\b(pases|pase|pasar|toma|tomar|haz|hacer)\b/g, "pasa");
    if (["ayuda", "que puedes hacer", "que sabes hacer", "que haces", "comandos"].includes(t)) return { accion: "ayuda", nombres: [] };
    if (/^pasa( la| el)? (lista|asistencia)$/.test(t)) return { accion: "pasar", nombres: [] };
    const patrones = [
      ["quitar", /^(?:quita) (?:al |el |la |a )?(?:estudiante|alumno|alumna) (.+)$/],
      ["quitar", /^(?:quita) (?:a )?(.+?) (?:de la clase|del curso|de la lista de clase)$/],
      ["agregar", /^(?:agrega) (?:al |a la |el |la |un |una |a )?(?:estudiante |alumno |alumna )?(.+)$/],
      ["ausente", /^(?:quita) (?:el |los )?presentes? (?:de |a )?(.+)$/],
      ["ausente", /^(?:quita) (?:a )?(.+)$/],
      ["ausente", /^(?:pon|marca|coloca|deja) (?:a |al |los |las )?(.+?) (?:como )?ausentes?$/],
      ["ausente", /^(.+?) (?:ya no esta|no vino|falto|faltaron|estan ausentes|esta ausente)$/],
      ["presente", /^(?:pon|marca|coloca|deja|anota) (?:como )?presentes? (?:a |al |los |las )?(.+)$/],
      ["presente", /^(?:pon|marca|coloca|deja|anota) (?:a |al |los |las )?(.+?) (?:como )?presentes?$/],
      ["presente", /^(.+?) (?:estan|esta|quedaron|queda|son) presentes?$/],
    ];
    for (const [accion, patron] of patrones) {
      const m = t.match(patron);
      if (!m) continue;
      const nombres = partirNombres(m[1]);
      if (accion === "agregar" && nombres.some((n) => n === "presente" || n === "ausente")) continue;
      if (!nombres.length || (nombres.length === 1 && nombres[0] === "estas personas") || nombres.every((n) => ["estas", "ellos", "ellas"].includes(n))) {
        return { accion: "falta_nombre", nombres: [] };
      }
      return { accion, nombres };
    }
    return { accion: "no", nombres: [] };
  }

  function numeroId(token) {
    const m = /^e(\d{1,4})$/.exec(token);
    return m ? Number(m[1]) : null;
  }

  function textoOpciones(candidatos) {
    const mostrados = candidatos.slice(0, 8);
    let lista = mostrados.map((p) => `${p.nombre} (${p.id})`).join("; ");
    if (candidatos.length > mostrados.length) lista += `; y ${candidatos.length - mostrados.length} más`;
    return lista;
  }

  function candidatos(pedido, personas) {
    let q = normalizar(pedido);
    let modo = "";
    if (/^(?:los dos|las dos|ambos|ambas)\b/.test(q)) {
      modo = "par";
      q = q.replace(/^(?:los dos|las dos|ambos|ambas)\s+/, "").trim();
    } else if (/^(?:todos los|todas las|todos|todas)\b/.test(q)) {
      modo = "todos";
      q = q.replace(/^(?:todos los|todas las|todos|todas)\s+/, "").trim();
    }
    if (!q) return [[], "Dime el nombre o el id.", modo];
    const tokens = q.split(" ").filter((tok) => !["el", "la", "id", "numero"].includes(tok));
    const numeros = tokens.map(numeroId).filter((n) => n !== null);
    if (numeros.length > 1) return [[], "Dime un id a la vez.", modo];
    if (numeros.length === 1) {
      const quien = personas.filter((p) => numeroId(normalizar(p.id)) === numeros[0]);
      if (!quien.length) return [[], `No hay nadie con el id E${String(numeros[0]).padStart(3, "0")}.`, modo];
      const resto = tokens.filter((tok) => numeroId(tok) === null);
      const palabras = normalizar(quien[0].nombre).split(" ");
      if (resto.length && resto.some((tok) => !palabras.includes(tok))) {
        return [[], `El ${quien[0].id} es ${quien[0].nombre}. No coincide con ese nombre.`, modo];
      }
      return [[quien[0]], null, modo];
    }
    const exactos = personas.filter((p) => normalizar(p.nombre) === q);
    if (exactos.length) return [exactos, null, modo];
    return [personas.filter((p) => {
      const palabras = normalizar(p.nombre).split(" ");
      return tokens.every((tok) => palabras.includes(tok));
    }), null, modo];
  }

  function resolverNombres(pedidos, personas) {
    if (!personas.length) return [[], "No hay estudiantes cargados.", []];
    const elegidos = [];
    const vistos = new Set();
    for (const pedido of pedidos) {
      const [candidato, err, modo] = candidatos(pedido, personas);
      if (err) return [[], err, []];
      if (!candidato.length) return [[], `No encontré a ${pedido}.`, []];
      if (modo === "par" && candidato.length !== 2) {
        return [[], `De «${pedido}» hay ${candidato.length}, no dos: ${textoOpciones(candidato)}. Dime el id. No cambié a nadie.`, candidato];
      }
      if (candidato.length > 1 && modo !== "todos" && modo !== "par") {
        return [[], `«${pedido}» hay ${candidato.length}: ${textoOpciones(candidato)}. Dime el apellido o el id. No cambié a nadie.`, candidato];
      }
      for (const persona of candidato) {
        if (!vistos.has(String(persona.id))) {
          elegidos.push(persona);
          vistos.add(String(persona.id));
        }
      }
    }
    return [elegidos, null, []];
  }

  function sprite(nombre) {
    return `/asistente/${nombre}.jpg`;
  }

  function visema(letra) {
    const c = String(letra || "").toLowerCase();
    if ("aá".includes(c)) return "boca_a";
    if ("eé".includes(c)) return "boca_e";
    if ("iíy".includes(c)) return "boca_i";
    if ("oó".includes(c)) return "boca_o";
    if ("uúü".includes(c)) return "boca_u";
    if ("mbp".includes(c)) return "boca_m";
    return "reposo";
  }

  function miradaDe(dx, dy) {
    const ax = Math.abs(dx);
    const ay = Math.abs(dy);
    if (ax < 40 && ay < 40) return "ojos_centro";
    if (ax >= ay) return dx < 0 ? "ojos_izq" : "ojos_der";
    return dy < 0 ? "ojos_arriba" : "ojos_abajo";
  }

  function escuchar() {
    const SR = raiz.SpeechRecognition || raiz.webkitSpeechRecognition;
    if (!SR) return Promise.reject(new Error("sin_oido"));
    return new Promise((resolve, reject) => {
      const rec = new SR();
      rec.lang = "es-CO";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = (ev) => resolve(ev.results[0][0].transcript || "");
      rec.onerror = (ev) => reject(new Error(ev.error === "not-allowed" ? "Permita el micrófono en el navegador." : "No pude oír. Escríbalo."));
      rec.onend = () => {};
      try { rec.start(); } catch (e) { reject(e); }
    });
  }

  let oirRaton = null;
  let timerBoca = 0;
  let timerParpadeo = 0;
  let ctx = { personas: async () => [], actuar: async () => AYUDA };
  let estado = null;

  function quitar() {
    clearInterval(timerBoca);
    clearInterval(timerParpadeo);
    if (oirRaton) document.removeEventListener("mousemove", oirRaton);
    oirRaton = null;
    estado = null;
    document.getElementById("chat-asistente")?.remove();
  }

  function contexto(opciones) {
    ctx = {
      personas: opciones.personas || (async () => []),
      actuar: opciones.actuar || (async () => AYUDA),
    };
  }

  /* Botón flotante abajo a la derecha (tipo WhatsApp). Tras el login, en cualquier página. */
  function montar(opciones) {
    if (opciones) contexto(opciones);
    if (document.getElementById("chat-asistente")) return;
    let aclaracion = null;
    let ocupado = false;
    let hablando = false;
    let parpadeo = false;
    let mirada = "ojos_centro";
    let abierto = false;

    const burbuja = document.createElement("button");
    burbuja.type = "button";
    burbuja.className = "chat-burbuja";
    burbuja.setAttribute("aria-label", "Abrir el asistente");
    burbuja.setAttribute("aria-expanded", "false");
    const fotoBurbuja = document.createElement("img");
    fotoBurbuja.src = sprite("reposo");
    fotoBurbuja.alt = "";
    fotoBurbuja.draggable = false;
    burbuja.append(fotoBurbuja);

    const cabeza = document.createElement("div");
    cabeza.className = "chat-cabeza";
    const cara = document.createElement("div");
    cara.className = "asistente-cara";
    cara.setAttribute("aria-hidden", "true");
    const foto = document.createElement("img");
    foto.src = sprite("reposo");
    foto.alt = "";
    foto.className = "asistente-foto";
    foto.draggable = false;
    cara.append(foto);
    const titulos = document.createElement("div");
    titulos.className = "chat-titulos";
    const nombreChat = document.createElement("strong");
    nombreChat.textContent = "Asistente";
    const estadoChat = document.createElement("span");
    estadoChat.textContent = "En línea";
    titulos.append(nombreChat, estadoChat);
    const cerrar = document.createElement("button");
    cerrar.type = "button";
    cerrar.className = "chat-cerrar";
    cerrar.setAttribute("aria-label", "Cerrar el chat");
    cerrar.textContent = "×";
    cabeza.append(cara, titulos, cerrar);

    const hilos = document.createElement("div");
    hilos.className = "chat-hilos";
    hilos.setAttribute("aria-live", "polite");
    function burbujaTexto(quien, texto) {
      const b = document.createElement("div");
      b.className = "chat-msg chat-msg-" + quien;
      b.textContent = texto;
      hilos.append(b);
      hilos.scrollTop = hilos.scrollHeight;
      return b;
    }
    burbujaTexto("bot", "Hola. Escriba o mande audio. Por ejemplo: pon a Ana como presente.");
    const caja = document.createElement("input");
    caja.className = "chat-caja";
    caja.type = "text";
    caja.placeholder = "Escriba un mensaje";
    caja.setAttribute("aria-label", "Escribir mensaje");
    const enviar = document.createElement("button");
    enviar.type = "submit";
    enviar.className = "chat-enviar";
    enviar.setAttribute("aria-label", "Enviar");
    enviar.textContent = "Enviar";
    const mic = document.createElement("button");
    mic.type = "button";
    mic.className = "chat-mic";
    mic.setAttribute("aria-label", "Mandar audio");
    mic.textContent = "Audio";
    const form = document.createElement("form");
    form.className = "chat-barra";
    form.append(mic, caja, enviar);
    const panel = document.createElement("div");
    panel.className = "chat-panel";
    panel.hidden = true;
    panel.append(cabeza, hilos, form);

    const nodo = document.createElement("aside");
    nodo.id = "chat-asistente";
    nodo.className = "chat-flotante";
    nodo.append(panel, burbuja);
    document.body.append(nodo);
    estado = { foto, fotoBurbuja, cara, caja };

    function mostrarCara(nombre) {
      const url = sprite(nombre);
      if (!parpadeo) {
        foto.src = url;
        if (!hablando) fotoBurbuja.src = url;
      }
    }

    function callar() {
      clearInterval(timerBoca);
      hablando = false;
      cara.dataset.modo = "";
      mostrarCara(mirada);
    }

    function animarBoca(texto) {
      clearInterval(timerBoca);
      const letras = Array.from(String(texto || "")).filter((c) => c.trim());
      if (!letras.length) { callar(); return; }
      hablando = true;
      cara.dataset.modo = "habla";
      let i = 0;
      mostrarCara(visema(letras[0]));
      timerBoca = setInterval(() => {
        i = (i + 1) % letras.length;
        mostrarCara(visema(letras[i]));
      }, 85);
    }

    function decir(texto) {
      animarBoca(texto);
      const voz = raiz.speechSynthesis;
      const letras = Array.from(String(texto || "")).filter((c) => c.trim()).length;
      if (!voz || !texto) { setTimeout(callar, Math.max(500, letras * 80)); return; }
      voz.cancel();
      const frase = new SpeechSynthesisUtterance(texto);
      frase.lang = "es-CO";
      const elegida = voz.getVoices().find((v) => v.lang && v.lang.toLowerCase().startsWith("es"));
      if (elegida) frase.voice = elegida;
      frase.onend = callar;
      frase.onerror = callar;
      voz.speak(frase);
    }

    function abrir(si) {
      abierto = !!si;
      panel.hidden = !abierto;
      burbuja.hidden = abierto;
      burbuja.setAttribute("aria-expanded", String(abierto));
      if (abierto) caja.focus();
    }

    oirRaton = (ev) => {
      const r = (abierto ? cara : burbuja).getBoundingClientRect();
      mirada = miradaDe(ev.clientX - (r.left + r.width / 2), ev.clientY - (r.top + r.height / 2));
      if (!hablando && !parpadeo) mostrarCara(mirada);
    };
    document.addEventListener("mousemove", oirRaton);
    timerParpadeo = setInterval(() => {
      if (!nodo.isConnected || hablando) return;
      parpadeo = true;
      const url = sprite("ojos_blink");
      foto.src = url;
      fotoBurbuja.src = url;
      setTimeout(() => {
        parpadeo = false;
        if (!hablando) mostrarCara(mirada);
      }, 140);
    }, 3800);

    function mostrar(texto) {
      burbujaTexto("bot", texto).dataset.fijo = "1";
      decir(texto);
    }

    async function turno(texto) {
      const orden = interpretar(texto);
      if (aclaracion && (orden.accion === "no" || orden.accion === "falta_nombre")) {
        const t = normalizar(texto);
        const pidePar = /^(los dos|las dos|ambos|ambas)\b/.test(t);
        const pideTodos = /^(todos|todas)\b/.test(t);
        let elegidos, err, opciones;
        if (pidePar || pideTodos) {
          const grupo = aclaracion.opciones || [];
          if (pidePar && grupo.length !== 2) return `Hay ${grupo.length}, no dos. Dime el id.`;
          elegidos = grupo; err = null; opciones = [];
        } else {
          [elegidos, err, opciones] = resolverNombres([texto], aclaracion.opciones || []);
        }
        if (opciones && opciones.length) { aclaracion = { ...aclaracion, opciones }; return err || "Sigo sin saber cuál."; }
        if (err) return err;
        if (!elegidos.length) return "No quedó nadie para cambiar.";
        const pendiente = aclaracion;
        aclaracion = null;
        return ctx.actuar({ accion: pendiente.accion, elegidos });
      }
      aclaracion = null;
      if (orden.accion === "ayuda") return AYUDA;
      if (orden.accion === "falta_nombre") return "Dime el nombre. Por ejemplo: pon a Ana como presente.";
      if (orden.accion === "no") return "No entendí. " + AYUDA;
      if (orden.accion === "pasar") return ctx.actuar({ accion: "pasar" });
      if (orden.accion === "agregar") {
        if (orden.nombres.length !== 1) return "Agregue a uno por uno, porque cada estudiante lleva su foto.";
        return ctx.actuar({ accion: "agregar", nombre: orden.nombres[0] });
      }
      const lista = await Promise.resolve(ctx.personas());
      const [elegidos, err, opciones] = resolverNombres(orden.nombres, lista);
      if (opciones.length) { aclaracion = { accion: orden.accion, opciones }; return err; }
      if (err) return err;
      return ctx.actuar({ accion: orden.accion, elegidos });
    }

    burbuja.addEventListener("click", () => abrir(true));
    cerrar.addEventListener("click", () => abrir(false));
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const texto = caja.value.trim();
      if (!texto || ocupado) return;
      ocupado = true;
      caja.value = "";
      burbujaTexto("yo", texto).dataset.fijo = "1";
      cara.dataset.modo = "oye";
      try { mostrar(await turno(texto)); }
      catch (e) { mostrar(e.message || "No pude hacerlo."); }
      if (!hablando) cara.dataset.modo = "";
      ocupado = false;
    });
    mic.addEventListener("click", async () => {
      if (ocupado) return;
      ocupado = true;
      abrir(true);
      cara.dataset.modo = "oye";
      mic.classList.add("escuchando");
      burbujaTexto("bot", "Lo escucho…");
      try {
        const texto = await escuchar();
        if (!texto) mostrar("No oí nada. Intente otra vez o escríbalo.");
        else {
          burbujaTexto("yo", texto).dataset.fijo = "1";
          mostrar(await turno(texto));
        }
      } catch (e) {
        mostrar(e.message === "sin_oido"
          ? "Este navegador no tiene micrófono de voz. Escríbame el mensaje."
          : (e.message || "No pude oír."));
      }
      mic.classList.remove("escuchando");
      if (!hablando) cara.dataset.modo = "";
      ocupado = false;
    });
  }

  raiz.Asistente = { normalizar, interpretar, resolverNombres, montar, contexto, quitar, AYUDA };
})(typeof window !== "undefined" ? window : globalThis);
