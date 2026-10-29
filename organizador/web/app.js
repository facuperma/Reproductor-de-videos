// TVon ON: la app del celular. Habla con el servidor que levanta TVon en la PC (organizador/remoto.py).
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const app = {
  pestana: "reproductor",
  estado: null,
  biblioteca: null,
  filtro: { filtro: "todos", categoria: null },
  archivos: [],
  seleccion: new Set(),
  eligiendo: false,
  peliculas: { q: "", orden: "populares", pagina: 1, lista: [], total: 0 },
  arrastrandoBarra: false,
};

// --- Conexión con la PC -------------------------------------------------------------

class ErrorApi extends Error {
  constructor(mensaje, codigo) { super(mensaje); this.codigo = codigo; }
}

async function api(ruta, cuerpo) {
  const opciones = cuerpo === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-TVon": "1" },
    body: JSON.stringify(cuerpo),
  };
  let r;
  try {
    r = await fetch(ruta, { cache: "no-store", ...opciones });
  } catch {
    marcarConexion(false);
    throw new ErrorApi("No hay conexión con la PC. ¿TVon está abierto y con ON encendido?", 0);
  }
  marcarConexion(true);
  if (r.status === 401) {
    mostrarEmparejar();
    throw new ErrorApi("Este celular no está conectado", 401);
  }
  if (r.status === 204) return null;
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErrorApi(datos.error || `Error ${r.status}`, r.status);
  return datos;
}

async function accion(nombre, datos = {}) {
  try {
    const r = await api("/api/accion", { accion: nombre, ...datos });
    if (r && r.aviso) tostada(r.aviso);
    refrescarEstado();
    return r;
  } catch (e) {
    if (e.codigo !== 401) tostada(e.message, true);
    throw e;
  }
}

function marcarConexion(ok) {
  $("#conexion").classList.toggle("caida", !ok);
}

function mostrarEmparejar(texto) {
  $("#app").hidden = true;
  $("#emparejar").hidden = false;
  if (texto) $("#emparejar-texto").textContent = texto;
}

async function emparejar() {
  const params = new URLSearchParams(location.search);
  const codigo = params.get("c");
  if (codigo) {
    // El código no queda en el historial ni en la barra de direcciones
    history.replaceState(null, "", location.pathname + location.hash);
    try {
      await api("/api/emparejar", { codigo });
    } catch (e) {
      mostrarEmparejar(e.message);
      return false;
    }
  }
  return true;
}

// --- Avisos ------------------------------------------------------------------------------

let reloj_tostada;
function tostada(texto, mala = false) {
  const t = $("#tostada");
  t.textContent = texto;
  t.classList.toggle("mala", mala);
  t.hidden = false;
  clearTimeout(reloj_tostada);
  reloj_tostada = setTimeout(() => { t.hidden = true; }, mala ? 5000 : 3000);
}

// --- Hoja de acciones -------------------------------------------------------------------

function abrirHoja(titulo, opciones) {
  $("#hoja-titulo").textContent = titulo;
  const cuerpo = $("#hoja-cuerpo");
  cuerpo.replaceChildren();
  for (const o of opciones) {
    if (o.elemento) { cuerpo.append(o.elemento); continue; }
    const b = document.createElement("button");
    b.className = "hoja-boton" + (o.peligro ? " peligro" : "");
    b.textContent = o.texto;
    if (o.marca) {
      const m = document.createElement("span");
      m.className = "marca";
      m.textContent = o.marca;
      b.append(m);
    }
    b.addEventListener("click", async () => {
      if (o.confirmar && !confirm(o.confirmar)) return;
      if (!o.dejarAbierta) cerrarHoja();
      try { await o.hacer(); } catch { /* ya se avisó */ }
    });
    cuerpo.append(b);
  }
  $("#velo").hidden = false;
  $("#hoja").hidden = false;
}

function cerrarHoja() {
  $("#velo").hidden = true;
  $("#hoja").hidden = true;
}

function pedirTexto(titulo, inicial = "") {
  const valor = prompt(titulo, inicial);
  return valor === null ? null : valor.trim() || null;
}

// --- Pestañas -------------------------------------------------------------------------------

function irA(pestana) {
  if (app.pestana === "pantalla" && pestana !== "pantalla") dejarDeVer();
  app.pestana = pestana;
  for (const b of $$(".pestanas button")) b.classList.toggle("activa", b.dataset.pestana === pestana);
  for (const s of $$(".pestana")) s.hidden = s.id !== `pestana-${pestana}`;
  window.scrollTo(0, 0);
  if (pestana === "biblioteca") cargarBiblioteca();
  if (pestana === "peliculas") { if (!app.peliculas.lista.length) buscarPeliculas(1); cargarDescargas(); cargarTorrents(); }
  if (pestana === "pantalla") prepararPantalla();
  if (pestana === "mouse") prepararMouse();
  else mantenerClic(false);
  refrescarEstado();
}

// --- Reproductor ------------------------------------------------------------------------------

function tiempo(ms) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

let pidiendoEstado = false;
async function refrescarEstado() {
  if (pidiendoEstado) return;
  pidiendoEstado = true;
  try {
    app.estado = await api("/api/estado");
    mostrarEstado();
  } catch { /* se marca la conexión caída */ } finally {
    pidiendoEstado = false;
  }
}

let archivoAnterior = null;
function mostrarEstado() {
  const e = app.estado;
  if (!e) return;
  $("#version").textContent = e.version;

  // Avisos generales
  $("#aviso-apagado").hidden = !e.apagado;
  if (e.apagado) $("#apagado-segundos").textContent = e.apagado.segundos;
  $("#aviso-siguiente").hidden = !e.siguiente;
  if (e.siguiente) {
    $("#siguiente-texto").textContent = e.siguiente.texto;
    $("#siguiente-nombre").textContent = e.siguiente.nombre;
  }

  // Qué se está mostrando
  const rep = e.reproduccion;
  $("#titulo-actual").textContent = e.archivo ? e.archivo.nombre : "Nada en reproducción";
  const estados = { reproduciendo: "▶ Reproduciendo", pausa: "⏸ En pausa", detenido: "⏹ Detenido",
                    vista_previa: "Vista previa: tocá ▶ para empezar" };
  $("#estado-actual").textContent = rep ? estados[rep.estado] : (e.archivo ? "🖼 Imagen" : "Elegí algo en la Biblioteca");
  const clave = e.archivo ? `${e.archivo.id}|${e.archivo.nombre}` : null;
  if (clave !== archivoAnterior) {
    archivoAnterior = clave;
    refrescarCuadro(true);
  }

  $("#controles").classList.toggle("sin-video", !rep);
  for (const b of $$("#controles button, #controles input")) {
    if (b.id !== "chk-apagar" && !b.matches("[data-accion=pantalla_completa], [data-accion=lista]")) b.disabled = !rep;
  }
  if (rep) {
    $("#btn-play").textContent = rep.estado === "reproduciendo" ? "⏸" : "▶";
    if (!app.arrastrandoBarra) {
      $("#barra").max = Math.max(1, rep.duracion);
      $("#barra").value = rep.posicion;
    }
    $("#tiempo-pos").textContent = tiempo(rep.posicion);
    $("#tiempo-dur").textContent = tiempo(rep.duracion);
    if (!volumenTocado) {
      $("#volumen").value = rep.volumen;
      $("#volumen-valor").textContent = rep.volumen;
    }
    $("#btn-silencio").textContent = rep.silencio ? "🔇" : "🔊";
  }
  $("#chk-apagar").checked = e.apagar_al_terminar;
  $("#chk-mover").checked = e.mover_descargas;

  mostrarSubtitulos(e.subtitulos, e.opensubtitles);
  mostrarCola(e.cola);
}

function mostrarSubtitulos(s, conClave) {
  const tarjeta = $("#tarjeta-subs");
  tarjeta.hidden = !s;
  if (!s) return;
  const activo = s.archivos.find((a) => a.activo) || s.pistas.find((p) => p.activa);
  $("#subs-resumen").textContent = activo ? `· ${activo.texto}` : "· desactivados";
  const opciones = [
    { texto: "Desactivados", activa: !s.activos, hacer: () => accion("subtitulos") },
    ...s.archivos.map((a) => ({ texto: a.texto, activa: a.activo, hacer: () => accion("subtitulos", { archivo: a.ruta }) })),
    ...s.pistas.map((p, i) => ({ texto: `${p.texto} (incluida en el video)`, activa: p.activa, hacer: () => accion("subtitulos", { pista: i }) })),
  ];
  const caja = $("#subs-opciones");
  const firma = JSON.stringify(opciones.map((o) => [o.texto, o.activa]));
  if (caja.dataset.firma !== firma) {
    caja.dataset.firma = firma;
    caja.replaceChildren(...opciones.map((o) => {
      const b = document.createElement("button");
      b.className = "opcion" + (o.activa ? " activa" : "");
      b.innerHTML = `<span class="marca">${o.activa ? "●" : "○"}</span>`;
      b.append(o.texto);
      b.addEventListener("click", () => o.hacer().catch(() => {}));
      return b;
    }));
  }
  const conArchivo = s.archivos.some((a) => a.activo);
  for (const b of $$(".subs-retraso button")) b.disabled = !conArchivo;
  $("#subs-retraso").textContent = textoSincronia(s.retraso);
  const tamanos = $("#subs-tamanos");
  const firmaT = JSON.stringify([s.tamanos, s.escala]);
  if (tamanos.dataset.firma !== firmaT) {
    tamanos.dataset.firma = firmaT;
    tamanos.replaceChildren(...s.tamanos.map((t) => {
      const b = document.createElement("button");
      b.className = "chip" + (t.escala === s.escala ? " activo" : "");
      b.textContent = t.texto;
      b.addEventListener("click", () => accion("tamano_subtitulos", { escala: t.escala }).catch(() => {}));
      return b;
    }));
  }
  $("#btn-buscar-subs").title = conClave ? "" : "Falta la clave de OpenSubtitles en la configuración de la PC";
}

function mostrarCola(cola) {
  $("#cola-cantidad").textContent = cola.length ? `(${cola.length})` : "";
  $("#cola-vacia").hidden = cola.length > 0;
  $("[data-accion=cola_vaciar]").hidden = !cola.length;
  const ul = $("#cola");
  const firma = JSON.stringify(cola);
  if (ul.dataset.firma === firma) return;
  ul.dataset.firma = firma;
  ul.replaceChildren(...cola.map((v, i) => {
    const li = item(`${i + 1}. ${v.nombre}`, "", "🎬");
    const acciones = document.createElement("div");
    acciones.className = "item-acciones";
    acciones.append(
      botonChico("▶", () => accion("cola_reproducir", { ruta: v.ruta })),
      botonChico("✕", () => accion("cola_quitar", { ruta: v.ruta })),
    );
    li.append(acciones);
    return li;
  }));
}

// El cuadro del video que se está viendo, cada tanto
let cuadroUrl = null, pidiendoCuadro = false;
async function refrescarCuadro(forzar = false) {
  const e = app.estado;
  const viendo = app.pestana === "reproductor" && !document.hidden;
  if (pidiendoCuadro || !e || (!forzar && !viendo)) return;
  const rep = e.reproduccion;
  if (!forzar && !(rep && rep.estado === "reproduciendo")) return;
  pidiendoCuadro = true;
  try {
    const r = await fetch("/api/cuadro.jpg", { cache: "no-store" });
    const hay = r.status === 200;
    if (hay) {
      const url = URL.createObjectURL(await r.blob());
      $("#cuadro").src = url;
      if (cuadroUrl) URL.revokeObjectURL(cuadroUrl);
      cuadroUrl = url;
    } else if (e.archivo && e.archivo.tipo === "imagen") {
      $("#cuadro").src = `/api/miniatura?id=${e.archivo.id}`;
    }
    const conImagen = hay || (e.archivo && e.archivo.tipo === "imagen");
    $("#cuadro").hidden = !conImagen;
    $("#cuadro-vacio").hidden = conImagen;
  } catch { /* siguiente vuelta */ } finally {
    pidiendoCuadro = false;
  }
}

let volumenTocado = false, relojVolumen;
function prepararReproductor() {
  const barra = $("#barra");
  barra.addEventListener("pointerdown", () => { app.arrastrandoBarra = true; });
  barra.addEventListener("input", () => { $("#tiempo-pos").textContent = tiempo(+barra.value); });
  barra.addEventListener("change", async () => {
    try { await accion("ir_a", { ms: +barra.value }); } catch {}
    app.arrastrandoBarra = false;
  });
  const volumen = $("#volumen");
  volumen.addEventListener("input", () => {
    volumenTocado = true;
    $("#volumen-valor").textContent = volumen.value;
    clearTimeout(relojVolumen);
    relojVolumen = setTimeout(async () => {
      try { await accion("volumen", { valor: +volumen.value }); } catch {}
      volumenTocado = false;
    }, 150);
  });
  $("#chk-apagar").addEventListener("change", (ev) => accion("apagar_al_terminar", { activo: ev.target.checked }).catch(() => {}));
  $("#chk-mover").addEventListener("change", (ev) => accion("mover_descargas", { activo: ev.target.checked }).catch(() => {}));
}

// -1500 -> «1,5 s antes», 300 -> «0,3 s después» (igual que en la PC)
function textoSincronia(ms) {
  if (!ms) return "sincronizados";
  const s = String(+(Math.abs(ms) / 1000).toFixed(2)).replace(".", ",");
  return `${s} s ${ms > 0 ? "después" : "antes"}`;
}

// Botones con data-accion: la acción y sus datos salen de los atributos
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-accion]");
  if (!b || b.disabled) return;
  const datos = {};
  for (const [k, v] of Object.entries(b.dataset)) {
    if (k !== "accion") datos[k] = /^-?\d+$/.test(v) ? +v : v;
  }
  if (b.dataset.accion === "apagar_ahora" && !confirm("¿Apagar la PC ahora?")) return;
  accion(b.dataset.accion, datos).catch(() => {});
});

// --- Biblioteca -----------------------------------------------------------------------------------

function item(nombre, sub, icono) {
  const li = document.createElement("li");
  li.className = "item";
  const ic = document.createElement("div");
  ic.className = "item-icono";
  if (icono instanceof Node) ic.append(icono); else ic.textContent = icono;
  const texto = document.createElement("div");
  texto.className = "item-texto";
  const n = document.createElement("div");
  n.className = "item-nombre";
  n.textContent = nombre;
  texto.append(n);
  if (sub) {
    const s = document.createElement("div");
    s.className = "item-sub";
    s.textContent = sub;
    texto.append(s);
  }
  li.append(ic, texto);
  return li;
}

function botonChico(texto, hacer) {
  const b = document.createElement("button");
  b.className = "boton chico";
  b.textContent = texto;
  b.addEventListener("click", (ev) => { ev.stopPropagation(); hacer().catch(() => {}); });
  return b;
}

async function cargarBiblioteca() {
  try {
    app.biblioteca = await api("/api/biblioteca");
  } catch { return; }
  mostrarFiltros();
  await cargarArchivos();
}

function nombreCategoria(c) {
  return c.id === app.biblioteca.favoritos ? `★ ${c.nombre}` : c.nombre;
}

function elegirFiltro(filtro, categoria) {
  app.filtro = { filtro, categoria };
  mostrarFiltros();
  cargarArchivos();
}

function mostrarFiltros() {
  const b = app.biblioteca;
  // Arriba, los filtros fijos (Todos, Videos…); las categorías van en su propia sección
  const cont = $("#filtros");
  cont.replaceChildren(...b.filtros.map((f) => {
    const el = document.createElement("button");
    el.className = "chip";
    el.classList.toggle("activo", app.filtro.filtro === f.filtro);
    el.textContent = `${f.nombre} (${f.cantidad})`;
    el.addEventListener("click", () => elegirFiltro(f.filtro, null));
    return el;
  }), (() => {
    const nueva = document.createElement("button");
    nueva.className = "chip";
    nueva.textContent = "+ Nueva categoría";
    nueva.addEventListener("click", nuevaCategoria);
    return nueva;
  })());
  cont.querySelector(".activo")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  mostrarCategorias();
}

// Cada categoría es una tarjeta: amarilla si tiene algo por ver, verde si ya se vio toda.
// Las vistas van aparte, en un grupo que se despliega.
function mostrarCategorias() {
  const cats = app.biblioteca.categorias;
  const tarjeta = (c) => {
    const el = document.createElement("button");
    el.className = "categoria" + (c.estado ? ` ${c.estado}` : "");
    el.classList.toggle("activo", app.filtro.filtro === "categoria" && app.filtro.categoria === c.id);
    const n = document.createElement("span");
    n.className = "categoria-nombre";
    n.textContent = nombreCategoria(c);
    const s = document.createElement("span");
    s.className = "categoria-sub";
    s.textContent = `${c.cantidad} archivo(s)` + (c.estado === "vista" ? " · ✓ vista" : c.estado === "pendiente" ? " · por ver" : "");
    el.append(n, s);
    el.addEventListener("click", () => {
      elegirFiltro("categoria", c.id);
      $("#cantidad-archivos").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    alMantener(el, () => menuCategoria(c));
    return el;
  };
  const vistas = cats.filter((c) => c.estado === "vista");
  $("#categorias").replaceChildren(...cats.filter((c) => c.estado !== "vista").map(tarjeta));
  $("#categorias-vistas").replaceChildren(...vistas.map(tarjeta));
  $("#grupo-vistas").hidden = !vistas.length;
  $("#titulo-vistas").textContent = `✓ Vistas (${vistas.length})`;
  const pendientes = cats.filter((c) => c.estado === "pendiente").length;
  $("#categorias-resumen").textContent = `· ${cats.length}` + (pendientes ? ` · ${pendientes} por ver` : "");
}

function menuCategoria(c) {
  const opciones = [
    { texto: "▶ Ver sus archivos", hacer: async () => elegirFiltro("categoria", c.id) },
  ];
  if (c.estado === "vista") {
    opciones.push({ texto: "↺ Marcar como no vista", hacer: async () => { await accion("categoria_vista", { id: c.id, visto: false }); cargarBiblioteca(); } });
  } else if (c.estado === "pendiente" || c.sin_pendiente) {
    opciones.push(
      { texto: "✓ Marcar como vista", hacer: async () => { await accion("categoria_vista", { id: c.id, visto: true }); cargarBiblioteca(); } },
      { texto: c.sin_pendiente ? "Volver a marcarla como pendiente" : "Quitar el amarillo de pendiente",
        hacer: async () => { await accion("categoria_pendiente", { id: c.id }); cargarBiblioteca(); } },
    );
  }
  if (c.fija) return abrirHoja(`Categoría «${c.nombre}»`, opciones);
  abrirHoja(`Categoría «${c.nombre}»`, [
    ...opciones,
    { texto: "✎ Renombrar", hacer: async () => {
      const nombre = pedirTexto("Nuevo nombre de la categoría:", c.nombre);
      if (nombre) { await accion("renombrar_categoria", { id: c.id, nombre }); cargarBiblioteca(); }
    } },
    { texto: "🗑 Borrar la categoría", peligro: true,
      confirmar: `¿Borrar la categoría «${c.nombre}»? Los archivos no se borran, solo pierden esta etiqueta.`,
      hacer: async () => {
        await accion("borrar_categoria", { id: c.id });
        app.filtro = { filtro: "todos", categoria: null };
        cargarBiblioteca();
      } },
  ]);
}

async function nuevaCategoria(ids = []) {
  const nombre = pedirTexto("Nombre de la categoría nueva:");
  if (!nombre) return;
  try {
    await accion("nueva_categoria", { nombre, ids: Array.isArray(ids) ? ids : [] });
    await cargarBiblioteca();
  } catch {}
}

let relojBusqueda;
async function cargarArchivos() {
  const p = new URLSearchParams({ filtro: app.filtro.filtro, q: $("#buscar").value });
  if (app.filtro.categoria) p.set("categoria", app.filtro.categoria);
  try {
    app.archivos = await api(`/api/archivos?${p}`);
  } catch { return; }
  const visibles = new Set(app.archivos.map((a) => a.id));
  for (const id of app.seleccion) if (!visibles.has(id)) app.seleccion.delete(id);
  mostrarArchivos();
}

// Las listas grandes se dibujan de a tandas al bajar
const TANDA = 120;
let dibujados = 0;
function mostrarArchivos() {
  $("#cantidad-archivos").textContent = `${app.archivos.length} archivo(s)`;
  $("#archivos").replaceChildren();
  dibujados = 0;
  dibujarMas();
  mostrarSeleccion();
}

function dibujarMas() {
  const ul = $("#archivos");
  const fav = app.biblioteca ? app.biblioteca.favoritos : -1;
  for (const a of app.archivos.slice(dibujados, dibujados + TANDA)) {
    let icono = a.tipo === "video" ? "🎬" : "🖼";
    if (a.tipo === "imagen" && a.existe) {
      icono = document.createElement("img");
      icono.loading = "lazy";
      icono.alt = "";
      icono.src = `/api/miniatura?id=${a.id}`;
    }
    const li = item(a.nombre, a.carpeta, icono);
    li.dataset.id = a.id;
    li.classList.toggle("faltante", !a.existe);
    li.classList.toggle("elegido", app.seleccion.has(a.id));
    if (a.categorias.includes(fav)) {
      const e = document.createElement("span");
      e.className = "estrella";
      e.textContent = "★";
      li.append(e);
    }
    if (a.visto) {
      const v = document.createElement("span");
      v.className = a.visto === "✓" ? "visto listo" : "visto";
      v.textContent = a.visto;
      li.append(v);
    }
    li.addEventListener("click", () => app.eligiendo ? alternarSeleccion(a.id, li) : menuArchivo(a));
    alMantener(li, () => { if (!app.eligiendo) { app.eligiendo = true; alternarSeleccion(a.id, li); } });
    ul.append(li);
  }
  dibujados += TANDA;
}

window.addEventListener("scroll", () => {
  if (app.pestana === "biblioteca" && dibujados < app.archivos.length
      && innerHeight + scrollY > document.body.scrollHeight - 600) dibujarMas();
}, { passive: true });

function alternarSeleccion(id, li) {
  if (app.seleccion.has(id)) app.seleccion.delete(id); else app.seleccion.add(id);
  li.classList.toggle("elegido", app.seleccion.has(id));
  mostrarSeleccion();
}

function mostrarSeleccion() {
  if (app.eligiendo && !app.seleccion.size && !$("#barra-seleccion").hidden) app.eligiendo = false;
  $("#btn-seleccionar").textContent = app.eligiendo ? "Listo" : "Elegir";
  $("#barra-seleccion").hidden = !app.eligiendo;
  $("#seleccion-cantidad").textContent = `${app.seleccion.size} elegido(s)`;
}

function terminarSeleccion() {
  app.eligiendo = false;
  app.seleccion.clear();
  for (const li of $$("#archivos .elegido")) li.classList.remove("elegido");
  mostrarSeleccion();
}

function menuArchivo(a) {
  const fav = app.biblioteca.favoritos;
  const esFav = a.categorias.includes(fav);
  const opciones = [
    { texto: a.tipo === "video" ? "▶ Reproducir en TVon" : "🖼 Mostrar en TVon", hacer: () => accion("reproducir", { id: a.id }) },
  ];
  if (a.tipo === "video") opciones.push({ texto: "☰ Agregar a la cola", hacer: () => accion("cola_agregar", { ids: [a.id] }) });
  opciones.push(
    { texto: esFav ? "☆ Quitar de Favoritos" : "★ Agregar a Favoritos",
      hacer: async () => { await accion("favoritos", { ids: [a.id], activo: !esFav }); cargarBiblioteca(); } },
    { texto: "🏷 Categorías…", hacer: () => menuCategorias([a.id], a.categorias) },
    { texto: "＋ Categoría con el título", hacer: async () => { await accion("categoria_titulo", { id: a.id }); cargarBiblioteca(); } },
    { texto: "⧉ Abrir en una ventana aparte", hacer: () => accion("abrir_ventana", { id: a.id }) },
    { texto: "📂 Mostrar la carpeta en la PC", hacer: () => accion("abrir_ubicacion", { id: a.id }) },
    { texto: "Quitar de la biblioteca", confirmar: "¿Quitar de la biblioteca? El archivo NO se borra del disco.",
      hacer: async () => { await accion("quitar", { ids: [a.id] }); cargarBiblioteca(); } },
    { texto: "🗑 Eliminar del disco", peligro: true,
      confirmar: `¿Mandar «${a.nombre}» a la Papelera de reciclaje de la PC? También se borran sus subtítulos.`,
      hacer: async () => { await accion("eliminar", { ids: [a.id] }); cargarBiblioteca(); } },
  );
  abrirHoja(a.nombre, opciones);
}

// Categorías de uno o varios archivos: cada una se pone o se saca con un toque
function menuCategorias(ids, actuales = null) {
  const cats = app.biblioteca.categorias;
  const tienen = (c) => actuales ? actuales.includes(c.id) : ids.every((id) => app.archivos.find((a) => a.id === id)?.categorias.includes(c.id));
  abrirHoja(ids.length === 1 ? "Categorías del archivo" : `Categorías de ${ids.length} archivos`, [
    ...cats.map((c) => {
      const puesta = tienen(c);
      return {
        texto: nombreCategoria(c), marca: puesta ? "✓" : "",
        hacer: async () => {
          await accion("asignar", { ids, categoria: c.id, activo: !puesta });
          await cargarBiblioteca();
          menuCategorias(ids, ids.length === 1 ? app.archivos.find((a) => a.id === ids[0])?.categorias : null);
        },
      };
    }),
    { texto: "＋ Nueva categoría…", hacer: () => nuevaCategoria(ids) },
  ]);
}

function prepararBiblioteca() {
  $("#buscar").addEventListener("input", () => {
    clearTimeout(relojBusqueda);
    relojBusqueda = setTimeout(cargarArchivos, 300);
  });
  $("#btn-seleccionar").addEventListener("click", () => {
    if (app.eligiendo) terminarSeleccion(); else { app.eligiendo = true; mostrarSeleccion(); }
  });
  for (const b of $$("[data-seleccion]")) {
    b.addEventListener("click", async () => {
      const ids = [...app.seleccion];
      if (!ids.length) return tostada("Tocá los archivos para elegirlos");
      const que = b.dataset.seleccion;
      try {
        if (que === "cola") { await accion("cola_agregar", { ids }); terminarSeleccion(); }
        if (que === "favoritos") { await accion("favoritos", { ids, activo: true }); terminarSeleccion(); cargarBiblioteca(); }
        if (que === "categorias") menuCategorias(ids);
        if (que === "mas") menuSeleccion(ids);
      } catch {}
    });
  }
}

function menuSeleccion(ids) {
  abrirHoja(`${ids.length} archivo(s)`, [
    { texto: "☆ Quitar de Favoritos", hacer: async () => { await accion("favoritos", { ids, activo: false }); terminarSeleccion(); cargarBiblioteca(); } },
    { texto: "Quitar de la biblioteca", confirmar: `¿Quitar ${ids.length} archivo(s) de la biblioteca? NO se borran del disco.`,
      hacer: async () => { await accion("quitar", { ids }); terminarSeleccion(); cargarBiblioteca(); } },
    { texto: "🗑 Eliminar del disco", peligro: true,
      confirmar: `¿Mandar ${ids.length} archivo(s) a la Papelera de reciclaje de la PC? También se borran sus subtítulos.`,
      hacer: async () => { await accion("eliminar", { ids }); terminarSeleccion(); cargarBiblioteca(); } },
  ]);
}

// Mantener apretado (sin mover el dedo) = menú
function alMantener(el, hacer) {
  let reloj, x0, y0;
  el.addEventListener("pointerdown", (ev) => {
    x0 = ev.clientX; y0 = ev.clientY;
    reloj = setTimeout(() => {
      reloj = null;
      el.dataset.mantenido = "1";
      navigator.vibrate?.(15);
      hacer();
    }, 550);
  });
  const cancelar = () => { clearTimeout(reloj); reloj = null; };
  el.addEventListener("pointerup", cancelar);
  el.addEventListener("pointercancel", cancelar);
  el.addEventListener("pointermove", (ev) => { if (Math.hypot(ev.clientX - x0, ev.clientY - y0) > 10) cancelar(); });
  el.addEventListener("contextmenu", (ev) => ev.preventDefault());
  // El clic que sigue a mantener apretado no cuenta
  el.addEventListener("click", (ev) => {
    if (el.dataset.mantenido) { delete el.dataset.mantenido; ev.stopImmediatePropagation(); }
  }, true);
}

// --- Dominio público -------------------------------------------------------------------------------

function tamano(n) {
  if (!n) return "";
  return n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : `${Math.round(n / 1024 ** 2)} MB`;
}

async function buscarPeliculas(pagina) {
  const p = app.peliculas;
  if (pagina === 1) { p.q = $("#buscar-peliculas").value.trim(); p.orden = $("#orden-peliculas").value || "populares"; }
  $("#peliculas-total").textContent = "Buscando…";
  try {
    const r = await api(`/api/dp/buscar?${new URLSearchParams({ q: p.q, orden: p.orden, pagina })}`);
    p.pagina = pagina;
    p.total = r.total;
    p.lista = pagina === 1 ? r.peliculas : [...p.lista, ...r.peliculas];
    const sel = $("#orden-peliculas");
    if (!sel.options.length) {
      for (const [clave, texto] of Object.entries(r.ordenes)) sel.add(new Option(`Ordenar: ${texto}`, clave));
    }
    mostrarPeliculas();
  } catch (e) {
    $("#peliculas-total").textContent = e.message;
  }
}

function mostrarPeliculas() {
  const p = app.peliculas;
  $("#peliculas-total").textContent = `${p.lista.length} de ${p.total.toLocaleString("es-AR")} películas`;
  $("#btn-mas-peliculas").hidden = p.lista.length >= p.total;
  $("#peliculas").replaceChildren(...p.lista.map((pel) => {
    const li = item(pel.titulo, [pel.anio, `${pel.descargas.toLocaleString("es-AR")} descargas`].filter(Boolean).join(" · "), "🎞");
    const acciones = document.createElement("div");
    acciones.className = "item-acciones";
    if (pel.estado_texto) {
      const et = document.createElement("span");
      et.className = "etiqueta";
      et.textContent = pel.estado_texto;
      acciones.append(et);
    } else {
      acciones.append(botonChico("⬇", async () => {
        await accion("dp_descargar", { peliculas: [{ identificador: pel.identificador, titulo: pel.titulo, anio: pel.anio }] });
        pel.estado_texto = "En cola";
        mostrarPeliculas();
        cargarDescargas();
      }));
    }
    li.append(acciones);
    return li;
  }));
}

async function cargarDescargas() {
  let r;
  try { r = await api("/api/dp/cola"); } catch { return; }
  $("#descargas-resumen").textContent = r.cantidad ? `· ${r.cantidad} · ${tamano(r.bytes)}` : "";
  $("#descargas-vacia").hidden = r.descargas.length > 0;
  $("#descargas").replaceChildren(...r.descargas.map((d) => {
    const titulo = d.anio ? `${d.titulo} (${d.anio})` : d.titulo;
    let sub = d.error ? `Error: ${d.error}` : d.estado_texto;
    if (d.estado === "descargando" && d.total) sub += ` · ${Math.round(100 * d.recibido / d.total)} % de ${tamano(d.total)}`;
    else if (d.tamano) sub += ` · ${tamano(d.tamano)}`;
    const li = item(titulo, sub, d.estado === "descargando" ? "⬇" : d.estado === "completa" ? "✔" : "🎞");
    if ((d.estado === "descargando" || d.estado === "pendiente") && d.total) {
      const barra = document.createElement("div");
      barra.className = "progreso";
      const lleno = document.createElement("div");
      lleno.style.width = `${(100 * d.recibido / d.total).toFixed(1)}%`;
      barra.append(lleno);
      li.querySelector(".item-texto").append(barra);
    }
    li.addEventListener("click", () => menuDescarga(d, titulo));
    return li;
  }));
  if (document.activeElement?.closest(".campo, .interruptor")) return; // no pisar lo que se está escribiendo
  $("#auto-activa").checked = r.auto.activa;
  $("#auto-peliculas").value = r.auto.max_peliculas;
  $("#auto-gb").value = r.auto.max_gb;
}

function menuDescarga(d, titulo) {
  const ids = [d.identificador];
  const listo = () => cargarDescargas();
  const opciones = [];
  if (d.estado === "descargando" || d.estado === "pendiente") opciones.push({ texto: "Cancelar la descarga", hacer: async () => { await accion("dp_cancelar", { ids }); listo(); } });
  if (d.estado === "error" || d.estado === "cancelada") opciones.push({ texto: "↻ Reintentar", hacer: async () => { await accion("dp_reintentar", { ids }); listo(); } });
  if (d.estado !== "descargando") opciones.push({ texto: "Quitar de la lista", hacer: async () => { await accion("dp_quitar", { ids }); listo(); } });
  if (d.estado === "completa") opciones.push({
    texto: "🗑 Eliminar la película", peligro: true,
    confirmar: "¿Mandarla a la Papelera de la PC con sus subtítulos? La descarga automática no la vuelve a bajar.",
    hacer: async () => { await accion("dp_eliminar", { ids }); listo(); },
  });
  abrirHoja(titulo, opciones);
}

// --- Torrents: el link magnet va del celular a la PC, que lo baja ------------------------------------

async function cargarTorrents() {
  let lista;
  try { lista = await api("/api/torrents"); } catch { return; }
  $("#torrents-vacia").hidden = lista.length > 0;
  $("#torrents").replaceChildren(...lista.map((t) => {
    let sub = t.error ? `Error: ${t.error}` : t.estado_texto;
    if (t.total) sub += ` · ${Math.round(100 * t.recibido / t.total)} % de ${tamano(t.total)}`;
    if (t.estado === "active" && t.velocidad) sub += ` · ${tamano(t.velocidad)}/s`;
    if (t.restante) sub += ` · faltan ${t.restante}`;
    const li = item(t.nombre, sub, t.estado === "paused" ? "⏸" : "🧲");
    if (t.total) {
      const barra = document.createElement("div");
      barra.className = "progreso";
      const lleno = document.createElement("div");
      lleno.style.width = `${(100 * t.recibido / t.total).toFixed(1)}%`;
      barra.append(lleno);
      li.querySelector(".item-texto").append(barra);
    }
    li.addEventListener("click", () => abrirHoja(t.nombre, [
      t.estado === "paused"
        ? { texto: "▶ Reanudar", hacer: async () => { await accion("torrent_reanudar", { gid: t.gid }); cargarTorrents(); } }
        : { texto: "⏸ Pausar", hacer: async () => { await accion("torrent_pausar", { gid: t.gid }); cargarTorrents(); } },
      { texto: "✕ Cancelar y borrar lo bajado", peligro: true, confirmar: `¿Cancelar «${t.nombre}»? Se borra lo que ya bajó.`,
        hacer: async () => { await accion("torrent_cancelar", { gid: t.gid }); cargarTorrents(); } },
    ]));
    return li;
  }));
}

function prepararPeliculas() {
  $("#form-torrent").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const campo = $("#enlace-torrent");
    if (!campo.value.trim()) return tostada("Pegá el link magnet (mantené apretado el recuadro → Pegar)", true);
    campo.blur();
    try {
      await accion("torrent_agregar", { enlace: campo.value.trim() });
      campo.value = "";
      setTimeout(cargarTorrents, 1500);
    } catch {}
  });
  $("#form-peliculas").addEventListener("submit", (ev) => { ev.preventDefault(); $("#buscar-peliculas").blur(); buscarPeliculas(1); });
  $("#orden-peliculas").addEventListener("change", () => buscarPeliculas(1));
  $("#btn-mas-peliculas").addEventListener("click", () => buscarPeliculas(app.peliculas.pagina + 1));
  $("#auto-activa").addEventListener("change", (ev) => accion("dp_auto", { activa: ev.target.checked }).catch(() => {}));
  $("#auto-peliculas").addEventListener("change", (ev) => accion("dp_auto", { max_peliculas: +ev.target.value || 1 }).catch(() => {}));
  $("#auto-gb").addEventListener("change", (ev) => accion("dp_auto", { max_gb: +ev.target.value || 1 }).catch(() => {}));
}

// --- Pantalla compartida ------------------------------------------------------------------------------

const pantalla = { monitor: 0, modo: "tocar", zoom: 1, viendo: false };

async function prepararPantalla() {
  $("#pantalla-error").hidden = true;
  try {
    const r = await api("/api/pantalla/monitores");
    const sel = $("#monitor");
    sel.replaceChildren(...r.monitores.map((m, i) => new Option(
      `${i + 1}${m.principal ? " (principal)" : ""}${i === r.tvon ? " · TVon" : ""} — ${m.ancho}×${m.alto}`, i)));
    sel.value = r.tvon;
    $("#campo-monitor").hidden = r.monitores.length < 2;
    $("#btn-compartir").disabled = !r.pantalla;
    if (!r.pantalla) mostrarErrorPantalla("Compartir la pantalla está desactivado en TVon (📱 ON → Opciones).");
    pantalla.control = r.control;
  } catch (e) {
    mostrarErrorPantalla(e.message);
  }
}

function mostrarErrorPantalla(texto) {
  $("#pantalla-error").textContent = texto;
  $("#pantalla-error").hidden = false;
}

function verPantalla() {
  const [ancho, calidad, fps] = $("#calidad").value.split(",");
  pantalla.monitor = +$("#monitor").value || 0;
  pantalla.viendo = true;
  pantalla.corte = new AbortController();
  recibirPantalla(`/api/pantalla.mjpg?${new URLSearchParams({ monitor: pantalla.monitor, ancho, calidad, fps, t: Date.now() })}`,
                  pantalla.corte.signal);
  $("#pantalla-apagada").hidden = true;
  $("#celular-a-pc").hidden = true;
  $("#pantalla-encendida").hidden = false;
  $("#hueco-teclado-pantalla").append($("#teclado"));
  $("#teclado").hidden = !pantalla.control;
  $("#ayuda-modo").hidden = !pantalla.control;
  $(".herramientas .segmentos").hidden = !pantalla.control;
}

function dejarDeVer() {
  if (!pantalla.viendo) return;
  pantalla.viendo = false;
  // Cortar la conexión: así la PC deja de capturar y saca el aviso
  pantalla.corte?.abort();
  $("#pantalla").removeAttribute("src");
  $("#pantalla-apagada").hidden = false;
  $("#celular-a-pc").hidden = false;
  $("#pantalla-encendida").hidden = true;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

// La transmisión llega como MJPEG. En vez de dársela al <img> (que puede dibujar un cuadro a
// medio llegar y se ve cortado), se lee acá: solo se muestran cuadros completos y, si el celular
// va atrasado, se saltean los viejos para no acumular demora.
const FIN_CABECERA = [13, 10, 13, 10];

function buscarBytes(datos, patron, desde = 0) {
  fuera: for (let i = desde; i <= datos.length - patron.length; i++) {
    for (let j = 0; j < patron.length; j++) if (datos[i + j] !== patron[j]) continue fuera;
    return i;
  }
  return -1;
}

async function recibirPantalla(url, senal) {
  const img = $("#pantalla");
  let pendiente = null, dibujando = false, anterior = null;
  const dibujar = async () => {
    if (dibujando || !pendiente) return;
    dibujando = true;
    const cuadro = pendiente;
    pendiente = null;
    const nuevo = URL.createObjectURL(new Blob([cuadro], { type: "image/jpeg" }));
    img.src = nuevo;
    try { await img.decode(); } catch { /* el siguiente cuadro lo arregla */ }
    if (anterior) URL.revokeObjectURL(anterior);
    anterior = nuevo;
    dibujando = false;
    if (pendiente) requestAnimationFrame(dibujar);
  };
  try {
    const r = await fetch(url, { cache: "no-store", signal: senal });
    if (!r.ok) {
      const datos = await r.json().catch(() => ({}));
      throw new Error(datos.error || `Error ${r.status}`);
    }
    const lector = r.body.getReader();
    let buffer = new Uint8Array(0);
    for (;;) {
      const { value, done } = await lector.read();
      if (done) break;
      const junto = new Uint8Array(buffer.length + value.length);
      junto.set(buffer);
      junto.set(value, buffer.length);
      buffer = junto;
      // Cada cuadro: «--cuadro», cabeceras con Content-Length, línea vacía y los bytes del JPEG
      for (;;) {
        const fin = buscarBytes(buffer, FIN_CABECERA);
        if (fin < 0) break;
        const largo = /Content-Length:\s*(\d+)/i.exec(new TextDecoder().decode(buffer.subarray(0, fin)));
        if (!largo) { buffer = buffer.subarray(fin + 4); continue; }
        const inicio = fin + 4, total = inicio + +largo[1];
        if (buffer.length < total) break;
        pendiente = buffer.slice(inicio, total);
        buffer = buffer.slice(total);
      }
      if (pendiente) requestAnimationFrame(dibujar);
    }
    throw new Error("terminó");
  } catch (e) {
    if (senal.aborted || !pantalla.viendo) return;
    dejarDeVer();
    mostrarErrorPantalla(e.message === "terminó" || e instanceof TypeError
      ? "Se cortó la transmisión (¿la PC dejó de compartir o se apagó ON?)." : e.message);
  }
}

function entrada(datos) {
  encolarEntrada({ monitor: pantalla.monitor, ...datos });
}

// Las entradas de mouse y teclado van de a una y en orden: mandadas juntas podrían llegar cambiadas.
// Los movimientos del touchpad se suman mientras se espera la respuesta anterior.
const cola = { pendientes: [], enviando: false, dx: 0, dy: 0 };

function sacarMovimiento() {
  const dx = Math.round(cola.dx), dy = Math.round(cola.dy);
  if (!dx && !dy) return null;
  cola.dx -= dx;
  cola.dy -= dy;
  return { tipo: "desplazar", dx, dy };
}

function encolarEntrada(datos) {
  const movimiento = sacarMovimiento();  // lo que se movió antes va antes
  if (movimiento) cola.pendientes.push(movimiento);
  cola.pendientes.push(datos);
  enviarCola();
}

function moverPuntero(dx, dy) {
  cola.dx += dx;
  cola.dy += dy;
  enviarCola();
}

async function enviarCola() {
  if (cola.enviando) return;
  cola.enviando = true;
  try {
    for (let datos; (datos = cola.pendientes.shift() || sacarMovimiento());) {
      try {
        await api("/api/pantalla/entrada", datos);
      } catch (e) {
        cola.pendientes = [];
        cola.dx = cola.dy = 0;
        tostada(e.message, true);
      }
    }
  } finally {
    cola.enviando = false;
  }
}

function prepararToques() {
  const lienzo = $("#lienzo");
  const img = $("#pantalla");

  const relativo = (ev) => {
    const r = img.getBoundingClientRect();
    return { x: (ev.clientX - r.left) / r.width, y: (ev.clientY - r.top) / r.height };
  };
  let inicio = null, ultimoToque = 0, reloj = null, ultimaY = 0, sobrante = 0, ultimoMovimiento = 0;

  lienzo.addEventListener("pointerdown", (ev) => {
    if (!pantalla.control || !ev.isPrimary) return;
    inicio = { ...relativo(ev), cx: ev.clientX, cy: ev.clientY, movido: false, mantenido: false };
    ultimaY = ev.clientY;
    sobrante = 0;
    if (pantalla.modo === "arrastrar") {
      entrada({ tipo: "apretar", x: inicio.x, y: inicio.y });
      lienzo.setPointerCapture(ev.pointerId);
      return;
    }
    reloj = setTimeout(() => {
      if (!inicio || inicio.movido) return;
      inicio.mantenido = true;
      navigator.vibrate?.(20);
      entrada({ tipo: "derecho", x: inicio.x, y: inicio.y });
    }, 600);
  });

  lienzo.addEventListener("pointermove", (ev) => {
    if (!inicio || !ev.isPrimary) return;
    if (Math.hypot(ev.clientX - inicio.cx, ev.clientY - inicio.cy) > 12) {
      inicio.movido = true;
      clearTimeout(reloj);
    }
    if (pantalla.modo === "arrastrar") {
      const ahora = performance.now();
      if (ahora - ultimoMovimiento > 40) {  // como mucho 25 movimientos por segundo
        ultimoMovimiento = ahora;
        const p = relativo(ev);
        entrada({ tipo: "mover", x: p.x, y: p.y });
      }
    } else if (inicio.movido && pantalla.zoom === 1) {
      // Deslizar = rueda del mouse (con zoom, deslizar mueve la imagen)
      sobrante += ev.clientY - ultimaY;
      ultimaY = ev.clientY;
      const pasos = Math.trunc(sobrante / 40);
      if (pasos) {
        sobrante -= pasos * 40;
        entrada({ tipo: "rueda", pasos });
      }
    }
  });

  const terminar = (ev) => {
    if (!inicio || !ev.isPrimary) return;
    clearTimeout(reloj);
    const fin = relativo(ev);
    if (pantalla.modo === "arrastrar") {
      entrada({ tipo: "soltar", x: fin.x, y: fin.y });
    } else if (!inicio.movido && !inicio.mantenido) {
      const ahora = Date.now();
      // Dos toques seguidos en el mismo lugar = doble clic
      if (ahora - ultimoToque < 350) {
        entrada({ tipo: "doble", x: inicio.x, y: inicio.y });
        ultimoToque = 0;
      } else {
        entrada({ tipo: "clic", x: inicio.x, y: inicio.y });
        ultimoToque = ahora;
      }
    }
    inicio = null;
  };
  lienzo.addEventListener("pointerup", terminar);
  lienzo.addEventListener("pointercancel", () => { clearTimeout(reloj); inicio = null; });
  lienzo.addEventListener("contextmenu", (ev) => ev.preventDefault());

  for (const b of $$("[data-modo]")) {
    b.addEventListener("click", () => {
      pantalla.modo = b.dataset.modo;
      for (const o of $$("[data-modo]")) o.classList.toggle("activo", o === b);
      $("#ayuda-modo").textContent = pantalla.modo === "tocar"
        ? "Tocá para hacer clic · dos toques: doble clic · mantené: clic derecho · deslizá: rueda"
        : "Arrastrá para mover ventanas, seleccionar o mover barras (mantiene apretado el clic)";
    });
  }
  $("#btn-zoom").addEventListener("click", () => {
    pantalla.zoom = pantalla.zoom === 1 ? 1.5 : pantalla.zoom === 1.5 ? 2 : 1;
    img.style.width = `${pantalla.zoom * 100}%`;
    lienzo.classList.toggle("zoom", pantalla.zoom > 1);
    $("#btn-zoom").textContent = `🔍 ${pantalla.zoom}×`;
  });
  $("#btn-completa").addEventListener("click", async () => {
    if (document.fullscreenElement) return document.exitFullscreen();
    try {
      await lienzo.requestFullscreen();
      await screen.orientation?.lock?.("landscape");
    } catch { /* no todos los navegadores dejan */ }
  });
  $("#btn-compartir").addEventListener("click", verPantalla);
  $("#btn-dejar").addEventListener("click", dejarDeVer);
  // Cambiar de modo no abre el teclado: se abre solo al tocar el recuadro de texto
  for (const b of $$("[data-teclado]")) {
    b.addEventListener("click", () => {
      for (const o of $$("[data-teclado]")) o.classList.toggle("activo", o === b);
      $("#vivo").hidden = b.dataset.teclado !== "vivo";
      $("#form-texto").hidden = b.dataset.teclado === "vivo";
    });
  }
  // El botón Enviar manda solo el texto; Enter manda el texto y un Enter, así en la PC pasa lo
  // de siempre: busca, envía el mensaje o, en Word, salta de línea
  const enviarTexto = (conEnter) => {
    const t = $("#texto");
    if (t.value) entrada({ tipo: "texto", texto: t.value });
    if (conEnter) entrada({ tipo: "teclas", teclas: "enter" });
    t.value = "";
  };
  $("#form-texto").addEventListener("submit", (ev) => { ev.preventDefault(); enviarTexto(false); });
  $("#texto").addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" || ev.isComposing) return;
    ev.preventDefault();
    enviarTexto(true);
  });
  for (const b of $$("[data-teclas]")) {
    b.addEventListener("click", () => {
      if (b.dataset.confirmar && !confirm(b.dataset.confirmar)) return;
      entrada({ tipo: "teclas", teclas: b.dataset.teclas });
    });
  }
  for (const b of $$("[data-rueda]")) b.addEventListener("click", () => entrada({ tipo: "rueda", pasos: +b.dataset.rueda }));
}

// --- Mouse (touchpad) y teclado en vivo ---------------------------------------------------------------

const mouse = { velocidad: 1.75, mantenido: false };

async function prepararMouse() {
  $("#hueco-teclado-mouse").append($("#teclado"));
  // El touchpad queda abajo, al alcance del pulgar
  requestAnimationFrame(() => window.scrollTo(0, document.body.scrollHeight));
  $("#mouse-error").hidden = true;
  try {
    const r = await api("/api/pantalla/monitores");
    pantalla.control = r.control;
    $("#teclado").hidden = !r.control;
    if (!r.control) {
      $("#mouse-error").textContent = "Manejar el mouse y el teclado está desactivado en TVon (📱 ON → Opciones).";
      $("#mouse-error").hidden = false;
    }
  } catch (e) {
    $("#mouse-error").textContent = e.message;
    $("#mouse-error").hidden = false;
  }
}

function prepararTouchpad() {
  const pad = $("#touchpad");
  const dedos = new Map();  // pointerId -> posición
  let gesto = null;

  pad.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    pad.setPointerCapture(ev.pointerId);
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY });
    if (dedos.size === 1) gesto = { inicio: performance.now(), t: performance.now(), maximo: 1, movido: false, rueda: 0 };
    else if (gesto) gesto.maximo = Math.max(gesto.maximo, dedos.size);
    pad.classList.add("activo");
  });

  pad.addEventListener("pointermove", (ev) => {
    const d = dedos.get(ev.pointerId);
    if (!d || !gesto) return;
    const dx = ev.clientX - d.x, dy = ev.clientY - d.y;
    d.x = ev.clientX;
    d.y = ev.clientY;
    if (Math.hypot(d.x - d.x0, d.y - d.y0) > 8) gesto.movido = true;
    if (!gesto.movido) return;
    if (gesto.maximo === 1) {
      // Más rápido el dedo, más lejos va el puntero (como un touchpad de verdad)
      const ahora = performance.now();
      const rapidez = Math.hypot(dx, dy) / Math.max(1, ahora - gesto.t);
      gesto.t = ahora;
      const factor = mouse.velocidad * Math.min(3, 0.6 + rapidez * 1.5);
      moverPuntero(dx * factor, dy * factor);
    } else if (dedos.size >= 2 && d === dedos.values().next().value) {
      // Dos dedos: la rueda, con el primero que apoyaste
      gesto.rueda += dy;
      const pasos = Math.trunc(gesto.rueda / 30);
      if (pasos) {
        gesto.rueda -= pasos * 30;
        encolarEntrada({ tipo: "rueda", pasos });
      }
    }
  });

  const soltar = (ev) => {
    if (!dedos.delete(ev.pointerId) || dedos.size || !gesto) return;
    pad.classList.remove("activo");
    // Un toque corto sin mover = clic; con dos dedos, clic derecho
    if (ev.type === "pointerup" && !gesto.movido && performance.now() - gesto.inicio < 350) {
      encolarEntrada({ tipo: "clic_aqui", boton: gesto.maximo >= 2 ? "derecho" : "izquierdo" });
    }
    gesto = null;
  };
  pad.addEventListener("pointerup", soltar);
  pad.addEventListener("pointercancel", soltar);
  pad.addEventListener("contextmenu", (ev) => ev.preventDefault());

  // Botones como los de un mouse: mientras está apretado, deslizar en el touchpad arrastra
  for (const b of $$("[data-boton]")) {
    const apretar = (apretado) => (ev) => {
      ev.preventDefault();
      if (b.classList.contains("apretado") === apretado) return;
      b.classList.toggle("apretado", apretado);
      if (apretado) navigator.vibrate?.(10);
      encolarEntrada({ tipo: "boton", boton: b.dataset.boton, apretado });
    };
    b.addEventListener("pointerdown", apretar(true));
    for (const tipo of ["pointerup", "pointercancel", "pointerleave"]) b.addEventListener(tipo, apretar(false));
    b.addEventListener("contextmenu", (ev) => ev.preventDefault());
  }
  $("#btn-mantener").addEventListener("click", () => mantenerClic(!mouse.mantenido));

  const velocidad = $("#velocidad");
  try { velocidad.value = localStorage.getItem("tvon_velocidad") || velocidad.value; } catch {}
  mouse.velocidad = +velocidad.value;
  velocidad.addEventListener("input", () => {
    mouse.velocidad = +velocidad.value;
    try { localStorage.setItem("tvon_velocidad", velocidad.value); } catch {}
  });
}

function mantenerClic(activo) {
  if (mouse.mantenido === activo) return;
  mouse.mantenido = activo;
  $("#btn-mantener").classList.toggle("apretado", activo);
  $("#btn-mantener").textContent = activo ? "🔓" : "🔒";
  encolarEntrada({ tipo: "boton", boton: "izquierdo", apretado: activo });
}

// Teclado en vivo: lo que se escribe va directo a la PC. Se compara el campo con cómo estaba, así
// funciona con el autocorrector y las sugerencias del teclado de Android (que reemplazan palabras
// enteras). Arranca con dos espacios para que el ⌫ ande aunque no se haya escrito nada.
const CENTINELA = "\u00a0\u00a0";

function prepararTecladoVivo() {
  const campo = $("#vivo");
  let anterior = CENTINELA, componiendo = false;
  const reiniciar = () => {
    campo.value = anterior = CENTINELA;
    campo.setSelectionRange(CENTINELA.length, CENTINELA.length);
  };
  const ordenar = () => {
    if (!componiendo && (!campo.value.startsWith(CENTINELA) || campo.value.length > 60)) reiniciar();
  };
  reiniciar();
  campo.addEventListener("focus", () => setTimeout(() => campo.setSelectionRange(campo.value.length, campo.value.length)));
  campo.addEventListener("compositionstart", () => { componiendo = true; });
  campo.addEventListener("compositionend", () => { componiendo = false; ordenar(); });
  campo.addEventListener("input", () => {
    // Por caracteres y no por unidades UTF-16: en la PC un emoji se borra con un solo ⌫
    const antes = Array.from(anterior), ahora = Array.from(campo.value);
    let comun = 0;
    while (comun < antes.length && comun < ahora.length && antes[comun] === ahora[comun]) comun++;
    const borrar = antes.length - comun, texto = ahora.slice(comun).join("");
    anterior = campo.value;
    if (borrar || texto) encolarEntrada({ tipo: "editar", borrar, texto });
    ordenar();
  });
  campo.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") return;
    ev.preventDefault();
    encolarEntrada({ tipo: "teclas", teclas: "enter" });
    if (!componiendo) reiniciar();
  });
}

// --- Inicio ---------------------------------------------------------------------------------------

async function iniciar() {
  for (const b of $$(".pestanas button")) b.addEventListener("click", () => irA(b.dataset.pestana));
  $("#velo").addEventListener("click", cerrarHoja);
  $("#btn-salir").addEventListener("click", async () => {
    if (!confirm("¿Desconectar este celular? Para volver a usarlo hay que escanear el QR de nuevo.")) return;
    try { await api("/api/salir", {}); } catch {}
    mostrarEmparejar("Celular desconectado.");
  });
  $("#host").textContent = location.host;
  prepararReproductor();
  prepararBiblioteca();
  prepararPeliculas();
  prepararToques();
  prepararTouchpad();
  prepararTecladoVivo();
  // Tocar fuera del teclado (el touchpad, un botón, la pantalla) suelta el recuadro de escribir:
  // si queda con el foco, Android vuelve a mostrarlo y lleva la página hasta él
  document.addEventListener("pointerdown", (ev) => {
    const activo = document.activeElement;
    if (activo?.matches("#vivo, #texto") && !ev.target.closest("#teclado")) activo.blur();
  }, true);

  if (!(await emparejar())) return;
  try {
    app.estado = await api("/api/estado");
  } catch (e) {
    if (e.codigo !== 401) mostrarEmparejar(e.message);
    return;
  }
  $("#emparejar").hidden = true;
  $("#app").hidden = false;
  mostrarEstado();
  // Se puede abrir directo en una pestaña: /#biblioteca
  const inicial = location.hash.slice(1);
  if ($(`#pestana-${inicial}`)) irA(inicial);

  // El estado se pide seguido solo con la app a la vista
  setInterval(() => {
    if (document.hidden || $("#app").hidden) return;
    if (app.pestana === "reproductor" || app.estado?.apagado || app.estado?.siguiente || tic++ % 3 === 0) refrescarEstado();
  }, 1000);
  setInterval(() => refrescarCuadro(), 1500);
  setInterval(() => {
    if (app.pestana === "peliculas" && !document.hidden) { cargarDescargas(); cargarTorrents(); }
  }, 2000);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { dejarDeVer(); mantenerClic(false); } else refrescarEstado();
  });
}
let tic = 0;

iniciar();
