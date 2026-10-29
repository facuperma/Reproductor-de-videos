package io.github.facuperma.tvon.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.facuperma.tvon.Descarga
import io.github.facuperma.tvon.Hoja
import io.github.facuperma.tvon.Modelo
import io.github.facuperma.tvon.Opcion
import io.github.facuperma.tvon.Torrent
import io.github.facuperma.tvon.miles
import io.github.facuperma.tvon.tamano

@Composable
fun PestanaPeliculas(vm: Modelo) {
    val foco = LocalFocusManager.current
    LazyColumn(contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp), modifier = Modifier.fillMaxSize()) {
        item {
            Tarjeta {
                TituloTarjeta("🧲 Torrent (link magnet)")
                Pista("Copiá el link magnet, pegalo acá y la PC la baja con 🧲 Torrents. Al terminar entra sola a la " +
                    "biblioteca. También podés tocar un link magnet en el navegador y abrirlo con TVon ON.")
                OutlinedTextField(
                    vm.enlaceTorrent, { vm.enlaceTorrent = it }, Modifier.fillMaxWidth(), singleLine = true,
                    colors = campoColores(), placeholder = { Text("magnet:?xt=…") },
                    keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, keyboardType = KeyboardType.Uri,
                        capitalization = KeyboardCapitalization.None, imeAction = ImeAction.Go),
                    keyboardActions = KeyboardActions(onGo = { foco.clearFocus(); vm.bajarTorrent() }),
                )
                Boton("⬇ Bajar en la PC", Modifier.fillMaxWidth(), Estilo.PRIMARIO) { foco.clearFocus(); vm.bajarTorrent() }
                if (vm.torrents.isEmpty()) Pista("No hay torrents bajando.")
                for (t in vm.torrents) ItemTorrent(vm, t)
            }
        }
        item {
            Tarjeta {
                TituloTarjeta("🎞 Películas de dominio público")
                Pista("De la colección del Internet Archive. Se bajan en la PC y entran solas a la biblioteca.")
                val buscar = { foco.clearFocus(); vm.correr { vm.buscarPeliculas(1) }; Unit }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        vm.peliculasTexto, { vm.peliculasTexto = it }, Modifier.weight(1f), singleLine = true,
                        colors = campoColores(), placeholder = { Text("Título (vacío = las más populares)") },
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                        keyboardActions = KeyboardActions(onSearch = { buscar() }),
                    )
                    Boton("Buscar", estilo = Estilo.PRIMARIO) { buscar() }
                }
                Orden(vm)
            }
        }
        item {
            Pista(vm.peliculasMensaje ?: "${vm.peliculas.size} de ${miles(vm.peliculasTotal.toLong())} películas",
                Modifier.padding(vertical = 6.dp))
        }
        items(vm.peliculas, key = { "p" + it.identificador }) { p ->
            Item(p.titulo, listOfNotNull(p.anio, "${miles(p.descargas)} descargas").joinToString(" · "), { IconoTexto("🎞") }) {
                if (p.estadoTexto.isNotEmpty()) Pista(p.estadoTexto, color = C.acentoClaro)
                else Boton("⬇", chico = true) {
                    vm.correr {
                        vm.accion("dp_descargar", "peliculas" to listOf(io.github.facuperma.tvon.json(
                            "identificador" to p.identificador, "titulo" to p.titulo, "anio" to p.anio)))
                        vm.peliculas = vm.peliculas.map { if (it.identificador == p.identificador) it.copy(estadoTexto = "En cola") else it }
                        vm.cargarDescargas()
                    }
                }
            }
        }
        if (vm.peliculas.size < vm.peliculasTotal) {
            item { Boton("Cargar más", Modifier.fillMaxWidth().padding(vertical = 6.dp)) { vm.masPeliculas() } }
        }
        item {
            val d = vm.descargas
            Tarjeta {
                TituloTarjeta("⬇ Descargas" + if (d != null && d.cantidad > 0) " · ${d.cantidad} · ${tamano(d.bytes)}" else "")
                if (d == null || d.lista.isEmpty()) Pista("No hay descargas.")
                d?.lista?.forEach { ItemDescarga(vm, it) }
            }
        }
        item { DescargaAutomatica(vm) }
    }
}

@Composable
private fun Orden(vm: Modelo) {
    var abierto by remember { mutableStateOf(false) }
    val texto = vm.ordenes.firstOrNull { it.first == vm.orden }?.second ?: "Más populares"
    Box {
        Boton("Ordenar: $texto ▾", Modifier.fillMaxWidth()) { abierto = true }
        DropdownMenu(abierto, { abierto = false }) {
            for ((clave, nombre) in vm.ordenes) {
                DropdownMenuItem(text = { Text(nombre) }, onClick = {
                    abierto = false
                    vm.orden = clave
                    vm.correr { vm.buscarPeliculas(1) }
                })
            }
        }
    }
}

@Composable
private fun ItemTorrent(vm: Modelo, t: Torrent) {
    var sub = t.error?.let { "Error: $it" } ?: t.estadoTexto
    if (t.total > 0) sub += " · ${100 * t.recibido / t.total} % de ${tamano(t.total)}"
    if (t.estado == "active" && t.velocidad > 0) sub += " · ${tamano(t.velocidad)}/s"
    if (t.restante.isNotEmpty()) sub += " · faltan ${t.restante}"
    Item(
        t.nombre, sub, { IconoTexto(if (t.estado == "paused") "⏸" else "🧲") },
        alTocar = {
            vm.hoja = Hoja(t.nombre, listOf(
                if (t.estado == "paused") Opcion("▶ Reanudar") { vm.accion("torrent_reanudar", "gid" to t.gid); vm.cargarTorrents() }
                else Opcion("⏸ Pausar") { vm.accion("torrent_pausar", "gid" to t.gid); vm.cargarTorrents() },
                Opcion("✕ Cancelar y borrar lo bajado", peligro = true, confirmar = "¿Cancelar «${t.nombre}»? Se borra lo que ya bajó.") {
                    vm.accion("torrent_cancelar", "gid" to t.gid); vm.cargarTorrents()
                },
            ))
        },
        abajo = { if (t.total > 0) Progreso(t.recibido.toFloat() / t.total) },
    )
}

@Composable
private fun ItemDescarga(vm: Modelo, d: Descarga) {
    val titulo = d.anio?.let { "${d.titulo} ($it)" } ?: d.titulo
    var sub = d.error?.let { "Error: $it" } ?: d.estadoTexto
    if (d.estado == "descargando" && d.total > 0) sub += " · ${100 * d.recibido / d.total} % de ${tamano(d.total)}"
    else if (d.tamano > 0) sub += " · ${tamano(d.tamano)}"
    val icono = when (d.estado) { "descargando" -> "⬇"; "completa" -> "✔"; else -> "🎞" }
    Item(
        titulo, sub, { IconoTexto(icono) },
        alTocar = {
            val ids = listOf(d.identificador)
            val listo: suspend () -> Unit = { vm.cargarDescargas() }
            val opciones = mutableListOf<Opcion>()
            if (d.estado == "descargando" || d.estado == "pendiente") opciones += Opcion("Cancelar la descarga") { vm.accion("dp_cancelar", "ids" to ids); listo() }
            if (d.estado == "error" || d.estado == "cancelada") opciones += Opcion("↻ Reintentar") { vm.accion("dp_reintentar", "ids" to ids); listo() }
            if (d.estado != "descargando") opciones += Opcion("Quitar de la lista") { vm.accion("dp_quitar", "ids" to ids); listo() }
            if (d.estado == "completa") opciones += Opcion("🗑 Eliminar la película", peligro = true,
                confirmar = "¿Mandarla a la Papelera de la PC con sus subtítulos? La descarga automática no la vuelve a bajar.") {
                vm.accion("dp_eliminar", "ids" to ids); listo()
            }
            vm.hoja = Hoja(titulo, opciones)
        },
        abajo = { if ((d.estado == "descargando" || d.estado == "pendiente") && d.total > 0) Progreso(d.recibido.toFloat() / d.total) },
    )
}

@Composable
private fun DescargaAutomatica(vm: Modelo) {
    val d = vm.descargas ?: return
    // Lo que se escribe no lo pisa la PC hasta salir del campo
    var peliculas by remember { mutableStateOf("") }
    var gb by remember { mutableStateOf("") }
    var editando by remember { mutableStateOf(false) }
    LaunchedEffect(d.autoPeliculas, d.autoGb, editando) {
        if (!editando) {
            peliculas = d.autoPeliculas.toString()
            gb = d.autoGb.toString()
        }
    }
    val guardar = {
        vm.hacer("dp_auto", "max_peliculas" to (peliculas.toIntOrNull() ?: 1).coerceAtLeast(1),
            "max_gb" to (gb.toIntOrNull() ?: 1).coerceAtLeast(1))
        Unit
    }
    Tarjeta {
        TituloTarjeta("Descarga automática")
        Interruptor("Bajar solas las más populares", d.autoActiva) { vm.hacer("dp_auto", "activa" to it) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("hasta")
            OutlinedTextField(
                peliculas, { peliculas = it.filter(Char::isDigit) }, Modifier.weight(1f)
                    .onFocusChanged { if (editando && !it.isFocused) guardar(); editando = it.isFocused },
                singleLine = true, colors = campoColores(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                suffix = { Text("pelis") },
            )
            Text("o")
            OutlinedTextField(
                gb, { gb = it.filter(Char::isDigit) }, Modifier.weight(1f)
                    .onFocusChanged { if (editando && !it.isFocused) guardar(); editando = it.isFocused },
                singleLine = true, colors = campoColores(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                suffix = { Text("GB") },
            )
        }
        Pista("Siempre se dejan al menos 5 GB libres en el disco de la PC.")
    }
}
