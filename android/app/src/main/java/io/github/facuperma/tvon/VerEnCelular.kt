package io.github.facuperma.tvon

import android.content.Context
import androidx.annotation.OptIn
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.Tracks
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Un video de la PC visto en el celular. El archivo llega por la misma conexión cifrada (con el
 * certificado fijo y la sesión); por dónde se va queda guardado en la PC, como si se lo viera ahí.
 *
 * Si el celular no puede reproducir el sonido (DTS, a veces AC3) o el video (AVI, WMV), se pide a la
 * PC que lo convierta mientras se ve (hace falta ffmpeg en la PC). Esa versión no se puede pedir por
 * partes: para adelantar se vuelve a pedir desde ese punto.
 */
@OptIn(UnstableApi::class)
class VerEnCelular(
    contexto: Context,
    private val pc: Pc,
    private val alcance: CoroutineScope,
    private val avisar: (String, Boolean) -> Unit,
    /** Cuando termina: el capítulo que sigue (null = no hay). */
    private val siguiente: (Int) -> Unit,
) {
    val jugador: ExoPlayer = ExoPlayer.Builder(contexto)
        .setMediaSourceFactory(DefaultMediaSourceFactory(
            OkHttpDataSource.Factory(pc.httpVideo).setDefaultRequestProperties(pc.cabeceras())))
        .build()

    var ficha by mutableStateOf<FichaVideo?>(null)
        private set
    /** null: el archivo tal cual; «audio» o «video»: convertido por la PC. */
    var conversion by mutableStateOf<String?>(null)
        private set
    var error by mutableStateOf<String?>(null)
    private var desde = 0L          // con conversión, el video arranca en este punto
    private var subtitulo: String? = null  // el texto del subtítulo elegido, para elegirlo cuando aparezcan las pistas
    private var reporte: Job? = null

    init {
        jugador.addListener(object : Player.Listener {
            override fun onTracksChanged(pistas: Tracks) = revisarPistas(pistas)
            override fun onPlayerError(e: PlaybackException) = alFallar(e)
            override fun onIsPlayingChanged(reproduciendo: Boolean) {
                if (!reproduciendo) guardarProgreso() // al pausar, la PC ya sabe por dónde va
            }

            override fun onPlaybackStateChanged(estado: Int) {
                if (estado == Player.STATE_ENDED) terminado()
            }
        })
        reporte = alcance.launch {
            // Cada 10 segundos, por si el celular se queda sin batería o se corta la wifi
            while (isActive) {
                delay(10_000)
                if (jugador.isPlaying) guardarProgreso()
            }
        }
    }

    fun abrir(f: FichaVideo, desdeMs: Long) {
        ficha = f
        error = null
        conversion = null
        subtitulo = f.subtitulos.firstOrNull { it.elegido }?.texto
        cargar(desdeMs)
    }

    private fun cargar(desdeMs: Long) {
        val f = ficha ?: return
        val modo = conversion
        desde = if (modo != null) desdeMs else 0L
        val ruta = "/api/video?id=${f.id}" + (modo?.let { "&compat=$it&desde=${desdeMs / 1000.0}" } ?: "")
        val subs = f.subtitulos.map { s ->
            MediaItem.SubtitleConfiguration.Builder(android.net.Uri.parse(pc.url("/api/subtitulo?id=${f.id}&n=${s.n}")))
                .setMimeType(if (s.texto.lowercase().contains(".vtt")) MimeTypes.TEXT_VTT else MimeTypes.APPLICATION_SUBRIP)
                .setLabel(s.texto)
                .setId("sub${s.n}")
                .build()
        }
        val item = MediaItem.Builder().setUri(pc.url(ruta)).setSubtitleConfigurations(subs)
            .apply { if (modo != null) setMimeType(MimeTypes.VIDEO_MP2T) }
            .build()
        jugador.trackSelectionParameters = jugador.trackSelectionParameters.buildUpon()
            .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, subtitulo == null).build()
        jugador.setMediaItem(item, if (modo != null) 0L else desdeMs)
        jugador.prepare()
        jugador.playWhenReady = true
    }

    /** Dónde va de verdad (con conversión, el video arrancó más adelante). */
    fun posicion(): Long = desde + jugador.currentPosition.coerceAtLeast(0)

    fun duracion(): Long {
        val d = jugador.duration
        return if (conversion == null && d != C.TIME_UNSET && d > 0) d else ficha?.duracion ?: 0L
    }

    /** Adelantar o retroceder (con conversión se vuelve a pedir desde ahí). */
    fun saltar(ms: Long) {
        val nueva = (posicion() + ms).coerceAtLeast(0)
        if (conversion != null) cargar(nueva) else jugador.seekTo(nueva)
    }

    private fun revisarPistas(pistas: Tracks) {
        // El subtítulo elegido en la PC (o en la ficha) se activa apenas aparece
        subtitulo?.let { texto ->
            val grupo = pistas.groups.firstOrNull { g ->
                g.type == C.TRACK_TYPE_TEXT && (0 until g.length).any { g.getTrackFormat(it).label == texto }
            }
            if (grupo != null) {
                jugador.trackSelectionParameters = jugador.trackSelectionParameters.buildUpon()
                    .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, false)
                    .setOverrideForType(TrackSelectionOverride(grupo.mediaTrackGroup, 0)).build()
                subtitulo = null
            }
        }
        if (conversion == "video") return
        val audio = pistas.groups.filter { it.type == C.TRACK_TYPE_AUDIO }
        val video = pistas.groups.filter { it.type == C.TRACK_TYPE_VIDEO }
        val sinVideo = video.isNotEmpty() && video.none { it.isSupported }
        val sinAudio = conversion == null && audio.isNotEmpty() && audio.none { it.isSupported }
        when {
            sinVideo -> convertir("video", "El celular no puede mostrar este video")
            sinAudio -> convertir("audio", "El celular no puede reproducir el sonido de este video")
        }
    }

    private fun alFallar(e: PlaybackException) {
        val formato = e.errorCode in setOf(
            PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED,
            PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED,
            PlaybackException.ERROR_CODE_DECODER_INIT_FAILED,
            PlaybackException.ERROR_CODE_DECODER_QUERY_FAILED,
            PlaybackException.ERROR_CODE_DECODING_FAILED,
            PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED,
            PlaybackException.ERROR_CODE_DECODING_FORMAT_EXCEEDS_CAPABILITIES,
            PlaybackException.ERROR_CODE_AUDIO_TRACK_INIT_FAILED,
        )
        when {
            formato && conversion != "video" -> convertir("video", "El celular no puede reproducir este archivo")
            e.errorCode == PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS ->
                error = "La PC no mandó el video. ¿Sigue en la biblioteca y con ON encendido?"
            e.errorCode in setOf(PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
                PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT) ->
                error = "Se cortó la conexión con la PC. Tocá Reintentar cuando vuelva la wifi."
            else -> error = "No se pudo reproducir: ${e.errorCodeName}"
        }
    }

    private fun convertir(modo: String, motivo: String) {
        val f = ficha ?: return
        if (!f.conversion) {
            error = "$motivo. Para verlo acá, instalá ffmpeg en la PC (winget install Gyan.FFmpeg) y volvé a " +
                "abrir TVon; o miralo en la PC."
            if (modo == "audio") return // se puede seguir viendo sin sonido
            jugador.stop()
            return
        }
        val donde = posicion()
        conversion = modo
        avisar("$motivo: la PC lo convierte mientras lo ves", false)
        cargar(donde)
    }

    fun reintentar() {
        error = null
        cargar(posicion())
    }

    private fun terminado() {
        val f = ficha ?: return
        val d = duracion()
        if (d > 0) enviarProgreso(f.id, d, d)
        f.siguiente?.let(siguiente)
    }

    fun guardarProgreso() {
        val f = ficha ?: return
        val d = duracion()
        if (d > 0) enviarProgreso(f.id, posicion(), d)
    }

    private fun enviarProgreso(id: Int, posicion: Long, duracion: Long) {
        alcance.launch {
            try {
                pc.post("/api/accion", JSONObject().put("accion", "progreso_celular").put("id", id)
                    .put("posicion", posicion).put("duracion", duracion))
            } catch (e: ErrorApi) {
                // la próxima vez se manda de nuevo
            }
        }
    }

    fun cerrar() {
        guardarProgreso()
        reporte?.cancel()
        jugador.release()
    }
}
