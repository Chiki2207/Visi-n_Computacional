/* Pruebas del chat (solo el entendimiento de nombres y la boca; no toca la IA ni el servidor).
   Correr:  node web/frontend/prueba_asistente.js
   Este archivo no lo sirve la página: es solo para revisar antes de subir cambios. */
"use strict";
const assert = require("assert");
const path = require("path");
require(path.join(__dirname, "asistente.js"));
const A = globalThis.Asistente;

const LISTA = [
  { id: "E001", nombre: "Ana María Pérez Gómez" },
  { id: "E002", nombre: "Luis Enrique Avendaño Ortiz" },
  { id: "E003", nombre: "Carlos Andrés Avendaño Ortiz" },      // hermano: mismos apellidos
  { id: "E004", nombre: "Luis Fernando Rojas" },               // mismo primer nombre
  { id: "E005", nombre: "Ana Lucía Pérez Gómez" },             // hermana: mismos apellidos
  { id: "E006", nombre: "Juan Pablo Muñoz" },
  { id: "E007", nombre: "Valentina Zuluaga Henao" },
];

let ok = 0, mal = 0;
function prueba(nombre, fn) {
  try { fn(); ok++; console.log("  ok   " + nombre); }
  catch (e) { mal++; console.log("  MAL  " + nombre + "\n       " + e.message); }
}
function resolver(frase, lista = LISTA) {
  const orden = A.interpretar(frase);
  const [elegidos, err, opciones] = A.resolverNombres(orden.nombres, lista);
  return { ids: elegidos.map((p) => p.id), err, opciones: opciones.map((p) => p.id), orden };
}
const textoDe = (r) => (r && typeof r === "object" ? r.texto : r) || "";

console.log("Nombres mal oídos:");
prueba("«Luis Enrique araña Ortiz» marca a Luis Enrique Avendaño Ortiz (el caso real)", () => {
  const r = resolver("ponme a Luis Enrique araña Ortiz como presente");
  assert.deepStrictEqual(r.ids, ["E002"]);
  assert.strictEqual(r.orden.accion, "presente");
});
prueba("«Carlos Andrés araña Ortiz» marca al hermano correcto, no a Luis", () => {
  assert.deepStrictEqual(resolver("pon a carlos andres arana ortiz presente").ids, ["E003"]);
});
prueba("«luiz enrrique avendano» (mal escrito) marca a E002", () => {
  assert.deepStrictEqual(resolver("pon a luiz enrrique avendano presente").ids, ["E002"]);
});
prueba("«Valentina Suluaga» (z por s) marca a E007", () => {
  assert.deepStrictEqual(resolver("pon a valentina suluaga presente").ids, ["E007"]);
});
prueba("«Juan Pablo Muños» marca a E006", () => {
  assert.deepStrictEqual(resolver("quita a juan pablo muños").ids, ["E006"]);
});

console.log("Nunca marca al equivocado:");
prueba("«Avendaño Ortiz» (los dos hermanos) pregunta ¿Cuál? sin marcar", () => {
  const r = resolver("pon a avendaño ortiz presente");
  assert.deepStrictEqual(r.ids, []);
  assert.deepStrictEqual(r.opciones.sort(), ["E002", "E003"]);
  assert.match(textoDe(r.err), /^¿Cuál\? 1\) .+ 2\) /);
});
prueba("«Ana Pérez» (dos hermanas) pregunta", () => {
  const r = resolver("pon a ana perez presente");
  assert.deepStrictEqual(r.ids, []);
  assert.deepStrictEqual(r.opciones.sort(), ["E001", "E005"]);
});
prueba("«Luis» (nombre compartido) pregunta entre los dos Luis", () => {
  const r = resolver("pon a luis presente");
  assert.deepStrictEqual(r.ids, []);
  assert.deepStrictEqual(r.opciones.sort(), ["E002", "E004"]);
});
prueba("«Luis Fernando Ortiz» (mezcla de dos) no marca a nadie, pregunta", () => {
  const r = resolver("pon a luis fernando ortiz presente");
  assert.deepStrictEqual(r.ids, []);
  assert.ok(r.opciones.length >= 1);
});
prueba("«Luis Enrique araña» (solo 2 palabras seguras) pide confirmar, no marca", () => {
  const r = resolver("pon a luis enrique araña presente");
  assert.deepStrictEqual(r.ids, []);
  assert.deepStrictEqual(r.opciones, ["E002"]);
  assert.match(textoDe(r.err), /^¿Es Luis Enrique Avendaño Ortiz\?/);
});
prueba("«Pedro Pérez» (no existe) dice que no lo encontró", () => {
  const r = resolver("pon a pedro perez presente");
  assert.deepStrictEqual(r.ids, []);
  assert.deepStrictEqual(r.opciones, []);
  assert.match(textoDe(r.err), /^No encontré a «pedro perez»/);
});
prueba("«Ana Lucía Pérez» exacto marca solo a E005", () => {
  assert.deepStrictEqual(resolver("pon a ana lucia perez presente").ids, ["E005"]);
});
prueba("con el código E004 marca a E004", () => {
  assert.deepStrictEqual(resolver("pon a E004 presente").ids, ["E004"]);
});
prueba("en una lista con un solo Luis, «Luis Enrique araña Ortiz» sigue siendo E002", () => {
  assert.deepStrictEqual(resolver("pon a luis enrique araña ortiz presente", LISTA.filter((p) => p.id !== "E004")).ids, ["E002"]);
});

console.log("Respuestas a ¿Cuál?:");
prueba("acepta número, palabra u ordinal", () => {
  for (const [t, n] of [["1", 1], ["el 2", 2], ["dos", 2], ["el segundo", 2], ["primero", 1], ["la tres", 3], ["opción 2", 2]]) {
    assert.strictEqual(A.numeroOpcion(t), n, t);
  }
  assert.strictEqual(A.numeroOpcion("Luis Fernando"), null);
});
prueba("un «no» solo es responder no (no es «entra a la lista»)", () => {
  assert.strictEqual(A.interpretar("no").accion, "no");
  assert.strictEqual(A.interpretar("entra a la lista no 4821").codigo, "4821");
});
prueba("«los dos» sigue siendo los dos (no la opción 2)", () => {
  assert.strictEqual(A.numeroOpcion("los dos"), null);
});

console.log("Mensajes y boca:");
prueba("la voz no lee códigos E002 ni comillas", () => {
  assert.strictEqual(A.paraVoz("Listo. Ana (E002) quedó presente."), "Listo. Ana quedó presente.");
  assert.strictEqual(A.paraVoz({ texto: "largo", voz: "corto" }), "corto");
});
prueba("ayuda corta", () => {
  assert.ok(A.AYUDA.texto.length <= 110 && A.AYUDA.voz.length <= 70);
});
prueba("boca: vocales abren, m/b/p y puntos cierran, termina cerrada", () => {
  const pasos = A.lineaBoca("Hola, mamá.");
  assert.ok(pasos.some((p) => p.cara === "hablar_o"));
  assert.ok(pasos.some((p) => p.cara === "hablar_a"));
  assert.strictEqual(pasos[pasos.length - 1].cara, "reposo");
  for (let i = 1; i < pasos.length; i++) assert.notStrictEqual(pasos[i].cara, pasos[i - 1].cara);
  assert.ok(pasos.every((p) => p.ms >= 30));
});

console.log("Eliminar estudiantes:");
prueba("«elimina a Juan Pablo Muñoz», «borra al estudiante…», «saca a … de la clase» son eliminar", () => {
  for (const f of ["elimina a Juan Pablo Muñoz", "borra al estudiante juan pablo muñoz", "saca a juan pablo muñoz de la clase",
    "saca a juan pablo muñoz de la lista", "por favor elimina al alumno Juan Pablo Muñoz", "quiero eliminar a juan pablo muñoz",
    "borra a juan pablo muñoz de la clase computacional 2", "puedes borrar a Juan Pablo Muñoz?"]) {
    const r = resolver(f);
    assert.strictEqual(r.orden.accion, "quitar", f);
    assert.deepStrictEqual(r.ids, ["E006"], f);
  }
});
prueba("eliminar con nombre mal oído: «elimina a Luis Enrique araña Ortiz» es E002", () => {
  const r = resolver("elimina a Luis Enrique araña Ortiz");
  assert.strictEqual(r.orden.accion, "quitar");
  assert.deepStrictEqual(r.ids, ["E002"]);
});
prueba("«eliminar» en otras cosas no es eliminar un estudiante", () => {
  for (const f of ["borra la lista", "elimina esta lista", "borra la foto", "elimina eso", "borra el chat", "elimina el historial",
    "borra todo", "como elimino una lista", "no elimines a juan pablo muñoz", "no", "no borres nada", "eliminar"]) {
    assert.notStrictEqual(A.interpretar(f).accion, "quitar", f);
  }
  assert.strictEqual(A.interpretar("elimina a un estudiante").accion, "falta_nombre");
  assert.strictEqual(A.interpretar("quita a juan pablo muñoz").accion, "ausente");     // como antes: ausente
  assert.strictEqual(A.interpretar("borra el presente de juan pablo muñoz").accion, "ausente");
});
prueba("sí / no de la confirmación", () => {
  for (const t of ["sí", "Si.", "sí, elimínalo", "dale", "claro que sí", "confirmo", "vale", "sí señor", "ok"]) assert.ok(A.esSi(t), t);
  for (const t of ["no", "si no", "sino", "elimina a ana", "tal vez", "", "nose", "1"]) assert.ok(!A.esSi(t), t);
  for (const t of ["no", "No, mejor no", "cancela", "nada", "olvídalo"]) assert.ok(A.esNo(t), t);
  assert.strictEqual(textoDe(A.preguntaEliminar([LISTA[1]], "Clase X")), "¿Elimino a Luis Enrique Avendaño Ortiz de Clase X? (sí / no)");
});

/* Conversación completa con una página de mentira (no llama a ningún servidor). */
function conversacion() {
  const hechos = [];
  A.contexto({
    personas: async () => LISTA,
    actuar: async (p) => { hechos.push(p); return p.accion === "quitar" ? `Listo. Eliminé a ${p.elegidos.map((x) => x.nombre).join(" y ")}.` : "ok"; },
    donde: () => "Clase X",
  });
  return { d: A.nuevoDialogo(), hechos };
}
async function pruebaAsync(nombre, fn) {
  try { await fn(); ok++; console.log("  ok   " + nombre); }
  catch (e) { mal++; console.log("  MAL  " + nombre + "\n       " + e.message); }
}

(async () => {
  await pruebaAsync("pregunta antes de eliminar y solo elimina con «sí»", async () => {
    const { d, hechos } = conversacion();
    assert.strictEqual(textoDe(await d.turno("elimina a Juan Pablo Muñoz")), "¿Elimino a Juan Pablo Muñoz de Clase X? (sí / no)");
    assert.strictEqual(hechos.length, 0);
    assert.match(textoDe(await d.turno("sí")), /^Listo\. Eliminé a Juan Pablo Muñoz/);
    assert.strictEqual(hechos.length, 1);
    assert.deepStrictEqual(hechos[0].elegidos.map((p) => p.id), ["E006"]);
    await d.turno("sí");                                     // un segundo «sí» no repite nada
    assert.strictEqual(hechos.length, 1);
  });
  await pruebaAsync("«no» cancela y no elimina", async () => {
    const { d, hechos } = conversacion();
    await d.turno("borra a juan pablo muñoz");
    assert.strictEqual(textoDe(await d.turno("no")), "Vale, no eliminé a nadie.");
    await d.turno("sí");
    assert.strictEqual(hechos.length, 0);
  });
  await pruebaAsync("otra orden en vez de «sí» olvida la pregunta", async () => {
    const { d, hechos } = conversacion();
    await d.turno("elimina a juan pablo muñoz");
    await d.turno("pon a valentina zuluaga presente");
    await d.turno("sí");
    assert.deepStrictEqual(hechos.map((h) => h.accion), ["presente"]);
  });
  await pruebaAsync("dos parecidos: «¿Cuál?», luego el número, luego confirmar", async () => {
    const { d, hechos } = conversacion();
    assert.match(textoDe(await d.turno("elimina a avendaño ortiz")), /^¿Cuál\? 1\)/);
    assert.match(textoDe(await d.turno("2")), /^¿Elimino a .+ de Clase X\? \(sí \/ no\)$/);
    assert.strictEqual(hechos.length, 0);
    await d.turno("dale");
    assert.strictEqual(hechos.length, 1);
    assert.strictEqual(hechos[0].elegidos.length, 1);
  });
  await pruebaAsync("nombre dudoso: una sola pregunta «¿Elimino a …?»", async () => {
    const { d, hechos } = conversacion();
    assert.strictEqual(textoDe(await d.turno("elimina a luis enrique araña")), "¿Elimino a Luis Enrique Avendaño Ortiz de Clase X? (sí / no)");
    await d.turno("no");
    assert.strictEqual(hechos.length, 0);
  });
  await pruebaAsync("cambiar de clase olvida la pregunta pendiente", async () => {
    const { d, hechos } = conversacion();
    await d.turno("elimina a juan pablo muñoz");
    A.contexto({ personas: async () => LISTA, actuar: async (p) => { hechos.push(p); return "ok"; } });
    await d.turno("sí");
    assert.strictEqual(hechos.length, 0);
  });
  await pruebaAsync("fuera de una clase pregunta de cuál", async () => {
    const hechos = [];
    A.contexto({ personas: async () => [], actuar: async (p) => { hechos.push(p); return "¿De qué clase? Ábrela o dime su código."; } });
    const d = A.nuevoDialogo();
    assert.match(textoDe(await d.turno("elimina a juan")), /^¿De qué clase\?/);
    assert.ok(hechos.every((h) => !h.elegidos || !h.elegidos.length));
  });


  /* Lista con Ana Sofía, como en el caso real. No se usa en las pruebas anteriores
     para no mezclar «Ana Pérez» (dos hermanas) con una tercera Ana. */
  const LISTA_CLASE = LISTA.concat([{ id: "E008", nombre: "Ana Sofía Pérez Ortega" }]);
  function conversacionClase() {
    const hechos = [];
    A.alInterpretar(null);
    A.contexto({
      personas: async () => LISTA_CLASE,
      actuar: async (p) => {
        hechos.push(p);
        if (p.accion === "presente" || p.accion === "ausente") {
          const n = p.elegidos.map((x) => x.nombre).join(" y ");
          const quedo = p.elegidos.length > 1 ? "quedaron" : "quedó";
          return `Listo. ${n} ${quedo} ${p.accion}.`;
        }
        if (p.accion === "agregar") return "agregar:" + p.nombre;
        if (p.accion === "pasar") return "pasar";
        return "ok";
      },
      donde: () => "Clase X",
    });
    return { d: A.nuevoDialogo(), hechos };
  }
  async function turnoClase(frase, dPrev) {
    const ctx = dPrev ? dPrev : conversacionClase();
    const resp = textoDe(await ctx.d.turno(frase));
    return { resp, hechos: ctx.hechos, d: ctx.d, ctx };
  }

  console.log("\nPresente y ausente (camino real del chat, sin Gemini):");
  await pruebaAsync("el caso que falló en vivo: «Ponme como ausente Ana Sofía» marca ausente", async () => {
    for (const f of [
      "Ponme como presente a Ana Sofía",
      "Ponme como ausente Ana Sofía",
      "Ponme como ausente Ana Sofía",
      "Ponme como ausente de Ana Sofía",
    ]) {
      const { resp, hechos } = await turnoClase(f);
      const esperada = /presente/i.test(f) ? "presente" : "ausente";
      assert.strictEqual(hechos.length, 1, f + " → " + resp);
      assert.strictEqual(hechos[0].accion, esperada, f);
      assert.deepStrictEqual(hechos[0].elegidos.map((p) => p.id), ["E008"], f);
      if (esperada === "ausente") assert.match(resp, /quedó ausente/);
      else assert.match(resp, /quedó presente/);
    }
  });

  const CASOS = [];
  const verbos = ["ponme", "pon", "pónme", "pongame", "márcame", "marca", "coloca", "deja", "registra"];
  const preps = ["", "a ", "de ", "al ", "la "];
  for (const v of verbos) {
    for (const estado of ["presente", "ausente"]) {
      for (const prep of preps) {
        CASOS.push([`${v} como ${estado} ${prep}Ana Sofía`, estado, ["E008"]]);
        CASOS.push([`${v} a Ana Sofía como ${estado}`, estado, ["E008"]]);
        CASOS.push([`${v} ${estado} ${prep}Ana Sofía`, estado, ["E008"]]);
      }
    }
  }
  const SUELTAS = [
    ["ponme ausente a Ana Sofía", "ausente", ["E008"]],
    ["ponme presente a Ana Sofía", "presente", ["E008"]],
    ["Ana Sofía ausente", "ausente", ["E008"]],
    ["Ana Sofía presente", "presente", ["E008"]],
    ["ana sofia ausente", "ausente", ["E008"]],
    ["ana sofia presente", "presente", ["E008"]],
    ["Ana Sofía está ausente", "ausente", ["E008"]],
    ["Ana Sofía esta presente", "presente", ["E008"]],
    ["Ana Sofía no está", "ausente", ["E008"]],
    ["Ana Sofía no esta", "ausente", ["E008"]],
    ["Ana Sofía no vino", "ausente", ["E008"]],
    ["ana sofia no vino", "ausente", ["E008"]],
    ["Ana Sofía faltó", "ausente", ["E008"]],
    ["Ana Sofía falto", "ausente", ["E008"]],
    ["falta Ana Sofía", "ausente", ["E008"]],
    ["falta ana sofia", "ausente", ["E008"]],
    ["ponle falta a Ana Sofía", "ausente", ["E008"]],
    ["ponle falta a ana sofia", "ausente", ["E008"]],
    ["marca inasistencia a Ana Sofía", "ausente", ["E008"]],
    ["cambia a Ana Sofía a ausente", "ausente", ["E008"]],
    ["cambia a Ana Sofía a presente", "presente", ["E008"]],
    ["pasa Ana Sofía a ausente", "ausente", ["E008"]],
    ["pasa a Ana Sofía a presente", "presente", ["E008"]],
    ["ausentes Ana Sofía y Juan Pablo", "ausente", ["E008", "E006"]],
    ["presentes Ana Sofía y Juan Pablo", "presente", ["E008", "E006"]],
    ["ponme como activo a Ana Sofía", "presente", ["E008"]],
    ["Ana Sofía activo", "presente", ["E008"]],
    ["ana sofia activa", "presente", ["E008"]],
    ["activa a Ana Sofía", "presente", ["E008"]],
    ["Ana Sofía inactivo", "ausente", ["E008"]],
    ["inactiva a Ana Sofía", "ausente", ["E008"]],
    ["ponme como inactivo a Ana Sofía", "ausente", ["E008"]],
    ["Ana Sofía está, ponla", "presente", ["E008"]],
    ["ana sofia esta ponla", "presente", ["E008"]],
    ["ya llegó Ana Sofía", "presente", ["E008"]],
    ["ya llego ana sofia", "presente", ["E008"]],
    ["Ana Sofía llegó", "presente", ["E008"]],
    ["Ana Sofía esta aquí", "presente", ["E008"]],
    ["Ana Sofía está aquí", "presente", ["E008"]],
    ["Ana Sofía sí vino", "presente", ["E008"]],
    ["ana sofia si vino", "presente", ["E008"]],
    ["Ana Sofía vino", "presente", ["E008"]],
    ["Ana Sofía asistió", "presente", ["E008"]],
    ["asistió Ana Sofía", "presente", ["E008"]],
    ["llegó Ana Sofía", "presente", ["E008"]],
    ["vino Ana Sofía", "presente", ["E008"]],
    ["Valentina no vino", "ausente", ["E007"]],
    ["falta Valentina Zuluaga", "ausente", ["E007"]],
    ["pon a valentina zuluaga como ausente", "ausente", ["E007"]],
    ["marca como ausente a valentina zuluaga", "ausente", ["E007"]],
    ["Juan Pablo Muñoz presente", "presente", ["E006"]],
    ["juan pablo munoz ausente", "ausente", ["E006"]],
    ["X no vino".replace("X", "Juan Pablo"), "ausente", ["E006"]],
  ];
  for (const c of SUELTAS) CASOS.push(c);

  await pruebaAsync("tabla de frases de asistencia por el camino real del chat", async () => {
    let n = 0;
    const vistos = new Set();
    for (const [frase, accion, ids] of CASOS) {
      const clave = frase.trim().toLowerCase() + "|" + accion;
      if (vistos.has(clave)) continue;
      vistos.add(clave);
      const { resp, hechos } = await turnoClase(frase);
      assert.strictEqual(hechos.length, 1, `«${frase}» no actuó: ${resp}`);
      assert.strictEqual(hechos[0].accion, accion, `«${frase}» → ${hechos[0].accion} (quería ${accion}): ${resp}`);
      assert.deepStrictEqual(hechos[0].elegidos.map((p) => p.id), ids, `«${frase}» ids ${hechos[0].elegidos.map((p) => p.id)} != ${ids}: ${resp}`);
      n++;
    }
    assert.ok(n >= 120, "hacen falta al menos 120 frases, van " + n);
    console.log("       (" + n + " frases distintas, todas bien)");
  });

  await pruebaAsync("«ponla» y «márcala» usan al último estudiante nombrado", async () => {
    const ctx = conversacionClase();
    const a = await turnoClase("Ponme como presente a Ana Sofía", ctx);
    assert.strictEqual(a.hechos[0].accion, "presente");
    const b = await turnoClase("ponla", ctx);
    assert.strictEqual(b.hechos.length, 2, b.resp);
    assert.strictEqual(b.hechos[1].accion, "presente");
    assert.deepStrictEqual(b.hechos[1].elegidos.map((p) => p.id), ["E008"]);
    const c = await turnoClase("márcala", ctx);
    assert.strictEqual(c.hechos[2].accion, "presente");
    const d = await turnoClase("ponla ausente", ctx);
    assert.strictEqual(d.hechos[3].accion, "ausente");
    assert.deepStrictEqual(d.hechos[3].elegidos.map((p) => p.id), ["E008"]);
  });
  await pruebaAsync("«ponla» sin nadie antes pregunta a quién, no dice «No entendí» por un nombre", async () => {
    const { resp, hechos } = await turnoClase("ponla");
    assert.strictEqual(resp, "¿A quién?");
    assert.strictEqual(hechos.length, 0);
  });
  await pruebaAsync("si solo nombra a un estudiante, pregunta presente o ausente (nunca «No entendí»)", async () => {
    const ctx = conversacionClase();
    const a = await turnoClase("Ana Sofía", ctx);
    assert.strictEqual(a.resp, "¿Qué hago con Ana Sofía Pérez Ortega: presente o ausente?");
    assert.strictEqual(a.hechos.length, 0);
    const b = await turnoClase("ausente", ctx);
    assert.strictEqual(b.hechos.length, 1);
    assert.strictEqual(b.hechos[0].accion, "ausente");
    assert.deepStrictEqual(b.hechos[0].elegidos.map((p) => p.id), ["E008"]);
  });
  await pruebaAsync("un «no» solo no marca ni elimina a nadie", async () => {
    const { resp, hechos } = await turnoClase("no");
    assert.strictEqual(resp, "No tengo nada pendiente. ¿Qué hago?");
    assert.strictEqual(hechos.length, 0);
    assert.strictEqual(A.interpretar("no").accion, "no");
  });
  await pruebaAsync("eliminar no se come las frases de ausente, ni al revés", async () => {
    const a = await turnoClase("elimina a Juan Pablo Muñoz");
    assert.match(a.resp, /^¿Elimino a Juan Pablo Muñoz/);
    assert.strictEqual(a.hechos.length, 0);
    const b = await turnoClase("quita a Juan Pablo Muñoz");
    assert.strictEqual(b.hechos[0].accion, "ausente");
    const c = await turnoClase("borra el presente de Juan Pablo Muñoz");
    assert.strictEqual(c.hechos[0].accion, "ausente");
    const d = await turnoClase("saca a Juan Pablo Muñoz de la clase");
    assert.match(d.resp, /^¿Elimino a Juan Pablo Muñoz/);
  });
  await pruebaAsync("otras órdenes siguen igual (ayuda, agregar, pasar, código)", async () => {
    const a = await turnoClase("ayuda");
    assert.match(a.resp, /presente o ausente/);
    const b = await turnoClase("agrega a Pedro Pérez");
    assert.strictEqual(b.hechos[0].accion, "agregar");
    const c = await turnoClase("pasa la lista");
    assert.strictEqual(c.hechos[0].accion, "pasar");
    const vistos = [];
    A.alEntrar(async (o) => { vistos.push(o); return null; });
    await turnoClase("4821");
    assert.deepStrictEqual(vistos, [{ codigo: "4821", nombre: "", tipo: "" }]);
    A.alEntrar(null);
  });
  await pruebaAsync("una frase sin nombre de la lista sigue en «No entendí» (sin Gemini)", async () => {
    const { resp, hechos } = await turnoClase("qué hora es en Bogotá");
    assert.strictEqual(resp, "No entendí. Escribe «ayuda» para ver qué puedo hacer.");
    assert.strictEqual(hechos.length, 0);
  });


  console.log("\nRespaldo (Gemini simulado, sin internet):");
  const NO_ENT = "No entendí. Escribe «ayuda» para ver qué puedo hacer.";
  function conRespaldo(fn) {
    const llamadas = [];
    A.alInterpretar(async (texto, nombres) => { llamadas.push({ texto, nombres }); return fn(texto, nombres); });
    return llamadas;
  }
  await pruebaAsync("lo que entienden las reglas NUNCA llama al respaldo", async () => {
    const llamadas = conRespaldo(() => ({ ok: true, accion: "ausente", nombres: ["Juan Pablo Muñoz"], confianza: 0.9 }));
    const { d, hechos } = conversacion();
    await d.turno("pon a Luis Enrique araña Ortiz presente");
    await d.turno("ayuda");
    await d.turno("4821");
    assert.strictEqual(llamadas.length, 0);
    assert.strictEqual(hechos[0].accion, "presente");
  });
  await pruebaAsync("«sí llegó» ya lo entienden las reglas, sin llamar al respaldo", async () => {
    const llamadas = conRespaldo(() => ({ ok: true, accion: "presente", nombres: ["luis enrique arana ortis"], confianza: 0.9 }));
    const { d, hechos } = conversacion();
    await d.turno("oiga profe, el Luis Enrique sí llegó, anótemelo");
    assert.strictEqual(llamadas.length, 0);
    assert.strictEqual(hechos.length, 1);
    assert.strictEqual(hechos[0].accion, "presente");
    assert.deepStrictEqual(hechos[0].elegidos.map((p) => p.id), ["E002"]);
  });
  await pruebaAsync("frase rara sin nombre de la lista: el respaldo la interpreta y el nombre pasa por el buscador real", async () => {
    const llamadas = conRespaldo(() => ({ ok: true, accion: "presente", nombres: ["luis enrique arana ortis"], confianza: 0.9 }));
    const { d, hechos } = conversacion();
    await d.turno("apúntame al de la camisa roja, porfa");
    assert.strictEqual(llamadas.length, 1);
    assert.ok(llamadas[0].nombres.includes("Luis Enrique Avendaño Ortiz"));     // se mandan los nombres de la clase
    assert.strictEqual(hechos.length, 1);
    assert.strictEqual(hechos[0].accion, "presente");
    assert.deepStrictEqual(hechos[0].elegidos.map((p) => p.id), ["E002"]);
  });
  await pruebaAsync("eliminar por el respaldo sigue pidiendo «sí / no»", async () => {
    conRespaldo(() => ({ ok: true, accion: "quitar", nombres: ["Juan Pablo Muñoz"], confianza: 0.95 }));
    const { d, hechos } = conversacion();
    assert.strictEqual(textoDe(await d.turno("ese muchacho Juan Pablo ya se retiró, bórrelo")), "¿Elimino a Juan Pablo Muñoz de Clase X? (sí / no)");
    assert.strictEqual(hechos.length, 0);
    await d.turno("sí");
    assert.strictEqual(hechos.length, 1);
    assert.strictEqual(hechos[0].confirmado, true);
  });
  await pruebaAsync("un nombre que el respaldo inventa no marca a nadie", async () => {
    conRespaldo(() => ({ ok: true, accion: "presente", nombres: ["Pedro Pérez Inventado"], confianza: 0.9 }));
    const { d, hechos } = conversacion();
    await d.turno("el pelao ese sí vino");
    assert.strictEqual(hechos.length, 0);
  });
  await pruebaAsync("si el respaldo falla, responde igual que antes", async () => {
    conRespaldo(() => { throw new Error("sin red"); });
    const { d } = conversacion();
    assert.strictEqual(textoDe(await d.turno("qué hora es en Bogotá")), NO_ENT);
  });
  await pruebaAsync("si el respaldo no está (sin clave), responde igual que antes", async () => {
    conRespaldo(() => ({ ok: false, accion: "no", motivo: "no_disponible" }));
    const { d } = conversacion();
    assert.strictEqual(textoDe(await d.turno("qué hora es en Bogotá")), NO_ENT);
  });
  await pruebaAsync("si el respaldo tarda, a los 3,5 s responde igual que antes", async () => {
    conRespaldo(() => new Promise(() => {}));     // nunca contesta
    const { d } = conversacion();
    const t0 = Date.now();
    assert.strictEqual(textoDe(await d.turno("qué hora es en Bogotá")), NO_ENT);
    assert.ok(Date.now() - t0 < 4500);
  });
  await pruebaAsync("respuesta rara del respaldo (acción inventada) no hace nada", async () => {
    conRespaldo(() => ({ ok: true, accion: "borrar_todo", nombres: ["Juan Pablo Muñoz"], confianza: 1 }));
    const { d, hechos } = conversacion();
    assert.strictEqual(textoDe(await d.turno("algo raro")), NO_ENT);
    assert.strictEqual(hechos.length, 0);
  });
  await pruebaAsync("«abre la lista cuatro ocho dos uno» ya lo entienden las reglas (sin respaldo)", async () => {
    const llamadas = conRespaldo(() => ({ ok: true, accion: "entrar", codigo: "1111", destino: "", tipo: "lista", confianza: 0.9 }));
    const vistos = [];
    A.alEntrar(async (o) => { vistos.push(o); return null; });
    const { d } = conversacion();
    await d.turno("hágame el favor y me abre la lista cuatro ocho dos uno");
    assert.strictEqual(llamadas.length, 0);
    assert.strictEqual(vistos.length, 1);
    assert.strictEqual(vistos[0].codigo, "4821");
    A.alEntrar(null);
  });
  await pruebaAsync("entrar a una lista por el respaldo usa la misma navegación", async () => {
    conRespaldo(() => ({ ok: true, accion: "entrar", codigo: "4821", destino: "", tipo: "lista", confianza: 0.9 }));
    const vistos = [];
    A.alEntrar(async (o) => { vistos.push(o); return null; });
    const { d } = conversacion();
    await d.turno("la de los de segundo semestre del martes, esa");
    assert.deepStrictEqual(vistos, [{ codigo: "4821", nombre: "", tipo: "lista" }]);
    A.alEntrar(null);
  });
  await pruebaAsync("con una pregunta «¿Cuál?» pendiente, la respuesta no va al respaldo", async () => {
    const llamadas = conRespaldo(() => ({ ok: true, accion: "ausente", nombres: ["Juan Pablo Muñoz"], confianza: 0.9 }));
    const { d, hechos } = conversacion();
    await d.turno("pon a Luis presente");
    await d.turno("el segundo");
    assert.strictEqual(llamadas.length, 0);
    assert.ok(hechos.every((h) => h.accion === "presente"));
  });
  await pruebaAsync("muestra «escribiendo» solo mientras pregunta al respaldo", async () => {
    conRespaldo(() => ({ ok: false, accion: "no", motivo: "no_entendio" }));
    A.contexto({ personas: async () => LISTA, actuar: async () => "ok" });
    const marcas = [];
    const d = A.nuevoDialogo({ pensando: (si) => marcas.push(si) });
    await d.turno("pon a Ana Lucía Pérez presente");
    assert.deepStrictEqual(marcas, []);
    await d.turno("qué hora es");
    assert.deepStrictEqual(marcas, [true, false]);
  });
  A.alInterpretar(null);

  console.log(`\n${ok} bien, ${mal} mal`);
  process.exit(mal ? 1 : 0);
})();
