/* Prueba con la interfaz real del chat (asistente.js montado en un DOM): escribir, Enter, leer la burbuja. */
const { JSDOM } = require("jsdom");
const fs = require("fs");
const codigo = fs.readFileSync(require("path").join(__dirname, "asistente.js"), "utf8");
const dom = new JSDOM(`<!doctype html><html><body></body></html>`, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window;
w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
w.HTMLMediaElement && (w.HTMLMediaElement.prototype.play = () => Promise.resolve());
w.eval(codigo);
const A = w.Asistente;
const regs = [
  { codigo: "E101", nombre: "Ana Sofía Pérez Ortega", estado: "ausente" },
  { codigo: "E102", nombre: "Ana María Gómez Restrepo", estado: "ausente" },
  { codigo: "E105", nombre: "Juan Pablo Muñoz Castaño", estado: "ausente" },
  { codigo: "E106", nombre: "Valentina Zuluaga Henao", estado: "ausente" },
];
const hechos = [];
A.montar();
A.alInterpretar(async () => null);
A.alEntrar(async (o) => { hechos.push({ entrar: o }); return null; });
A.contexto({
  personas: () => regs.map((r) => ({ id: r.codigo, nombre: r.nombre })),
  actuar: async (pedido) => {
    hechos.push(pedido);
    if (pedido.accion === "quitar") return `Listo. Eliminé a ${pedido.elegidos.map((x) => x.nombre).join(" y ")}.`;
    if (pedido.accion !== "presente" && pedido.accion !== "ausente") return "No pude hacerlo.";
    const t = pedido.elegidos.map((p) => { const r = regs.find((x) => x.codigo === p.id); r.estado = pedido.accion; return r.nombre; });
    return t.length > 1 ? `Listo. ${t.join(" y ")} quedaron ${pedido.accion}s.` : `Listo. ${t[0]} quedó ${pedido.accion}.`;
  },
  donde: () => "Clase computacional2",
});
const caja = w.document.querySelector(".chat-caja");
const form = caja.closest("form");
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
async function decir(t) {
  const antes = w.document.querySelectorAll(".chat-msg-bot").length;
  caja.value = t;
  caja.dispatchEvent(new w.Event("input", { bubbles: true }));
  form.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
  for (let i = 0; i < 100; i++) { await espera(10); if (w.document.querySelectorAll(".chat-msg-bot").length > antes) break; }
  const bs = w.document.querySelectorAll(".chat-msg-bot");
  return bs.length > antes ? bs[bs.length - 1].textContent : "(sin respuesta)";
}
(async () => {
  const guion = [
    ["Ponme como presente a Ana Sofía", /Ana Sofía Pérez Ortega quedó presente/],
    ["Ponme como ausente Ana Sofía", /Ana Sofía Pérez Ortega quedó ausente/],
    ["Ponme como ausente de Ana Sofía", /Ana Sofía Pérez Ortega quedó ausente/],
    ["ana sofia esta, ponla", /Ana Sofía Pérez Ortega quedó presente/],
    ["pon a Ana presente", /^¿Cuál\? 1\) Ana Sofía/],
    ["2", /Ana María Gómez Restrepo quedó presente/],
    ["márcala ausente", /Ana María Gómez Restrepo quedó ausente/],
    ["Juan Pablo no vino y Valentina sí", /Juan Pablo Muñoz Castaño quedó ausente.*Valentina Zuluaga Henao quedó presente/],
    ["elimina a Juan Pablo", /^¿Elimino a Juan Pablo Muñoz Castaño de Clase computacional2\? \(sí \/ no\)$/],
    ["no", /no eliminé/],
    ["sí", /nada pendiente/],
    ["Valentina", /^¿Qué hago con Valentina Zuluaga Henao: presente o ausente\?$/],
    ["ausente", /Valentina Zuluaga Henao quedó ausente/],
    ["hola", /^Hola/],
    ["gracias", /gusto/],
    ["asdfgh", /No entendí/],
  ];
  let ok = 0;
  for (const [f, esp] of guion) {
    const r = await decir(f);
    const bien = esp.test(r);
    if (bien) ok++;
    console.log(`${bien ? "  ok " : "  MAL"}  «${f}» → ${r}`);
  }
  const quitarSinConfirmar = hechos.some((h) => h.accion === "quitar" && !h.confirmado);
  console.log(`\nInterfaz real: ${ok}/${guion.length} bien. Eliminó sin confirmar: ${quitarSinConfirmar ? "SÍ (MAL)" : "no"}`);
  process.exit(ok === guion.length && !quitarSinConfirmar ? 0 : 1);
})().catch((e) => { console.error("REVENTÓ:", e); process.exit(2); });
