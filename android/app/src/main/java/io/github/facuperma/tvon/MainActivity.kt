package io.github.facuperma.tvon

import android.content.Intent
import android.content.pm.ActivityInfo
import android.os.Bundle
import android.view.KeyEvent
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import io.github.facuperma.tvon.ui.App
import io.github.facuperma.tvon.ui.TemaTVon

class MainActivity : ComponentActivity() {
    private val vm: Modelo by viewModels()
    private var primeraVez = true

    override fun onCreate(estado: Bundle?) {
        super.onCreate(estado)
        // Fondo siempre oscuro: la hora y la batería de arriba van en blanco (si no, no se ven)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        if (estado == null) recibir(intent)
        setContent {
            TemaTVon {
                App(vm)
                BackHandler(enabled = vm.fase == Fase.Lista && atras(soloMirar = true)) { atras(soloMirar = false) }
                val aTodaPantalla = vm.pantallaCompleta || vm.viendoAca != null
                LaunchedEffect(aTodaPantalla) { pantallaCompleta(aTodaPantalla) }
                // Con el touchpad o la pantalla de la PC a la vista, el celular no se apaga solo
                val despierto = vm.fase == Fase.Lista && (vm.pestana == Pestana.MOUSE || vm.viendo)
                LaunchedEffect(despierto) {
                    if (despierto) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }
            }
        }
    }

    /** Atrás: sale de la pantalla completa, de mirar la PC, de elegir o vuelve al reproductor. */
    private fun atras(soloMirar: Boolean): Boolean {
        val accion: (() -> Unit)? = when {
            vm.viendoAca != null -> vm::dejarDeVerAca
            vm.detalles.isNotEmpty() -> vm::cerrarDetalle
            vm.pantallaCompleta -> { { vm.pantallaCompleta = false } }
            vm.viendo -> vm::dejarDeVer
            vm.eligiendo -> vm::terminarSeleccion
            vm.pestana == Pestana.PANTALLA -> { { vm.irA(Pestana.MOUSE) } }
            vm.pestana != Pestana.INICIO -> { { vm.irA(Pestana.INICIO) } }
            else -> null
        }
        if (!soloMirar) accion?.invoke()
        return accion != null
    }

    private fun pantallaCompleta(activa: Boolean) {
        val control = WindowCompat.getInsetsController(window, window.decorView)
        if (activa) {
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            control.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            control.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            control.show(WindowInsetsCompat.Type.systemBars())
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        recibir(intent)
    }

    /** Un link magnet (o el link del QR de TVon) que llega de otra app. */
    private fun recibir(intent: Intent?) {
        val texto = when (intent?.action) {
            Intent.ACTION_VIEW -> intent.dataString
            Intent.ACTION_SEND -> intent.getStringExtra(Intent.EXTRA_TEXT)
            else -> null
        } ?: return
        val magnet = Regex("""magnet:\?\S+""").find(texto)?.value
        when {
            magnet != null -> vm.recibirMagnet(magnet)
            Enlace.leer(texto) != null -> vm.usarEnlace(texto)
            else -> vm.mostrarAviso("TVon ON solo recibe links magnet o el enlace del QR de TVon", true)
        }
    }

    override fun onStart() {
        super.onStart()
        if (!primeraVez) vm.alVolver()
        primeraVez = false
    }

    override fun onStop() {
        super.onStop()
        // Al salir de la app se corta la pantalla compartida y se suelta el clic que quedó apretado
        if (!isChangingConfigurations) vm.alIrse()
    }

    override fun dispatchKeyEvent(evento: KeyEvent): Boolean {
        val arriba = when (evento.keyCode) {
            KeyEvent.KEYCODE_VOLUME_UP -> true
            KeyEvent.KEYCODE_VOLUME_DOWN -> false
            else -> return super.dispatchKeyEvent(evento)
        }
        if (evento.action == KeyEvent.ACTION_DOWN && vm.teclaVolumen(arriba)) return true
        if (evento.action == KeyEvent.ACTION_UP && vm.teclaVolumen(arriba, soloMirar = true)) return true
        return super.dispatchKeyEvent(evento)
    }
}
