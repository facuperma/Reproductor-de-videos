package io.github.facuperma.tvon.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.facuperma.tvon.Cartel
import io.github.facuperma.tvon.Detalle
import io.github.facuperma.tvon.FichaVideo
import io.github.facuperma.tvon.Hoja
import io.github.facuperma.tvon.Modelo
import io.github.facuperma.tvon.Opcion
import io.github.facuperma.tvon.PedirTexto
import io.github.facuperma.tvon.Pestana
import io.github.facuperma.tvon.SerieDet
import io.github.facuperma.tvon.tiempo

private val ORDENES = listOf("recientes" to "Agregadas hace poco", "titulo" to "Título (A → Z)",
    "anio" to "Año (más nuevas)", "puntaje" to "Mejor puntaje")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PestanaInicio(vm: Modelo) {
    val ini = vm.inicio
    val foco = LocalFocusManager.current
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(vertical = 8.dp)) {
        item {
            OutlinedTextField(
                vm.catalogoTexto, vm::buscarCatalogo, Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                singleLine = true, colors = campoColores(), placeholder = { Text("🔎 Buscar películas y series…") },
            )
        }
        if (ini == null) {
            val texto = vm.inicioError?.let { "No se pudo cargar la biblioteca: $it. Se reintenta solo…" }
                ?: "Cargando la biblioteca de la PC…"
            item { Pista(texto, Modifier.padding(16.dp)) }
            return@LazyColumn
        }
        if (vm.catalogoTexto.isBlank()) {
            if (ini.peliculas + ini.series == 0) {
                item {
                    Tarjeta(Modifier.padding(horizontal = 16.dp)) {
                        Text("Todavía no hay videos en la biblioteca de la PC.")
                        Pista("Agregá carpetas en TVon (Archivo → Agregar carpeta) o bajá una película desde ➕ Agregar.")
                    }
                }
            }
            fila(vm, "▶ Seguir viendo", ini.seguir)
            fila(vm, "⏭ A continuación", ini.siguientes)
            fila(vm, "🆕 Agregadas hace poco", ini.recientes)
            fila(vm, "★ Favoritos", ini.favoritos)
            item {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Chip("🎬 Películas (${ini.peliculas})", vm.catalogoTipo == "pelicula") { vm.filtrarCatalogo(tipo = "pelicula") }
                        Chip("📺 Series (${ini.series})", vm.catalogoTipo == "serie") { vm.filtrarCatalogo(tipo = "serie") }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Desplegable(if (vm.catalogoGenero.isEmpty()) "Todos los géneros" else vm.catalogoGenero,
                            listOf("" to "Todos los géneros") + ini.generos.map { it to it }) { vm.filtrarCatalogo(genero = it) }
                        Desplegable(ORDENES.first { it.first == vm.catalogoOrden }.second, ORDENES) { vm.filtrarCatalogo(orden = it) }
                    }
                }
            }
        }
        if (vm.catalogo.isEmpty()) {
            item { Pista(if (vm.catalogoTexto.isBlank()) "Nada con ese filtro." else "No hay nada con ese nombre.", Modifier.padding(16.dp)) }
        }
        // Grilla de pósters, de a tres
        items(vm.catalogo.chunked(3)) { fila ->
            Row(Modifier.padding(horizontal = 12.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (c in fila) Box(Modifier.weight(1f)) { CartelPoster(vm, c, Modifier.fillMaxWidth()) { foco.clearFocus() } }
                repeat(3 - fila.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.fila(vm: Modelo, titulo: String, carteles: List<Cartel>) {
    if (carteles.isEmpty()) return
    item {
        Column {
        Text(titulo, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 17.sp,
            modifier = Modifier.padding(start = 16.dp, top = 14.dp, bottom = 6.dp))
        LazyRow(contentPadding = PaddingValues(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(carteles, key = { "${it.tipo}${it.id}${it.clave}" }) { CartelPoster(vm, it, Modifier.width(118.dp)) }
        }
        }
    }
}

@Composable
private fun Desplegable(texto: String, opciones: List<Pair<String, String>>, alElegir: (String) -> Unit) {
    var abierto by remember { mutableStateOf(false) }
    Box {
        Chip("$texto ▾") { abierto = true }
        DropdownMenu(abierto, { abierto = false }) {
            for ((clave, nombre) in opciones) {
                DropdownMenuItem(text = { Text(nombre) }, onClick = { abierto = false; alElegir(clave) })
            }
        }
    }
}

/** El póster guardado en la PC o, si no tiene, un cartel con el título. */
@Composable
fun Poster(vm: Modelo, clave: String, hay: Boolean, titulo: String, modifier: Modifier = Modifier) {
    val imagen by produceState<ImageBitmap?>(null, clave, hay) { value = if (hay) vm.poster(clave) else null }
    Box(
        modifier
            .aspectRatio(2f / 3f)
            .clip(RoundedCornerShape(8.dp))
            .background(C.panelClaro),
        contentAlignment = Alignment.Center,
    ) {
        imagen?.let { Image(it, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            ?: Text(titulo, color = C.texto, textAlign = TextAlign.Center, fontSize = 13.sp, maxLines = 4,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(8.dp))
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CartelPoster(vm: Modelo, c: Cartel, modifier: Modifier, antes: () -> Unit = {}) {
    val vibrar = LocalHapticFeedback.current
    Column(
        modifier.combinedClickable(
            onClick = { antes(); vm.abrir(c) },
            onLongClick = { vibrar.performHapticFeedback(HapticFeedbackType.LongPress); menuCartel(vm, c) },
        )
    ) {
        Box {
            Poster(vm, c.clave, c.poster, c.titulo, Modifier.fillMaxWidth())
            if (c.visto) {
                Text("✓", color = Color.Black, fontWeight = FontWeight.Bold,
                    modifier = Modifier.align(Alignment.TopEnd).padding(4.dp).clip(RoundedCornerShape(10.dp))
                        .background(C.vista).padding(horizontal = 6.dp))
            } else if (c.tipo == "serie" && c.sinVer > 0 && c.sinVer < c.episodios) {
                Text("${c.sinVer}", color = Color.Black, fontWeight = FontWeight.Bold, fontSize = 12.sp,
                    modifier = Modifier.align(Alignment.TopEnd).padding(4.dp).clip(RoundedCornerShape(10.dp))
                        .background(C.pendiente).padding(horizontal = 6.dp))
            }
            c.progreso?.let {
                Box(Modifier.align(Alignment.BottomStart).padding(6.dp)) { Progreso(it) }
            }
        }
        Text(c.titulo, color = Color.White, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(top = 4.dp))
        val sub = listOfNotNull(c.anio, c.sub.takeIf { it.isNotEmpty() }).joinToString(" · ")
        if (sub.isNotEmpty()) Pista(sub)
    }
}

private fun menuCartel(vm: Modelo, c: Cartel) {
    val opciones = mutableListOf<Opcion>()
    c.id?.let { id ->
        opciones += Opcion("📱 Ver en el celular") { vm.verAcaId(id) }
        opciones += Opcion("📺 Ver en la PC") { vm.accion("reproducir", "id" to id) }
        opciones += Opcion("☰ A la cola de la PC") { vm.accion("cola_agregar", "ids" to listOf(id)) }
        opciones += Opcion(if (c.visto) "↺ Marcar como no visto" else "✓ Marcar como visto") {
            vm.accion("visto", "ids" to listOf(id), "visto" to !c.visto); vm.cargarInicio(); vm.cargarCatalogo()
        }
    }
    if (c.tipo == "serie") opciones += Opcion("📺 Ver la serie") { vm.abrirSerie(c.clave) }
    opciones += Opcion("🎞 Corregir la ficha…") { corregirFicha(vm, c.clave, c.titulo) }
    vm.hoja = Hoja(c.titulo, opciones)
}

private fun corregirFicha(vm: Modelo, clave: String, titulo: String) {
    vm.pedirTexto = PedirTexto("Título con el que se busca la ficha (podés sumar el año, p. ej. «Dune 2021»):", titulo) { texto ->
        vm.accion("ficha_corregir", "clave" to clave, "texto" to texto)
    }
}

// --- Detalle: la serie o la ficha del video ------------------------------------------------------------

@Composable
fun PantallaDetalle(vm: Modelo, d: Detalle) {
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().background(C.panel).padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text("←", fontSize = 24.sp, color = Color.White,
                modifier = Modifier.clip(RoundedCornerShape(20.dp)).clickable { vm.cerrarDetalle() }.padding(12.dp))
            Text(when (d) { is Detalle.DeSerie -> d.serie.titulo; is Detalle.DeVideo -> d.ficha.titulo },
                color = Color.White, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        when (d) {
            is Detalle.DeSerie -> DetalleSerie(vm, d.serie)
            is Detalle.DeVideo -> DetalleVideo(vm, d.ficha)
        }
    }
}

@Composable
private fun Cabecera(vm: Modelo, clave: String, poster: Boolean, titulo: String, anio: String?, generos: List<String>,
                     puntaje: Double?, fuente: String, sinopsis: String, extra: String = "") {
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Poster(vm, clave, poster, titulo, Modifier.width(120.dp))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(titulo, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 19.sp)
            if (extra.isNotEmpty()) Text(extra, color = C.acentoClaro)
            val linea = listOfNotNull(anio, puntaje?.let { "★ $it" }).joinToString(" · ")
            if (linea.isNotEmpty()) Text(linea)
            if (generos.isNotEmpty()) Pista(generos.joinToString(" · "))
            if (fuente.isNotEmpty()) Pista("Ficha: $fuente")
        }
    }
    if (sinopsis.isNotEmpty()) {
        var completa by rememberSaveable(sinopsis) { mutableStateOf(false) }
        Text(sinopsis, maxLines = if (completa) Int.MAX_VALUE else 5, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(top = 10.dp).clickable { completa = !completa })
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetalleSerie(vm: Modelo, s: SerieDet) {
    var temporada by rememberSaveable(s.clave) {
        mutableStateOf(s.temporadas.firstOrNull { t -> t.episodios.any { it.id == s.seguir } }?.numero
            ?: s.temporadas.firstOrNull()?.numero ?: 1)
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
        item {
            val total = s.temporadas.sumOf { it.episodios.size }
            val vistos = s.temporadas.sumOf { t -> t.episodios.count { it.visto } }
            Cabecera(vm, s.clave, s.poster, s.titulo, s.anio, s.generos, s.puntaje, s.fuente, s.sinopsis,
                "$vistos de $total capítulos vistos")
        }
        s.seguir?.let { id ->
            val ep = s.temporadas.flatMap { it.episodios }.firstOrNull { it.id == id }
            item {
                Column(Modifier.padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Pista("Para seguir: ${ep?.titulo.orEmpty()}")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Boton("📱 Ver en el celular", Modifier.weight(1f), Estilo.PRIMARIO) { vm.verAcaId(id) }
                        Boton("📺 En la PC", Modifier.weight(1f)) { vm.hacer("reproducir", "id" to id) }
                    }
                }
            }
        }
        if (s.temporadas.size > 1) {
            item {
                FlowRow(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (t in s.temporadas) Chip("Temporada ${t.numero}", t.numero == temporada) { temporada = t.numero }
                }
            }
        }
        val eps = s.temporadas.firstOrNull { it.numero == temporada }?.episodios.orEmpty()
        items(eps, key = { it.id }) { e ->
            Item(
                e.titulo, sub = if (e.visto) "✓ Visto" else e.progreso?.let { "Vas por ${(it * 100).toInt()} %" } ?: "",
                colorNombre = when { e.visto -> C.vista; e.progreso != null -> C.pendiente; else -> C.texto },
                tenue = !e.existe, icono = { IconoTexto("${e.episodio}") },
                alTocar = { vm.correr { vm.abrirFicha(e.id) } },
                abajo = { e.progreso?.let { Progreso(it) } },
            ) {
                Boton("▶", chico = true) { vm.verAcaId(e.id) }
            }
        }
        item {
            Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Boton("🎞 Corregir ficha", chico = true) { corregirFicha(vm, s.clave, s.titulo) }
                val ids = eps.map { it.id }
                if (ids.isNotEmpty()) Boton("✓ Temporada vista", chico = true) {
                    vm.correr { vm.accion("visto", "ids" to ids, "visto" to true); vm.refrescarDetalles() }
                }
            }
        }
    }
}

@Composable
private fun DetalleVideo(vm: Modelo, f: FichaVideo) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Cabecera(vm, f.clave, f.poster, f.titulo, f.anio, f.generos, f.puntaje, f.fuente, f.sinopsis,
            if (f.serie) f.nombreLindo.split(" · ").drop(1).joinToString(" · ") else "")
        Spacer(Modifier.height(4.dp))
        if (!f.existe) Text("El archivo ya no está en la PC.", color = C.error)
        if (f.posicion > 0) {
            Boton("📱 Seguir en el celular desde ${tiempo(f.posicion)}", Modifier.fillMaxWidth(), Estilo.PRIMARIO,
                habilitado = f.existe) { vm.verAca(f) }
            Boton("📱 Desde el principio", Modifier.fillMaxWidth(), habilitado = f.existe) { vm.verAca(f, desdeElPrincipio = true) }
        } else {
            Boton("📱 Ver en el celular", Modifier.fillMaxWidth(), Estilo.PRIMARIO, habilitado = f.existe) { vm.verAca(f) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Boton("📺 Ver en la PC", Modifier.weight(1f), habilitado = f.existe) {
                vm.correr { vm.accion("reproducir", "id" to f.id); vm.irA(Pestana.REPRODUCTOR) }
            }
            Boton("☰ A la cola", Modifier.weight(1f)) { vm.hacer("cola_agregar", "ids" to listOf(f.id)) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Boton(if (f.visto) "↺ No visto" else "✓ Visto", Modifier.weight(1f)) {
                vm.correr { vm.accion("visto", "ids" to listOf(f.id), "visto" to !f.visto); vm.refrescarDetalles() }
            }
            Boton(if (f.favorito) "☆ Quitar fav." else "★ Favorito", Modifier.weight(1f)) {
                vm.correr { vm.accion("favoritos", "ids" to listOf(f.id), "activo" to !f.favorito); vm.refrescarDetalles() }
            }
        }
        Boton("🎞 Corregir la ficha", Modifier.fillMaxWidth()) { corregirFicha(vm, f.clave, f.titulo) }
        Pista(if (f.subtitulos.isEmpty()) "Sin subtítulos junto al video (buscalos desde ▶ Control → CC)."
            else "Subtítulos: " + (f.subtitulos.firstOrNull { it.elegido }?.texto ?: "desactivados") +
                ". En el reproductor se cambian con el botón de subtítulos.")
        if (!f.conversion) Pista("Si un video no se oye o no se ve en el celular, instalá ffmpeg en la PC y TVon lo convierte solo.")
        Pista(f.nombre, Modifier.padding(top = 8.dp))
    }
}

// --- Reproductor en el celular ---------------------------------------------------------------------------

@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
fun PantallaVerAca(vm: Modelo) {
    val ver = vm.viendoAca ?: return
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        androidx.compose.ui.viewinterop.AndroidView(
            factory = { contexto ->
                androidx.media3.ui.PlayerView(contexto).apply {
                    player = ver.jugador
                    keepScreenOn = true
                    setShowSubtitleButton(true)
                    setShowNextButton(false)
                    setShowPreviousButton(false)
                }
            },
            update = { it.player = ver.jugador },
            modifier = Modifier.fillMaxSize(),
        )
        Row(Modifier.align(Alignment.TopStart).fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Chip("✕") { vm.dejarDeVerAca() }
            Text(ver.ficha?.nombreLindo.orEmpty(), color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f))
            // Convertido por la PC no se puede adelantar con la barra: estos botones lo piden de nuevo
            if (ver.conversion != null) {
                Chip("⏪ 30 s") { ver.saltar(-30_000) }
                Chip("30 s ⏩") { ver.saltar(30_000) }
            }
        }
        ver.error?.let { mensaje ->
            Column(Modifier.align(Alignment.Center).padding(24.dp).clip(RoundedCornerShape(12.dp)).background(C.panel)
                .padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(mensaje)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Boton("Reintentar", estilo = Estilo.PRIMARIO) { ver.reintentar() }
                    Boton("Seguir así", chico = true) { ver.error = null }
                    Boton("Cerrar", chico = true) { vm.dejarDeVerAca() }
                }
            }
        }
    }
}
