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

console.log(`\n${ok} bien, ${mal} mal`);
process.exit(mal ? 1 : 0);
