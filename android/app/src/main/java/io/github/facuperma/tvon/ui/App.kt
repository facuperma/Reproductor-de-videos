package io.github.facuperma.tvon.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.facuperma.tvon.Fase
import io.github.facuperma.tvon.Modelo
import io.github.facuperma.tvon.Opcion
import io.github.facuperma.tvon.Pestana
import io.github.facuperma.tvon.R
import io.github.facuperma.tvon.huellaLinda
import kotlinx.coroutines.delay

@Composable
fun App(vm: Modelo) {
    Box(
        Modifier
            .fillMaxSize()
            .background(C.fondo)
    ) {
        when (val fase = vm.fase) {
            Fase.Cargando -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Logo(96) }
            is Fase.Emparejar -> PantallaEmparejar(vm, fase.mensaje)
            is Fase.SinConexion -> PantallaSinConexion(vm, fase.mensaje)
            Fase.Lista -> Principal(vm)
        }
        Dialogos(vm)
        Tostada(vm, Modifier.align(Alignment.BottomCenter))
    }
}

@Composable
fun Logo(lado: Int) = Image(painterResource(R.drawable.logo), null, Modifier.size(lado.dp))

@Composable
fun TituloTVon(tamano: Int = 17) {
    Text(buildAnnotatedString {
        append("TV")
        withStyle(SpanStyle(color = C.verde, fontWeight = FontWeight.ExtraBold, fontSize = (tamano * 1.45).sp)) { append("ON") }
    }, fontWeight = FontWeight.Bold, fontSize = tamano.sp, color = Color.White)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Principal(vm: Modelo) {
    if (vm.pantallaCompleta && vm.viendo) {
        // La pantalla de la PC a todo el celular, acostado
        PantallaCompleta(vm)
        return
    }
    if (vm.viendoAca != null) {
        // Una película de la PC, vista en el celular
        PantallaVerAca(vm)
        return
    }
    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(C.panel)
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Logo(28)
            Box(Modifier.weight(1f)) { TituloTVon() }
            Box(
                Modifier
                    .size(10.dp)
                    .clip(CircleShape)
                    .background(if (vm.conectado) C.verde else C.peligro)
            )
        }
        Avisos(vm)
        Box(Modifier.weight(1f).imePadding()) {
            val detalle = vm.detalles.lastOrNull()
            if (detalle != null) PantallaDetalle(vm, detalle) else when (vm.pestana) {
                Pestana.INICIO -> PestanaInicio(vm)
                Pestana.REPRODUCTOR -> PestanaReproductor(vm)
                Pestana.BIBLIOTECA -> PestanaBiblioteca(vm)
                Pestana.PELICULAS -> PestanaPeliculas(vm)
                Pestana.MOUSE -> PestanaMouse(vm)
                Pestana.PANTALLA -> PestanaPantalla(vm)
                Pestana.MAS -> PestanaMas(vm)
            }
        }
        // Con el teclado del celular abierto, las pestañas se esconden: más lugar para escribir
        if (!WindowInsets.isImeVisible) NavigationBar(containerColor = C.panel, windowInsets = WindowInsets(0, 0, 0, 0)) {
            for (p in Pestana.entries.filter { it.enBarra }) {
                NavigationBarItem(
                    selected = vm.detalles.isEmpty() && (vm.pestana == p || (p == Pestana.MOUSE && vm.pestana == Pestana.PANTALLA)),
                    onClick = {
                        vm.detalles = emptyList()
                        vm.irA(p)
                    },
                    icon = { Text(p.icono, fontSize = 18.sp) },
                    label = { Text(p.texto, fontSize = 10.sp, maxLines = 1) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedTextColor = Color.White, unselectedTextColor = C.tenue, indicatorColor = C.chipActivo,
                    ),
                )
            }
        }
    }
}

/** Avisos que valen en cualquier pestaña: apagado, siguiente capítulo, TVon escondido. */
@Composable
private fun Avisos(vm: Modelo) {
    val e = vm.estado ?: return
    Column(Modifier.padding(horizontal = 12.dp)) {
        e.apagadoSegundos?.let { s ->
            Banner("🔌 La PC se apaga en $s s", peligro = true) {
                Boton("Cancelar", chico = true) { vm.hacer("cancelar_apagado") }
                Boton("Apagar ahora", chico = true, estilo = Estilo.PELIGRO) {
                    vm.confirmar = io.github.facuperma.tvon.Confirmar("¿Apagar la PC ahora?", "Apagar") { vm.accion("apagar_ahora") }
                }
            }
        }
        e.siguiente?.let { s ->
            Banner(s.texto, s.nombre) {
                Boton("▶ Ahora", chico = true, estilo = Estilo.PRIMARIO) { vm.hacer("siguiente_ahora") }
                Boton("Cancelar", chico = true) { vm.hacer("cancelar_siguiente") }
            }
        }
        if (!e.ventanaVisible && vm.pestana != Pestana.MOUSE && vm.pestana != Pestana.PANTALLA) {
            Banner("TVon está escondido en la PC", "ON sigue: el mouse y el teclado andan.") {
                Boton("Abrir TVon", chico = true, estilo = Estilo.PRIMARIO) { vm.hacer("mostrar_tvon") }
            }
        }
    }
}

@Composable
private fun Banner(titulo: String, sub: String = "", peligro: Boolean = false, botones: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (peligro) C.peligroFondo else C.panelClaro)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(titulo, fontWeight = FontWeight.Bold, color = Color.White)
        if (sub.isNotEmpty()) Pista(sub)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { botones() }
    }
}

@Composable
private fun Tostada(vm: Modelo, modifier: Modifier) {
    val aviso = vm.aviso ?: return
    LaunchedEffect(aviso.id) {
        delay(if (aviso.malo) 5000 else 3000)
        if (vm.aviso?.id == aviso.id) vm.aviso = null
    }
    Box(
        modifier
            .navigationBarsPadding()
            .padding(start = 16.dp, end = 16.dp, bottom = 96.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (aviso.malo) C.peligroFondo else C.panelClaro)
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) { Text(aviso.texto, color = if (aviso.malo) C.peligroTexto else Color.White) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Dialogos(vm: Modelo) {
    vm.hoja?.let { hoja ->
        ModalBottomSheet(
            onDismissRequest = { vm.hoja = null },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = C.panel,
        ) {
            Column(
                Modifier
                    .padding(horizontal = 16.dp)
                    .padding(bottom = 24.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Text(hoja.titulo, fontWeight = FontWeight.SemiBold, color = Color.White, modifier = Modifier.padding(bottom = 10.dp))
                for (o in hoja.opciones) OpcionHoja(vm, o)
            }
        }
    }

    vm.confirmar?.let { c ->
        AlertDialog(
            onDismissRequest = { vm.confirmar = null },
            containerColor = C.panel, titleContentColor = Color.White, textContentColor = C.texto,
            text = { Text(c.texto) },
            confirmButton = {
                TextButton(onClick = { vm.confirmar = null; vm.correr { c.hacer() } }) { Text(c.si) }
            },
            dismissButton = { TextButton(onClick = { vm.confirmar = null }) { Text("Cancelar") } },
        )
    }

    vm.pedirTexto?.let { p ->
        var texto by rememberSaveable(p) { mutableStateOf(p.inicial) }
        val listo = {
            vm.pedirTexto = null
            texto.trim().takeIf { it.isNotEmpty() }?.let { t -> vm.correr { p.hacer(t) } }
        }
        AlertDialog(
            onDismissRequest = { vm.pedirTexto = null },
            containerColor = C.panel, titleContentColor = Color.White, textContentColor = C.texto,
            title = { Text(p.titulo, fontSize = 17.sp) },
            text = {
                OutlinedTextField(
                    texto, { texto = it }, singleLine = true, colors = campoColores(),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { listo() }),
                )
            },
            confirmButton = { TextButton(onClick = { listo() }) { Text("Aceptar") } },
            dismissButton = { TextButton(onClick = { vm.pedirTexto = null }) { Text("Cancelar") } },
        )
    }

    vm.huellaPorConfirmar?.let { h ->
        AlertDialog(
            onDismissRequest = { vm.huellaPorConfirmar = null },
            containerColor = C.panel, titleContentColor = Color.White, textContentColor = C.texto,
            title = { Text("¿Es tu PC?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Este código QR es de un TVon sin la huella del certificado. Compará esta huella con la " +
                        "que muestra la ventana 📱 ON de la PC (🔒 Huella del certificado):")
                    Text(huellaLinda(h.huella), color = C.acentoClaro, fontSize = 13.sp)
                    Pista("Si no es igual, no sigas: otra máquina podría estar haciéndose pasar por tu PC. " +
                        "Actualizando TVon en la PC, el QR ya trae la huella y no hace falta comparar.")
                }
            },
            confirmButton = { TextButton(onClick = { vm.emparejarCon(h.enlace, h.huella) }) { Text("Es la misma") } },
            dismissButton = { TextButton(onClick = { vm.huellaPorConfirmar = null }) { Text("Cancelar") } },
        )
    }
}

@Composable
private fun OpcionHoja(vm: Modelo, o: Opcion) {
    TextButton(
        onClick = {
            vm.hoja = null
            if (o.confirmar != null) vm.confirmar = io.github.facuperma.tvon.Confirmar(o.confirmar) { o.hacer() }
            else vm.correr { o.hacer() }
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(o.texto, color = if (o.peligro) Color(0xFFFFB4B4) else C.texto, modifier = Modifier.weight(1f), fontSize = 16.sp)
        if (o.marca.isNotEmpty()) {
            Spacer(Modifier.width(8.dp))
            Text(o.marca, color = C.verde)
        }
    }
}
