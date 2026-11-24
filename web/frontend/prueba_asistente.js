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
  await pruebaAsync("frase rara: el respaldo la interpreta y el nombre pasa por el buscador real", async () => {
    const llamadas = conRespaldo(() => ({ ok: true, accion: "presente", nombres: ["luis enrique arana ortis"], confianza: 0.9 }));
    const { d, hechos } = conversacion();
    await d.turno("oiga profe, el Luis Enrique sí llegó, anótemelo");
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
  await pruebaAsync("entrar a una lista por el respaldo usa la misma navegación", async () => {
    conRespaldo(() => ({ ok: true, accion: "entrar", codigo: "4821", destino: "", tipo: "lista", confianza: 0.9 }));
    const vistos = [];
    A.alEntrar(async (o) => { vistos.push(o); return null; });
    const { d } = conversacion();
    await d.turno("hágame el favor y me abre la lista cuatro ocho dos uno");
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
