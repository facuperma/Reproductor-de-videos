package io.github.facuperma.tvon.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.SystemClock
import android.provider.Settings
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import io.github.facuperma.tvon.CALIDADES
import io.github.facuperma.tvon.Modelo
import kotlin.math.max
import kotlin.math.min

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PestanaPantalla(vm: Modelo) {
    val contexto = LocalContext.current
    var arrastrar by rememberSaveable { mutableStateOf(false) }
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp)
    ) {
        SelectorMouse(vm)
        Spacer(Modifier.height(8.dp))
        if (!vm.viendo) {
            val m = vm.monitores
            Tarjeta {
                TituloTarjeta("🖥 Pantalla de la PC")
                Pista("Mirá la pantalla de la PC y manejala con el dedo. En la PC aparece un aviso mientras la estás viendo.")
                Text("Calidad")
                var calidad by remember { mutableStateOf(vm.almacen.calidad.coerceIn(CALIDADES.indices)) }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    CALIDADES.forEachIndexed { i, c -> Chip(c.texto, i == calidad) { calidad = i; vm.almacen.calidad = i } }
                }
                if (m != null && m.lista.size > 1) {
                    Text("Monitor")
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        m.lista.forEachIndexed { i, mon ->
                            val texto = "${i + 1}" + (if (mon.principal) " (principal)" else "") + (if (i == m.tvon) " · TVon" else "") +
                                " — ${mon.ancho}×${mon.alto}"
                            Chip(texto, i == vm.monitor) { vm.monitor = i }
                        }
                    }
                }
                val permitida = m?.pantalla != false
                Boton("Ver la pantalla", Modifier.fillMaxWidth(), Estilo.PRIMARIO, habilitado = permitida) {
                    vm.verPantalla(CALIDADES[calidad])
                }
                if (!permitida) Text("Compartir la pantalla está desactivado en TVon (📱 ON → Opciones).", color = C.error)
                vm.errorPantalla?.let { Text(it, color = C.error) }
            }
            Tarjeta {
                TituloTarjeta("📲 Pantalla del celular en la PC")
                Pista("Lo hace Windows por Miracast:")
                Text("1. Tocá «Preparar la PC»: en la PC se abre Proyectar en este equipo. Elegí Disponible en todas " +
                    "partes y abrí la app Conectar (si no está, Windows ofrece instalar «Pantalla inalámbrica»).")
                Text("2. Tocá «Transmitir desde este celular» y elegí la PC (en algunos celulares se llama Smart View " +
                    "o Duplicar pantalla, en la barra de notificaciones).")
                Boton("📲 Preparar la PC para recibir", Modifier.fillMaxWidth()) { vm.hacer("mostrar_celular") }
                Boton("📡 Transmitir desde este celular", Modifier.fillMaxWidth()) {
                    try {
                        contexto.startActivity(Intent(Settings.ACTION_CAST_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    } catch (e: ActivityNotFoundException) {
                        vm.mostrarAviso("Este celular no tiene esa opción en Ajustes: buscá «Smart View» o «Duplicar pantalla» en la barra de notificaciones.", true)
                    }
                }
            }
            return@Column
        }

        val control = vm.monitores?.control != false
        Row(Modifier.fillMaxWidth().padding(bottom = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (control) {
                Chip("👆 Tocar", !arrastrar) { arrastrar = false }
                Chip("✋ Arrastrar", arrastrar) { arrastrar = true }
            }
            Box(Modifier.weight(1f))
            Boton("⛶", chico = true) { vm.pantallaCompleta = true }
            Boton("✕", chico = true, estilo = Estilo.PELIGRO) { vm.dejarDeVer() }
        }
        Lienzo(vm, arrastrar, control, Modifier.fillMaxWidth())
        if (control) {
            Pista(if (!arrastrar) "Tocá para hacer clic · dos toques: doble clic · mantené: clic derecho · deslizá: rueda · pellizcá: zoom"
                else "Arrastrá para mover ventanas, seleccionar o mover barras (mantiene apretado el clic)",
                Modifier.padding(vertical = 6.dp))
            Teclado(vm)
        }
    }
}

/** La pantalla de la PC a todo el celular, acostado. */
@Composable
fun PantallaCompleta(vm: Modelo) {
    var arrastrar by rememberSaveable { mutableStateOf(false) }
    val control = vm.monitores?.control != false
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        Lienzo(vm, arrastrar, control, Modifier.fillMaxSize(), completa = true)
        Row(
            Modifier
                .align(Alignment.TopEnd)
                .padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (control) Chip(if (arrastrar) "✋" else "👆") { arrastrar = !arrastrar }
            Chip("✕ Salir") { vm.pantallaCompleta = false }
        }
    }
}

@Composable
private fun Lienzo(vm: Modelo, arrastrar: Boolean, control: Boolean, modifier: Modifier, completa: Boolean = false) {
    val imagen = vm.pantallaPC
    var tamano by remember { mutableStateOf(IntSize.Zero) }
    var zoom by remember { mutableFloatStateOf(1f) }
    var corrimiento by remember { mutableStateOf(Offset.Zero) }
    val foco = LocalFocusManager.current
    val vibrar = LocalHapticFeedback.current
    // Los gestos leen siempre lo último (el modo, la imagen) sin reiniciarse
    val modoArrastrar by rememberUpdatedState(arrastrar)
    val actual by rememberUpdatedState(imagen)

    fun limitar(o: Offset): Offset {
        val maxX = (zoom - 1) * tamano.width / 2
        val maxY = (zoom - 1) * tamano.height / 2
        return Offset(o.x.coerceIn(-maxX, maxX), o.y.coerceIn(-maxY, maxY))
    }

    /** De un punto del recuadro a coordenadas relativas (0 a 1) sobre la pantalla de la PC. */
    fun relativo(p: Offset): Offset {
        val img = actual ?: return Offset(.5f, .5f)
        val centro = Offset(tamano.width / 2f, tamano.height / 2f)
        val c = (p - centro - corrimiento) / zoom + centro
        val escala = min(tamano.width / img.width.toFloat(), tamano.height / img.height.toFloat())
        val ancho = img.width * escala
        val alto = img.height * escala
        return Offset((c.x - (tamano.width - ancho) / 2) / ancho, (c.y - (tamano.height - alto) / 2) / alto)
    }

    val proporcion = imagen?.let { it.width.toFloat() / it.height } ?: (16f / 9f)
    Box(
        modifier
            .then(if (completa) Modifier else Modifier.aspectRatio(proporcion))
            .clip(RoundedCornerShape(if (completa) 0.dp else 8.dp))
            .background(Color.Black)
            .onSizeChanged { tamano = it }
            .pointerInput(control) {
                if (!control) return@pointerInput
                var ultimoToque = 0L
                awaitEachGesture {
                    val abajo = awaitFirstDown(requireUnconsumed = false)
                    foco.clearFocus() // tocar la pantalla suelta el recuadro de escribir
                    val inicio = abajo.position
                    var ultima = inicio
                    var movido = false
                    var mantenido = false
                    var varios = false
                    var sobrante = 0f
                    var ultimoMovimiento = 0L
                    val arrastrando = modoArrastrar
                    if (arrastrando) relativo(inicio).let { vm.entrada("tipo" to "apretar", "x" to it.x, "y" to it.y) }
                    val limite = SystemClock.uptimeMillis() + 600
                    while (true) {
                        val esperarMantener = !arrastrando && !movido && !mantenido && !varios
                        val evento = if (esperarMantener) {
                            withTimeoutOrNull(max(1L, limite - SystemClock.uptimeMillis())) { awaitPointerEvent() }
                        } else awaitPointerEvent()
                        if (evento == null) {
                            // Mantener apretado sin mover = clic derecho
                            mantenido = true
                            vibrar.performHapticFeedback(HapticFeedbackType.LongPress)
                            relativo(inicio).let { vm.entrada("tipo" to "derecho", "x" to it.x, "y" to it.y) }
                            continue
                        }
                        val apretados = evento.changes.filter { it.pressed }
                        if (apretados.isEmpty()) break
                        if (apretados.size >= 2) {
                            // Pellizcar: zoom; con dos dedos se mueve la imagen
                            varios = true
                            zoom = (zoom * evento.calculateZoom()).coerceIn(1f, 4f)
                            corrimiento = limitar(corrimiento + evento.calculatePan())
                            evento.changes.forEach { it.consume() }
                            continue
                        }
                        val c = apretados.first()
                        ultima = c.position
                        if ((c.position - inicio).getDistance() / density > 12) movido = true
                        if (arrastrando) {
                            val ahora = SystemClock.uptimeMillis()
                            if (ahora - ultimoMovimiento > 40) { // como mucho 25 movimientos por segundo
                                ultimoMovimiento = ahora
                                relativo(c.position).let { vm.entrada("tipo" to "mover", "x" to it.x, "y" to it.y) }
                            }
                        } else if (movido && !varios) {
                            val delta = c.position - c.previousPosition
                            if (zoom > 1f) {
                                corrimiento = limitar(corrimiento + delta) // con zoom, deslizar mueve la imagen
                            } else {
                                sobrante += delta.y / density // sin zoom, deslizar = rueda del mouse
                                val pasos = (sobrante / 40).toInt()
                                if (pasos != 0) {
                                    sobrante -= pasos * 40
                                    vm.entrada("tipo" to "rueda", "pasos" to pasos)
                                }
                            }
                        }
                        evento.changes.forEach { it.consume() }
                    }
                    if (arrastrando) {
                        relativo(ultima).let { vm.entrada("tipo" to "soltar", "x" to it.x, "y" to it.y) }
                    } else if (!movido && !mantenido && !varios) {
                        val ahora = SystemClock.uptimeMillis()
                        val p = relativo(inicio)
                        // Dos toques seguidos = doble clic
                        if (ahora - ultimoToque < 350) {
                            vm.entrada("tipo" to "doble", "x" to p.x, "y" to p.y)
                            ultimoToque = 0
                        } else {
                            vm.entrada("tipo" to "clic", "x" to p.x, "y" to p.y)
                            ultimoToque = ahora
                        }
                    }
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        if (imagen == null) {
            CircularProgressIndicator(color = C.acento)
        } else {
            Image(
                imagen, "Pantalla de la PC",
                Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        scaleX = zoom
                        scaleY = zoom
                        translationX = corrimiento.x
                        translationY = corrimiento.y
                    },
                contentScale = ContentScale.Fit,
            )
        }
        if (zoom > 1f) {
            Chip("🔍 ${"%.1f".format(zoom)}× ✕", modifier = Modifier.align(Alignment.BottomStart).padding(8.dp)) {
                zoom = 1f
                corrimiento = Offset.Zero
            }
        }
    }
}
