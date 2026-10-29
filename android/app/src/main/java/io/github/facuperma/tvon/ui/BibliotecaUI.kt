package io.github.facuperma.tvon.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.facuperma.tvon.ArchivoBib
import io.github.facuperma.tvon.Categoria
import io.github.facuperma.tvon.Hoja
import io.github.facuperma.tvon.Modelo
import io.github.facuperma.tvon.Opcion
import io.github.facuperma.tvon.PedirTexto
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PestanaBiblioteca(vm: Modelo) {
    val bib = vm.biblioteca
    val lista = rememberLazyListState()
    val alcance = rememberCoroutineScope()
    var categoriasAbiertas by rememberSaveable { mutableStateOf(true) }
    val esFavoritos = bib != null && vm.filtro == "categoria" && vm.categoria == bib.favoritos

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            state = lista,
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = if (vm.eligiendo) 80.dp else 16.dp),
        ) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        vm.busqueda, vm::buscar, Modifier.weight(1f), singleLine = true, colors = campoColores(),
                        placeholder = { Text("Buscar por nombre…") },
                    )
                    Boton(if (vm.eligiendo) "Listo" else "Elegir") {
                        if (vm.eligiendo) vm.terminarSeleccion() else vm.eligiendo = true
                    }
                }
            }
            if (bib == null) {
                item { Pista("Cargando…", Modifier.padding(16.dp)) }
                return@LazyColumn
            }
            item {
                LazyRow(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(bib.filtros) { f ->
                        Chip("${f.nombre} (${f.cantidad})", vm.filtro == f.filtro) { vm.elegirFiltro(f.filtro, null) }
                    }
                    item { Chip("+ Nueva categoría") { nuevaCategoria(vm) } }
                }
            }
            item {
                val pendientes = bib.categorias.count { it.estado == "pendiente" }
                Tarjeta {
                    Row(Modifier.fillMaxWidth().clickable { categoriasAbiertas = !categoriasAbiertas }) {
                        Text("🏷 Categorías", color = Color.White, fontWeight = FontWeight.SemiBold)
                        Pista(" · ${bib.categorias.size}" + if (pendientes > 0) " · $pendientes por ver" else "",
                            Modifier.weight(1f).padding(start = 4.dp))
                        Text(if (categoriasAbiertas) "▾" else "▸", color = C.tenue)
                    }
                    if (categoriasAbiertas) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Punto(C.pendiente); Pista(" por ver   ")
                            Punto(C.vista); Pista(" vista")
                        }
                        Pista("Mantené apretada una categoría para más opciones")
                        val elegir = { c: Categoria ->
                            vm.elegirFiltro("categoria", c.id)
                            alcance.launch { lista.animateScrollToItem(3) }
                            Unit
                        }
                        // Todas las categorías a la vista: primero las que tienen algo por ver, al final las vistas
                        val orden = bib.categorias.sortedBy { when (it.estado) { "pendiente" -> 0; "vista" -> 2; else -> 1 } }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (c in orden) TarjetaCategoria(vm, c, elegir)
                        }
                    }
                }
            }
            item {
                val visibles = vm.archivosVisibles.size
                Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    for ((clave, texto) in listOf("sin_ver" to "Sin ver", "vistos" to "✓ Vistos", "todos" to "Todos")) {
                        Chip(texto, vm.mostrar == clave) { vm.elegirMostrar(clave) }
                    }
                    Pista(if (visibles == vm.archivos.size) "$visibles archivo(s)" else "$visibles de ${vm.archivos.size}",
                        Modifier.weight(1f).padding(start = 4.dp))
                }
            }
            if (esFavoritos) {
                // En Favoritos, cada archivo va dentro de su categoría: un grupo que se despliega
                val nombres = bib.categorias.filter { it.id != bib.favoritos }.associate { it.id to it.nombre }
                val (sueltos, agrupados) = vm.archivosVisibles.map { a ->
                    a to a.categorias.filter { it in nombres }.minByOrNull { nombres.getValue(it).lowercase() }
                }.partition { it.second == null }
                items(sueltos.map { it.first }, key = { it.id }) { ItemArchivo(vm, it) }
                for ((cid, grupo) in agrupados.groupBy({ it.second!! }, { it.first }).toSortedMap(compareBy { nombres.getValue(it).lowercase() })) {
                    val abierto = cid in vm.favAbiertos
                    item(key = "grupo-$cid") {
                        Text((if (abierto) "▾ " else "▸ ") + "📁 ${nombres.getValue(cid)} (${grupo.size})",
                            color = Color.White, fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.fillMaxWidth()
                                .clickable { vm.favAbiertos = if (abierto) vm.favAbiertos - cid else vm.favAbiertos + cid }
                                .padding(vertical = 10.dp))
                    }
                    if (abierto) items(grupo, key = { "g$cid-${it.id}" }) { ItemArchivo(vm, it) }
                }
            } else {
                items(vm.archivosVisibles, key = { it.id }) { ItemArchivo(vm, it) }
            }
        }

        if (vm.eligiendo) {
            Row(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(C.panel)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text("${vm.seleccion.size} elegido(s)", Modifier.weight(1f), fontSize = 14.sp)
                val ids = vm.seleccion.toList()
                val conAlgo = { hacer: () -> Unit -> if (ids.isEmpty()) vm.mostrarAviso("Tocá los archivos para elegirlos", false) else hacer() }
                Boton("☰ Cola", chico = true) { conAlgo { vm.correr { vm.accion("cola_agregar", "ids" to ids); vm.terminarSeleccion() } } }
                Boton("★", chico = true) {
                    conAlgo { vm.correr { vm.accion("favoritos", "ids" to ids, "activo" to true); vm.terminarSeleccion(); vm.cargarBiblioteca() } }
                }
                Boton("🏷", chico = true) { conAlgo { menuCategorias(vm, ids) } }
                Boton("⋯", chico = true) { conAlgo { menuSeleccion(vm, ids) } }
            }
        }
    }
}

@Composable
private fun Punto(color: Color) = Box(Modifier.size(9.dp).clip(CircleShape).background(color))

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun TarjetaCategoria(vm: Modelo, c: Categoria, elegir: (Categoria) -> Unit) {
    val bib = vm.biblioteca ?: return
    val activa = vm.filtro == "categoria" && vm.categoria == c.id
    val color = when (c.estado) { "pendiente" -> C.pendiente; "vista" -> C.vista; else -> Color.Transparent }
    val vibrar = LocalHapticFeedback.current
    Column(
        Modifier
            .widthIn(min = 130.dp, max = 220.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(if (activa) C.chipActivo else C.panelClaro)
            .border(1.dp, if (activa) C.acento else C.borde, RoundedCornerShape(10.dp))
            .drawBehind { if (color != Color.Transparent) drawRect(color, Offset.Zero, size.copy(width = 4.dp.toPx())) }
            .combinedClickable(
                onClick = { elegir(c) },
                onLongClick = { vibrar.performHapticFeedback(HapticFeedbackType.LongPress); menuCategoria(vm, c) },
            )
            .padding(start = 14.dp, end = 10.dp, top = 8.dp, bottom = 8.dp)
    ) {
        Text(bib.nombre(c), color = if (color != Color.Transparent) color else Color.White, fontWeight = FontWeight.SemiBold,
            maxLines = 2, overflow = TextOverflow.Ellipsis)
        Pista("${c.cantidad} archivo(s)" + when (c.estado) { "vista" -> " · ✓ vista"; "pendiente" -> " · por ver"; else -> "" })
    }
}

@Composable
private fun ItemArchivo(vm: Modelo, a: ArchivoBib) {
    val fav = vm.biblioteca?.favoritos ?: -1
    val visto = a.tipo == "video" && a.existe && a.visto.isNotEmpty()
    // Como en la PC: el nombre en verde si ya se vio, amarillo si quedó a medias
    val color = when {
        !visto -> C.texto
        a.visto == "✓" -> C.vista
        else -> C.pendiente
    }
    val sub = if (visto && a.visto != "✓") "Vas por ${a.visto} · ${a.carpeta}" else a.carpeta
    Item(
        nombre = a.titulo, sub = sub, colorNombre = color, elegido = a.id in vm.seleccion, tenue = !a.existe,
        icono = {
            if (a.tipo == "imagen" && a.existe) Miniatura(vm, a.id) else IconoTexto(if (a.tipo == "video") "🎬" else "🖼")
        },
        alTocar = { if (vm.eligiendo) vm.alternarSeleccion(a.id) else menuArchivo(vm, a) },
        alMantener = {
            if (!vm.eligiendo) {
                vm.eligiendo = true
                vm.alternarSeleccion(a.id)
            }
        },
    ) {
        if (fav in a.categorias) Text("★", color = C.pendiente)
    }
}

@Composable
private fun Miniatura(vm: Modelo, id: Int) {
    val imagen by produceState<ImageBitmap?>(null, id) { value = vm.miniatura(id) }
    imagen?.let { Image(it, null, Modifier.size(36.dp).clip(RoundedCornerShape(6.dp)), contentScale = ContentScale.Crop) }
        ?: IconoTexto("🖼")
}

// --- Menús (hoja de acciones) ------------------------------------------------------------------------

private fun nuevaCategoria(vm: Modelo, ids: List<Int> = emptyList()) {
    vm.pedirTexto = PedirTexto("Nombre de la categoría nueva:") { nombre ->
        vm.accion("nueva_categoria", "nombre" to nombre, "ids" to ids)
        vm.cargarBiblioteca()
    }
}

private fun menuArchivo(vm: Modelo, a: ArchivoBib) {
    val bib = vm.biblioteca ?: return
    val esFav = bib.favoritos in a.categorias
    val ids = listOf(a.id)
    val opciones = mutableListOf(
        Opcion(if (a.tipo == "video") "▶ Reproducir en TVon" else "🖼 Mostrar en TVon") { vm.accion("reproducir", "id" to a.id) },
    )
    if (a.tipo == "video") opciones += Opcion("☰ Agregar a la cola") { vm.accion("cola_agregar", "ids" to ids) }
    opciones += listOf(
        Opcion(if (esFav) "☆ Quitar de Favoritos" else "★ Agregar a Favoritos") {
            vm.accion("favoritos", "ids" to ids, "activo" to !esFav)
            vm.cargarBiblioteca()
        },
        Opcion("🏷 Categorías…") { menuCategorias(vm, ids, a.categorias) },
        Opcion("＋ Categoría con el título") {
            vm.accion("categoria_titulo", "id" to a.id)
            vm.cargarBiblioteca()
        },
        Opcion("⧉ Abrir en una ventana aparte") { vm.accion("abrir_ventana", "id" to a.id) },
        Opcion("📂 Mostrar la carpeta en la PC") { vm.accion("abrir_ubicacion", "id" to a.id) },
        Opcion("Quitar de la biblioteca", confirmar = "¿Quitar de la biblioteca? El archivo NO se borra del disco.") {
            vm.accion("quitar", "ids" to ids)
            vm.cargarBiblioteca()
        },
        Opcion("🗑 Eliminar del disco", peligro = true,
            confirmar = "¿Mandar «${a.nombre}» a la Papelera de reciclaje de la PC? También se borran sus subtítulos.") {
            vm.accion("eliminar", "ids" to ids)
            vm.cargarBiblioteca()
        },
    )
    vm.hoja = Hoja(a.nombre, opciones)
}

/** Categorías de uno o varios archivos: cada una se pone o se saca con un toque. */
private fun menuCategorias(vm: Modelo, ids: List<Int>, actuales: List<Int>? = null) {
    val bib = vm.biblioteca ?: return
    val tiene = { c: Categoria ->
        actuales?.contains(c.id) ?: ids.all { id -> vm.archivos.find { it.id == id }?.categorias?.contains(c.id) == true }
    }
    vm.hoja = Hoja(if (ids.size == 1) "Categorías del archivo" else "Categorías de ${ids.size} archivos",
        bib.categorias.map { c ->
            val puesta = tiene(c)
            Opcion(bib.nombre(c), marca = if (puesta) "✓" else "") {
                vm.accion("asignar", "ids" to ids, "categoria" to c.id, "activo" to !puesta)
                vm.cargarBiblioteca()
                menuCategorias(vm, ids, if (ids.size == 1) vm.archivos.find { it.id == ids[0] }?.categorias else null)
            }
        } + Opcion("＋ Nueva categoría…") { nuevaCategoria(vm, ids) })
}

private fun menuSeleccion(vm: Modelo, ids: List<Int>) {
    val listo: suspend () -> Unit = {
        vm.terminarSeleccion()
        vm.cargarBiblioteca()
    }
    vm.hoja = Hoja("${ids.size} archivo(s)", listOf(
        Opcion("☆ Quitar de Favoritos") { vm.accion("favoritos", "ids" to ids, "activo" to false); listo() },
        Opcion("Quitar de la biblioteca", confirmar = "¿Quitar ${ids.size} archivo(s) de la biblioteca? NO se borran del disco.") {
            vm.accion("quitar", "ids" to ids); listo()
        },
        Opcion("🗑 Eliminar del disco", peligro = true,
            confirmar = "¿Mandar ${ids.size} archivo(s) a la Papelera de reciclaje de la PC? También se borran sus subtítulos.") {
            vm.accion("eliminar", "ids" to ids); listo()
        },
    ))
}

private fun menuCategoria(vm: Modelo, c: Categoria) {
    val recargar: suspend () -> Unit = { vm.cargarBiblioteca() }
    val opciones = mutableListOf(Opcion("▶ Ver sus archivos") { vm.elegirFiltro("categoria", c.id) })
    if (c.estado == "vista") {
        opciones += Opcion("↺ Marcar como no vista") { vm.accion("categoria_vista", "id" to c.id, "visto" to false); recargar() }
    } else if (c.estado == "pendiente" || c.sinPendiente) {
        opciones += Opcion("✓ Marcar como vista") { vm.accion("categoria_vista", "id" to c.id, "visto" to true); recargar() }
        opciones += Opcion(if (c.sinPendiente) "Volver a marcarla como pendiente" else "Quitar el amarillo de pendiente") {
            vm.accion("categoria_pendiente", "id" to c.id); recargar()
        }
    }
    if (!c.fija) {
        opciones += if (c.enFavoritos) Opcion("☆ Quitar toda la categoría de Favoritos") {
            vm.accion("categoria_favoritos", "id" to c.id, "activo" to false); recargar()
        } else Opcion("★ Agregar toda la categoría a Favoritos") {
            vm.accion("categoria_favoritos", "id" to c.id, "activo" to true); recargar()
        }
        opciones += Opcion("✎ Renombrar") {
            vm.pedirTexto = PedirTexto("Nuevo nombre de la categoría:", c.nombre) { nombre ->
                vm.accion("renombrar_categoria", "id" to c.id, "nombre" to nombre); recargar()
            }
        }
        opciones += Opcion("🗑 Borrar la categoría", peligro = true,
            confirmar = "¿Borrar la categoría «${c.nombre}»? Los archivos no se borran, solo pierden esta etiqueta.") {
            vm.accion("borrar_categoria", "id" to c.id)
            vm.filtro = "todos"
            vm.categoria = null
            recargar()
        }
    }
    vm.hoja = Hoja("Categoría «${c.nombre}»", opciones)
}
