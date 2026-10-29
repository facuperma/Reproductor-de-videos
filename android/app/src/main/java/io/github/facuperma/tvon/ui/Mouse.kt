package io.github.facuperma.tvon.ui

import android.os.SystemClock
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import io.github.facuperma.tvon.Pestana
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.facuperma.tvon.Confirmar
import io.github.facuperma.tvon.Modelo
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/** Arriba de Mouse y de Pantalla: se pasa de una a otra sin otra pestaña. */
@Composable
fun SelectorMouse(vm: Modelo) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Chip("🖱 Touchpad", vm.pestana == Pestana.MOUSE) { vm.irA(Pestana.MOUSE) }
        Chip("🖥 Ver la pantalla de la PC", vm.pestana == Pestana.PANTALLA) { vm.irA(Pestana.PANTALLA) }
    }
}

@Composable
fun PestanaMouse(vm: Modelo) {
    // Sin desplazar la página: el touchpad ocupa todo lo de abajo, al alcance del pulgar,
    // y los botones quedan pegados al borde, como en una notebook
    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SelectorMouse(vm)
        vm.errorControl?.let { Text(it, color = C.error) }
        if (vm.monitores?.control != false) Teclado(vm, compacto = true)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Pista("Velocidad")
            var velocidad by remember { mutableFloatStateOf(vm.almacen.velocidad) }
            Slider(
                velocidad, { velocidad = it; vm.almacen.velocidad = it }, Modifier.weight(1f).padding(start = 12.dp),
                valueRange = 0.5f..4f, colors = deslizador(),
            )
        }
        Touchpad(vm, Modifier.weight(1f).heightIn(min = 140.dp))
        BotonesMouse(vm)
    }
}

@Composable
private fun Touchpad(vm: Modelo, modifier: Modifier) {
    var activo by remember { mutableStateOf(false) }
    val foco = LocalFocusManager.current
    Box(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(if (activo) C.panelClaro else C.panel)
            .border(1.dp, if (activo) C.acento else C.borde, RoundedCornerShape(16.dp))
            .pointerInput(Unit) {
                awaitEachGesture {
                    val primero = awaitFirstDown(requireUnconsumed = false)
                    activo = true
                    // Tocar el touchpad suelta el recuadro de texto (y esconde el teclado del celular)
                    foco.clearFocus()
                    val inicio = SystemClock.uptimeMillis()
                    var t = inicio
                    var maximo = 1
                    var movido = false
                    var rueda = 0f
                    val origen = primero.position
                    while (true) {
                        val evento = awaitPointerEvent()
                        val apretados = evento.changes.filter { it.pressed }
                        if (apretados.isEmpty()) break
                        maximo = max(maximo, apretados.size)
                        // En dp, como la versión web: la sensación no depende de la pantalla del celular
                        if (maximo == 1) {
                            val c = apretados.first()
                            val dx = (c.position.x - c.previousPosition.x) / density
                            val dy = (c.position.y - c.previousPosition.y) / density
                            if ((c.position - origen).getDistance() / density > 8) movido = true
                            if (movido) {
                                // Más rápido el dedo, más lejos va el puntero (como un touchpad de verdad)
                                val ahora = SystemClock.uptimeMillis()
                                val rapidez = hypot(dx, dy) / max(1L, ahora - t)
                                t = ahora
                                val factor = vm.almacen.velocidad * min(3f, 0.6f + rapidez * 1.5f)
                                vm.moverPuntero(dx * factor, dy * factor)
                            }
                        } else {
                            // Dos dedos: la rueda, con el primero que apoyaste
                            val c = apretados.first()
                            val dy = (c.position.y - c.previousPosition.y) / density
                            if (abs(c.position.y - origen.y) / density > 8) movido = true
                            rueda += dy
                            val pasos = (rueda / 30).toInt()
                            if (pasos != 0) {
                                rueda -= pasos * 30
                                vm.entrada("tipo" to "rueda", "pasos" to pasos)
                            }
                        }
                        evento.changes.forEach { it.consume() }
                    }
                    activo = false
                    // Un toque corto sin mover = clic; con dos dedos, clic derecho
                    if (!movido && SystemClock.uptimeMillis() - inicio < 350) {
                        vm.entrada("tipo" to "clic_aqui", "boton" to if (maximo >= 2) "derecho" else "izquierdo")
                    }
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Pista("Deslizá: mover · tocá: clic\n2 dedos: rueda · tocá con 2 dedos: clic derecho",
            Modifier.padding(24.dp))
    }
}

@Composable
private fun BotonesMouse(vm: Modelo) {
    Row(Modifier.fillMaxWidth().height(64.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        BotonMouse(vm, "Izquierdo", "izquierdo", Modifier.weight(1f))
        Box(
            Modifier
                .width(64.dp)
                .fillMaxSize()
                .clip(RoundedCornerShape(12.dp))
                .background(if (vm.mantenido) C.acento else C.panelClaro)
                .border(1.dp, if (vm.mantenido) C.acento else C.borde, RoundedCornerShape(12.dp))
                .clickable { vm.mantenerClic(!vm.mantenido) },
            contentAlignment = Alignment.Center,
        ) { Text(if (vm.mantenido) "🔓" else "🔒", fontSize = 20.sp) }
        BotonMouse(vm, "Derecho", "derecho", Modifier.weight(1f))
    }
}

/** Como el botón de un mouse: mientras está apretado, deslizar en el touchpad arrastra. */
@Composable
private fun BotonMouse(vm: Modelo, texto: String, boton: String, modifier: Modifier) {
    var apretado by remember { mutableStateOf(false) }
    val vibrar = LocalHapticFeedback.current
    Box(
        modifier
            .fillMaxSize()
            .clip(RoundedCornerShape(12.dp))
            .background(if (apretado) C.acento else C.panelClaro)
            .border(1.dp, if (apretado) C.acento else C.borde, RoundedCornerShape(12.dp))
            .pointerInput(boton) {
                awaitEachGesture {
                    awaitFirstDown().consume()
                    apretado = true
                    vibrar.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                    vm.entrada("tipo" to "boton", "boton" to boton, "apretado" to true)
                    while (awaitPointerEvent().changes.any { it.pressed }) { /* esperar a que se suelte */ }
                    apretado = false
                    vm.entrada("tipo" to "boton", "boton" to boton, "apretado" to false)
                }
            },
        contentAlignment = Alignment.Center,
    ) { Text(texto, color = if (apretado) Color.White else C.texto) }
}

// --- Teclado -----------------------------------------------------------------------------------------

private val TECLAS = listOf(
    "Enter" to "enter", "⌫" to "retroceso", "Esc" to "esc", "Tab" to "tab", "Espacio" to "espacio",
    "←" to "izquierda", "↑" to "arriba", "↓" to "abajo", "→" to "derecha", "Rueda ▲" to "+3", "Rueda ▼" to "-3",
    "Alt+Tab" to "alt+tab", "⊞ Win" to "win", "Ctrl+C" to "ctrl+c", "Ctrl+V" to "ctrl+v", "Alt+F4" to "alt+f4",
    "🔉" to "volumen_menos", "🔊" to "volumen_mas", "🔇" to "silencio",
)

// Teclado en vivo: se compara el campo con cómo estaba, así funciona con el autocorrector y las
// sugerencias del teclado (que reemplazan palabras enteras). Arranca con dos espacios para que el ⌫
// ande aunque no se haya escrito nada.
private const val CENTINELA = "  "
private val VACIO = TextFieldValue(CENTINELA, TextRange(CENTINELA.length))

/**
 * El recuadro de escribir, bien educado: al tocarlo abre el teclado del celular; cuando el teclado se
 * esconde (atrás, Enter, tocar el touchpad o la pantalla) suelta el foco, así no vuelve a abrirse solo
 * ni se queda «escuchando». Al salir de la app, también lo suelta.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Modifier.recuadroDeEscribir(): Modifier {
    val teclado = LocalSoftwareKeyboardController.current
    val foco = LocalFocusManager.current
    var enfocado by remember { mutableStateOf(false) }
    var tecladoAntes by remember { mutableStateOf(false) }
    val tecladoAhora = WindowInsets.isImeVisible
    LaunchedEffect(tecladoAhora) {
        if (tecladoAntes && !tecladoAhora && enfocado) foco.clearFocus()
        tecladoAntes = tecladoAhora
    }
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { foco.clearFocus() }
    return onFocusChanged {
        enfocado = it.isFocused
        if (it.isFocused) teclado?.show()
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Teclado(vm: Modelo, compacto: Boolean = false) {
    var enVivo by rememberSaveable { mutableStateOf(true) }
    Tarjeta {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("⌨ Teclado", color = Color.White, modifier = Modifier.weight(1f))
            Chip("En vivo", enVivo) { enVivo = true }
            Box(Modifier.width(6.dp))
            Chip("Escribir y enviar", !enVivo) { enVivo = false }
        }
        if (enVivo) {
            if (!compacto) Pista("Tocá el recuadro y escribí: cada letra va directo a la PC.")
            TecladoVivo(vm)
        } else {
            TecladoEnviar(vm)
        }
        val tocar = { teclas: String ->
            when {
                teclas.startsWith("+") || teclas.startsWith("-") -> vm.entrada("tipo" to "rueda", "pasos" to teclas.toInt())
                teclas == "alt+f4" -> vm.confirmar = Confirmar("¿Cerrar la ventana activa de la PC (Alt+F4)?", "Cerrar") {
                    vm.entrada("tipo" to "teclas", "teclas" to teclas)
                }
                else -> vm.entrada("tipo" to "teclas", "teclas" to teclas)
            }
        }
        if (compacto) {
            // En una sola fila que se desliza: el touchpad conserva el lugar
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(TECLAS) { (texto, teclas) -> Boton(texto, chico = true) { tocar(teclas) } }
            }
        } else {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((texto, teclas) in TECLAS) Boton(texto, chico = true) { tocar(teclas) }
            }
        }
    }
}

@Composable
private fun TecladoVivo(vm: Modelo) {
    val foco = LocalFocusManager.current
    var valor by remember { mutableStateOf(VACIO) }
    var anterior by remember { mutableStateOf(CENTINELA) }
    OutlinedTextField(
        value = valor,
        onValueChange = { nuevo ->
            // Por caracteres y no por unidades UTF-16: en la PC un emoji se borra con un solo ⌫
            val antes = anterior.codePoints().toArray()
            val ahora = nuevo.text.codePoints().toArray()
            var comun = 0
            while (comun < antes.size && comun < ahora.size && antes[comun] == ahora[comun]) comun++
            val borrar = antes.size - comun
            val texto = String(ahora, comun, ahora.size - comun)
            anterior = nuevo.text
            if (borrar > 0 || texto.isNotEmpty()) vm.entrada("tipo" to "editar", "borrar" to borrar, "texto" to texto)
            valor = if (nuevo.composition == null && (!nuevo.text.startsWith(CENTINELA) || nuevo.text.length > 60)) {
                anterior = CENTINELA
                VACIO
            } else nuevo
        },
        modifier = Modifier.fillMaxWidth().recuadroDeEscribir(),
        singleLine = true,
        colors = campoColores(),
        label = { Text("Tocá acá para escribir en la PC") },
        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 18.sp, textAlign = TextAlign.Start, color = C.texto),
        keyboardOptions = KeyboardOptions(
            autoCorrectEnabled = false, capitalization = KeyboardCapitalization.None, imeAction = ImeAction.Send,
        ),
        keyboardActions = KeyboardActions(onSend = {
            vm.entrada("tipo" to "teclas", "teclas" to "enter")
            valor = VACIO
            anterior = CENTINELA
            // Terminó de escribir: el teclado se va y manda de nuevo el video (o lo que esté en la PC)
            foco.clearFocus()
        }),
    )
}

@Composable
private fun TecladoEnviar(vm: Modelo) {
    val foco = LocalFocusManager.current
    var texto by rememberSaveable { mutableStateOf("") }
    // El botón Enviar manda solo el texto; Enter manda el texto y un Enter, así en la PC pasa lo
    // de siempre: busca, envía el mensaje o, en Word, salta de línea
    val enviar = { conEnter: Boolean ->
        if (texto.isNotEmpty()) vm.entrada("tipo" to "texto", "texto" to texto)
        if (conEnter) vm.entrada("tipo" to "teclas", "teclas" to "enter")
        texto = ""
        foco.clearFocus()
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            texto, { texto = it }, Modifier.weight(1f).recuadroDeEscribir(), singleLine = true, colors = campoColores(),
            placeholder = { Text("Escribir en la PC…") },
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { enviar(true) }),
        )
        Boton("Enviar", estilo = Estilo.PRIMARIO) { enviar(false) }
    }
}
