package io.github.facuperma.tvon.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import io.github.facuperma.tvon.Modelo

/** Abre el lector de QR de Google (no hace falta permiso de cámara) y usa lo que lea. */
fun escanear(contexto: Context, vm: Modelo) {
    val opciones = GmsBarcodeScannerOptions.Builder()
        .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
        .enableAutoZoom()
        .build()
    GmsBarcodeScanning.getClient(contexto, opciones).startScan()
        .addOnSuccessListener { codigo -> codigo.rawValue?.let(vm::usarEnlace) }
        .addOnFailureListener { e ->
            vm.mostrarAviso("No se pudo abrir el lector de QR (${e.message}). Pegá el enlace a mano.", true)
        }
}

@Composable
fun PantallaEmparejar(vm: Modelo, mensaje: String?) {
    val contexto = LocalContext.current
    var enlace by rememberSaveable { mutableStateOf("") }
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Logo(96)
        TituloTVon(28)
        Text(mensaje ?: "Manejá TVon desde el celular.", textAlign = TextAlign.Center,
            color = if (mensaje != null) C.error else C.texto)
        Tarjeta {
            Text("1. En la PC, abrí TVon y tocá 📱 ON.")
            Text("2. Encendelo y escaneá el código QR con este botón.")
            Pista("El celular y la PC tienen que estar en la misma red wifi (o los dos en Tailscale).")
        }
        if (vm.emparejando) {
            CircularProgressIndicator(color = C.acento)
        } else {
            Boton("📷 Escanear el código QR", Modifier.fillMaxWidth(), Estilo.PRIMARIO) { escanear(contexto, vm) }
        }
        Pista("¿No anda la cámara? Pegá el enlace que aparece debajo del QR:")
        OutlinedTextField(
            enlace, { enlace = it }, Modifier.fillMaxWidth(), singleLine = true, colors = campoColores(),
            placeholder = { Text("https://192.168.…:8765/?c=…") },
        )
        Boton("Conectar", Modifier.fillMaxWidth(), habilitado = enlace.isNotBlank() && !vm.emparejando) {
            vm.usarEnlace(enlace)
        }
        Pista("🔒 La app comprueba el certificado de tu PC con la huella que viene en el QR: la conexión va " +
            "cifrada y nadie más puede hacerse pasar por TVon.", Modifier.padding(top = 12.dp))
    }
}

@Composable
fun PantallaSinConexion(vm: Modelo, mensaje: String) {
    val contexto = LocalContext.current
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Logo(96)
        TituloTVon(28)
        Text(mensaje, textAlign = TextAlign.Center, color = C.error)
        CircularProgressIndicator(color = C.acento)
        Pista("Se reintenta solo cada unos segundos.", Modifier.padding(bottom = 12.dp))
        Boton("Reintentar ahora", Modifier.fillMaxWidth()) { vm.correr { vm.conectar() } }
        Boton("📷 Escanear el código QR de nuevo", Modifier.fillMaxWidth(), Estilo.PRIMARIO) { escanear(contexto, vm) }
    }
}
