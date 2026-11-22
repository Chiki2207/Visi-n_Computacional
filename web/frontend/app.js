"use strict";
/* Asistencia · Uniamazonia — página sin compilación (JavaScript puro: carga rápido en el celular).
   El servidor guarda internamente; el docente solo registra estudiantes y sube la foto del salón. */

const API = ((window.CONFIG && window.CONFIG.API_URL) || "").replace(/\/+$/, "");
const raiz = document.getElementById("app");
const est = {
  token: leer("asis_token"),
  usuario: leer("asis_usuario"),
  sondeo: null,
  fotos: new Map(),     // ruta → URL blob (selfies y fotos ya cargadas: no se vuelven a pedir)
};
const enc = encodeURIComponent;
const esTactil = window.matchMedia("(pointer: coarse)").matches;

/* ------------------------------------------------------------------ utilidades */
function leer(k) { try { return localStorage.getItem(k) || ""; } catch { return ""; } }
function guardar(k, v) { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch { /* sin almacenamiento */ } }

/** Crea un elemento. Nunca usa innerHTML con datos: todo texto va como texto. */
function el(tag, attrs, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "style") Object.assign(n.style, v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat(Infinity)) {
    if (h === null || h === undefined || h === false) continue;
    n.append(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return n;
}

/** Íconos (SVG fijos del código, nunca datos del usuario). */
function icono(nombre, t = 20) {
  const D = {
    persona: "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
    candado: "M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10z",
    ojo: "M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z",
    ojoNo: "M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z",
    camara: "M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM9 2 7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z",
    imagen: "M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z",
    foco: "M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm-7 7H3v4c0 1.1.9 2 2 2h4v-2H5v-4zM5 5h4V3H5c-1.1 0-2 .9-2 2v4h2V5zm14-2h-4v2h4v4h2V5c0-1.1-.9-2-2-2zm0 16h-4v2h4c1.1 0 2-.9 2-2v-4h-2v4z",
  };
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("width", t); svg.setAttribute("height", t); svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("fill", "currentColor"); p.setAttribute("d", D[nombre]);
  svg.append(p);
  return svg;
}

function toast(msg, ms = 3200) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

function fechaLarga(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-CO", { weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" });
}
function fechaCorta(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("es-CO", { day: "numeric", month: "short" })} · ${d.toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" })}`;
}
function nota(x) { return x === null || x === undefined ? "" : Number(x).toFixed(2); }
function irA(h) { if (location.hash === h) enrutar(); else location.hash = h; }
function poner(...n) {
  raiz.replaceChildren(...n);
  window.scrollTo(0, 0);
}
function cargando(texto = "Cargando…") {
  return el("main", { class: "page-shell" }, el("div", { class: "glass pad row fade-in", style: { marginTop: "40px" } }, el("div", { class: "rueda" }), el("span", { class: "muted", text: texto })));
}
function errorMsg(e) { return el("p", { class: "msg msg-error", role: "alert", text: e.message || String(e) }); }

/* ------------------------------------------------------------------ API */
async function api(ruta, { metodo = "GET", json, form, crudo = false } = {}) {
  const headers = {};
  if (est.token) headers.Authorization = "Bearer " + est.token;
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  let r;
  try { r = await fetch(API + ruta, { method: metodo, headers, body }); }
  catch { throw new Error("No hay conexión con el servidor"); }
  if (r.status === 401 && ruta !== "/api/auth/entrar") { salirLocal(); irA("#/entrar"); throw new Error("La sesión venció: vuelva a entrar"); }
  if (!r.ok) {
    let msg = `Error ${r.status}`;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d) => d.msg).join("; ") : msg; } catch { /* sin cuerpo */ }
    throw new Error(msg);
  }
  return crudo ? r : r.json();
}

/** Subida de fotos con porcentaje (importante con datos móviles). */
function subir(ruta, form, alProgreso = () => {}) {
  return new Promise((ok, mal) => {
    const x = new XMLHttpRequest();
    x.open("POST", API + ruta);
    if (est.token) x.setRequestHeader("Authorization", "Bearer " + est.token);
    x.upload.onprogress = (e) => { if (e.lengthComputable) alProgreso(Math.round((100 * e.loaded) / e.total)); };
    x.onerror = () => mal(new Error("No hay conexión con el servidor"));
    x.onload = () => {
      let j = {};
      try { j = JSON.parse(x.responseText || "{}"); } catch { /* sin cuerpo */ }
      if (x.status === 401) { salirLocal(); irA("#/entrar"); mal(new Error("La sesión venció: vuelva a entrar")); return; }
      if (x.status >= 200 && x.status < 300) ok(j);
      else mal(new Error(typeof j.detail === "string" ? j.detail : `Error ${x.status}`));
    };
    x.send(form);
  });
}

/** Foto del estudiante: se achica en el teléfono (máx. 1600 px) para subir ~300 KB en vez de ~4 MB.
    La cara sigue quedando de cientos de píxeles; el reconocimiento la lleva a 112×112 igual. */
async function achicarSelfie(file, lado = 1600) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, lado / Math.max(bmp.width, bmp.height));
    if (k === 1 && file.size < 1500000) { bmp.close(); return file; }
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height); bmp.close();
    const b = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
    return b ? new File([b], "selfie.jpg", { type: "image/jpeg" }) : file;
  } catch { return file; }    // si el navegador no puede abrirla (p. ej. HEIC en Android), se sube tal cual
}

/** Imagen protegida → URL blob (se recuerda: abrir de nuevo es instantáneo). */
async function foto(ruta) {
  if (est.fotos.has(ruta)) return est.fotos.get(ruta);
  const r = await api(ruta, { crudo: true });
  const u = URL.createObjectURL(await r.blob());
  est.fotos.set(ruta, u);
  return u;
}
function olvidarFoto(prefijo) {
  for (const [k, u] of est.fotos) if (k.startsWith(prefijo)) { URL.revokeObjectURL(u); est.fotos.delete(k); }
}
function imgDe(ruta, attrs) {
  const i = el("img", { ...attrs, loading: "lazy" });
  foto(ruta).then((u) => { i.src = u; }).catch(() => { i.alt = "Sin foto"; });
  return i;
}

function salirLocal() {
  est.token = ""; est.usuario = "";
  guardar("asis_token", ""); guardar("asis_usuario", "");
  for (const u of est.fotos.values()) URL.revokeObjectURL(u);
  est.fotos.clear();
  if (window.Asistente) Asistente.quitar();
}

function chatGeneral() {
  if (!window.Asistente || !est.token) return;
  Asistente.montar({
    personas: async () => [],
    actuar: async (pedido) => {
      if (pedido.accion === "pasar") return "Abra una clase y use «Pasar lista» con la foto del salón. El reconocimiento lo hace el sistema de siempre.";
      if (pedido.accion === "presente" || pedido.accion === "ausente") return "Eso se hace dentro de una lista ya hecha. Ábrala en Historial.";
      if (pedido.accion === "agregar" || pedido.accion === "quitar") return "Para agregar o quitar estudiantes entre a una clase, pestaña Estudiantes.";
      return "Abra una clase o una lista para que yo pueda ayudarle ahí.";
    },
  });
}

function chatDeClase(c, contenido, pestana) {
  if (!window.Asistente || !est.token) return;
  Asistente.montar();
  Asistente.contexto({
    personas: () => api(`/api/clases/${enc(c.id)}/estudiantes`).then((al) => al.map((x) => ({ id: x.codigo, nombre: x.nombre }))),
    actuar: (pedido) => actuarEnClase(c, contenido, pestana, pedido),
  });
}

async function actuarEnClase(c, contenido, pestana, pedido) {
  if (pedido.accion === "pasar") {
    if (pestana !== "lista") irA(`#/clase/${enc(c.id)}/lista`);
    return "Para pasar lista tome la foto del salón en «Pasar lista». El reconocimiento lo hace el sistema de siempre.";
  }
  if (pedido.accion === "presente" || pedido.accion === "ausente") {
    return "Eso se hace cuando ya hay una lista. Ábrala en Historial, o pase lista con la foto del salón.";
  }
  if (pedido.accion === "agregar") {
    const nombre = String(pedido.nombre || "").split(" ").filter(Boolean).map((p) => p[0].toUpperCase() + p.slice(1)).join(" ");
    return "Para agregar a " + nombre + ", use la pestaña Estudiantes y el botón de agregar con su foto. Así queda igual que siempre.";
  }
  if (pedido.accion === "quitar") {
    if (!pedido.elegidos || !pedido.elegidos.length) return "Dime a quién quitar de la clase.";
    const quitados = [];
    for (const p of pedido.elegidos) {
      await api(`/api/clases/${enc(c.id)}/estudiantes/${enc(p.id)}`, { metodo: "DELETE" });
      quitados.push(`${p.nombre} (${p.id})`);
    }
    if (pestana === "estudiantes") await pestanaEstudiantes(c, contenido);
    return `Listo. Quité a ${quitados.join(" y ")} de la clase. La foto queda guardada aparte.`;
  }
  return "No pude hacerlo.";
}

/* ------------------------------------------------------------------ rutas */
const RUTAS = [
  [/^#\/entrar$/, vistaEntrar],
  [/^#\/clases$/, vistaClases],
  [/^#\/clase\/([^/]+)\/(lista|estudiantes|historial)$/, vistaClase],
  [/^#\/lista\/([^/]+)$/, vistaLista],
];
async function enrutar() {
  if (est.sondeo) { clearTimeout(est.sondeo); est.sondeo = null; }
  const h = location.hash || "#/clases";
  if (!est.token && h !== "#/entrar") { irA("#/entrar"); return; }
  if (est.token && h === "#/entrar") { irA("#/clases"); return; }
  for (const [re, fn] of RUTAS) {
    const m = h.match(re);
    if (m) {
      try { await fn(...m.slice(1).map(decodeURIComponent)); }
      catch (e) { poner(el("main", { class: "page-shell" }, cabecera(), el("div", { style: { marginTop: "24px" } }, errorMsg(e)))); }
      return;
    }
  }
  irA("#/clases");
}
window.addEventListener("hashchange", enrutar);
enrutar();

/* ------------------------------------------------------------------ login (igual al de Vision_Computaciona_completo) */
function vistaEntrar() {
  if (window.Asistente) Asistente.quitar();
  const usuario = el("input", { type: "text", placeholder: "Ingresa tu usuario", autocomplete: "username", required: true });
  const clave = el("input", { type: "password", placeholder: "••••••••", autocomplete: "current-password", required: true });
  const ver = el("button", { type: "button", class: "ua-login-toggle", "aria-label": "Ver contraseña" }, icono("ojo", 22));
  ver.addEventListener("click", () => {
    const mostrar = clave.type === "password";
    clave.type = mostrar ? "text" : "password";
    ver.replaceChildren(icono(mostrar ? "ojoNo" : "ojo", 22));
    ver.setAttribute("aria-label", mostrar ? "Ocultar contraseña" : "Ver contraseña");
  });
  const error = el("p", { class: "ua-login-error", role: "alert", hidden: true });
  const boton = el("button", { type: "submit", class: "ua-login-submit", text: "Acceder", disabled: true });
  const revisar = () => { boton.disabled = !usuario.value.trim() || !clave.value; };
  usuario.addEventListener("input", revisar); clave.addEventListener("input", revisar);

  const form = el("form", { class: "ua-login-form", onsubmit: async (ev) => {
    ev.preventDefault();
    error.hidden = true; boton.disabled = true; boton.textContent = "Iniciando sesión…";
    try {
      const r = await api("/api/auth/entrar", { metodo: "POST", json: { usuario: usuario.value.trim(), clave: clave.value } });
      est.token = r.token; est.usuario = r.usuario.nombre;
      guardar("asis_token", r.token); guardar("asis_usuario", r.usuario.nombre);
      irA("#/clases");
    } catch (e) {
      error.textContent = e.message; error.hidden = false;
      boton.disabled = false; boton.textContent = "Acceder";
    }
  } },
    el("h1", { class: "ua-login-title", text: "Iniciar sesión" }),
    el("p", { class: "ua-login-description", text: "Docentes" }),
    el("label", { class: "ua-login-field" }, el("span", { class: "ua-login-field-label" }, icono("persona"), " Usuario"), usuario),
    el("label", { class: "ua-login-field" }, el("span", { class: "ua-login-field-label" }, icono("candado"), " Contraseña"),
      el("div", { class: "ua-login-password" }, clave, ver)),
    error, boton);

  poner(el("div", { class: "ua-login-page" },
    el("div", { class: "ua-login-card ua-login-card-left", "aria-hidden": "true" }, el("span", { text: "CLASE" })),
    el("div", { class: "ua-login-card ua-login-card-right", "aria-hidden": "true" }, el("span", { text: "LISTA" })),
    el("div", { class: "ua-login-seal", "aria-hidden": "true", text: "✓" }),
    el("main", { class: "ua-login-main" }, el("div", { class: "ua-login-content" },
      el("div", { class: "ua-login-logo-section" },
        el("img", { class: "ua-login-logo-image", src: "/marca/logouniamazonia.webp", alt: "Universidad de la Amazonia" })),
      form))));
  usuario.focus();
}

/* ------------------------------------------------------------------ cabecera */
function cabecera() {
  return el("header", { class: "topbar fade-in" },
    el("a", { class: "marca", href: "#/clases" },
      el("img", { src: "/marca/logouniamazonia-sm.webp", alt: "Universidad de la Amazonia" }),
      el("div", {}, el("div", { class: "brand marca-nombre", text: "Asistencia" }), el("div", { class: "marca-sub", text: "Universidad de la Amazonia" }))),
    el("div", { class: "row" },
      el("span", { class: "usuario-nombre", text: est.usuario }),
      el("button", { class: "btn btn-ghost btn-sm", type: "button", text: "Salir", onclick: async () => {
        try { await api("/api/auth/salir", { metodo: "POST" }); } catch { /* ya vencida */ }
        salirLocal(); irA("#/entrar");
      } })));
}

/* ------------------------------------------------------------------ mis clases */
async function vistaClases() {
  poner(cargando("Cargando tus clases…"));
  chatGeneral();
  const clases = await api("/api/clases");
  const nombre = el("input", { class: "field grow", placeholder: "Nombre de la clase (ej. Computación 2 · Grupo A)", maxlength: 120, required: true, "aria-label": "Nombre de la clase" });
  const crear = el("button", { class: "btn btn-primary", type: "submit", text: "Crear clase" });
  const error = el("p", { class: "msg msg-error", hidden: true });
  const form = el("form", { class: "row", style: { marginTop: "18px" }, onsubmit: async (ev) => {
    ev.preventDefault(); error.hidden = true; crear.disabled = true; crear.textContent = "Creando…";
    try {
      const c = await api("/api/clases", { metodo: "POST", json: { nombre: nombre.value } });
      irA(`#/clase/${enc(c.id)}/estudiantes`);
    } catch (e) { error.textContent = e.message; error.hidden = false; crear.disabled = false; crear.textContent = "Crear clase"; }
  } }, nombre, crear);

  const lista = clases.length
    ? clases.map((c, i) => el("a", { class: "glass clase-card fade-in", href: `#/clase/${enc(c.id)}/lista`, style: { animationDelay: `${60 + i * 40}ms` } },
        el("div", { class: "row" },
          el("div", { class: "grow" }, el("h2", { class: "brand h2", text: c.nombre }),
            el("p", { class: "muted small", style: { margin: "4px 0 0" }, text: `${c.estudiantes} estudiantes · ${c.listas} listas` })),
          el("span", { class: "flecha", "aria-hidden": "true", text: "→" }))))
    : [el("p", { class: "vacio fade-in", text: "Aún no hay clases. Crea la primera arriba." })];

  poner(el("main", { class: "page-shell" }, cabecera(),
    el("section", { class: "glass pad fade-in", style: { marginTop: "28px" } },
      el("h1", { class: "brand h1", text: "Tus clases" }),
      el("p", { class: "muted", style: { margin: "6px 0 0" }, text: "Entra a una clase para registrar estudiantes y pasar lista con una foto." }),
      form, error),
    el("section", { class: "stack", style: { marginTop: "18px" } }, lista)));
}

/* ------------------------------------------------------------------ campo de foto: cámara o archivo */
function campoFoto({ titulo, ayuda, camara = "environment", alCambiar = () => {} }) {
  let archivo = null, url = null;
  const vista = el("div", { class: "dropzone", role: "button", tabindex: 0, "aria-label": "Elegir foto" });
  const quitar = el("button", { class: "btn btn-ghost btn-sm", type: "button", text: "Quitar", hidden: true, onclick: () => poner_(null) });
  const enArchivo = el("input", { type: "file", accept: "image/*,.heic,.heif", class: "sr-only", tabindex: -1 });
  const enCamara = el("input", { type: "file", accept: "image/*", capture: camara, class: "sr-only", tabindex: -1 });
  const pintar = () => {
    if (url) URL.revokeObjectURL(url);
    url = archivo ? URL.createObjectURL(archivo) : null;
    vista.replaceChildren(archivo
      ? el("img", { src: url, alt: "Vista previa" })
      : el("div", { class: "dropzone-texto" }, el("div", { class: "dropzone-icono" }, icono(camara === "user" ? "persona" : "imagen", 40)),
          el("p", { class: "brand", style: { margin: "6px 0 0", fontSize: "1.15rem" }, text: camara === "user" ? "Foto del estudiante" : "Foto del salón" }),
          el("p", { class: "muted xs", style: { margin: "2px 0 0" }, text: "Tome la foto o arrástrela aquí" })));
    quitar.hidden = !archivo;
  };
  const poner_ = (f) => {
    if (f && !(f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name))) { toast("Ese archivo no es una foto"); return; }
    archivo = f; pintar(); alCambiar(archivo);
  };
  for (const inp of [enArchivo, enCamara]) inp.addEventListener("change", () => { poner_(inp.files[0] || null); inp.value = ""; });
  const tomar = async () => {
    if (esTactil || !(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) { enCamara.click(); return; }
    const f = await camaraEnVivo(camara);
    if (f) poner_(f);
  };
  vista.addEventListener("click", () => (archivo ? null : tomar()));
  vista.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); tomar(); } });
  vista.addEventListener("dragover", (ev) => { ev.preventDefault(); vista.dataset.activa = "true"; });
  vista.addEventListener("dragleave", () => { vista.dataset.activa = "false"; });
  vista.addEventListener("drop", (ev) => { ev.preventDefault(); vista.dataset.activa = "false"; poner_(ev.dataTransfer.files[0] || null); });
  pintar();
  const nodo = el("div", { class: "stack" },
    el("div", { class: "row" }, el("div", { class: "grow" }, el("p", { class: "brand", style: { margin: 0 }, text: titulo }), el("p", { class: "muted xs", style: { margin: 0 }, text: ayuda })), quitar),
    vista,
    el("div", { class: "grid2" },
      el("button", { class: "btn btn-dark", type: "button", onclick: tomar }, icono("camara"), "Tomar foto"),
      el("button", { class: "btn btn-ghost", type: "button", onclick: () => enArchivo.click() }, icono("imagen"), "Galería / Archivo")),
    enArchivo, enCamara);
  return { nodo, get archivo() { return archivo; }, limpiar: () => poner_(null) };
}

/** Cámara del computador dentro de la página (en el celular se usa la cámara del teléfono). */
function camaraEnVivo(modo) {
  return new Promise((resolver) => {
    let stream = null;
    const video = el("video", { autoplay: true, playsinline: true, muted: true, class: modo === "user" ? "espejo" : "" });
    const estado = el("span", { class: "muted small", text: "Abriendo la cámara…" });
    const capturar = el("button", { class: "btn btn-primary", type: "button", disabled: true }, icono("camara"), "Capturar");
    const cerrar = (f) => {
      if (stream) stream.getTracks().forEach((t) => t.stop());
      modal.remove(); document.removeEventListener("keydown", tecla); resolver(f);
    };
    const tecla = (ev) => { if (ev.key === "Escape") cerrar(null); };
    capturar.addEventListener("click", () => {
      const c = document.createElement("canvas");
      c.width = video.videoWidth; c.height = video.videoHeight;
      c.getContext("2d").drawImage(video, 0, 0);
      c.toBlob((b) => cerrar(b ? new File([b], `camara_${Date.now()}.jpg`, { type: "image/jpeg" }) : null), "image/jpeg", 0.92);
    });
    const modal = el("div", { class: "modal", onclick: (ev) => { if (ev.target === modal) cerrar(null); } },
      el("div", { class: "modal-caja" }, video,
        el("div", { class: "modal-pie" }, estado,
          el("div", { class: "row" }, el("button", { class: "btn btn-ghost", type: "button", text: "Cancelar", onclick: () => cerrar(null) }), capturar))));
    document.body.append(modal);
    document.addEventListener("keydown", tecla);
    navigator.mediaDevices.getUserMedia({ video: { facingMode: modo, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then((s) => { stream = s; video.srcObject = s; estado.textContent = modo === "user" ? "Que mire a la cámara, de frente" : "Que se vean todas las caras"; capturar.disabled = false; })
      .catch(() => { estado.textContent = "No se pudo abrir la cámara. Use «Galería / Archivo»."; });
  });
}

/** Ver una foto en grande. */
function verFoto(ruta, titulo) {
  const img = el("img", { alt: titulo });
  foto(ruta).then((u) => { img.src = u; }).catch(() => {});
  const cerrar = () => { modal.remove(); document.removeEventListener("keydown", tecla); };
  const tecla = (ev) => { if (ev.key === "Escape") cerrar(); };
  const modal = el("div", { class: "modal", onclick: (ev) => { if (ev.target === modal) cerrar(); } },
    el("div", { class: "modal-caja" }, img, el("div", { class: "modal-pie" }, el("strong", { text: titulo }),
      el("button", { class: "btn btn-dark btn-sm", type: "button", text: "Cerrar", onclick: cerrar }))));
  document.body.append(modal); document.addEventListener("keydown", tecla);
}

/* ------------------------------------------------------------------ una clase */
async function vistaClase(id, pestana) {
  poner(cargando());
  const c = await api(`/api/clases/${enc(id)}`);
  const pest = (clave, texto) => el("a", { class: "tab", href: `#/clase/${enc(id)}/${clave}`, text: texto, "aria-current": pestana === clave ? "page" : null });
  const contenido = el("section", { style: { marginTop: "18px" } });
  poner(el("main", { class: "page-shell" }, cabecera(),
    el("div", { class: "fade-in", style: { marginTop: "22px" } },
      el("a", { class: "back", href: "#/clases", text: "← Mis clases" }),
      el("h1", { class: "brand h1", style: { marginTop: "6px" }, text: c.nombre }),
      el("p", { class: "muted small", style: { margin: "4px 0 0" }, text: `${c.estudiantes} estudiantes · ${c.listas} listas` })),
    el("nav", { class: "tabs fade-in", style: { marginTop: "18px" }, "aria-label": "Secciones" },
      pest("lista", "Pasar lista"), pest("estudiantes", "Estudiantes"), pest("historial", "Historial")),
    contenido));
  if (pestana === "lista") pestanaPasar(c, contenido);
  else if (pestana === "estudiantes") await pestanaEstudiantes(c, contenido);
  else await pestanaHistorial(c, contenido);
  chatDeClase(c, contenido, pestana);
}

function pestanaPasar(c, cont) {
  const boton = el("button", { class: "btn btn-primary btn-block", type: "submit", text: "Pasar lista", disabled: true });
  const campo = campoFoto({ titulo: "Foto del salón", ayuda: "Que se vean las caras de todos, mirando a la cámara", camara: "environment",
    alCambiar: (f) => { boton.disabled = !f; } });
  const error = el("p", { class: "msg msg-error", hidden: true });
  const form = el("form", { class: "glass pad stack fade-in", onsubmit: async (ev) => {
    ev.preventDefault(); if (!campo.archivo) return;
    error.hidden = true; boton.disabled = true; boton.textContent = "Subiendo foto…";
    const fd = new FormData(); fd.append("foto", campo.archivo, campo.archivo.name || "foto.jpg");
    try {
      const a = await subir(`/api/clases/${enc(c.id)}/asistencias`, fd, (p) => { boton.textContent = p < 100 ? `Subiendo foto… ${p} %` : "Enviada, reconociendo…"; });
      irA(`#/lista/${enc(a.id)}`);
    } catch (e) { error.textContent = e.message; error.hidden = false; boton.disabled = false; boton.textContent = "Pasar lista"; }
  } },
    el("div", {}, el("h2", { class: "brand h2", text: "Pasar lista ahora" }),
      el("p", { class: "muted small", style: { margin: "4px 0 0" }, text: "Tome una foto del salón: el sistema reconoce a cada estudiante y arma la lista." })),
    c.estudiantes ? null : el("p", { class: "msg msg-warn", text: "Esta clase todavía no tiene estudiantes: regístrelos en la pestaña Estudiantes." }),
    campo.nodo, error, boton,
    el("p", { class: "muted xs", style: { margin: 0 }, text: "Consejo: si la foto llega por WhatsApp, mándela como documento (sin comprimir) para que se reconozcan mejor las caras del fondo." }));
  cont.replaceChildren(form);
  // ¿alguien sin huella? (no frena: al pasar lista el servidor saca las que falten)
  api(`/api/clases/${enc(c.id)}/estudiantes`).then((al) => {
    const malos = al.filter((x) => x.huella === "sin_cara" || x.huella === "sin_foto" || x.huella === "error_servidor");
    const prep = al.filter((x) => x.huella === "procesando").length;
    const avisos = [];
    if (malos.length) avisos.push(el("p", { class: "msg msg-error", text: `Sin huella (su foto no sirve, cámbiela en Estudiantes): ${malos.map((x) => x.nombre).join(", ")}` }));
    if (prep) avisos.push(el("p", { class: "msg msg-ok", text: `Preparando la huella de ${prep} estudiante${prep > 1 ? "s" : ""}… (se termina sola, puede pasar lista igual)` }));
    if (avisos.length && form.isConnected) form.firstChild.after(...avisos);
  }).catch(() => {});
}

async function pestanaEstudiantes(c, cont) {
  cont.replaceChildren(el("div", { class: "glass pad row" }, el("div", { class: "rueda" }), el("span", { class: "muted", text: "Cargando estudiantes…" })));
  const alumnos = await api(`/api/clases/${enc(c.id)}/estudiantes`);
  const recargar = () => pestanaEstudiantes(c, cont);

  // Solo foto y nombre: el código lo pone el sistema por dentro.
  const nombre = el("input", { class: "field", id: "est-nombre", maxlength: 160, placeholder: "Nombres y apellidos", autocomplete: "off" });
  const boton = el("button", { class: "btn btn-primary btn-block", type: "submit", text: "Registrar estudiante", disabled: true });
  const revisar = () => { boton.disabled = !campo.archivo || !nombre.value.trim(); };
  const campo = campoFoto({ titulo: "Foto del estudiante", ayuda: "De frente, cara completa, buena luz, sin filtro", camara: "user", alCambiar: revisar });
  nombre.addEventListener("input", revisar);
  const error = el("p", { class: "msg msg-error", hidden: true });
  const form = el("form", { class: "glass pad stack fade-in", onsubmit: async (ev) => {
    ev.preventDefault(); error.hidden = true; boton.disabled = true; boton.textContent = "Preparando foto…";
    const fd = new FormData();
    fd.append("nombre", nombre.value.trim());
    const f = await achicarSelfie(campo.archivo);
    fd.append("selfie", f, f.name || "selfie.jpg");
    try {
      const e = await subir(`/api/clases/${enc(c.id)}/estudiantes`, fd, (p) => { boton.textContent = p < 100 ? `Subiendo… ${p} %` : "Guardando…"; });
      toast(`Foto subida con éxito · ${e.nombre}`);
      recargar();
    } catch (e) { error.textContent = e.message; error.hidden = false; boton.textContent = "Registrar estudiante"; revisar(); }
  } },
    el("h2", { class: "brand h2", text: "Registrar estudiante" }),
    campo.nodo,
    el("div", {}, el("label", { class: "label", for: "est-nombre", text: "Nombre" }), nombre),
    error, boton);

  const estados = new Map();          // código → cambia el estado de su huella sin recargar la página
  const tarjetas = alumnos.map((a) => tarjetaAlumno(c, a, recargar, estados));
  const resumen = el("p", { class: "muted small", style: { margin: "4px 0 0" } });
  const pintarResumen = (al) => {
    const n = (h) => al.filter((x) => x.huella === h).length;
    resumen.textContent = `${n("lista")} con huella` + (n("procesando") ? ` · ${n("procesando")} procesando` : "")
      + (n("sin_cara") + n("sin_foto") ? ` · ${n("sin_cara") + n("sin_foto")} sin huella (foto que no sirve)` : "")
      + (n("error_servidor") ? ` · ${n("error_servidor")} con error del servidor (se reintenta)` : "");
  };
  pintarResumen(alumnos);
  cont.replaceChildren(el("div", { class: "stack" }, form,
    el("section", { class: "glass pad fade-in" },
      el("h2", { class: "brand h2", text: `Estudiantes (${alumnos.length})` }), resumen,
      alumnos.length ? el("div", { class: "alumnos", style: { marginTop: "14px" } }, tarjetas)
        : el("p", { class: "vacio", style: { marginTop: "14px" }, text: "Todavía no hay estudiantes. Registre el primero arriba." }))));
  // mientras alguna huella se esté procesando, se actualiza sola
  const ruta = location.hash;
  const seguir = async () => {
    if (location.hash !== ruta || !cont.isConnected) return;
    try {
      const al = await api(`/api/clases/${enc(c.id)}/estudiantes`);
      for (const a of al) if (estados.has(a.codigo)) estados.get(a.codigo)(a);
      pintarResumen(al);
      if (al.some((a) => a.huella === "procesando" || a.huella === "error_servidor")) est.sondeo = setTimeout(seguir, 3000);
    } catch { est.sondeo = setTimeout(seguir, 5000); }
  };
  if (alumnos.some((a) => a.huella === "procesando" || a.huella === "error_servidor")) est.sondeo = setTimeout(seguir, 2000);
}

function chipHuella(a) {
  if (a.huella === "lista") return el("span", { class: "chip chip-ok", text: "Huella lista" });
  if (a.huella === "procesando") return el("span", { class: "chip chip-warn", text: "Procesando huella…" });
  if (a.huella === "sin_foto") return el("span", { class: "chip chip-bad", text: "Falta la foto" });
  if (a.huella === "sin_cara") return el("span", { class: "chip chip-bad", title: a.huella_error || "", text: "La foto no sirve: tome otra" });
  if (a.huella === "error_servidor") return el("span", {},
    el("span", { class: "chip chip-bad", text: "No se pudo sacar la huella (se reintenta sola)" }),
    el("span", { class: "muted xs", style: { display: "block", marginTop: "2px", wordBreak: "break-word" }, text: a.huella_error || "" }));
  return el("span", { class: "chip chip-warn", text: "Procesando huella…" });   // estado desconocido: nunca acusar a la foto
}

function tarjetaAlumno(c, a, recargar, estados) {
  const ruta = `/api/clases/${enc(c.id)}/estudiantes/${enc(a.codigo)}`;
  const rutaFoto = `${ruta}/selfie?v=${enc(a.actualizado || "")}`;
  const cambiar = el("input", { type: "file", accept: "image/*,.heic,.heif", capture: "user", class: "sr-only", tabindex: -1, onchange: async () => {
    const f0 = cambiar.files[0]; cambiar.value = ""; if (!f0) return;
    const f = await achicarSelfie(f0);
    const fd = new FormData(); fd.append("selfie", f, f.name || "selfie.jpg");
    toast("Subiendo foto…", 20000);
    try { await api(ruta, { metodo: "PATCH", form: fd }); olvidarFoto(ruta); toast("Foto subida con éxito"); recargar(); } catch (e) { toast(e.message, 6000); }
  } });
  const estado = el("div", { style: { marginTop: "4px" } }, chipHuella(a));
  if (estados) estados.set(a.codigo, (nuevo) => estado.replaceChildren(chipHuella(nuevo)));
  return el("div", { class: "alumno" },
    a.tiene_selfie ? imgDe(rutaFoto, { class: "foto", alt: "" }) : el("div", { class: "foto" }),
    el("div", { class: "grow", style: { minWidth: 0 } },
      el("div", { class: "nombre", text: a.nombre }),
      estado,
      el("div", { class: "row", style: { gap: "14px", marginTop: "2px" } },
        el("button", { class: "link-btn verde", type: "button", text: "Cambiar foto", onclick: () => cambiar.click() }),
        el("button", { class: "link-btn rojo", type: "button", text: "Quitar", onclick: async () => {
          if (!confirm(`¿Quitar a ${a.nombre} de la clase? (Su foto se guarda aparte por si acaso.)`)) return;
          try { await api(ruta, { metodo: "DELETE" }); toast("Estudiante quitado"); recargar(); } catch (e) { toast(e.message); }
        } }))),
    a.tiene_selfie ? el("button", { class: "icon-btn", type: "button", title: "Ver foto", "aria-label": `Ver foto de ${a.nombre}`, onclick: () => verFoto(rutaFoto, a.nombre) }, icono("ojo", 22)) : null,
    cambiar);
}

async function pestanaHistorial(c, cont) {
  cont.replaceChildren(el("div", { class: "glass pad row" }, el("div", { class: "rueda" }), el("span", { class: "muted", text: "Cargando listas…" })));
  const listas = await api(`/api/clases/${enc(c.id)}/asistencias`);
  if (!listas.length) { cont.replaceChildren(el("p", { class: "vacio", text: "Aún no hay listas. Pase la primera en «Pasar lista»." })); return; }
  cont.replaceChildren(el("div", { class: "stack" }, listas.map((a, i) => el("a", { class: "glass clase-card fade-in", href: `#/lista/${enc(a.id)}`, style: { animationDelay: `${i * 30}ms` } },
    el("div", { class: "row" },
      el("div", { class: "grow" },
        el("p", { class: "brand", style: { margin: 0, fontSize: "1.1rem" }, text: primeraMayus(fechaLarga(a.creada)) }),
        el("div", { class: "row", style: { gap: "6px", marginTop: "6px" } },
          a.estado === "lista" ? [
            el("span", { class: "chip chip-ok", text: `${a.presentes} presentes` }),
            a.por_revisar ? el("span", { class: "chip chip-warn", text: `${a.por_revisar} por revisar` }) : null,
            el("span", { class: "chip chip-bad", text: `${a.ausentes} ausentes` }),
          ] : el("span", { class: a.estado === "error" ? "chip chip-bad" : "chip chip-gris", text: a.estado === "error" ? "no se pudo" : "procesando…" }),
          a.de_la_ventana ? el("span", { class: "chip chip-gris", text: "desde el computador" }) : null)),
      el("span", { class: "flecha", "aria-hidden": "true", text: "→" }))))));
}

function primeraMayus(t) { return t ? t[0].toUpperCase() + t.slice(1) : t; }

/* ------------------------------------------------------------------ una lista */
async function vistaLista(id) {
  poner(cargando("Cargando lista…"));
  chatGeneral();
  const a = await api(`/api/asistencias/${enc(id)}`);
  const volver = el("a", { class: "back", href: `#/clase/${enc(a.clase_id)}/lista`, text: `← ${a.clase}` });
  if (a.estado === "procesando") return esperar(a, volver);
  if (a.estado === "error") {
    poner(el("main", { class: "page-shell" }, cabecera(), el("div", { class: "stack", style: { marginTop: "22px" } }, volver,
      el("section", { class: "glass pad stack" }, el("h1", { class: "brand h2", text: "No se pudo pasar lista" }), errorMsg(new Error(a.error || "Error")),
        el("div", { class: "row" },
          el("a", { class: "btn btn-primary", href: `#/clase/${enc(a.clase_id)}/lista`, text: "Intentar con otra foto" }),
          el("button", { class: "btn btn-danger", type: "button", text: "Descartar", onclick: () => borrarLista(a) }))))));
    chatGeneral();
    return;
  }
  mostrarLista(a, volver);
}

function esperar(a, volver) {
  const inicio = Date.parse(a.creada) || Date.now();
  const texto = el("span", { class: "brand" });
  const tic = () => { texto.textContent = `Reconociendo caras… ${Math.max(0, Math.round((Date.now() - inicio) / 1000))} s`; };
  tic();
  poner(el("main", { class: "page-shell" }, cabecera(), el("div", { class: "stack", style: { marginTop: "22px" } }, volver,
    el("section", { class: "glass pad stack fade-in" },
      el("div", { class: "row" }, el("div", { class: "rueda" }), texto),
      el("div", { class: "barra-progreso" }, el("span")),
      el("p", { class: "muted small", style: { margin: 0 }, text: "Suele tardar menos de un minuto. Puede salir de aquí: la lista queda en el Historial." })))));
  const ruta = location.hash;
  const sondear = async () => {
    tic();
    try { const b = await api(`/api/asistencias/${enc(a.id)}`); if (location.hash !== ruta) return; if (b.estado !== "procesando") { enrutar(); return; } }
    catch { /* reintenta */ }
    est.sondeo = setTimeout(sondear, 2500);
  };
  est.sondeo = setTimeout(sondear, 2500);
}

async function borrarLista(a) {
  if (!confirm("¿Borrar esta lista? (Se guarda una copia aparte por si acaso.)")) return;
  try { await api(`/api/asistencias/${enc(a.id)}`, { metodo: "DELETE" }); toast("Lista borrada"); irA(`#/clase/${enc(a.clase_id)}/historial`); }
  catch (e) { toast(e.message); }
}

const claseDe = (r) => (r.estado === "presente" ? "presente" : r.revisar ? "revisar" : "ausente");

function mostrarLista(a, volver) {
  const regs = a.registros;
  const selfie = (r) => `/api/clases/${enc(a.clase_id)}/estudiantes/${enc(r.codigo)}/selfie`;
  const img = el("img", { alt: "Foto del salón" });
  const marco = el("div", { class: "foto-marco" }, img);
  const conteo = el("div", { class: "row", style: { gap: "6px" } });
  const zonaAvisos = el("div", { class: "stack" });
  const zonaRevisar = el("div");
  const zonaFilas = el("ul", { class: "filas" });
  const zonaFicha = el("div");          // al tocar una cara: su cara en la foto + su foto registrada
  let elegido = null;
  let verCaras = true;                  // «Ver sin caras» solo esconde los recuadros; no cambia nada guardado

  async function cambiar(r, estado) {
    try {
      const nuevo = await api(`/api/asistencias/${enc(a.id)}/registros/${enc(r.codigo)}`, { metodo: "PATCH", json: { estado } });
      Object.assign(r, nuevo);
      toast(`${r.nombre}: ${estado}`);
      pintar();
    } catch (e) { toast(e.message, 5000); }
  }

  function recorte(bb) {
    const c = el("canvas", { width: 240, height: 240, "aria-label": "Cara en la foto" });
    const dibujar = () => {
      const [x1, y1, x2, y2] = bb;
      const lado = Math.max(x2 - x1, y2 - y1) * 1.9, cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
      const g = c.getContext("2d"); g.imageSmoothingQuality = "high";
      g.fillStyle = "#111"; g.fillRect(0, 0, 240, 240);
      g.drawImage(img, cx - lado / 2, cy - lado / 2, lado, lado, 0, 0, 240, 240);
    };
    if (img.complete && img.naturalWidth) dibujar(); else img.addEventListener("load", dibujar, { once: true });
    return c;
  }

  function pintarConteo() {
    const p = regs.filter((r) => claseDe(r) === "presente").length, v = regs.filter((r) => claseDe(r) === "revisar").length;
    conteo.replaceChildren(...[el("span", { class: "chip chip-ok", text: `${p} presentes` }),
      v ? el("span", { class: "chip chip-warn", text: `${v} por revisar` }) : null,
      el("span", { class: "chip chip-bad", text: `${regs.length - p - v} ausentes` }),
      el("span", { class: "chip chip-gris", text: `${a.rostros ?? 0} caras en la foto` })].filter(Boolean));   // sin «null» en pantalla
  }

  function pintarCajas() {
    marco.querySelectorAll(".caja").forEach((n) => n.remove());
    if (!a.ancho && img.naturalWidth) { a.ancho = img.naturalWidth; a.alto = img.naturalHeight; }
    if (!a.ancho || !verCaras) return;
    const usadas = new Set();
    const caja = (bb, tipo, etiqueta, alElegir, activa) => {
      const [x1, y1, x2, y2] = bb;
      const lado = (x1 / a.ancho > 0.55 ? " derecha" : "") + (y1 / a.alto < 0.08 ? " abajo" : "");   // el nombre no se sale de la foto
      marco.append(el("button", { class: `caja caja-${tipo}${activa ? " activa" : ""}${lado}`, type: "button", title: etiqueta, "aria-label": etiqueta, onclick: alElegir,
        style: { left: `${(100 * x1) / a.ancho}%`, top: `${(100 * y1) / a.alto}%`, width: `${(100 * (x2 - x1)) / a.ancho}%`, height: `${(100 * (y2 - y1)) / a.alto}%` } },
        activa ? el("span", { class: "caja-nombre", text: etiqueta }) : null));
    };
    const llave = (bb) => bb.slice(0, 4).map((v) => Number(v).toFixed(1)).join();
    for (const r of regs) {
      const t = claseDe(r);
      if (!r.bbox || t === "ausente") continue;
      usadas.add(llave(r.bbox));
      caja(r.bbox, t, t === "revisar" ? `¿${r.nombre}?` : r.nombre, () => elegir(r), elegido === r);
    }
    (a.detecciones || []).forEach((d, i) => {
      if (!d.bbox || d.bbox[0] === null || usadas.has(llave(d.bbox))) return;
      caja(d.bbox, "desconocida", `Cara ${i + 1}: sin nombre`, () => toast("Esa cara no se parece lo suficiente a nadie de la lista"), false);
    });
  }

  function pintarRevisar() {
    const rev = regs.filter((r) => claseDe(r) === "revisar");
    if (!rev.length) { zonaRevisar.replaceChildren(); return; }
    zonaRevisar.replaceChildren(el("section", { class: "glass pad stack fade-in" },
      el("div", {}, el("h2", { class: "brand h2", text: "¿Están en la foto?" }),
        el("p", { class: "muted small", style: { margin: "4px 0 0" }, text: "Caras lejanas o de lado que se parecen a estos estudiantes. Compare y confirme." })),
      el("div", { class: "grid2" }, rev.map((r) => el("div", { class: "revisar-card" },
        el("figure", {}, recorte(r.bbox), el("figcaption", { text: "En la foto" })),
        el("figure", {}, imgDe(selfie(r), { alt: `Foto de ${r.nombre}` }), el("figcaption", { text: "Su foto" })),
        el("div", { class: "pie stack" },
          el("p", { class: "brand", style: { margin: 0, textAlign: "center" }, text: `¿Es ${r.nombre}?` }),
          el("div", { class: "grid2", style: { gridTemplateColumns: "1fr 1fr" } },
            el("button", { class: "btn btn-ok", type: "button", text: "Sí, está", onclick: () => cambiar(r, "presente") }),
            el("button", { class: "btn btn-ghost", type: "button", text: "No", onclick: () => cambiar(r, "ausente") }))))))));
  }

  function pintarFilas() {
    const orden = { presente: 0, revisar: 1, ausente: 2 };
    const filas = [...regs].sort((x, y) => orden[claseDe(x)] - orden[claseDe(y)] || String(x.nombre).localeCompare(String(y.nombre)));
    zonaFilas.replaceChildren(...filas.map((r) => {
      const t = claseDe(r);
      const otro = r.estado === "presente" ? "ausente" : "presente";
      return el("li", { class: `fila fila-${t}${elegido === r ? " activa" : ""}` },
        imgDe(selfie(r), { class: "foto", alt: "" }),
        el("div", { class: "info" },
          el("div", { class: "nombre", text: r.nombre }),
          el("div", { class: "estado", text: t === "presente" ? "Presente" : t === "revisar" ? "¿Revisar?" : "Ausente" }),
          // Solo si está o no; la nota y las sugerencias no se muestran. Únicamente se avisa si no tiene foto válida.
          String(r.motivo || "").startsWith("registro_fallo") ? el("div", { class: "muted xs", text: "sin huella: su foto no sirve, tómele otra" })
            : String(r.motivo || "").startsWith("sin_foto") ? el("div", { class: "muted xs", text: "no tiene foto registrada" }) : null),
        r.bbox && t !== "ausente" ? el("button", { class: "icon-btn", type: "button", title: "Ver en la foto", "aria-label": `Ver a ${r.nombre} en la foto`, onclick: () => { elegir(r); marco.scrollIntoView({ behavior: "smooth", block: "center" }); } }, icono("foco", 20)) : null,
        el("button", { class: `btn btn-sm ${otro === "presente" ? "btn-ok" : "btn-danger"}`, type: "button", text: otro === "presente" ? "Poner presente" : "Poner ausente", onclick: () => cambiar(r, otro) }));
    }));
  }

  function pintarFicha() {
    const r = elegido;
    if (!r || !r.bbox || !verCaras) { zonaFicha.replaceChildren(); return; }
    const t = claseDe(r);
    zonaFicha.replaceChildren(el("div", { class: `ficha-cara ficha-${t} fade-in` },
      el("figure", {}, recorte(r.bbox), el("figcaption", { text: "En la foto" })),
      el("figure", {}, imgDe(selfie(r), { alt: `Foto de ${r.nombre}` }), el("figcaption", { text: "Su foto" })),
      el("div", { class: "pie row" },
        el("div", { class: "grow" },
          el("div", { class: "brand", style: { fontSize: "1.1rem" }, text: r.nombre }),
          el("div", { class: "estado-ficha", text: t === "presente" ? "Presente" : t === "revisar" ? "¿Es esta persona? Confírmelo abajo" : "Ausente" })),
        el("button", { class: "btn btn-ghost btn-sm", type: "button", text: "Cerrar", onclick: () => elegir(r) }))));
  }
  const botonCaras = el("button", { class: "btn btn-ghost btn-sm", type: "button", "aria-pressed": "false", onclick: () => {
    verCaras = !verCaras;
    if (!verCaras) elegido = null;
    pintarCajas(); pintarFilas(); pintarFicha(); pintarBotonCaras();
  } });
  function pintarBotonCaras() {
    botonCaras.replaceChildren(icono(verCaras ? "ojoNo" : "ojo", 18), verCaras ? "Ver sin caras" : "Ver con caras");
    botonCaras.setAttribute("aria-pressed", String(!verCaras));
  }
  function elegir(r) {
    elegido = elegido === r ? null : r;
    if (elegido) verCaras = true;       // si estaban ocultas, al elegir a alguien vuelven
    pintarCajas(); pintarFilas(); pintarFicha(); pintarBotonCaras();
  }
  function pintarAvisos() {
    const v = regs.filter((r) => claseDe(r) === "revisar").length;
    const avisos = [];
    if (v) avisos.push(el("p", { class: "msg msg-warn", text: `${v === 1 ? "1 cara (lejana o de lado) se parece" : `${v} caras (lejanas o de lado) se parecen`} a estudiantes de la lista: confírmelo abajo en «¿Están en la foto?».`
      + (a.lado_foto && a.lado_foto <= 1600 ? ` La foto llegó comprimida (${a.lado_foto} px): mándela como documento para que salgan solas.` : "") }));
    if (a.de_la_ventana) avisos.push(el("p", { class: "msg msg-ok", text: "Esta lista se hizo desde el programa del computador." }));
    zonaAvisos.replaceChildren(...avisos);
  }
  function pintar() { pintarConteo(); pintarAvisos(); pintarCajas(); pintarRevisar(); pintarFilas(); pintarFicha(); pintarBotonCaras(); }

  const descargar = el("button", { class: "btn btn-ghost btn-sm", type: "button", text: "Descargar lista", onclick: async () => {
    try {
      const r = await api(`/api/asistencias/${enc(a.id)}/excel`, { crudo: true });
      const u = URL.createObjectURL(await r.blob());
      const link = el("a", { href: u, download: a.id }); document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(u), 4000);
    } catch (e) { toast(e.message); }
  } });

  poner(el("main", { class: "page-shell" }, cabecera(),
    el("div", { class: "fade-in", style: { marginTop: "22px" } }, volver,
      el("h1", { class: "brand h1", style: { marginTop: "6px" }, text: fechaCorta(a.creada) }),
      el("p", { class: "muted small", style: { margin: "2px 0 10px" }, text: primeraMayus(fechaLarga(a.creada)) }),
      el("div", { class: "row", style: { gap: "8px" } }, descargar, botonCaras,
        el("button", { class: "btn btn-danger btn-sm", type: "button", text: "Borrar", onclick: () => borrarLista(a) }))),
    el("div", { class: "stack", style: { marginTop: "14px" } }, conteo, zonaAvisos,
      el("section", { class: "glass pad stack fade-in" }, marco, zonaFicha,
        el("p", { class: "muted xs", style: { margin: 0, textAlign: "center" }, text: "Verde: presente · Amarillo: por revisar · Toque una cara para ver quién es" })),
      zonaRevisar,
      el("section", { class: "glass pad stack fade-in" }, el("h2", { class: "brand h2", text: "Lista" }), zonaFilas))));
  pintar();
  img.addEventListener("load", pintarCajas, { once: true });
  foto(`/api/asistencias/${enc(a.id)}/foto`).then((u) => { img.src = u; }).catch((e) => marco.replaceWith(errorMsg(e)));
  chatDeLista(a, regs, pintar);
}

function chatDeLista(a, regs, pintar) {
  if (!window.Asistente || !est.token) return;
  Asistente.montar();
  Asistente.contexto({
    personas: () => regs.map((r) => ({ id: r.codigo, nombre: r.nombre })),
    actuar: async (pedido) => {
      if (pedido.accion === "pasar") return "Esta lista ya fue realizada. Puede decir: pon a Ana como presente.";
      if (pedido.accion === "agregar" || pedido.accion === "quitar") {
        return "Para agregar o quitar un estudiante vuelva a la clase, pestaña Estudiantes. Aquí solo cambio presentes y ausentes.";
      }
      if (pedido.accion !== "presente" && pedido.accion !== "ausente") return "No pude hacerlo.";
      const tocados = [];
      for (const p of pedido.elegidos) {
        const r = regs.find((x) => x.codigo === p.id);
        if (!r) return `No encontré a ${p.nombre} en esta lista.`;
        const nuevo = await api(`/api/asistencias/${enc(a.id)}/registros/${enc(r.codigo)}`, { metodo: "PATCH", json: { estado: pedido.accion } });
        Object.assign(r, nuevo);
        tocados.push(`${r.nombre} (${r.codigo})`);
      }
      pintar();
      const verbo = pedido.accion === "presente" ? "presente" : "ausente";
      return tocados.length > 1
        ? `Listo. ${tocados.join(" y ")} quedaron ${verbo}s.`
        : `Listo. ${tocados[0]} quedó ${verbo}.`;
    },
  });
}
