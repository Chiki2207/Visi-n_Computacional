/* Asistente de la página. No llama al reconocimiento de caras.
   Son los mismos cuatro pasos que ui/asistente.py:

   1. normalizar: minúsculas y sin tildes.
   2. interpretar: saca la acción y los nombres (reglas / expresiones regulares).
   3. resolverNombres: busca en la lista. Si hay dos iguales, no elige.
   4. La página ejecuta esa acción con las rutas que ya tenía (presente, ausente, agregar, quitar).

   Respaldo (solo web): si interpretar() da «no», app.js puede pedir a Gemini
   (POST /api/chat/interpretar → chat_llm.py). Gemini solo propone la orden; los nombres
   vuelven a pasar por resolverNombres y eliminar pide «sí / no». Sin clave o si falla,
   el chat responde «No entendí» como antes. Documentado al final del README.md del proyecto.
*/
(function (raiz) {
  "use strict";

  const AYUDA = {
    texto: "Puedo marcar presente o ausente, eliminar estudiantes de la clase y abrir una lista por su código (ej.: 4821).",
    voz: "Puedo marcar presentes y ausentes, y abrir listas por código.",
  };

  function normalizar(texto) {
    return String(texto || "").trim().toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[¿?¡!.,;:]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }

  function partirNombres(trozo) {
    let t = trozo.trim().replace(/^(a|al|los|las|el|la)\s+/, "");
    t = t.replace(/\s+e\s+(?=[ie])/g, ", ").replace(/\s+y\s+/g, ", ");
    const fuera = new Set([
      "presente", "presentes", "ausente", "ausentes",
      "activo", "activos", "activa", "activas",
      "inactivo", "inactivos", "inactiva", "inactivas",
      "asistencia", "asistencias", "inasistencia", "inasistencias",
      "falta", "faltas", "aqui", "aca",
      "estudiante", "estudiantes", "alumno", "alumna", "alumnos", "alumnas",
      "como", "ponla", "ponlo", "ponle", "ponlas", "ponlos", "marcala", "marcalo",
    ]);
    return t.split(",").map((parte) => parte.trim()
      .replace(/^(a|al|de|el|la)\s+/, "")
      .replace(/\s+por favor$/, "")).filter((n) => n && !fuera.has(n));
  }

  /* «entra a la lista 4821», «4821», «abre la clase Computación 2»: cambiar de lista desde el chat.
     Solo navega por la página; no toca nada del reconocimiento. */
  const VERBO_ENTRAR = /^(?:entra|entrar|entre|entremos|ingresa|ingresar|ingrese|abre|abrir|abra|abreme|ve|vamos|ir|llevame|lleva|muestrame|muestra|muestre|selecciona|seleccionar|seleccione|elige|elegir|escoge|escoger)\b\s*/;

  function cuatroCifras(trozo) {
    const solo = String(trozo || "").replace(/\s+/g, "");
    return /^\d{4}$/.test(solo) ? solo : "";
  }

  function interpretarEntrar(t) {
    const directo = cuatroCifras(t);
    if (directo) return { accion: "entrar", codigo: directo, nombre: "", tipo: "" };
    const conVerbo = VERBO_ENTRAR.test(t);
    let r = t.replace(VERBO_ENTRAR, "")
      .replace(/^(?:me\s+)?(?:a|al|en|para|hacia)\s+/, "")
      .replace(/^(?:la|el|los|las)\s+/, "");
    let tipo = "";
    let conCodigo = false;
    const mt = r.match(/^(listas?|clases?|curso|grupo|materia)\b\s*/);
    if (mt) { tipo = mt[1].startsWith("lista") ? "lista" : "clase"; r = r.slice(mt[0].length); }
    r = r.replace(/^(?:de la|del|de|con el|con)\s+/, "");
    const mt2 = r.match(/^(?:clase|curso|grupo|materia)\b\s*/);
    if (mt2) { tipo = tipo || "clase"; r = r.slice(mt2[0].length); }
    const mc = r.match(/^(?:codigo|numero|num|#)\s*|^no\s*(?=\d)/);     // «no 4821» sí; un «no» solo, no
    if (mc) { conCodigo = true; r = r.slice(mc[0].length); }
    r = r.replace(/\s+por favor$/, "").trim();
    if (!conVerbo && !tipo && !conCodigo) return null;
    if (!conVerbo && !conCodigo && !cuatroCifras(r) && !/\b\d{4}\b/.test(r)) return null;   // «lista de Ana» sin verbo no es entrar
    if (!r) return { accion: "entrar", codigo: "", nombre: "", tipo };
    const enMedio = r.match(/\b(\d{4})\b/);
    const codigo = cuatroCifras(r) || (enMedio ? enMedio[1] : "");
    return { accion: "entrar", codigo, nombre: r, tipo };
  }

  /* «elimina a Juan», «borra al estudiante X», «elimina a X de la clase»: quitarlo de la clase.
     Siempre se pregunta antes (sí / no). «Borra la lista», «borra eso», «borra el chat»… no es esto. */
  const NO_ES_ALUMNO = /^(?:(?:la|el|los|las|esta|este|esa|ese|estas|estos|mi|tu|su|todo|toda)\s+)?(?:listas?|fotos?|clases?|cursos?|grupos?|materias?|historial|asistencias?|chat|conversacion|mensajes?|eso|esto|todo|nada|texto|audio|grabacion|registros?|selfies?|imagen|imagenes|codigo|huellas?|datos)\b/;
  function interpretarEliminar(t) {
    const m = t.match(/^elimina\s+(.+)$/);
    if (!m) return null;
    let r = m[1].replace(/\s+por favor$/, "").trim();
    if (/^(?:el |los |la )?(?:presentes?|ausentes?)\b/.test(r)) return null;     // «borra el presente de Juan»: lo ve «ausente»
    r = r.replace(/^(?:a |al )?(?:(?:la|el|los|las|un|una|del|de)\s+)?(?:estudiantes?|alumnos?|alumnas?)(?:\s+|$)/, "");
    r = r.replace(/\s+de\s+(?:la |el |esta |este |mi )?(?:clase|curso|lista|grupo|materia)\b.*$/, "").trim();
    if (!r || /^(?:a\s+)?(?:alguien|uno|una|un estudiante|una estudiante)$/.test(r)) return { accion: "falta_nombre", nombres: [] };
    if (NO_ES_ALUMNO.test(r)) return null;
    const nombres = partirNombres(r);
    if (!nombres.length || nombres.every((n) => ["estas", "ellos", "ellas", "este", "esta", "ese", "esa"].includes(n))) {
      return { accion: "falta_nombre", nombres: [] };
    }
    return { accion: "quitar", nombres };
  }

  /* Respuesta a «¿Elimino a …? (sí / no)». Solo un sí claro elimina. */
  function esSi(texto) {
    const t = normalizar(texto);
    return /^(?:si+|sip|claro|dale|hazlo|confirmo|confirmado|correcto|exacto|seguro|adelante|ok|okay|okey|vale|listo|de una|(?:elimina|borra)(?:lo|la|los|las))(?: (?:si+|claro|dale|hazlo|confirmo|por favor|seguro|de una|senor|profe|correcto|adelante|que si|(?:elimina|borra)(?:lo|la|los|las)?))*$/.test(t);
  }
  function esNo(texto) {
    return /^(?:no+|nop|nel|nada|cancela|cancelar|cancelalo|ninguno|ninguna|olvidalo|dejalo|mejor no|espera)(?: .*)?$/.test(normalizar(texto));
  }

  function preguntaEliminar(elegidos, donde) {
    const nombres = elegidos.map((p) => p.nombre);
    const quienes = nombres.length > 1 ? `${nombres.slice(0, -1).join(", ")} y ${nombres[nombres.length - 1]}` : nombres[0];
    const lugar = donde ? ` de ${donde}` : "";
    return {
      texto: `¿Elimino a ${quienes}${lugar}? (sí / no)`,
      voz: nombres.length > 3 ? `¿Elimino a estos ${nombres.length}?` : `¿Elimino a ${quienes}?`,
    };
  }

  /* ---------- Asistencia en lenguaje suelto (solo reglas) ----------
     1. Se quita el relleno («eh», «pues», «parce», «porfa», «a ver»…).
     2. Se buscan palabras de estado en cualquier parte: presente/activo/llegó/vino/asistió/está aquí,
        ausente/inactivo/faltó/falta/no vino/no está/no ha llegado.
     3. Lo que queda, sin verbos ni preposiciones, es el nombre (o varios, separados por «y» o comas).
     4. Si hay dos estados en una frase («Ana presente y Juan ausente») se parten en dos órdenes.
     Si no hay estado claro, no se adivina: se pregunta «¿presente o ausente?». */
  const RELLENO = new RegExp("(?:^| )(?:" + [
    "e+h+m*", "e+m+", "m{2,}", "pues", "parce", "parcero", "parcera", "porfa", "porfis", "porfi", "porfavor", "por favor", "por fa",
    "muchas gracias", "mil gracias", "gracias", "oye", "oiga", "oigan", "mira", "mire", "a ver", "bueno", "profe", "profesor", "profesora",
    "(?:hagame|hazme|me hace|me haces|hagan|haga) el favor(?: de| y)?", "que pena", "hoy", "todavia", "aun", "ahora", "ahorita", "ya",
    "entonces", "tambien", "senor", "senora", "listo", "dale", "quiero que", "quiero", "necesito que", "necesito", "puedes", "puede", "podrias",
    "me puedes", "me puede", "vale",
  ].join("|") + ")(?= |$)", "g");
  function limpiar(t) {
    let s = " " + t + " ", antes;
    do { antes = s; s = s.replace(RELLENO, " "); } while (s !== antes);
    return s.replace(/\s+/g, " ").trim();
  }
  /* Como normalizar, pero deja las comas (separan nombres u órdenes). */
  function normalizarConComas(texto) {
    return String(texto || "").trim().toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[,;]+/g, " , ")
      .replace(/[¿?¡!.:"«»()]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }

  const PAL_AUS = "ausentes?|inactiv[oa]s?|inasistencias?|faltas?|falto|faltaron|faltan|falte";
  const PAL_PRES = "presentes?|activ[oa]s?|asistencias?|llego|llegaron|vino|vinieron|asistio|asistieron|aqui|aca";
  const NEGADO = /(?:^| )no (?:ha |han |se |lo |la |)(?:vino|vinieron|viene|vienen|venido|llego|llegaron|llega|llegan|llegado|asistio|asistieron|asiste|esta|estan|aparecio|aparece)(?= |$)/g;
  function estadoDe(t) {
    let s = " " + t + " ";
    let aus = false, pres = false;
    if (NEGADO.test(s)) { aus = true; s = s.replace(NEGADO, " "); }
    NEGADO.lastIndex = 0;
    if (new RegExp("(?:^| )(?:" + PAL_AUS + ")(?= |$)").test(s)) aus = true;
    if (new RegExp("(?:^| )(?:" + PAL_PRES + ")(?= |$)").test(s)) pres = true;
    if (/(?:^| )tampoco(?= |$)/.test(s)) aus = true;
    const debil = !aus && !pres && /(?:^| )(?:esta|estan)(?= |$)/.test(s);
    // «… y Valentina sí» / «… y Juan no»: la frase anterior se sobreentiende
    const palabras = s.trim().split(" ").filter((w) => w && !/^(?:si|no|y|pero|a|al|la|el|de|mejor|que)$/.test(w));
    const eliptico = !aus && !pres && !debil && palabras.length ? (/ si $/.test(s) ? "pres" : / no $/.test(s) ? "aus" : "") : "";
    return { aus: aus || eliptico === "aus", pres: pres || debil || eliptico === "pres" };
  }

  const VERBO_ASIS = "(?:pon|pone|poner|ponerla|ponerlo|pongo|ponme|ponla|ponlo|ponle|ponles|ponlos|ponlas|ponmelo|ponmela" +
    "|(?:pong|marqu|coloqu)(?:a|o|as|an|ame|ala|alo|ale|anme|amelo|amela|e|es|en|eme|ela|elo|ele|enme|emelo|emela)" +
    "|(?:marc|coloc|dej|registr|anot|apunt|cambi|pas|agreg)(?:a|o|e|ar|as|an|en|es|ame|ala|alo|ale|alos|alas|amelo|amela|eme|ela|elo|ele|emelo|emela|enme|anme)" +
    "|anade|anadir)";
  const NO_NOMBRE = new RegExp("(?:^| )(?:" + [
    VERBO_ASIS, PAL_AUS, PAL_PRES, "no", "si", "a", "al", "de", "del", "la", "el", "los", "las", "lo", "le", "les", "me", "se", "que", "como",
    "con", "en", "para", "por", "su", "mi", "este", "esta", "estan", "estas", "estos", "ese", "esa", "esos", "esas", "alli", "ahi", "hay", "ha", "han",
    "es", "son", "fue", "tampoco", "quedo", "quedaron", "queda", "quedan", "asi", "porque", "pero", "llegado", "venido", "estudiante", "estudiantes",
    "alumno", "alumna", "alumnos", "alumnas", "muchacho", "muchacha", "pelao", "pelada", "chico", "chica", "joven", "lista", "clase", "nino", "nina",
    "cero", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "mil", "\\d+",
    "primero", "primera", "segundo", "segunda", "tercero", "tercera", "cuarto", "cuarta", "quinto", "quinta", "opcion", "numero",
  ].join("|") + ")(?= |$)", "g");
  function sinRelleno(s) {
    let r = " " + s + " ", antes;
    do { antes = r; r = r.replace(NO_NOMBRE, " "); } while (r !== antes);
    return r.replace(/\s+/g, " ").trim();
  }
  /* Nombres de un trozo: se parte por comas e «y» / «e» y a cada parte se le quita lo que no es nombre. */
  function nombresDe(trozo) {
    return trozo.split(/\s*,\s*|\s+(?:y|e)\s+/).map(sinRelleno).filter(Boolean);
  }

  /* Una orden de asistencia a partir de un trozo ya limpio. */
  function ordenAsistencia(trozo) {
    const e = estadoDe(trozo);
    const nombres = nombresDe(trozo);
    if (!e.aus && !e.pres) return null;
    const accion = e.aus && e.pres ? "preguntar" : e.aus ? "ausente" : "presente";
    if (!nombres.length) return { accion: accion === "preguntar" ? "falta_nombre" : "falta_nombre", nombres: [] };
    return { accion, nombres };
  }

  /* «Ana presente y Juan ausente», «Ana vino pero Juan faltó»: varias órdenes. */
  function ordenesAsistencia(tc) {
    const partes = tc.split(/\s*,\s*|\s+(?:y|e|pero|luego|despues|mientras)\s+/).map((p) => p.trim()).filter(Boolean);
    const grupos = [];
    let actual = null;
    for (const parte of partes) {
      const e = estadoDe(parte);
      const conEstado = e.aus || e.pres;
      const conNombre = nombresDe(parte).length > 0;
      if (actual && actual.conEstado && conEstado && conNombre) { grupos.push(actual); actual = null; }
      if (!actual) actual = { partes: [], conEstado: false };
      actual.partes.push(parte);
      actual.conEstado = actual.conEstado || conEstado;
    }
    if (actual) grupos.push(actual);
    if (grupos.length < 2) return null;
    const ordenes = [];
    let previa = null;
    for (const g of grupos) {
      const trozo = g.partes.join(" , ");
      let o = ordenAsistencia(trozo);
      if (!o && previa) o = { accion: previa.accion, nombres: nombresDe(trozo) };
      if (!o || !o.nombres.length) return null;
      ordenes.push(o);
      previa = o;
    }
    return ordenes;
  }

  /* «ponla», «márcalo», «ponla ausente», «no, ponlo presente»: el último estudiante nombrado. */
  function interpretarPronombre(t) {
    const m = t.match(/^(?:no )?(?:ponla|ponlo|ponlas|ponlos|ponle|ponmela|ponmelo|marcala|marcalo|marcalas|marcalos|marcale|marcamela|marcamelo|activala|activalo|activalas|activalos|dejala|dejalo|dejale|pongala|pongalo|marquela|marquelo|inactivala|inactivalo)(?: (?:como |de |a )?(presentes?|ausentes?|activ[oa]s?|inactiv[oa]s?|asistencias?|inasistencias?|faltas?))?$/);
    if (!m) return null;
    if (/^(?:no )?inactiva/.test(m[0])) return { accion: "ausente", nombres: [], ultimo: true };
    const estado = accionDeEstado(m[1] || "presente");
    return { accion: estado || "presente", nombres: [], ultimo: true };
  }

  function accionDeEstado(s) {
    const t = normalizar(s);
    if (new RegExp("^(?:" + PAL_AUS + ")$").test(t)) return "ausente";
    if (new RegExp("^(?:" + PAL_PRES + ")$").test(t)) return "presente";
    return null;
  }

  /* Respuesta a «¿Qué hago con X: presente o ausente?». */
  function estadoDeRespuesta(texto) {
    const t = limpiar(normalizar(texto)).replace(/^(?:no )?(?:ponla|ponlo|marcala|marcalo|activala|activalo|dejala|dejalo|pongala|pongalo|marquela|marquelo|pon|marca)\s*/, "")
      .replace(/^(?:como|de)\s+/, "").trim();
    if (!t) return /^(?:ponla|ponlo|marcala|marcalo|activala|activalo|pongala|pongalo|marquela|marquelo)/.test(limpiar(normalizar(texto))) ? "presente" : null;
    const e = estadoDe(t);
    if (sinRelleno(t)) return null;            // trae un nombre: es otra orden
    if (e.aus && !e.pres) return "ausente";
    if (e.pres && !e.aus) return "presente";
    return null;
  }

  function preguntaEstado(elegidos) {
    const nombres = elegidos.map((p) => p.nombre);
    const quienes = nombres.length > 1 ? `${nombres.slice(0, -1).join(", ")} y ${nombres[nombres.length - 1]}` : nombres[0];
    return { texto: `¿Qué hago con ${quienes}: presente o ausente?`, voz: "¿Presente o ausente?" };
  }

  function hayClavesAsistencia(t) {
    const e = estadoDe(t);
    return e.aus || e.pres;
  }
  function hayClavesBorrar(t) {
    return /\b(?:elimina|borra|borrelo|borrela|borralo|borrala|borralos|retiro|retiralo|retirala|retirar|elimines|borres|saques)\b/.test(t);
  }

  function aplicarVerbos(t, paraAsistencia) {
    t = t
      .replace(/\b(pongas|ponga|pongame|ponme|pongan|poner|ponle)\b/g, "pon")
      .replace(/\b(marques|marque|marcar|marcame)\b/g, "marca")
      .replace(/\b(quites|quite|quitar)\b/g, "quita")
      .replace(/\b(elimina|elimine|eliminar|eliminame|eliminalo|eliminala|borra|borre|borrar|borrame|borralo|borrala)\b/g, "elimina")
      .replace(/\b(saca|saque|sacar|sacame)\b/g, "quita")
      .replace(/\b(pases|pase|pasar|toma|tomar|haz|hacer)\b/g, "pasa");
    if (paraAsistencia) t = t.replace(/\b(registra|registrar|registre|registrame|agregues|agregue|agregar|anades|anade|anadir|mete|meter)\b/g, "pon");
    else t = t.replace(/\b(agregues|agregue|agregar|anades|anade|anadir|registra|registrar|registre|registrame|mete|meter|crea|crear)\b/g, "agrega");
    return t;
  }

  /* Números dichos en palabras para los códigos: «cuatro ocho dos uno», «cuatro mil ochocientos veintiuno». */
  const DIGITOS = { cero: 0, uno: 1, una: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5, seis: 6, siete: 7, ocho: 8, nueve: 9 };
  const VALORES = Object.assign({}, DIGITOS, { diez: 10, once: 11, doce: 12, trece: 13, catorce: 14, quince: 15, dieciseis: 16, diecisiete: 17,
    dieciocho: 18, diecinueve: 19, veinte: 20, veintiuno: 21, veintiun: 21, veintidos: 22, veintitres: 23, veinticuatro: 24, veinticinco: 25,
    veintiseis: 26, veintisiete: 27, veintiocho: 28, veintinueve: 29, treinta: 30, cuarenta: 40, cincuenta: 50, sesenta: 60, setenta: 70,
    ochenta: 80, noventa: 90, cien: 100, ciento: 100, doscientos: 200, trescientos: 300, cuatrocientos: 400, quinientos: 500,
    seiscientos: 600, setecientos: 700, ochocientos: 800, novecientos: 900 });
  function numerosEnPalabras(t) {
    const ws = t.split(" ");
    const out = [];
    let i = 0;
    while (i < ws.length) {
      let j = i;
      while (j < ws.length && Object.prototype.hasOwnProperty.call(DIGITOS, ws[j])) j++;
      if (j - i === 4) { out.push(ws.slice(i, j).map((w) => DIGITOS[w]).join("")); i = j; continue; }
      if (Object.prototype.hasOwnProperty.call(VALORES, ws[i]) || ws[i] === "mil") {
        let k = i, total = 0, actual = 0, mil = false, usados = 0;
        while (k < ws.length) {
          const w = ws[k];
          if (w === "y" && usados && Object.prototype.hasOwnProperty.call(VALORES, ws[k + 1] || "")) { k++; continue; }
          if (w === "mil") { total += (actual || 1) * 1000; actual = 0; mil = true; usados++; k++; continue; }
          if (Object.prototype.hasOwnProperty.call(VALORES, w)) { actual += VALORES[w]; usados++; k++; continue; }
          break;
        }
        const n = total + actual;
        if (mil && usados >= 2 && n >= 1000 && n <= 9999) { out.push(String(n)); i = k; continue; }
      }
      out.push(ws[i]);
      i++;
    }
    return out.join(" ");
  }

  const SALUDO = /^(?:hola|holi|holis|hey|buenas|buen dia|buenos dias|buenas tardes|buenas noches|buenas dias|que mas|quiubo|quihubo|que hubo|saludos)(?: .*)?$/;
  const AYUDAS = /^(?:ayuda|ayudame|ayudeme|que puedes hacer|que sabes hacer|que haces|comandos|como funciona|como funcionas|como te uso|que hago|instrucciones|menu)$/;

  function interpretar(texto) {
    const crudo = normalizar(texto);
    const limpio = limpiar(crudo).replace(/^(?:me|nos)\s+/, "");
    if (!limpio) {
      if (/(?:^| )gracias(?: |$)/.test(crudo)) return { accion: "gracias", nombres: [] };
      return { accion: crudo ? "relleno" : "vacio", nombres: [] };
    }
    if (AYUDAS.test(limpio) || AYUDAS.test(crudo)) return { accion: "ayuda", nombres: [] };
    if (/(?:^| )gracias(?: |$)/.test(crudo) && /^(?:ok|okay|okey|vale|listo|bueno|dale|si|bien|perfecto|excelente|chevere|de una|muy amable)?$/.test(limpio)) {
      return { accion: "gracias", nombres: [] };
    }
    if (SALUDO.test(limpio)) {
      const resto = limpio.replace(/^(?:buenos dias|buenas tardes|buenas noches|buenas dias|buen dia|buenas|holis|holi|hola|hey|que mas|quiubo|quihubo|que hubo|saludos)\s*/, "")
        .replace(/^(?:buenos dias|buenas tardes|buenas noches|tardes|noches|dias|como (?:esta|estas|va|vas)|que tal)\s*/, "").trim();
      if (!resto) return { accion: "saludo", nombres: [] };
      const o = interpretar(resto);
      return o.accion === "no" || o.accion === "relleno" || o.accion === "vacio" ? { accion: "saludo", nombres: [] } : o;
    }
    if (/^(?:no (?:elimines|borres|saques|quites|pongas|marques|lo|la|le|los|las|me)|no (?:a )?nadie|no hagas nada|nada|mejor no|creo que no)\b/.test(limpio)) {
      if (limpio === "no" || limpio === "nada") return { accion: "no", nombres: [] };
      return { accion: "nada", nombres: [] };
    }
    const pron = interpretarPronombre(limpio);
    if (pron) return pron;
    const paraAsistencia = hayClavesAsistencia(limpio);
    const t = aplicarVerbos(limpio, paraAsistencia);
    if (/^pasa( la| el)? (lista|asistencia)$/.test(t)) return { accion: "pasar", nombres: [] };
    const conNumeros = numerosEnPalabras(t);
    const entrar = interpretarEntrar(conNumeros) || (conNumeros !== t ? null : null);
    if (entrar && (entrar.codigo || !paraAsistencia)) return { ...entrar, nombres: [] };
    const eliminar = interpretarEliminar(t);
    if (eliminar) return eliminar;
    const patrones = [
      ["quitar", /^(?:quita) (?:al |el |la |a )?(?:estudiante|alumno|alumna) (.+)$/],
      ["quitar", /^(?:quita) (?:a |al )?(.+?) (?:de (?:la |el |esta |este |mi )?(?:clase|curso|lista|grupo|materia)\b.*)$/],
      ["agregar", /^(?:agrega) (?:al |a la |el |la |un |una |a )?(?:estudiante |alumno |alumna )?(.+)$/],
      ["ausente", /^(?:quita|elimina) (?:el |los )?presentes? (?:de |a )?(.+)$/],
      ["ausente", /^(?:quita) (?:a )?(.+)$/],
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
    /* asistencia: con comas, para poder separar nombres y órdenes */
    const conComas = limpiar(normalizarConComas(texto)).replace(/^(?:me|nos)\s+/, "").replace(/^(?:, )+|(?: ,)+$/g, "").trim();
    const varias = ordenesAsistencia(conComas);
    if (varias) return { accion: "varias", ordenes: varias, nombres: [] };
    const una = ordenAsistencia(conComas);
    if (una) return una;
    return { accion: "no", nombres: [] };
  }

  /* Solo un nombre de la lista, sin decir qué hacer: se pregunta. */
  function inferirDeLista(texto, lista) {
    const limpio = limpiar(normalizar(texto));
    if (!limpio || hayClavesBorrar(limpio)) return null;
    const nombre = sinRelleno(limpio);
    if (!nombre) return null;
    // al menos la mitad de lo dicho tiene que ser, tal cual, una palabra de algún nombre de la lista
    const palabrasLista = new Set();
    for (const p of lista) for (const w of palabrasDe(p.nombre)) palabrasLista.add(w);
    const dichas = palabrasDe(nombre);
    const exactas = dichas.filter((w) => palabrasLista.has(w) || numeroId(w) !== null).length;
    if (!dichas.length || exactas * 2 < dichas.length) return null;
    const [elegidos, , opciones] = resolverNombres([nombre], lista);
    if (!elegidos.length && !opciones.length) return null;
    return { accion: "preguntar", nombres: [nombre] };
  }

  function numeroId(token) {
    const m = /^e(\d{1,4})$/.exec(token);
    return m ? Number(m[1]) : null;
  }

  /* ---------- Nombres mal oídos («araña» por «avendaño»): parecido por palabra.
     Se compara palabra por palabra (sin tildes, ñ = n) con Jaro-Winkler y una versión «como suena»
     (v = b, z = s, ll = y, sin h…). Solo se aplica solo si hay UN estudiante claramente mejor. */
  const VACIAS = new Set(["de", "del", "la", "las", "los", "el", "y", "e", "a", "al", "da", "do"]);

  function palabrasDe(texto) {
    return normalizar(texto).split(" ").filter((w) => w && !VACIAS.has(w));
  }

  function comoSuena(w) {
    return w.replace(/h/g, "").replace(/ll/g, "y").replace(/v/g, "b").replace(/z/g, "s")
      .replace(/c([ei])/g, "s$1").replace(/qu/g, "k").replace(/c/g, "k").replace(/g([ei])/g, "j$1")
      .replace(/x/g, "ks").replace(/w/g, "u").replace(/(.)\1+/g, "$1");
  }

  function jaroWinkler(a, b) {
    if (a === b) return 1;
    const la = a.length, lb = b.length;
    if (!la || !lb) return 0;
    const rango = Math.max(0, Math.floor(Math.max(la, lb) / 2) - 1);
    const ma = new Array(la).fill(false), mb = new Array(lb).fill(false);
    let m = 0;
    for (let i = 0; i < la; i++) {
      for (let j = Math.max(0, i - rango); j < Math.min(lb, i + rango + 1); j++) {
        if (!mb[j] && a[i] === b[j]) { ma[i] = mb[j] = true; m++; break; }
      }
    }
    if (!m) return 0;
    let t = 0, k = 0;
    for (let i = 0; i < la; i++) {
      if (!ma[i]) continue;
      while (!mb[k]) k++;
      if (a[i] !== b[k]) t++;
      k++;
    }
    const jaro = (m / la + m / lb + (m - t / 2) / m) / 3;
    let pre = 0;
    while (pre < 4 && a[pre] === b[pre]) pre++;
    return jaro + pre * 0.1 * (1 - jaro);
  }

  function parecidoPalabra(q, w) {
    if (q === w) return 1;
    if (comoSuena(q) === comoSuena(w)) return 0.96;
    if (q.length >= 4 && w.startsWith(q)) return 0.92;          // «avend» → «avendano»
    return Math.max(jaroWinkler(q, w), jaroWinkler(comoSuena(q), comoSuena(w)) - 0.02);
  }

  /* Qué tanto se parece lo dicho al nombre: cada palabra dicha busca su mejor pareja (sin repetir). */
  function puntaje(qs, persona) {
    const ws = palabrasDe(persona.nombre);
    const usadas = new Set();
    let suma = 0, fuertes = 0, flojas = 0, peor = 1;
    for (const q of qs) {
      let mejor = 0, cual = -1;
      ws.forEach((w, i) => {
        if (usadas.has(i)) return;
        const v = parecidoPalabra(q, w);
        if (v > mejor) { mejor = v; cual = i; }
      });
      if (cual >= 0) usadas.add(cual);
      suma += mejor;
      if (mejor >= 0.88) fuertes++;
      else flojas++;
      peor = Math.min(peor, mejor);
    }
    return { persona, puntaje: qs.length ? suma / qs.length : 0, fuertes, flojas, peor };
  }

  /* Devuelve { seguro: [persona] } si hay uno claro, { dudas: [...] } si hay que preguntar, o {}. */
  function aproximados(pedido, personas) {
    const qs = palabrasDe(pedido).filter((w) => numeroId(w) === null);
    if (!qs.length) return {};
    const todos = personas.map((p) => puntaje(qs, p)).sort((x, y) => y.puntaje - x.puntaje);
    // «alto»: todo coincide, o falla UNA palabra (algo parecida) y al menos dos coinciden bien
    const alto = (r) => r.puntaje >= 0.8 && (r.flojas === 0 || (r.flojas === 1 && r.fuertes >= 2 && r.peor >= 0.5));
    // se aplica solo si la palabra fallada está rodeada de 3 que sí coinciden (o se parece bastante)
    const firme = (r) => r.flojas === 0 || r.fuertes >= 3 || r.peor >= 0.7;
    const altos = todos.filter(alto);
    if (altos.length === 1) {
      const otro = todos.find((r) => r !== altos[0]);
      if (!otro || altos[0].puntaje - otro.puntaje >= 0.08) {
        // una sola palabra parecida («cuatro» ~ «castro») nunca basta: se pregunta
        const unaSola = qs.length === 1 && altos[0].peor < 0.96;
        return firme(altos[0]) && !unaSola ? { seguro: [altos[0].persona] } : { dudas: [altos[0].persona] };
      }
    }
    if (altos.length > 1) {
      const tope = altos[0].puntaje;
      return { dudas: altos.filter((r) => tope - r.puntaje < 0.08).slice(0, 5).map((r) => r.persona) };
    }
    const dudas = todos.filter((r) => r.puntaje >= 0.72 && r.fuertes >= 1).slice(0, 3).map((r) => r.persona);
    return dudas.length ? { dudas } : {};
  }

  /* «¿Cuál? 1) … 2) …» (texto) y algo corto para la voz. */
  function preguntaCual(opciones) {
    if (opciones.length === 1) {
      return { texto: `¿Es ${opciones[0].nombre}? (sí / no)`, voz: `¿Es ${opciones[0].nombre}?` };
    }
    const mostradas = opciones.slice(0, 8);
    const texto = "¿Cuál? " + mostradas.map((p, i) => `${i + 1}) ${p.nombre}`).join("  ")
      + (opciones.length > mostradas.length ? `  y ${opciones.length - mostradas.length} más` : "");
    const voz = opciones.length <= 3
      ? "¿Cuál? " + opciones.map((p, i) => `${i + 1}, ${p.nombre}`).join(". ") + "."
      : `¿Cuál? Hay ${opciones.length}. Dime el número.`;
    return { texto, voz };
  }

  const NUMEROS = { uno: 1, una: 1, primero: 1, primera: 1, dos: 2, segundo: 2, segunda: 2, tres: 3, tercero: 3,
    tercera: 3, cuatro: 4, cuarto: 4, cuarta: 4, cinco: 5, quinto: 5, quinta: 5, seis: 6, siete: 7, ocho: 8 };
  function numeroOpcion(texto) {
    const t = normalizar(texto).replace(/^(?:el|la|numero|opcion|es el|es la)\s+/, "").replace(/^(?:numero|opcion)\s+/, "");
    if (/^\d{1,2}$/.test(t)) return Number(t);
    return NUMEROS[t] || null;
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
    if (!q) return [[], "¿A quién?", modo];
    const tokens = q.split(" ").filter((tok) => !["el", "la", "id", "numero"].includes(tok));
    const numeros = tokens.map(numeroId).filter((n) => n !== null);
    if (numeros.length > 1) return [[], "Un código a la vez.", modo];
    if (numeros.length === 1) {
      const quien = personas.filter((p) => numeroId(normalizar(p.id)) === numeros[0]);
      if (!quien.length) return [[], `No hay nadie con el código E${String(numeros[0]).padStart(3, "0")}.`, modo];
      const resto = tokens.filter((tok) => numeroId(tok) === null);
      const palabras = normalizar(quien[0].nombre).split(" ");
      if (resto.length && resto.some((tok) => !palabras.includes(tok))) {
        return [[], `El ${quien[0].id} es ${quien[0].nombre}, no coincide.`, modo];
      }
      return [[quien[0]], null, modo];
    }
    const exactos = personas.filter((p) => normalizar(p.nombre) === q);
    if (exactos.length) return [exactos, null, modo];
    const contienen = personas.filter((p) => {
      const palabras = normalizar(p.nombre).split(" ");
      return tokens.every((tok) => palabras.includes(tok));
    });
    if (contienen.length || modo) return [contienen, null, modo];
    const ap = aproximados(q, personas);           // nombre mal oído o mal escrito
    if (ap.seguro) return [ap.seguro, null, modo];
    if (ap.dudas) return [ap.dudas, null, "duda"];
    return [[], null, modo];
  }

  /* Devuelve [elegidos, error, opciones, pausa]. Si hay que preguntar «¿Cuál?», pausa guarda
     los ya elegidos y los nombres que faltan, para seguir después de la respuesta. Nunca elige
     entre dos parecidos: pregunta. */
  function resolverNombres(pedidos, personas, previos = []) {
    if (!personas.length) return [[], "No hay estudiantes cargados.", [], null];
    const elegidos = [...previos];
    const vistos = new Set(elegidos.map((p) => String(p.id)));
    for (let k = 0; k < pedidos.length; k++) {
      const pedido = pedidos[k];
      const [candidato, err, modo] = candidatos(pedido, personas);
      if (err) return [[], err, [], null];
      if (!candidato.length) return [[], `No encontré a «${pedido}» en esta lista.`, [], null];
      const pausa = { previos: elegidos.slice(), resto: pedidos.slice(k + 1), pedido };
      if (modo === "par" && candidato.length !== 2) return [[], preguntaCual(candidato), candidato, pausa];
      if (modo === "duda" || (candidato.length > 1 && modo !== "todos" && modo !== "par")) {
        return [[], preguntaCual(candidato), candidato, pausa];
      }
      for (const persona of candidato) {
        if (!vistos.has(String(persona.id))) {
          elegidos.push(persona);
          vistos.add(String(persona.id));
        }
      }
    }
    return [elegidos, null, [], null];
  }

  const SPRITES_V = "2";   // subir este numero cuando cambien las fotos de asistente/ (el navegador las guarda 1 dia)
  function sprite(nombre) {
    return `/asistente/${nombre}.jpg?v=${SPRITES_V}`;
  }

  /* Boca al hablar: hablar_* son la cara en reposo con SOLO la boca cambiada (los ojos y la cara
     no se mueven, así no parpadea). m, b, p y los espacios cierran la boca. */
  const BOCAS = { a: "hablar_a", e: "hablar_e", i: "hablar_i", y: "hablar_i", o: "hablar_o", u: "hablar_u" };
  function lineaBoca(texto) {
    const t = String(texto || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    const pasos = [];
    const poner = (cara, ms, i) => {
      const ult = pasos[pasos.length - 1];
      if (ult && ult.cara === cara) { ult.ms += ms; return; }
      pasos.push({ cara, ms, i });
    };
    for (let i = 0; i < t.length; i++) {
      const c = t[i];
      if (BOCAS[c] && !(c === "y" && /[aeiou]/.test(t[i + 1] || ""))) poner(BOCAS[c], 105, i);
      else if ("mbp".includes(c)) poner("reposo", 65, i);
      else if (/[.;:!?¿¡]/.test(c)) poner("reposo", 230, i);
      else if (/[\s,]/.test(c)) poner("reposo", c === "," ? 160 : 35, i);
      else if (/[a-z0-9]/.test(c)) {
        if (/[0-9]/.test(c)) poner("hablar_e", 150, i);       // los números se dicen largos
        else if (pasos.length) pasos[pasos.length - 1].ms += 30;
      }
    }
    if (!pasos.length || pasos[pasos.length - 1].cara !== "reposo") pasos.push({ cara: "reposo", ms: 120, i: t.length });
    return pasos;
  }

  /* Lo que se dice en voz: corto (sin códigos E001 ni comillas). */
  function paraVoz(r) {
    if (!r) return "";
    if (typeof r === "object") return String(r.voz || r.texto || "");
    return String(r).replace(/\s*\(E\d{1,4}\)/g, "").replace(/[«»]/g, "").trim();
  }
  function paraTexto(r) {
    if (!r) return "";
    return typeof r === "object" ? String(r.texto || r.voz || "") : String(r);
  }

  function miradaDe(dx, dy) {
    const ax = Math.abs(dx);
    const ay = Math.abs(dy);
    if (ax < 40 && ay < 40) return "ojos_centro";
    if (ax >= ay) return dx < 0 ? "ojos_izq" : "ojos_der";
    return dy < 0 ? "ojos_arriba" : "ojos_abajo";
  }

  /* Voz a texto con el reconocimiento del navegador (igual que antes).
     Devuelve { promesa, enviar, cancelar }:
     - promesa: el texto oído ("" si no oyó nada, null si se canceló).
     - enviar(): deja de oír y manda lo que ya oyó (botón enviar / soltar el micrófono).
     - cancelar(): deja de oír y no manda nada (botón basura / deslizar a la izquierda).
     Si nadie toca nada, termina solo cuando la persona deja de hablar, como siempre. */
  function escuchar(alSonido = () => {}) {
    const SR = raiz.SpeechRecognition || raiz.webkitSpeechRecognition;
    if (!SR) return { promesa: Promise.reject(new Error("sin_oido")), enviar() {}, cancelar() {} };
    let rec = null;
    let cancelado = false;
    let final = "";
    let parcial = "";
    const promesa = new Promise((resolve, reject) => {
      rec = new SR();
      rec.lang = "es-CO";
      rec.interimResults = true;     // así, si la persona toca enviar a mitad de frase, no se pierde lo dicho
      rec.maxAlternatives = 1;
      rec.onresult = (ev) => {
        parcial = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i];
          if (r.isFinal) final += (final ? " " : "") + (r[0].transcript || "").trim();
          else parcial += r[0].transcript || "";
        }
      };
      rec.onspeechstart = () => alSonido(true);
      rec.onspeechend = () => alSonido(false);
      rec.onerror = (ev) => {
        if (cancelado || ev.error === "aborted") return;
        if (ev.error === "no-speech") return;      // onend lo cierra con ""
        reject(new Error(ev.error === "not-allowed" || ev.error === "service-not-allowed" ? "Permite el micrófono en el navegador."
          : ev.error === "audio-capture" ? "No encuentro el micrófono."
            : ev.error === "network" ? "Sin internet para la voz. Escríbelo." : "No te oí bien. Escríbelo."));
      };
      rec.onend = () => resolve(cancelado ? null : (final || parcial).trim());
      try { rec.start(); } catch (e) { reject(e); }
    });
    return {
      promesa,
      enviar() { try { rec && rec.stop(); } catch { /* ya terminó */ } },
      cancelar() { cancelado = true; try { rec && rec.abort(); } catch { /* ya terminó */ } },
    };
  }

  /* Ícono SVG fijo (nunca datos del usuario). */
  function iconoSvg(d, t = 22) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", t);
    svg.setAttribute("height", t);
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("fill", "currentColor");
    path.setAttribute("d", d);
    svg.append(path);
    return svg;
  }
  const ICONO_MIC = "M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z";
  const ICONO_ENVIAR = "M2.01 21 23 12 2.01 3 2 10l15 2-15 2z";
  const ICONO_BASURA = "M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z";

  /* Las 9 miradas: frente + 8 direcciones (ángulo en grados, 0 = derecha, 90 = abajo, como la pantalla). */
  const MIRADAS = [
    ["ojos_der", 0], ["ojos_abajo_der", 45], ["ojos_abajo", 90], ["ojos_abajo_izq", 135],
    ["ojos_izq", 180], ["ojos_arriba_izq", -135], ["ojos_arriba", -90], ["ojos_arriba_der", -45],
  ];
  function difAngulo(a, b) {
    let d = Math.abs(a - b) % 360;
    return d > 180 ? 360 - d : d;
  }

  let oirRaton = null;
  let soltarRaton = null;
  let cuadro = 0;
  let navegar = null;      // la página dice cómo entrar a una lista (por código o nombre)
  let timerAviso = 0;
  let timerBoca = 0;
  let timerParpadeo = 0;
  let grabacion = null;    // si está oyendo por el micrófono: se corta al salir
  let ctx = { personas: async () => [], actuar: async () => AYUDA };
  let estado = null;

  function quitar() {
    clearInterval(timerBoca);
    clearInterval(timerParpadeo);
    clearTimeout(timerAviso);
    if (grabacion) { try { grabacion(); } catch { /* nada */ } grabacion = null; }
    if (cuadro) cancelAnimationFrame(cuadro);
    cuadro = 0;
    if (oirRaton) {
      document.removeEventListener("pointermove", oirRaton);
      document.removeEventListener("pointerdown", oirRaton);
    }
    if (soltarRaton) document.removeEventListener("mouseout", soltarRaton);
    oirRaton = null;
    soltarRaton = null;
    estado = null;
    if (dialogoActual) dialogoActual.olvidar();
    document.getElementById("chat-asistente")?.remove();
  }

  function contexto(opciones) {
    ctx = {
      personas: opciones.personas || (async () => []),
      actuar: opciones.actuar || (async () => AYUDA),
      donde: opciones.donde || "",
    };
    if (dialogoActual) dialogoActual.olvidar();      // otra clase u otra lista: nada pendiente se arrastra
  }

  /* La página dice cómo entrar a una lista o clase cuando se la piden en el chat. */
  function alEntrar(fn) {
    navegar = typeof fn === "function" ? fn : null;
  }

  /* Mensaje del asistente sin que nadie escriba (p. ej. «Entraste a la lista …»). */
  function avisar(r) {
    if (estado && estado.avisar && r) estado.avisar(r);
  }

  /* Debajo del nombre «Asistente»: en qué lista o clase está el chat ahora. */
  function lugar(texto) {
    if (estado && estado.lugar) estado.lugar(texto ? String(texto) : "");
  }

  /* Respaldo (Gemini, en el servidor): SOLO cuando las reglas no entendieron la frase.
     Lo que devuelve se vuelve una orden igual a las de las reglas y sigue el mismo camino:
     los nombres pasan por el buscador aproximado contra la lista real y eliminar pide «sí / no».
     Si no hay respaldo, tarda o falla, el chat responde como siempre («No entendí»). */
  const RESPALDO_MS = 3500;
  const ACCIONES_RESPALDO = new Set(["entrar", "presente", "ausente", "quitar", "agregar", "pasar", "ayuda"]);
  let respaldo = null;
  function alInterpretar(fn) {
    respaldo = typeof fn === "function" ? fn : null;
  }

  function ordenDeRespaldo(r) {
    if (!r || r.ok !== true || !ACCIONES_RESPALDO.has(r.accion)) return null;
    const nombres = Array.isArray(r.nombres) ? r.nombres.map((n) => String(n || "").trim()).filter(Boolean).slice(0, 20) : [];
    if (r.accion === "entrar") {
      const codigo = /^\d{4}$/.test(String(r.codigo || "")) ? String(r.codigo) : "";
      const nombre = String(r.destino || "").trim();
      if (!codigo && !nombre) return null;
      return { accion: "entrar", codigo, nombre, tipo: r.tipo === "lista" || r.tipo === "clase" ? r.tipo : "", nombres: [] };
    }
    if (r.accion === "pasar" || r.accion === "ayuda") return { accion: r.accion, nombres: [] };
    if (!nombres.length) return { accion: "falta_nombre", nombres: [] };
    return { accion: r.accion, nombres };
  }

  async function preguntarRespaldo(texto) {
    if (!respaldo) return null;
    let nombres = [];
    try { nombres = ((await Promise.resolve(ctx.personas())) || []).map((p) => p.nombre).filter(Boolean); }
    catch { nombres = []; }
    let reloj = 0;
    const tarde = new Promise((ok) => { reloj = setTimeout(() => ok(null), RESPALDO_MS); });
    try { return ordenDeRespaldo(await Promise.race([Promise.resolve(respaldo(texto, nombres)), tarde])); }
    catch { return null; }
    finally { clearTimeout(reloj); }
  }

  const NO_ENTENDI = { texto: "No entendí. Escribe «ayuda» para ver qué puedo hacer.", voz: "No entendí." };

  /* La conversación (sin la página): «¿Cuál?», «¿Elimino a …?» y qué hacer con cada orden. */
  const CONFIRMAR_MS = 3 * 60 * 1000;     // un «sí» que llega mucho después no elimina
  let dialogoActual = null;
  const SALUDO_R = { texto: "Hola. Dime, por ejemplo: «pon a Ana presente».", voz: "Hola. ¿A quién marco?" };
  const GRACIAS_R = { texto: "Con gusto.", voz: "Con gusto." };
  const PISTA_R = { texto: "Dime qué hago, por ejemplo: «pon a Ana presente».", voz: "Dime qué hago." };
  const NADA_PENDIENTE = { texto: "No tengo nada pendiente. ¿Qué hago?", voz: "No tengo nada pendiente." };
  const SUELTO = /^(?:si+|sip|no+|nop|nel|ok|okay|okey|vale|listo|dale|claro|de una|bueno|correcto|exacto|confirmo|cancela|cancelar)$/;

  function nuevoDialogo(opciones = {}) {
    const pensando = typeof opciones.pensando === "function" ? opciones.pensando : () => {};
    let aclaracion = null;
    let porConfirmar = null;      // { elegidos, ctx, hasta }
    let porEstado = null;         // { elegidos, ctx }
    let ultimoElegidos = [];
    let ultimoCtx = null;

    function recordar(elegidos) {
      if (elegidos && elegidos.length) { ultimoElegidos = elegidos.slice(); ultimoCtx = ctx; }
    }
    function pendiente() { return !!(aclaracion || porConfirmar || porEstado); }

    function pedirConfirmar(elegidos) {
      aclaracion = null;
      porEstado = null;
      recordar(elegidos);
      porConfirmar = { elegidos, ctx, hasta: Date.now() + CONFIRMAR_MS };
      const donde = typeof ctx.donde === "function" ? ctx.donde() : ctx.donde;
      return preguntaEliminar(elegidos, donde || "");
    }
    function pedirEstado(elegidos) {
      aclaracion = null;
      porConfirmar = null;
      recordar(elegidos);
      porEstado = { elegidos, ctx };
      return preguntaEstado(elegidos);
    }

    async function hacer(accion, elegidos) {
      if (!elegidos.length) return "No cambié a nadie.";
      if (accion === "quitar") return pedirConfirmar(elegidos);
      if (accion === "preguntar") return pedirEstado(elegidos);
      recordar(elegidos);
      return ctx.actuar({ accion, elegidos });
    }

    async function seguirCon(pausa, accion, elegidos) {
      // tras elegir, se siguen los nombres que faltaban de la misma orden
      if (pausa.resto && pausa.resto.length) {
        const lista = await Promise.resolve(ctx.personas());
        const [mas, err, opciones, otra] = resolverNombres(pausa.resto, lista, elegidos);
        if (opciones.length) { aclaracion = { accion, opciones, pausa: otra }; return err; }
        if (err) return err;
        elegidos = mas;
      }
      return hacer(accion, elegidos);
    }

    /* Una orden ya entendida (de las reglas o del respaldo). */
    async function ejecutar(orden, texto) {
      if (orden.ultimo) {
        if (!ultimoElegidos.length || ultimoCtx !== ctx) return "¿A quién?";
        return hacer(orden.accion, ultimoElegidos);
      }
      if (orden.accion === "entrar") {
        if (!orden.codigo && !orden.nombre) return "Dime el código de 4 números.";
        if (!navegar) return "Desde aquí no puedo cambiar de lista.";
        return navegar({ codigo: orden.codigo, nombre: orden.nombre, tipo: orden.tipo });
      }
      if (orden.accion === "ayuda") return AYUDA;
      if (orden.accion === "saludo") return SALUDO_R;
      if (orden.accion === "gracias") return GRACIAS_R;
      if (orden.accion === "vacio" || orden.accion === "relleno") return PISTA_R;
      if (orden.accion === "nada") return "Vale, no hago nada.";
      if (orden.accion === "falta_nombre") return "¿A quién?";
      if (orden.accion === "pasar") return ctx.actuar({ accion: "pasar" });
      if (orden.accion === "agregar") {
        if (orden.nombres.length !== 1) return "Uno a la vez: cada uno lleva su foto.";
        return ctx.actuar({ accion: "agregar", nombre: orden.nombres[0] });
      }
      if (orden.accion === "varias") {
        const dichos = [];
        for (const o of orden.ordenes) {
          const r = await ejecutar(o, texto);
          dichos.push(r);
          if (pendiente()) break;            // quedó una pregunta: se sigue después
        }
        const t = dichos.map(paraTexto).filter(Boolean).join(" ");
        const v = dichos.map(paraVoz).filter(Boolean).join(" ");
        return { texto: t, voz: v.length > 150 ? "Listo." : v };
      }
      const lista = await Promise.resolve(ctx.personas());
      if (!lista.length) return ctx.actuar({ accion: orden.accion === "preguntar" ? "presente" : orden.accion, elegidos: [] });   // fuera de una lista: la página dice dónde
      const [elegidos, err, opciones, pausa] = resolverNombres(orden.nombres, lista);
      if (orden.accion === "quitar" && opciones.length === 1 && !(pausa.resto || []).length && !(pausa.previos || []).length) {
        return pedirConfirmar(opciones);        // «¿Es X?» y «¿Elimino a X?» en una sola pregunta
      }
      if (opciones.length) { aclaracion = { accion: orden.accion, opciones, pausa }; return err; }
      if (err) return err;
      return hacer(orden.accion, elegidos);
    }

    async function turno(texto) {
      texto = String(texto == null ? "" : texto);
      if (porConfirmar) {
        const p = porConfirmar;
        porConfirmar = null;
        const vigente = p.ctx === ctx && Date.now() <= p.hasta;
        if (esSi(texto)) {
          if (!vigente) return "Eso ya venció. Pídemelo otra vez.";
          recordar(p.elegidos);
          return ctx.actuar({ accion: "quitar", elegidos: p.elegidos, confirmado: true });
        }
        if (esNo(texto)) return "Vale, no eliminé a nadie.";
        // cualquier otra cosa: se olvida la pregunta y se atiende como orden nueva
      }
      if (porEstado) {
        const p = porEstado;
        porEstado = null;
        const estado = estadoDeRespuesta(texto);
        if (estado) {
          if (p.ctx !== ctx) return "Eso ya venció. Pídemelo otra vez.";
          recordar(p.elegidos);
          return ctx.actuar({ accion: estado, elegidos: p.elegidos });
        }
        if (esNo(texto)) return "Vale, no cambié nada.";
      }
      let orden;
      try { orden = interpretar(texto); }
      catch { orden = { accion: "no", nombres: [] }; }
      if (aclaracion && (orden.accion === "no" || orden.accion === "falta_nombre" || orden.accion === "relleno")) {
        const t = normalizar(texto);
        const grupo = aclaracion.opciones || [];
        const pausa = aclaracion.pausa || { previos: [], resto: [] };
        const pend = aclaracion;
        if (/^(no|nop|nel|ninguno|ninguna|ningun|cancela|cancelar|nada|olvidalo|dejalo|mejor no)$/.test(t)) { aclaracion = null; return "Vale, no cambié nada."; }
        let elegidos = null;
        const n = numeroOpcion(t);
        if (n && n >= 1 && n <= grupo.length) elegidos = [grupo[n - 1]];
        else if (grupo.length === 1 && /^(si|sip|ese|esa|eso|correcto|exacto|dale|claro|ok|vale)\b/.test(t)) elegidos = [grupo[0]];
        else if (n) return `¿Cuál? Elige del 1 al ${grupo.length}.`;
        else if (/^(los dos|las dos|ambos|ambas)\b/.test(t)) {
          if (grupo.length !== 2) return `Son ${grupo.length}, no dos. Dime el número.`;
          elegidos = grupo;
        } else if (/^(todos|todas)\b/.test(t)) elegidos = grupo;
        else {
          const dicho = sinRelleno(limpiar(t)) || t;
          const [elegido, err, opciones] = resolverNombres([dicho], grupo);
          if (opciones && opciones.length) { aclaracion = { ...aclaracion, opciones }; return err; }
          if (err || !elegido.length) return { texto: "Sigo sin saber cuál. Dime el número.", voz: "Dime el número." };
          elegidos = elegido;
        }
        aclaracion = null;
        return seguirCon(pausa, pend.accion, [...(pausa.previos || []), ...elegidos.filter((p) => !(pausa.previos || []).some((q) => String(q.id) === String(p.id)))]);
      }
      aclaracion = null;
      if (orden.accion === "no") {
        if (SUELTO.test(normalizar(texto))) return NADA_PENDIENTE;      // «sí» o «no» sin nada pendiente
        // un nombre de la lista sin decir qué hacer: se pregunta en vez de «No entendí»
        let inferida = null;
        try {
          const lista = await Promise.resolve(ctx.personas());
          inferida = lista && lista.length ? inferirDeLista(texto, lista) : null;
        } catch { inferida = null; }
        if (inferida) orden = inferida;
        else {
          // las reglas no entendieron: solo aquí se pregunta al respaldo (lo común sigue siendo al instante)
          if (!respaldo) return NO_ENTENDI;
          pensando(true);
          let otra = null;
          try { otra = await preguntarRespaldo(texto); }
          finally { pensando(false); }
          if (!otra) return NO_ENTENDI;
          orden = otra;
        }
      }
      return ejecutar(orden, texto);
    }

    function olvidar() { aclaracion = null; porConfirmar = null; porEstado = null; ultimoElegidos = []; ultimoCtx = null; }
    dialogoActual = { turno, olvidar };
    return dialogoActual;
  }

  /* Botón flotante abajo a la derecha (tipo WhatsApp). Tras el login, en cualquier página. */
  function montar(opciones) {
    if (opciones) contexto(opciones);
    if (document.getElementById("chat-asistente")) return;
    let ocupado = false;
    let hablando = false;
    let parpadeo = false;
    let mirada = "ojos_centro";
    let abierto = false;

    // Se cargan todas las caras de una vez: al mover el ratón no hay parpadeos blancos.
    const precarga = ["reposo", "ojos_centro", ...MIRADAS.map(([n]) => n), "ojos_blink",
      "hablar_a", "hablar_e", "hablar_i", "hablar_o", "hablar_u"].map((n) => {
      const im = new Image();
      im.decoding = "async";
      im.src = sprite(n);
      return im;
    });

    const burbuja = document.createElement("button");
    burbuja.type = "button";
    burbuja.className = "chat-burbuja";
    burbuja.setAttribute("aria-label", "Abrir el asistente");
    burbuja.setAttribute("aria-expanded", "false");
    /* Cada cara son dos fotos encimadas: la nueva aparece encima con un fundido corto
       (al mirar a otro lado). Al hablar y parpadear se cambia al instante, como antes. */
    function capas(clase) {
      const hacer = (extra) => {
        const im = document.createElement("img");
        im.src = sprite("reposo");
        im.alt = "";
        im.draggable = false;
        im.decoding = "async";
        im.className = (clase ? clase + " " : "") + "cara-capa" + extra;
        return im;
      };
      const a = hacer(" cara-capa-a");
      const b = hacer(" cara-capa-b");
      b.style.opacity = "0";
      return { a, b, frente: a, timer: 0 };
    }
    const fotosBurbuja = capas("");
    const fotoBurbuja = fotosBurbuja.a;
    burbuja.append(fotosBurbuja.a, fotosBurbuja.b);

    // Globito al lado del botón cuando el chat está cerrado (p. ej. «Entraste a la lista …»).
    const aviso = document.createElement("button");
    aviso.type = "button";
    aviso.className = "chat-aviso";
    aviso.hidden = true;

    const cabeza = document.createElement("div");
    cabeza.className = "chat-cabeza";
    const cara = document.createElement("div");
    cara.className = "asistente-cara";
    cara.setAttribute("aria-hidden", "true");
    const fotos = capas("asistente-foto");
    const foto = fotos.a;
    cara.append(fotos.a, fotos.b);
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
    burbujaTexto("bot", "Hola. Escribe o habla: «pon a Ana presente».");
    const caja = document.createElement("input");
    caja.className = "chat-caja";
    caja.type = "text";
    caja.placeholder = "Escribe un mensaje";
    caja.setAttribute("aria-label", "Escribir mensaje");
    caja.enterKeyHint = "send";
    const enviar = document.createElement("button");
    enviar.type = "submit";
    enviar.className = "chat-enviar chat-redondo";
    enviar.setAttribute("aria-label", "Enviar");
    enviar.title = "Enviar";
    enviar.append(iconoSvg(ICONO_ENVIAR));
    enviar.hidden = true;
    const mic = document.createElement("button");
    mic.type = "button";
    mic.className = "chat-mic chat-redondo";
    mic.setAttribute("aria-label", "Mandar audio (toca para hablar o mantén presionado)");
    mic.title = "Toca para hablar, o mantén presionado y suelta para enviar";
    mic.append(iconoSvg(ICONO_MIC));
    // Barra mientras oye: basura · punto rojo + 0:00 · ondas · enviar (como WhatsApp)
    const basura = document.createElement("button");
    basura.type = "button";
    basura.className = "chat-basura";
    basura.setAttribute("aria-label", "Cancelar audio");
    basura.title = "Cancelar";
    basura.append(iconoSvg(ICONO_BASURA));
    const punto = document.createElement("span");
    punto.className = "chat-rec-punto";
    punto.setAttribute("aria-hidden", "true");
    const reloj = document.createElement("span");
    reloj.className = "chat-rec-tiempo";
    reloj.textContent = "0:00";
    const ondas = document.createElement("span");
    ondas.className = "chat-ondas";
    ondas.setAttribute("aria-hidden", "true");
    const barras = Array.from({ length: 22 }, () => {
      const b = document.createElement("i");
      ondas.append(b);
      return b;
    });
    const deslizar = document.createElement("span");
    deslizar.className = "chat-deslizar";
    const deslizarTexto = document.createElement("span");
    deslizarTexto.textContent = "‹ Desliza para cancelar";
    deslizar.append(deslizarTexto);
    const enviarAudio = document.createElement("button");
    enviarAudio.type = "button";
    enviarAudio.className = "chat-enviar chat-redondo";
    enviarAudio.setAttribute("aria-label", "Enviar audio");
    enviarAudio.title = "Enviar";
    enviarAudio.append(iconoSvg(ICONO_ENVIAR));
    const grabando = document.createElement("div");
    grabando.className = "chat-grabando";
    grabando.setAttribute("role", "status");
    grabando.setAttribute("aria-label", "Oyendo");
    grabando.hidden = true;
    grabando.append(basura, punto, reloj, ondas, deslizar, enviarAudio);
    const form = document.createElement("form");
    form.className = "chat-barra";
    form.append(caja, enviar, mic, grabando);
    const pintarBotones = () => {
      const hay = !!caja.value.trim();
      enviar.hidden = !hay;
      mic.hidden = hay;
    };
    caja.addEventListener("input", pintarBotones);
    const panel = document.createElement("div");
    panel.className = "chat-panel";
    panel.hidden = true;
    panel.append(cabeza, hilos, form);

    const nodo = document.createElement("aside");
    nodo.id = "chat-asistente";
    nodo.className = "chat-flotante";
    nodo.append(panel, aviso, burbuja);
    document.body.append(nodo);

    const FUNDIDO_MS = 130;
    function ponerFoto(par, url, suave, ms = FUNDIDO_MS) {
      const actual = par.frente;
      if (actual.getAttribute("src") === url) return;     // misma cara: no se vuelve a pedir
      const otra = actual === par.a ? par.b : par.a;
      clearTimeout(par.timer);
      if (!suave || reducir) {
        actual.src = url;
        actual.style.transition = "none";
        actual.style.opacity = "1";
        otra.style.transition = "none";
        otra.style.opacity = "0";
        return;
      }
      // la nueva entra encima (opacidad 0 → 1); la de abajo se queda entera: no se ve el fondo
      otra.style.transition = "none";
      otra.style.opacity = "0";
      otra.style.zIndex = "2";
      actual.style.zIndex = "1";
      otra.src = url;
      void otra.offsetWidth;
      otra.style.transition = `opacity ${ms}ms ease-out`;
      otra.style.opacity = "1";
      par.frente = otra;
      par.timer = setTimeout(() => { actual.style.transition = "none"; actual.style.opacity = "0"; }, ms + 20);
    }

    function mostrarCara(nombre, suave, ms) {
      const url = sprite(nombre);
      if (!parpadeo) {
        ponerFoto(fotos, url, suave, ms);
        ponerFoto(fotosBurbuja, url, suave, ms);
      }
    }

    /* Boca: sigue una línea de tiempo sacada del texto (vocales, m/b/p cerradas, pausas en comas
       y puntos). Si el navegador avisa por qué palabra va (onboundary), se re-sincroniza ahí. */
    let boca = null;            // { pasos, k, desde, raf }
    function callar() {
      clearInterval(timerBoca);
      if (boca) cancelAnimationFrame(boca.raf);
      boca = null;
      hablando = false;
      cara.dataset.modo = "";
      mostrarCara(mirada, true, 90);
    }

    function animarBoca(texto) {
      clearInterval(timerBoca);
      if (boca) cancelAnimationFrame(boca.raf);
      const pasos = lineaBoca(texto);
      if (pasos.length < 2) { callar(); return; }
      hablando = true;
      cara.dataset.modo = "habla";
      boca = { pasos, k: -1, desde: performance.now(), raf: 0, sigue: true };
      const tic = (ahora) => {
        if (!boca) return;
        let t = ahora - boca.desde;
        let k = 0;
        while (k < boca.pasos.length && t >= boca.pasos[k].ms) { t -= boca.pasos[k].ms; k++; }
        if (k >= boca.pasos.length) {
          if (!boca.sigue) { callar(); return; }
          // la voz va más lenta que lo calculado: repite suave la última palabra hasta que termine
          boca.desde = ahora - boca.pasos.slice(0, Math.max(0, boca.pasos.length - 4)).reduce((x, p) => x + p.ms, 0);
          k = Math.max(0, boca.pasos.length - 4);
        }
        if (k !== boca.k) {
          boca.k = k;
          mostrarCara(boca.pasos[k].cara, true, 55);
        }
        boca.raf = requestAnimationFrame(tic);
      };
      boca.raf = requestAnimationFrame(tic);
    }

    function sincronizar(indice) {
      if (!boca) return;
      const k = boca.pasos.findIndex((p) => p.i >= indice);
      if (k < 0) return;
      boca.desde = performance.now() - boca.pasos.slice(0, k).reduce((x, p) => x + p.ms, 0);
    }

    function decir(r) {
      const texto = paraVoz(r);
      animarBoca(texto);
      const voz = raiz.speechSynthesis;
      if (!voz || !texto || typeof SpeechSynthesisUtterance === "undefined") { if (boca) boca.sigue = false; return; }
      voz.cancel();
      const frase = new SpeechSynthesisUtterance(texto);
      frase.lang = "es-CO";
      frase.rate = 1.05;
      const elegida = voz.getVoices().find((v) => v.lang && v.lang.toLowerCase().startsWith("es"));
      if (elegida) frase.voice = elegida;
      frase.onstart = () => { if (boca) boca.desde = performance.now(); };
      frase.onboundary = (ev) => { if (typeof ev.charIndex === "number") sincronizar(ev.charIndex); };
      frase.onend = callar;
      frase.onerror = callar;
      try { voz.speak(frase); } catch { if (boca) boca.sigue = false; }   // sin voz: la boca termina sola
    }

    function callarVoz() {
      try { if (raiz.speechSynthesis) raiz.speechSynthesis.cancel(); } catch { /* nada */ }
      if (hablando) callar();
    }

    function abrir(si) {
      abierto = !!si;
      panel.hidden = !abierto;
      burbuja.hidden = abierto;
      burbuja.setAttribute("aria-expanded", String(abierto));
      if (abierto) {
        aviso.hidden = true;
        burbuja.classList.remove("con-aviso");
        caja.focus();
      }
      pedirCuadro();          // la cara cambió de sitio (botón ↔ panel): vuelve a apuntar al ratón
    }

    /* Mirada que sigue al ratón en toda la página.
       - El punto al que mira se suaviza cuadro a cuadro (requestAnimationFrame): sin saltos.
       - Zona muerta e histéresis: cerca de la cara mira al frente y no tiembla entre dos caras.
       - La foto gira y se mueve un poco hacia el ratón (como si moviera la cabeza).
       - Solo trabaja mientras el ratón se mueve; quieto no gasta nada. */
    const reducir = !!(raiz.matchMedia && raiz.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const objetivo = { x: null, y: null };
    const suave = { x: 0, y: 0 };

    function centroCara() {
      const r = (abierto ? cara : burbuja).getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, lado: Math.max(24, r.width || 0) };
    }

    function elegirMirada(dx, dy, lado) {
      const zona = Math.max(30, lado * 0.7);
      const dist = Math.hypot(dx, dy);
      if (mirada === "ojos_centro" ? dist < zona * 1.2 : dist < zona * 0.8) return "ojos_centro";
      const ang = Math.atan2(dy, dx) * 180 / Math.PI;
      const actual = MIRADAS.find(([n]) => n === mirada);
      if (actual && difAngulo(ang, actual[1]) < 22.5 + 9) return mirada;     // histéresis: no tiembla en el borde
      let mejor = MIRADAS[0];
      for (const m of MIRADAS) if (difAngulo(ang, m[1]) < difAngulo(ang, mejor[1])) mejor = m;
      return mejor[0];
    }

    function girarCabeza() {
      if (reducir) return;
      const d = Math.hypot(suave.x, suave.y);
      const fuerza = Math.min(1, d / 320);
      const gx = d ? (suave.x / d) * fuerza : 0;
      const gy = d ? (suave.y / d) * fuerza : 0;
      const t = `translate3d(${(gx * 4).toFixed(2)}px, ${(gy * 3).toFixed(2)}px, 0) rotate(${(gx * 6).toFixed(2)}deg) scale(1.06)`;
      for (const im of [fotos.a, fotos.b, fotosBurbuja.a, fotosBurbuja.b]) im.style.transform = t;
    }

    function cuadroMirada() {
      cuadro = 0;
      if (!nodo.isConnected) return;
      const c = centroCara();
      const tx = objetivo.x === null ? 0 : objetivo.x - c.x;
      const ty = objetivo.y === null ? 0 : objetivo.y - c.y;
      const k = reducir ? 1 : 0.2;
      suave.x += (tx - suave.x) * k;
      suave.y += (ty - suave.y) * k;
      const nueva = elegirMirada(suave.x, suave.y, c.lado);
      if (nueva !== mirada) {
        mirada = nueva;
        if (!hablando && !parpadeo) mostrarCara(mirada, true);
      }
      girarCabeza();
      if (Math.abs(tx - suave.x) > 0.6 || Math.abs(ty - suave.y) > 0.6) cuadro = requestAnimationFrame(cuadroMirada);
    }

    function pedirCuadro() {
      if (!cuadro) cuadro = requestAnimationFrame(cuadroMirada);
    }

    oirRaton = (ev) => {
      objetivo.x = ev.clientX;
      objetivo.y = ev.clientY;
      pedirCuadro();
    };
    soltarRaton = (ev) => {
      if (ev.relatedTarget) return;      // sigue dentro de la página
      objetivo.x = null;                 // salió de la ventana: vuelve a mirar al frente
      objetivo.y = null;
      pedirCuadro();
    };
    document.addEventListener("pointermove", oirRaton, { passive: true });
    document.addEventListener("pointerdown", oirRaton, { passive: true });
    document.addEventListener("mouseout", soltarRaton);
    girarCabeza();
    timerParpadeo = setInterval(() => {
      if (!nodo.isConnected || hablando) return;
      parpadeo = true;
      const url = sprite("ojos_blink");
      ponerFoto(fotos, url, false);
      ponerFoto(fotosBurbuja, url, false);
      setTimeout(() => {
        parpadeo = false;
        if (!hablando) mostrarCara(mirada);
      }, 140);
    }, 3800);

    function mostrar(r) {
      if (!r) return;     // p. ej. al entrar a una lista: el aviso llega solo
      burbujaTexto("bot", paraTexto(r)).dataset.fijo = "1";
      decir(r);
    }

    function avisarAqui(r) {
      const texto = paraTexto(r);
      burbujaTexto("bot", texto).dataset.fijo = "1";
      if (abierto) { decir(r); return; }
      animarBoca(paraVoz(r));
      if (boca) boca.sigue = false;     // sin voz: la boca termina sola
      aviso.textContent = texto;
      aviso.hidden = false;
      burbuja.classList.add("con-aviso");
      clearTimeout(timerAviso);
      timerAviso = setTimeout(() => { aviso.hidden = true; }, 6000);
    }

    function ponerLugar(texto) {
      estadoChat.textContent = texto || "En línea";
      estadoChat.title = texto || "";
    }

    estado = { foto, fotoBurbuja, cara, caja, precarga, avisar: avisarAqui, lugar: ponerLugar };

    let escribiendo = null;
    function pensandoAqui(si) {
      if (si && !escribiendo) {
        escribiendo = document.createElement("div");
        escribiendo.className = "chat-msg chat-msg-bot chat-escribiendo";
        escribiendo.setAttribute("aria-label", "Escribiendo");
        for (let i = 0; i < 3; i++) escribiendo.append(document.createElement("span"));
        hilos.append(escribiendo);
        hilos.scrollTop = hilos.scrollHeight;
      } else if (!si && escribiendo) {
        escribiendo.remove();
        escribiendo = null;
      }
    }
    const dialogo = nuevoDialogo({ pensando: pensandoAqui });
    const turno = (texto) => dialogo.turno(texto);

    burbuja.addEventListener("click", () => abrir(true));
    aviso.addEventListener("click", () => abrir(true));
    cerrar.addEventListener("click", () => abrir(false));
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const texto = caja.value.trim();
      if (!texto || ocupado) return;
      ocupado = true;
      caja.value = "";
      pintarBotones();
      burbujaTexto("yo", texto).dataset.fijo = "1";
      cara.dataset.modo = "oye";
      try { mostrar(await turno(texto)); }
      catch (e) { mostrar(e.message || "No pude hacerlo."); }
      if (!hablando) cara.dataset.modo = "";
      ocupado = false;
    });
    /* Micrófono estilo WhatsApp.
       - Toque: empieza a oír y queda la barra con basura (cancelar) y enviar.
       - Mantener presionado: oye mientras lo tiene; al soltar envía; deslizar a la izquierda cancela.
       - Si no toca nada, termina solo cuando deja de hablar (como antes).
       El texto que se oye pasa por el mismo camino que lo escrito. */
    let oyendo = null;          // { control, inicio, timer, medidor }
    let mantener = null;        // { x, t, id } mientras se mantiene presionado

    /* Las ondas se mueven solas y suben cuando el navegador detecta voz (onspeechstart).
       No se abre el micrófono una segunda vez: así no le quita el audio al reconocimiento. */
    function medirVoz() {
      return { parar() { grabando.classList.remove("con-voz"); } };
    }

    function pintarReloj() {
      if (!oyendo) return;
      const s = Math.floor((Date.now() - oyendo.inicio) / 1000);
      reloj.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }

    function terminarOido() {
      if (!oyendo) return;
      clearInterval(oyendo.timer);
      oyendo.medidor.parar();
      oyendo = null;
      grabacion = null;
      mantener = null;
      form.classList.remove("grabando", "manteniendo");
      grabando.hidden = true;
      grabando.style.removeProperty("--arrastre");
      mic.classList.remove("escuchando");
      reloj.textContent = "0:00";
      pintarBotones();
    }

    async function empezarOido(conMantener) {
      if (ocupado || oyendo) return;
      ocupado = true;
      abrir(true);
      callarVoz();                 // que el asistente no hable encima (ni se oiga a sí mismo)
      const control = escuchar((hay) => grabando.classList.toggle("con-voz", hay));
      oyendo = { control, inicio: Date.now(), timer: 0, medidor: { parar() {} } };
      grabacion = () => control.cancelar();
      cara.dataset.modo = "oye";
      mic.classList.add("escuchando");
      form.classList.add("grabando");
      form.classList.toggle("manteniendo", !!conMantener);
      grabando.hidden = false;
      reloj.textContent = "0:00";
      oyendo.timer = setInterval(pintarReloj, 250);
      oyendo.medidor = medirVoz();
      try {
        const texto = await control.promesa;
        const duro = Date.now() - oyendo.inicio;
        terminarOido();
        if (texto === null) { /* cancelado: sin mensaje */ }
        else if (!texto) {
          // muy corto = el micrófono no alcanzó a arrancar; si no, de verdad no se oyó nada
          burbujaTexto("bot", duro < 1200 ? "El micrófono no arrancó. Toca otra vez." : "No te oí. Intenta otra vez.").dataset.fijo = "1";
        } else {
          burbujaTexto("yo", texto).dataset.fijo = "1";
          mostrar(await turno(texto));
        }
      } catch (e) {
        terminarOido();
        mostrar(e.message === "sin_oido" ? "Este navegador no reconoce voz. Escríbelo." : (e.message || "No te oí."));
      }
      if (!hablando) cara.dataset.modo = "";
      ocupado = false;
    }

    function enviarOido() { if (oyendo) oyendo.control.enviar(); }
    function cancelarOido() { if (oyendo) oyendo.control.cancelar(); }

    mic.addEventListener("pointerdown", (ev) => {
      if (ev.button !== undefined && ev.button !== 0) return;
      if (ocupado || oyendo) return;
      ev.preventDefault();
      mantener = { x: ev.clientX, t: Date.now(), id: ev.pointerId };
      try { mic.setPointerCapture(ev.pointerId); } catch { /* nada */ }
      empezarOido(true);
    });
    mic.addEventListener("pointermove", (ev) => {
      if (!mantener || !oyendo || ev.pointerId !== mantener.id) return;
      const dx = Math.min(0, ev.clientX - mantener.x);
      grabando.style.setProperty("--arrastre", `${Math.max(-120, dx)}px`);
      if (dx < -90) { mantener = null; cancelarOido(); }
    });
    const soltar = (ev) => {
      if (!mantener || ev.pointerId !== mantener.id) return;
      const largo = Date.now() - mantener.t;
      mantener = null;
      form.classList.remove("manteniendo");
      grabando.style.removeProperty("--arrastre");
      if (ev.type === "pointercancel") return;     // el navegador se lo quitó: queda la barra con sus botones
      if (largo > 450) enviarOido();               // lo mantuvo presionado: al soltar se envía
      // toque corto: sigue oyendo, con la barra de basura y enviar (como WhatsApp con el candado)
    };
    mic.addEventListener("pointerup", soltar);
    mic.addEventListener("pointercancel", soltar);
    mic.addEventListener("click", (ev) => {
      // teclado (Enter/Espacio) o lectores de pantalla: no pasan por pointerdown
      if (ev.detail === 0 && !oyendo) empezarOido(false);
    });
    mic.addEventListener("contextmenu", (ev) => ev.preventDefault());
    mic.addEventListener("touchend", (ev) => ev.preventDefault(), { passive: false });   // sin «clic fantasma» al soltar
    // En el celular, el clic que sigue al toque cae donde estaba el micrófono (ahora el botón enviar):
    // los botones de la barra no hacen caso al primer medio segundo.
    const recien = () => !oyendo || Date.now() - oyendo.inicio < 500;
    basura.addEventListener("click", () => { if (!recien()) cancelarOido(); });
    enviarAudio.addEventListener("click", () => { if (!recien()) enviarOido(); });
  }

  raiz.Asistente = { normalizar, interpretar, alInterpretar, ordenDeRespaldo, resolverNombres, aproximados, numeroOpcion, lineaBoca, paraVoz, montar, contexto, quitar, alEntrar, avisar, lugar, AYUDA,
    esSi, esNo, preguntaEliminar, preguntaEstado, estadoDeRespuesta, nuevoDialogo };
})(typeof window !== "undefined" ? window : globalThis);
