package io.github.facuperma.tvon.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import io.github.facuperma.tvon.BuildConfig
import io.github.facuperma.tvon.Confirmar
import io.github.facuperma.tvon.Modelo
import io.github.facuperma.tvon.huellaLinda

@Composable
fun PestanaMas(vm: Modelo) {
    val e = vm.estado
    val contexto = LocalContext.current
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp)
    ) {
        Tarjeta {
            TituloTarjeta("🖥 TVon en la PC") { Pista("● ON encendido", color = C.verde) }
            Pista(if (e?.ventanaVisible == false) "TVon está escondido junto al reloj de la PC." else "TVon está abierto en la PC.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Boton("Abrir TVon en la PC", Modifier.weight(1f), Estilo.PRIMARIO) { vm.hacer("mostrar_tvon") }
                Boton("Esconderlo", Modifier.weight(1f)) { vm.hacer("esconder_tvon") }
            }
            Interruptor("Arrancar TVon con Windows, con ON encendido", e?.arrancaConWindows ?: false) {
                vm.hacer("arrancar_con_windows", "activo" to it)
            }
            Pista("Con esto el celular siempre encuentra la PC y puede abrir TVon, aunque no lo hayas abierto. Si cerrás " +
                "la ventana de TVon con ON encendido, queda junto al reloj y el mouse y el teclado siguen andando.")
        }
        Tarjeta {
            TituloTarjeta("Biblioteca automática")
            Interruptor("Mover a Videos lo que termine de bajarse en Descargas", e?.moverDescargas ?: false) {
                vm.hacer("mover_descargas", "activo" to it)
            }
            Pista("Las carpetas que se revisan se cambian en Configuración → Preferencias, en la PC (o desde la pestaña Pantalla).")
        }
        Tarjeta {
            TituloTarjeta("Este celular")
            var volumen by remember { mutableStateOf(vm.almacen.teclasVolumen) }
            Interruptor("Los botones de volumen del celular cambian el volumen de TVon (en Reproductor)", volumen) {
                volumen = it
                vm.almacen.teclasVolumen = it
            }
        }
        Tarjeta {
            TituloTarjeta("🔒 Conexión")
            Pista("Conectado a TVon ${e?.version.orEmpty()} en ${vm.base.removePrefix("https://")}, cifrado (HTTPS) y " +
                "solo con el certificado de tu PC. App TVon ON ${BuildConfig.VERSION_NAME}.")
            Pista("Huella del certificado: ${huellaLinda(vm.huella)}", color = C.acentoClaro)
            Text("Para usarlo fuera de casa con Tailscale: en la ventana 📱 ON de la PC tocá «🌍 Usarlo fuera de casa» " +
                "y escaneá ese código. La app prueba sola la conexión que ande.")
            Boton("📷 Agregar otra conexión (escanear QR)", Modifier.fillMaxWidth()) { escanear(contexto, vm) }
            Boton("Desconectar este celular", Modifier.fillMaxWidth(), Estilo.PELIGRO) {
                vm.confirmar = Confirmar("¿Desconectar este celular? Para volver a usarlo hay que escanear el QR de nuevo.",
                    "Desconectar") { vm.desconectar() }
            }
        }
    }
}
