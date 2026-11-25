/* Batería masiva del chat (solo reglas; no toca la IA ni el servidor).
   Correr:  node web/frontend/prueba_chat_masiva.js
   La página no sirve este archivo (servidor.py solo sirve index.html, app.js, asistente.js y estilo.css).
   Va por el mismo camino que la página: Asistente.contexto(...) como chatDeLista/chatGeneral de app.js,
   nuevoDialogo().turno(texto), respaldo (Gemini) que devuelve null como cuando el servidor da 403. */
"use strict";
const assert = require("assert");
const path = require("path");
require(path.join(__dirname, "asistente.js"));
const A = globalThis.Asistente;

/* ---------- Lista realista: 25 nombres colombianos, con repetidos a propósito ---------- */
const P = (id, nombres, ap1, ap2) => ({ id, nombre: `${nombres} ${ap1} ${ap2}`, nombres, ap1, ap2 });
const ROSTER = [
  P("E101", "Ana Sofía", "Pérez", "Ortega"),
  P("E102", "Ana María", "Gómez", "Restrepo"),
  P("E103", "Luis Enrique", "Avendaño", "Ortiz"),
  P("E104", "Carlos Andrés", "Avendaño", "Ortiz"),
  P("E105", "Juan Pablo", "Muñoz", "Castaño"),
  P("E106", "Valentina", "Zuluaga", "Henao"),
  P("E107", "María José", "Rodríguez", "Peña"),
  P("E108", "José David", "Martínez", "López"),
  P("E109", "Daniela", "Hernández", "Cárdenas"),
  P("E110", "Santiago", "Ramírez", "Quintero"),
  P("E111", "Camila Andrea", "Torres", "Vargas"),
  P("E112", "Andrés Felipe", "Morales", "Rincón"),
  P("E113", "Laura Valentina", "Castro", "Díaz"),
  P("E114", "Sebastián", "Ríos", "Montoya"),
  P("E115", "Natalia", "Guzmán", "Arango"),
  P("E116", "Mateo", "Jiménez", "Ospina"),
  P("E117", "Juliana", "Ortiz", "Salazar"),
  P("E118", "Diego Alejandro", "Mejía", "Rojas"),
  P("E119", "Paula Andrea", "Sánchez", "Gil"),
  P("E120", "Kevin Stiven", "Cuéllar", "Trujillo"),
  P("E121", "Yeison Ferney", "Rojas", "Mora"),
  P("E122", "Cristian Camilo", "Vera", "Duque"),
  P("E123", "Luz Marina", "Paz", "Flores"),
  P("E124", "Rosa Esperanza", "Blanco", "León"),
  P("E125", "Brayan", "Estiven", "Sierra"),
];
const OTRA_CLASE = [P("E201", "Pedro Nel", "Ospina", "Vélez"), P("E202", "Ana Lucía", "Mora", "Quiroga"), P("E203", "Ana Isabel", "Rueda", "Paz")];
const N = (s) => A.normalizar(s);
const VACIAS = new Set(["de", "del", "la", "las", "los", "el", "y", "e", "a", "al"]);
/* Quién debería ser: todos los que tienen TODAS las palabras dichas (igual que lo pensaría una persona). */
function oraculo(forma, lista = ROSTER) {
  const ws = N(forma).split(" ").filter((w) => w && !VACIAS.has(w));
  return lista.filter((p) => { const nw = N(p.nombre).split(" "); return ws.every((w) => nw.includes(w)); }).map((p) => p.id);
}

/* ---------- La página de mentira: copia de chatDeLista (app.js) ---------- */
let ahora = Date.now();
const realNow = Date.now;
Date.now = () => ahora;
function pagina(lista = ROSTER, opciones = {}) {
  const hechos = [], navs = [];
  const regs = lista.map((p) => ({ codigo: p.id, nombre: p.nombre, estado: "ausente" }));
  A.alInterpretar(async () => null);          // Gemini con 403: app.js devuelve null
  A.alEntrar(async (orden) => { navs.push(orden); return null; });
  if (opciones.general) {
    A.contexto({
      personas: async () => [],
      actuar: async (pedido) => {
        hechos.push(pedido);
        if (pedido.accion === "pasar") return "Abre una clase y sube la foto.";
        if (pedido.accion === "presente" || pedido.accion === "ausente") return "Primero abre una lista (dime su código).";
        if (pedido.accion === "agregar") return "Abre la clase, pestaña Estudiantes.";
        if (pedido.accion === "quitar") return "¿De qué clase? Ábrela o dime su código.";
        return "Abre una clase o dime el código de una lista.";
      },
    });
  } else {
    A.contexto({
      personas: () => regs.map((r) => ({ id: r.codigo, nombre: r.nombre })),
      actuar: async (pedido) => {
        hechos.push(pedido);
        if (pedido.accion === "pasar") return "Esta lista ya está hecha.";
        if (pedido.accion === "agregar") return "Para agregar ve a la clase › Estudiantes.";
        if (pedido.accion === "quitar") {
          if (!pedido.elegidos || !pedido.elegidos.length) return "Esta lista no tiene estudiantes.";
          return `Listo. Eliminé a ${pedido.elegidos.map((x) => x.nombre).join(" y ")}.`;
        }
        if (pedido.accion !== "presente" && pedido.accion !== "ausente") return "No pude hacerlo.";
        const tocados = [];
        for (const p of pedido.elegidos) {
          const r = regs.find((x) => x.codigo === p.id);
          if (!r) return `No encontré a ${p.nombre} en esta lista.`;
          r.estado = pedido.accion;
          tocados.push(r.nombre);
        }
        return tocados.length > 1 ? `Listo. ${tocados.join(" y ")} quedaron ${pedido.accion}s.` : `Listo. ${tocados[0]} quedó ${pedido.accion}.`;
      },
      donde: () => "Clase computacional2",
    });
  }
  const d = A.nuevoDialogo({ pensando: () => {} });
  return { d, hechos, navs, regs };
}
const txt = (r) => (r == null ? "" : typeof r === "object" ? String(r.texto || r.voz || "") : String(r));
const voz = (r) => A.paraVoz(r);

/* ---------- Motor ---------- */
let total = 0, bien = 0;
const fallos = [];
const porCategoria = {};
function cat(c, ok) { porCategoria[c] = porCategoria[c] || { ok: 0, mal: 0 }; porCategoria[c][ok ? "ok" : "mal"]++; }

function invariantes(pg, frase, r) {
  const t = txt(r);
  if (r !== null && typeof r !== "string" && typeof r !== "object") throw new Error("respuesta rara: " + typeof r);
  if (/\u2014/.test(t) || /\u2014/.test(voz(r))) throw new Error("raya larga en: " + t);
  if (/todovirtual/i.test(t)) throw new Error("marca en: " + t);
  if (t.length > 260) throw new Error("respuesta larga (" + t.length + "): " + t);
  if (voz(r).length > 160) throw new Error("voz larga: " + voz(r));
  for (const h of pg.hechos) {
    if (h.accion === "quitar" && h.elegidos && h.elegidos.length && h.confirmado !== true) throw new Error("ELIMINÓ SIN CONFIRMAR: " + frase);
  }
}

async function caso(categoria, frases, esperar, opciones = {}) {
  total++;
  const pg = opciones.pg || pagina(opciones.lista, opciones);
  const respuestas = [];
  try {
    for (const f of [].concat(frases)) {
      if (typeof f === "function") { await f(pg); continue; }
      const r = await pg.d.turno(f);
      invariantes(pg, f, r);
      respuestas.push(r);
    }
    esperar(pg, respuestas.map(txt));
    bien++; cat(categoria, true);
  } catch (e) {
    cat(categoria, false);
    fallos.push(`[${categoria}] ${JSON.stringify([].concat(frases).filter((f) => typeof f === "string"))}\n      → ${respuestas.map(txt).join(" | ")}\n      ${e.message.split("\n")[0]}`);
  }
}
const ids = (h) => h.elegidos.map((p) => p.id).sort();
const marca = (accion, quien) => (pg, rs) => {
  const esperados = [].concat(quien).sort();
  assert.strictEqual(pg.hechos.length, 1, `esperaba 1 acción, hubo ${pg.hechos.length}`);
  assert.strictEqual(pg.hechos[0].accion, accion, `acción ${pg.hechos[0].accion} en vez de ${accion}`);
  assert.deepStrictEqual(ids(pg.hechos[0]), esperados, `marcó ${ids(pg.hechos[0])} en vez de ${esperados}`);
};
const marcas = (lista) => (pg) => {
  assert.strictEqual(pg.hechos.length, lista.length, `esperaba ${lista.length} acciones, hubo ${pg.hechos.length}: ${JSON.stringify(pg.hechos.map((h) => [h.accion, h.elegidos && ids(h)]))}`);
  lista.forEach(([accion, quien], i) => {
    assert.strictEqual(pg.hechos[i].accion, accion, `acción ${i}: ${pg.hechos[i].accion} en vez de ${accion}`);
    assert.deepStrictEqual(ids(pg.hechos[i]), [].concat(quien).sort(), `acción ${i}: ${ids(pg.hechos[i])} en vez de ${quien}`);
  });
};
const pregunta = (patron) => (pg, rs) => {
  assert.strictEqual(pg.hechos.length, 0, `no debía actuar y actuó: ${JSON.stringify(pg.hechos.map((h) => [h.accion, h.elegidos && ids(h)]))}`);
  const ult = rs[rs.length - 1];
  assert.ok(/^¿/.test(ult) || /\?/.test(ult), "esperaba una pregunta, dijo: " + ult);
  if (patron) assert.match(ult, patron);
};
const nada = (patron) => (pg, rs) => {
  assert.strictEqual(pg.hechos.filter((h) => h.accion !== "pasar").length, 0, `no debía actuar y actuó: ${JSON.stringify(pg.hechos.map((h) => [h.accion, h.elegidos && ids(h)]))}`);
  if (patron) assert.match(rs[rs.length - 1], patron);
};
/* Marca a quien toca o, si hay varios posibles, pregunta sin marcar. */
function esperarSegun(accion, forma, lista = ROSTER) {
  const o = oraculo(forma, lista);
  if (o.length === 1) return marca(accion, o);
  if (o.length > 1) return pregunta(/^¿Cuál\? 1\) /);
  return (pg) => assert.strictEqual(pg.hechos.length, 0, "nombre sin dueño y marcó a alguien");
}

/* ---------- Generador estable (siempre las mismas frases) ---------- */
let semilla = Number(process.env.SEMILLA || 20261124);
const azar = () => { semilla = (semilla * 1103515245 + 12345) % 2147483648; return semilla / 2147483648; };
const uno = (xs) => xs[Math.floor(azar() * xs.length)];
const sinTildes = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");

function formasDe(p) {
  const primero = p.nombres.split(" ")[0];
  return [p.nombre, p.nombres, `${p.nombres} ${p.ap1}`, `${primero} ${p.ap1}`, p.ap1, `${p.ap1} ${p.ap2}`, primero];
}
const TODAS_FORMAS = [];
for (const p of ROSTER) for (const f of formasDe(p)) if (!TODAS_FORMAS.includes(f)) TODAS_FORMAS.push(f);

const VERBOS = ["ponme", "pon", "pónme", "póngame", "pongame", "márcame", "marca", "márcalo", "coloca", "deja", "registra", "anota", "pónganme", "marque"];
const PALABRA = { presente: ["presente", "activo", "activa"], ausente: ["ausente", "inactivo", "inactiva"] };
const CON_VERBO = [
  "{v} a {N} como {w}", "{v} como {w} a {N}", "{v} {w} a {N}", "{v} a {N} {w}", "{v} {N} como {w}",
  "{v} como {w} {N}", "{v} de {w} a {N}", "{v} como {w} de {N}", "{v} {N} {w}", "{v} al {N} como {w}", "{v} a la {N} como {w}",
];
const SIN_VERBO = ["{N} {w}", "{N} está {w}", "{N} esta {w}", "{w} {N}", "{N} quedó {w}", "{N} como {w}"];
const SOLO = {
  presente: ["{N} llegó", "ya llegó {N}", "{N} ya llegó", "{N} sí vino", "{N} si vino", "{N} vino", "{N} está aquí", "{N} esta aca",
    "{N} asistió", "llegó {N}", "{N} está, ponla", "{N} esta ponla", "activa a {N}", "{N} sí está", "cambia a {N} a presente",
    "pasa a {N} a presente", "marca asistencia a {N}", "ponle asistencia a {N}", "{N} ya está", "vino {N}", "asistió {N}", "{N} está presente"],
  ausente: ["{N} no vino", "{N} faltó", "{N} falto", "falta {N}", "ponle falta a {N}", "{N} no está", "{N} no esta", "{N} no llegó",
    "marca inasistencia a {N}", "inactiva a {N}", "{N} no asistió", "cambia a {N} a ausente", "pasa a {N} a ausente", "{N} no vino hoy",
    "{N} ya no está", "ponle inasistencia a {N}", "{N} está ausente", "{N} hoy no vino", "{N} no ha llegado"],
};
const PREFIJOS = ["", "", "", "eh ", "pues ", "parce ", "oye ", "mira ", "porfa ", "por favor ", "oiga profe, ", "ehh, ", "bueno, ", "a ver, "];
const SUFIJOS = ["", "", "", " porfa", " por favor", " gracias", " pues", " parce", "!!", "...", "?", " ya"];
function vestir(f) {
  let s = uno(PREFIJOS) + f + uno(SUFIJOS);
  const k = azar();
  if (k < 0.2) s = sinTildes(s).toLowerCase();
  else if (k < 0.3) s = s.toUpperCase();
  else if (k < 0.4) s = s[0].toUpperCase() + s.slice(1);
  return s;
}
const llenar = (plantilla, v, n, w) => plantilla.replace("{v}", v).replace("{N}", n).replace("{w}", w);

/* Nombres mal oídos o mal escritos (voz): quién debería ser. */
const MAL_OIDOS = [
  ["Luis Enrique araña Ortiz", "E103"], ["Carlos Andrés araña Ortiz", "E104"], ["Valentina Suluaga", "E106"], ["Juan Pablo Muños", "E105"],
  ["Santiago Ramires", "E110"], ["Daniela Hernandes", "E109"], ["Sebastian Rios", "E114"], ["Kevin Estiven Cuellar", "E120"],
  ["Jeison Ferney Rojas", "E121"], ["Natalia Guzman Arango", "E115"], ["Mateo Gimenez", "E116"], ["Cristian Camilo Bera Duque", "E122"],
  ["Diego Alejandro Mejia", "E118"], ["Paula Andrea Sanches", "E119"], ["Juliana Ortis Salazar", "E117"], ["Jose David Martines", "E108"],
  ["Maria Jose Rodrigues", "E107"], ["Laura Valentina Castro Dias", "E113"], ["Brayan Estiben Sierra", "E125"], ["Rosa Esperansa Blanco", "E124"],
  ["luz marina pas flores", "E123"], ["camila andrea torres bargas", "E111"], ["andres felipe morales rincon", "E112"], ["yeison rojas mora", "E121"],
];

(async () => {
  const t0 = realNow();

  /* 1) Presente / ausente con verbo × preposición × forma del nombre × estado */
  for (const plantilla of CON_VERBO) for (const estado of ["presente", "ausente"]) for (let k = 0; k < 14; k++) {
    const forma = uno(TODAS_FORMAS);
    const f = vestir(llenar(plantilla, uno(VERBOS), forma, uno(PALABRA[estado])));
    await caso("asistencia con verbo", f, esperarSegun(estado, forma));
  }
  /* 2) Sin verbo */
  for (const plantilla of SIN_VERBO) for (const estado of ["presente", "ausente"]) for (let k = 0; k < 18; k++) {
    const forma = uno(TODAS_FORMAS);
    await caso("asistencia sin verbo", vestir(llenar(plantilla, "", forma, uno(PALABRA[estado]))), esperarSegun(estado, forma));
  }
  /* 3) Frases propias de cada estado */
  for (const estado of ["presente", "ausente"]) for (const plantilla of SOLO[estado]) for (let k = 0; k < 12; k++) {
    const forma = uno(TODAS_FORMAS);
    await caso("asistencia suelta", vestir(llenar(plantilla, "", forma, "")), esperarSegun(estado, forma));
  }
  /* 4) Cada estudiante, por su nombre completo y por lo más corto que lo identifica, en ambos estados */
  for (const p of ROSTER) for (const forma of formasDe(p)) for (const estado of ["presente", "ausente"]) {
    await caso("cada estudiante", `pon a ${forma} ${estado}`, esperarSegun(estado, forma));
    await caso("cada estudiante", `${forma} ${estado === "presente" ? "llegó" : "no vino"}`, esperarSegun(estado, forma));
  }
  /* 5) Nombres mal oídos / mal escritos */
  for (const [forma, id] of MAL_OIDOS) for (const estado of ["presente", "ausente"]) {
    for (const plantilla of ["pon a {N} {w}", "ponme como {w} a {N}", "{N} {w}", "márcame a {N} como {w}"]) {
      await caso("nombre mal oído", vestir(llenar(plantilla, "", forma, estado)).replace(/^\s+/, ""), (pg, rs) => {
        if (pg.hechos.length) return marca(estado, id)(pg, rs);      // si marca, que sea el correcto
        assert.match(rs[rs.length - 1], /^¿(Es|Cuál)/, "ni marcó ni preguntó: " + rs[rs.length - 1]);
      });
    }
  }
  /* 6) Varios a la vez */
  const unicos = ROSTER.filter((p) => oraculo(p.nombres).length === 1).map((p) => p.nombres);
  for (let k = 0; k < 40; k++) {
    const a = uno(unicos); let b = uno(unicos); while (b === a) b = uno(unicos); let c = uno(unicos); while (c === a || c === b) c = uno(unicos);
    const ia = oraculo(a)[0], ib = oraculo(b)[0], ic = oraculo(c)[0];
    await caso("varios a la vez", vestir(`ausentes ${a} y ${b}`), marca("ausente", [ia, ib]));
    await caso("varios a la vez", vestir(`${a} y ${b} no vinieron`), marca("ausente", [ia, ib]));
    await caso("varios a la vez", vestir(`pon a ${a} y ${b} como presentes`), marca("presente", [ia, ib]));
    await caso("varios a la vez", vestir(`${a}, ${b} y ${c} presentes`), marca("presente", [ia, ib, ic]));
    await caso("varios a la vez", vestir(`marca presentes a ${a} y a ${b}`), marca("presente", [ia, ib]));
    await caso("varios a la vez", vestir(`${a} y ${b} faltaron`), marca("ausente", [ia, ib]));
    /* dos órdenes en una frase */
    await caso("dos órdenes", vestir(`pon a ${a} presente y a ${b} ausente`), marcas([["presente", ia], ["ausente", ib]]));
    await caso("dos órdenes", vestir(`${a} presente, ${b} ausente`), marcas([["presente", ia], ["ausente", ib]]));
    await caso("dos órdenes", vestir(`${a} vino y ${b} no vino`), marcas([["presente", ia], ["ausente", ib]]));
    await caso("dos órdenes", vestir(`${a} llegó pero ${b} faltó`), marcas([["presente", ia], ["ausente", ib]]));
    await caso("dos órdenes", vestir(`${a} y ${b} presentes, ${c} ausente`), marcas([["presente", [ia, ib]], ["ausente", ic]]));
    await caso("dos órdenes", vestir(`${a} no vino y ${b} sí`), marcas([["ausente", ia], ["presente", ib]]));
    await caso("dos órdenes", vestir(`${a} vino y ${b} no`), marcas([["presente", ia], ["ausente", ib]]));
    await caso("dos órdenes", vestir(`${a} no vino, ${b} tampoco`), marcas([["ausente", ia], ["ausente", ib]]));
    await caso("dos órdenes", vestir(`${a} vino y ${b} también`), marca("presente", [ia, ib]));
    await caso("dos órdenes", vestir(`${a} faltó pero ${b} sí vino`), marcas([["ausente", ia], ["presente", ib]]));
    await caso("dos órdenes", vestir(`${a} sí vino, ${b} no`), marcas([["presente", ia], ["ausente", ib]]));
  }

  /* 7) El caso real que falló en vivo */
  for (const f of ["Ponme como presente a Ana Sofía", "Ponme como ausente Ana Sofía", "Ponme como ausente de Ana Sofía", "ponme como ausente a ana sofia", "PONME COMO AUSENTE ANA SOFÍA"]) {
    await caso("caso en vivo", f, marca(/presente/i.test(f) ? "presente" : "ausente", "E101"));
  }

  /* 8) ¿Cuál? 1) 2): número, nombre, respuesta equivocada */
  const ambiguos = TODAS_FORMAS.filter((f) => oraculo(f).length > 1);
  for (const forma of ambiguos) for (const estado of ["presente", "ausente"]) {
    const grupo = oraculo(forma);
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "1"], marca(estado, grupo[0]));
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "el segundo"], marca(estado, grupo[1]));
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "opción 2"], marca(estado, grupo[1]));
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "9"], pregunta());
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "9", "1"], marca(estado, grupo[0]));
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "no"], nada(/no cambié/i));
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "cancela"], nada());
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "xyzzy qwerty"], nada());
    const otro = ROSTER.find((p) => p.id === grupo[1]);
    await caso("¿Cuál?", [`pon a ${forma} ${estado}`, otro.nombre], marca(estado, grupo[1]));
    if (grupo.length === 2) await caso("¿Cuál?", [`pon a ${forma} ${estado}`, "los dos"], marca(estado, grupo));
  }
  await caso("¿Cuál?", ["pon a Ana presente", "Sofía"], marca("presente", "E101"));
  await caso("¿Cuál?", ["pon a Ana presente", "la de Gómez"], marca("presente", "E102"));
  await caso("¿Cuál?", ["pon a Ana presente", "ana maria"], marca("presente", "E102"));
  await caso("¿Cuál?", ["pon a Ana presente", "Pedro"], nada());
  await caso("¿Cuál?", ["Valentina no vino", "la Zuluaga"], marca("ausente", "E106"));
  await caso("¿Cuál?", ["Ortiz llegó", "3"], marca("presente", "E117"));

  /* 9) Eliminar: confirmación, cancelar, vencimiento */
  const SI = ["sí", "si", "Sí.", "dale", "claro", "confirmo", "sí, elimínalo", "ok", "de una", "hazlo"];
  const NO = ["no", "No, mejor no", "cancela", "nada", "olvídalo", "nel"];
  const BORRAR = ["elimina a {N}", "borra a {N}", "saca a {N} de la clase", "quiero eliminar a {N}", "elimine al estudiante {N}", "bórrame a {N}",
    "por favor elimina a {N}", "borra al alumno {N} de la lista", "eliminar a {N}", "puedes borrar a {N}?"];
  for (const plantilla of BORRAR) for (let k = 0; k < 6; k++) {
    const p = uno(ROSTER.filter((x) => oraculo(x.nombres).length === 1));
    const f = llenar(plantilla, "", uno([p.nombres, p.nombre, sinTildes(p.nombre).toLowerCase()]), "");
    await caso("eliminar", f, pregunta(new RegExp("^¿Elimino a " + p.nombre.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))));
    await caso("eliminar", [f, uno(SI)], (pg) => {
      assert.strictEqual(pg.hechos.length, 1); assert.strictEqual(pg.hechos[0].accion, "quitar");
      assert.strictEqual(pg.hechos[0].confirmado, true); assert.deepStrictEqual(ids(pg.hechos[0]), [p.id]);
    });
    await caso("eliminar", [f, uno(NO)], nada(/no eliminé/i));
    await caso("eliminar", [f, uno(NO), "sí"], nada());
    await caso("eliminar", [f, () => { ahora += 4 * 60 * 1000; }, "sí"], nada(/venció/i));
    await caso("eliminar", [f, "sí", "sí"], (pg) => assert.strictEqual(pg.hechos.length, 1, "un segundo sí repitió"));
  }
  for (const forma of ["Ana", "Avendaño Ortiz", "Valentina", "Rojas"]) {
    const g = oraculo(forma);
    await caso("eliminar", [`elimina a ${forma}`], pregunta(/^¿Cuál\? 1\)/));
    await caso("eliminar", [`elimina a ${forma}`, "2"], pregunta(/^¿Elimino a /));
    await caso("eliminar", [`elimina a ${forma}`, "2", "sí"], (pg) => { assert.strictEqual(pg.hechos.length, 1); assert.deepStrictEqual(ids(pg.hechos[0]), [g[1]]); assert.strictEqual(pg.hechos[0].confirmado, true); });
    await caso("eliminar", [`elimina a ${forma}`, "2", "no"], nada());
  }
  await caso("eliminar", ["elimina a Luis Enrique araña"], pregunta(/^¿Elimino a Luis Enrique Avendaño Ortiz/));
  for (const f of ["borra la lista", "elimina esta lista", "borra la foto", "elimina eso", "borra el chat", "elimina el historial", "borra todo",
    "como elimino una lista", "no elimines a Juan Pablo", "no borres a nadie", "no", "eliminar", "no borres nada", "no saques a Valentina Zuluaga"]) {
    await caso("no es eliminar", f, (pg, rs) => { assert.strictEqual(pg.hechos.length, 0); assert.ok(!/^¿Elimino/.test(rs[0]), "preguntó eliminar: " + rs[0]); });
  }
  await caso("eliminar", ["elimina a Juan Pablo"], pregunta(/^¿Elimino a Juan Pablo Muñoz Castaño/), { general: false });
  await caso("eliminar sin lista", ["elimina a Juan Pablo"], (pg, rs) => { assert.ok(pg.hechos.every((h) => !h.elegidos || !h.elegidos.length), "eliminó sin lista"); assert.match(rs[0], /qué clase/i); }, { general: true });
  await caso("quita = ausente", "quita a Juan Pablo", marca("ausente", "E105"));
  await caso("quita = ausente", "borra el presente de Juan Pablo", marca("ausente", "E105"));

  /* 10) Preguntas pendientes interrumpidas por otra orden */
  await caso("interrumpir", ["pon a Ana presente", "pon a Juan Pablo ausente", "1"], marca("ausente", "E105"));
  await caso("interrumpir", ["pon a Ana presente", "elimina a Juan Pablo"], pregunta(/^¿Elimino a Juan Pablo/));
  await caso("interrumpir", ["pon a Ana presente", "elimina a Juan Pablo", "1"], nada());
  await caso("interrumpir", ["elimina a Juan Pablo", "pon a Valentina Zuluaga presente", "sí"], marca("presente", "E106"));
  await caso("interrumpir", ["elimina a Juan Pablo", "4821"], (pg) => { assert.strictEqual(pg.hechos.length, 0); assert.strictEqual(pg.navs.length, 1); });
  await caso("interrumpir", ["elimina a Juan Pablo", "4821", "sí"], (pg) => assert.strictEqual(pg.hechos.length, 0));
  await caso("interrumpir", ["Ana Sofía", "Juan Pablo no vino"], marca("ausente", "E105"));
  await caso("interrumpir", ["Ana Sofía", "ausente"], marca("ausente", "E101"));
  await caso("interrumpir", ["Ana Sofía", "presente"], marca("presente", "E101"));
  await caso("interrumpir", ["Ana Sofía", "ponla"], marca("presente", "E101"));
  await caso("interrumpir", ["Ana Sofía", "no"], nada());
  await caso("interrumpir", ["Ana Sofía", "elimina a Juan Pablo", "presente"], nada());
  await caso("interrumpir", ["pon a Ana presente", "ayuda"], nada(/presente o ausente/));
  await caso("interrumpir", ["pon a Ana presente", "ayuda", "1"], nada());

  /* 11) «ponla», «márcala»: el último nombrado */
  await caso("ponla", ["Juan Pablo no vino", "no, ponlo presente"], (pg) => { assert.strictEqual(pg.hechos.length, 2); assert.strictEqual(pg.hechos[1].accion, "presente"); assert.deepStrictEqual(ids(pg.hechos[1]), ["E105"]); });
  await caso("ponla", ["pon a Ana Sofía presente", "márcala ausente"], marcas([["presente", "E101"], ["ausente", "E101"]]));
  await caso("ponla", ["pon a Ana Sofía presente", "ponla"], marcas([["presente", "E101"], ["presente", "E101"]]));
  await caso("ponla", ["ponla"], nada(/A quién/));
  await caso("ponla", ["márcalo"], nada(/A quién/));
  await caso("ponla", ["pon a Ana presente", "2", "ahora ponla ausente"], marcas([["presente", "E102"], ["ausente", "E102"]]));

  /* 12) Entrar a listas o clases (escrito y por voz) */
  const ENTRAR = [
    ["4821", { codigo: "4821" }], ["entra a la lista 4821", { codigo: "4821" }], ["abre la lista 4821", { codigo: "4821" }], ["lista 4821", { codigo: "4821" }],
    ["código 4821", { codigo: "4821" }], ["entra al código 4821", { codigo: "4821" }], ["48 21", { codigo: "4821" }], ["4 8 2 1", { codigo: "4821" }],
    ["cuatro ocho dos uno", { codigo: "4821" }], ["entra a la lista cuatro ocho dos uno", { codigo: "4821" }], ["cuatro mil ochocientos veintiuno", { codigo: "4821" }],
    ["abre la lista cuatro mil ochocientos veintiuno", { codigo: "4821" }], ["llévame a la lista 4821 porfa", { codigo: "4821" }], ["ábreme la 4821", { codigo: "4821" }],
    ["Entra a la lista número 4821.", { codigo: "4821" }], ["ENTRA A LA LISTA 4821", { codigo: "4821" }], ["oye, entra a la lista 4821", { codigo: "4821" }],
    ["mil doscientos treinta y cuatro", { codigo: "1234" }], ["nueve mil cuatrocientos treinta y seis", { codigo: "9436" }], ["entra a la 9436", { codigo: "9436" }],
    ["abre la clase computacional2", { nombre: "computacional2" }], ["entra a la clase cálculo", { nombre: "calculo" }], ["abre la clase de cálculo", { nombre: "calculo" }],
    ["muéstrame la clase computacional 2", { nombre: "computacional 2" }], ["ve a la clase física", { nombre: "fisica" }],
  ];
  for (const [f, esp] of ENTRAR) {
    for (const general of [false, true]) {
      await caso("entrar", f, (pg) => {
        assert.strictEqual(pg.hechos.length, 0, "marcó a alguien al entrar");
        assert.strictEqual(pg.navs.length, 1, "no navegó");
        if (esp.codigo) assert.strictEqual(pg.navs[0].codigo, esp.codigo);
        if (esp.nombre) assert.strictEqual(N(pg.navs[0].nombre), esp.nombre);
      }, { general });
    }
  }

  /* 13) Ayuda, saludos, gracias, sin sentido, vacío, «sí» / «no» sueltos */
  for (const f of ["ayuda", "Ayuda!", "qué puedes hacer", "que sabes hacer", "comandos", "cómo funciona", "ayúdame"]) await caso("ayuda", f, nada(/presente o ausente/i));
  for (const f of ["hola", "Hola!", "buenas", "buenas tardes", "buenos días", "buenas noches", "hola parce", "qué más", "quiubo", "hey"]) await caso("saludo", f, nada(/^Hola/));
  for (const f of ["gracias", "muchas gracias", "ok gracias", "mil gracias", "listo gracias", "gracias parce"]) await caso("gracias", f, nada(/gusto/i));
  for (const f of ["asdfgh", "qué hora es", "jajaja", "???", "...", "el clima de hoy", "cuánto es 2 más 2", "1", "123", "ok", "vale", "mmm", "eh", "pues"]) {
    await caso("sin sentido", f, nada());
  }
  for (const f of ["", "   ", "\n"]) await caso("vacío", f, nada());
  for (const f of ["sí", "si", "no", "No.", "dale", "claro", "mejor no", "no no", "sí sí", "NO", "Sí!!", "nop", "nel", "ok", "vale", "listo"]) {
    await caso("sí/no suelto", f, nada());
    await caso("sí/no suelto", ["pon a Ana Sofía presente", f], (pg) => assert.strictEqual(pg.hechos.length, 1, "un sí/no suelto volvió a marcar"));
    await caso("sí/no suelto", ["Ana Sofía", f], (pg, rs) => { assert.ok(pg.hechos.every((h) => h.accion !== "quitar")); if (/^(no|nop|nel|mejor no|no no)/i.test(N(f))) assert.strictEqual(pg.hechos.length, 0, "un no marcó"); });
  }
  await caso("sí/no suelto", ["sí", "sí", "no"], nada());

  /* 14) Frases largas y relleno */
  const LARGAS = [
    ["oye parce mira, porfa ponme a la Ana Sofía Pérez como presente que ya llegó, gracias", "presente", "E101"],
    ["eh profe, pues la Valentina Zuluaga no vino hoy, póngala como ausente por favor", "ausente", "E106"],
    ["bueno a ver, el Juan Pablo Muñoz sí vino, márcamelo presente porfa", "presente", "E105"],
    ["mira, Santiago Ramírez faltó, ponle falta", "ausente", "E110"],
    ["hágame el favor y me pone a Mateo Jiménez presente", "presente", "E116"],
    ["parce, la Juliana Ortiz Salazar ya está aquí", "presente", "E117"],
    ["Profe, el Kevin Stiven no ha llegado todavía", "ausente", "E120"],
    ["Oiga, póngame ausente a Daniela Hernández que no vino", "ausente", "E109"],
    ["porfa marca a natalia guzman como presente, gracias parce", "presente", "E115"],
    ["eh, eh, ponme a Sebastián Ríos ausente, porfa", "ausente", "E114"],
  ];
  for (const [f, e, id] of LARGAS) await caso("frases largas", f, marca(e, id));

  /* 15) Nombres que también son palabras comunes */
  for (const [f, e, id] of [
    ["pon a Luz presente", "presente", "E123"], ["Luz no vino", "ausente", "E123"], ["Rosa llegó", "presente", "E124"],
    ["pon a Rosa ausente", "ausente", "E124"], ["Paz presente", "presente", "E123"], ["Blanco no vino", "ausente", "E124"],
    ["marca a Esperanza como presente", "presente", "E124"], ["Vera faltó", "ausente", "E122"], ["Gil presente", "presente", "E119"],
    ["pon a la Luz Marina ausente", "ausente", "E123"], ["Sierra vino", "presente", "E125"], ["León presente", "presente", "E124"],
  ]) await caso("nombres que son palabras", f, marca(e, id));
  for (const f of ["se fue la luz", "qué rosa tan bonita", "quiero paz", "la pared es blanco"]) {
    await caso("nombres que son palabras", f, (pg) => assert.strictEqual(pg.hechos.length, 0, "marcó por una palabra común"));
  }

  /* 16) Cambiar de clase a mitad del diálogo */
  await caso("cambiar de clase", ["pon a Ana presente", (pg) => { pg.otra = pagina(OTRA_CLASE); }, "1"], (pg) => { assert.strictEqual(pg.hechos.length, 0); assert.strictEqual(pg.otra.hechos.length, 0); });
  await caso("cambiar de clase", ["elimina a Juan Pablo", (pg) => { A.contexto({ personas: () => OTRA_CLASE, actuar: async (p) => { pg.hechos.push(p); return "ok"; } }); }, "sí"], nada());
  await caso("cambiar de clase", ["pon a Juan Pablo presente", (pg) => { A.contexto({ personas: () => OTRA_CLASE, actuar: async (p) => { pg.hechos.push(p); return "ok"; } }); }, "ponlo ausente"], (pg) => assert.strictEqual(pg.hechos.length, 1, "ponlo arrastró a alguien de la otra clase"));
  await caso("cambiar de clase", ["Ana Sofía", (pg) => { A.contexto({ personas: () => OTRA_CLASE, actuar: async (p) => { pg.hechos.push(p); return "ok"; } }); }, "presente"], nada());
  for (const [f, e, id] of [["pon a Pedro Nel presente", "presente", "E201"], ["Ana Lucía no vino", "ausente", "E202"], ["pon a Ana presente", null, null]]) {
    await caso("otra clase", f, id ? marca(e, id) : pregunta(/^¿Cuál/), { lista: OTRA_CLASE });
  }

  /* 17) Sin lista abierta (chat general) */
  for (const f of ["pon a Ana Sofía presente", "Juan Pablo no vino", "ponme como ausente a Valentina"]) {
    await caso("sin lista", f, (pg, rs) => { assert.ok(pg.hechos.every((h) => !h.elegidos || !h.elegidos.length), "marcó sin lista"); assert.match(rs[0], /abre una lista|código/i); }, { general: true });
  }

  /* 18) Con el código E del estudiante */
  for (const p of ROSTER.slice(0, 10)) {
    await caso("código E", `pon a ${p.id} presente`, marca("presente", p.id));
    await caso("código E", `${p.id.toLowerCase()} ausente`, marca("ausente", p.id));
  }

  /* 19) Agregar y pasar lista siguen igual */
  await caso("otras órdenes", "pasa lista", (pg) => assert.strictEqual(pg.hechos[0].accion, "pasar"));
  await caso("otras órdenes", "agrega a Pedro Pérez", (pg) => assert.strictEqual(pg.hechos[0].accion, "agregar"));
  await caso("otras órdenes", "agrega al estudiante Pedro Pérez", (pg) => assert.strictEqual(pg.hechos[0].accion, "agregar"));

  /* 20) Fuzz: frases revueltas. Nunca revienta, nunca elimina sin confirmar,
         y si marca a alguien, ese alguien fue nombrado (comparte una palabra con la frase). */
  const VOCAB = ["pon", "ponme", "marca", "a", "de", "la", "el", "y", "como", "presente", "ausente", "no", "vino", "llegó", "falta", "faltó",
    "elimina", "borra", "sí", "no", "eh", "pues", "parce", "porfa", "lista", "clase", "4821", "cuatro", "mil", "ponla", "márcala", "activo",
    "inactivo", "está", "aquí", "ya", "hola", "gracias", ",", "ayuda", "uno", "dos", "el segundo", "todos", "los dos", "pero", "que"];
  const PALABRAS_NOMBRES = [];
  for (const p of ROSTER) for (const w of p.nombre.split(" ")) PALABRAS_NOMBRES.push(w);
  for (let k = 0; k < 1500; k++) {
    const n = 1 + Math.floor(azar() * 9);
    const ws = [];
    for (let i = 0; i < n; i++) ws.push(azar() < 0.35 ? uno(PALABRAS_NOMBRES) : uno(VOCAB));
    const f = ws.join(" ").replace(/ ,/g, ",");
    const g = azar() < 0.5 ? [f] : [f, uno(["sí", "1", "2", "no", "presente", "ausente", "ponla", uno(PALABRAS_NOMBRES)])];
    await caso("fuzz", g, (pg, rs) => {
      const dicho = new Set(N(g.join(" ")).split(" "));
      for (const h of pg.hechos) {
        if (!h.elegidos) continue;
        for (const p of h.elegidos) {
          const nombrado = N(p.nombre).split(" ").some((w) => dicho.has(w));
          const preguntado = rs.some((r) => /^¿/.test(r) && r.includes(p.nombre));     // se lo preguntó y la persona eligió
          assert.ok(nombrado || preguntado, `marcó a ${p.nombre} sin que lo nombraran ni lo confirmaran`);
          if (!nombrado) assert.ok(rs.length > 1, "marcó a alguien no nombrado en una sola frase");
        }
      }
    });
  }

  /* ---------- Resultado ---------- */
  Date.now = realNow;
  A.alInterpretar(null); A.alEntrar(null);
  console.log("Categorías:");
  for (const [c, v] of Object.entries(porCategoria)) console.log(`  ${v.mal ? "MAL" : "ok "}  ${c.padEnd(28)} ${v.ok}/${v.ok + v.mal}`);
  if (fallos.length) {
    console.log(`\nFallos (${fallos.length}), primeros 80:`);
    for (const f of fallos.slice(0, 80)) console.log("  " + f);
  }
  console.log(`\n${bien} bien, ${total - bien} mal, de ${total} casos (${realNow() - t0} ms)`);
  process.exit(total === bien ? 0 : 1);
})();
