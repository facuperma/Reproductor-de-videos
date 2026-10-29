package io.github.facuperma.tvon

import android.net.Uri
import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.ConnectionSpec
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.InetAddress
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.X509TrustManager

class ErrorApi(mensaje: String, val codigo: Int) : Exception(mensaje)

const val SIN_CONEXION = "No hay conexión con la PC. ¿TVon está abierto y con ON encendido? " +
    "(Con «Arrancar TVon con Windows» en la ventana ON, siempre queda listo)"
const val OTRO_CERTIFICADO = "La PC no presentó el certificado de TVon que conoce este celular. " +
    "Si cambiaste de PC o reinstalaste TVon, escaneá el código QR de nuevo. Si no, alguien podría " +
    "estar haciéndose pasar por tu PC: no sigas."
private const val CODIGO_CERTIFICADO = -1

/** El link del QR de TVon: https://IP:puerto/?c=código&h=huella del certificado. */
data class Enlace(val base: String, val codigo: String, val huella: String?) {
    companion object {
        fun leer(texto: String): Enlace? {
            val uri = try { Uri.parse(texto.trim()) } catch (e: Exception) { return null }
            if (uri.scheme != "https" || uri.port <= 0) return null
            val host = uri.host?.removePrefix("[")?.removeSuffix("]") ?: return null
            // Como en la PC: solo una IP (un nombre de dominio puede ser una página haciéndose pasar por TVon)
            if (host != "localhost" && !esIp(host)) return null
            val codigo = uri.getQueryParameter("c")?.takeIf { it.isNotBlank() } ?: return null
            val huella = uri.getQueryParameter("h")?.uppercase()?.takeIf { it.matches(Regex("[0-9A-F]{64}")) }
            return Enlace("https://${uri.encodedAuthority}", codigo, huella)
        }

        private fun esIp(host: String): Boolean {
            val ipv4 = Regex("""\d{1,3}(\.\d{1,3}){3}""")
            if (!ipv4.matches(host) && !host.contains(':')) return false
            // Con un literal, getByName no consulta DNS
            return try { InetAddress.getByName(host); true } catch (e: Exception) { false }
        }
    }
}

fun huellaLinda(hex: String) = hex.chunked(2).joinToString(":")

private fun sha256(datos: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(datos).joinToString("") { "%02X".format(it) }

/** Acepta solo el certificado cuya huella SHA-256 conocemos (la que vino en el QR). */
private class CertificadoFijo(private val huella: String) : X509TrustManager {
    override fun checkServerTrusted(cadena: Array<out X509Certificate>, tipo: String) {
        val recibida = sha256(cadena.firstOrNull()?.encoded ?: throw CertificateException("Sin certificado"))
        if (!MessageDigest.isEqual(recibida.toByteArray(), huella.toByteArray())) {
            throw CertificateException("Certificado desconocido")
        }
    }

    override fun checkClientTrusted(cadena: Array<out X509Certificate>, tipo: String) =
        throw CertificateException("No se usa")

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}

/** Solo anota el certificado que presenta la PC y corta el saludo: no se manda ningún dato. */
private class SoloMirar : X509TrustManager {
    var huella: String? = null
    override fun checkServerTrusted(cadena: Array<out X509Certificate>, tipo: String) {
        huella = cadena.firstOrNull()?.encoded?.let(::sha256)
        throw CertificateException("Solo mirar")
    }

    override fun checkClientTrusted(cadena: Array<out X509Certificate>, tipo: String) =
        throw CertificateException("No se usa")

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}

private fun cliente(confianza: X509TrustManager, lectura: Long = 20): OkHttpClient {
    val tls = SSLContext.getInstance("TLS").apply { init(null, arrayOf(confianza), null) }
    return OkHttpClient.Builder()
        .sslSocketFactory(tls.socketFactory, confianza)
        // La identidad de la PC la prueba la huella fija, no el nombre: la IP de la casa puede cambiar
        .hostnameVerifier { _, _ -> true }
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(lectura, TimeUnit.SECONDS)
        .build()
}

// La PC arma el nombre del celular con esto: «Android · SM-A546E»
val AGENTE = "TVonON/${BuildConfig.VERSION_NAME} (Linux; Android ${Build.VERSION.RELEASE}; ${Build.MODEL})"

/** La huella del certificado que presenta la PC en esa dirección (para un QR viejo, sin huella). */
suspend fun mirarHuella(base: String): String = withContext(Dispatchers.IO) {
    val mirar = SoloMirar()
    try {
        cliente(mirar).newCall(Request.Builder().url("$base/").head().build()).execute().close()
    } catch (e: IOException) {
        // esperado: el saludo se corta a propósito
    }
    mirar.huella ?: throw ErrorApi(SIN_CONEXION, 0)
}

/** Habla con el servidor de ON de una PC, con su certificado fijo y la sesión de este celular. */
class Pc(val base: String, val huella: String, @Volatile var token: String?) {
    private val http = cliente(CertificadoFijo(huella))
    /** Para la transmisión de la pantalla: cada cuadro llega en menos de un segundo. */
    val httpLargo: OkHttpClient = http.newBuilder().readTimeout(15, TimeUnit.SECONDS).build()

    /** Para el reproductor: el mismo certificado fijo, con más paciencia (el video se pide por partes). */
    val httpVideo: OkHttpClient = http.newBuilder().readTimeout(60, TimeUnit.SECONDS).build()

    /** Lo que el reproductor manda en cada pedido: la sesión de este celular. */
    fun cabeceras(): Map<String, String> =
        mapOf("User-Agent" to AGENTE) + (token?.let { mapOf("Cookie" to "tvon_sesion=$it") } ?: emptyMap())

    fun url(ruta: String) = base + ruta

    private fun pedido(ruta: String) = Request.Builder().url(base + ruta)
        .header("User-Agent", AGENTE)
        .header("Cache-Control", "no-store")
        .apply { token?.let { header("Cookie", "tvon_sesion=$it") } }

    private fun enviar(cliente: OkHttpClient, req: Request): Response = ejecutar(cliente.newCall(req))

    /** Una transmisión larga (la pantalla): se corta con `cancel()` desde otro hilo. */
    fun llamada(ruta: String): Call = httpLargo.newCall(pedido(ruta).build())

    fun ejecutar(llamada: Call): Response {
        val r = try {
            llamada.execute()
        } catch (e: SSLHandshakeException) {
            throw if (e.causas().any { it is CertificateException }) ErrorApi(OTRO_CERTIFICADO, CODIGO_CERTIFICADO)
            else ErrorApi(SIN_CONEXION, 0)
        } catch (e: IOException) {
            throw ErrorApi(SIN_CONEXION, 0)
        }
        if (r.isSuccessful) return r
        val texto = r.use { it.body?.string().orEmpty() }
        val mensaje = try { JSONObject(texto).optString("error") } catch (e: Exception) { "" }
        throw ErrorApi(mensaje.ifBlank { "Error ${r.code}" }, r.code)
    }

    suspend fun get(ruta: String): Any? = withContext(Dispatchers.IO) {
        enviar(http, pedido(ruta).build()).use { leerJson(it) }
    }

    suspend fun obj(ruta: String): JSONObject = get(ruta) as? JSONObject ?: JSONObject()
    suspend fun lista(ruta: String): JSONArray = get(ruta) as? JSONArray ?: JSONArray()

    suspend fun post(ruta: String, cuerpo: JSONObject): JSONObject? = withContext(Dispatchers.IO) {
        val req = pedido(ruta)
            // Cabecera propia: la PC la exige en toda orden (protección contra CSRF)
            .header("X-TVon", "1")
            .post(cuerpo.toString().toRequestBody(JSON))
            .build()
        enviar(http, req).use { leerJson(it) as? JSONObject }
    }

    /** Una imagen (cuadro del video, miniatura); null si no hay. */
    suspend fun bytes(ruta: String): ByteArray? = withContext(Dispatchers.IO) {
        enviar(http, pedido(ruta).build()).use { r ->
            try { if (r.code == 204) null else r.body?.bytes() } catch (e: IOException) { throw ErrorApi(SIN_CONEXION, 0) }
        }
    }

    /** Canjea el código del QR por una sesión propia de este celular. */
    suspend fun emparejar(codigo: String): String = withContext(Dispatchers.IO) {
        val req = pedido("/api/emparejar")
            .header("X-TVon", "1")
            .post(JSONObject().put("codigo", codigo).toString().toRequestBody(JSON))
            .build()
        enviar(http, req).use { r ->
            r.headers("Set-Cookie").firstNotNullOfOrNull { Regex("""tvon_sesion=([^;]+)""").find(it)?.groupValues?.get(1) }
                ?: throw ErrorApi("La PC no devolvió una sesión", 500)
        }
    }

    private fun leerJson(r: Response): Any? {
        if (r.code == 204) return null
        val texto = try { r.body?.string().orEmpty().trim() } catch (e: IOException) { throw ErrorApi(SIN_CONEXION, 0) }
        if (texto.isEmpty()) return null
        return try {
            if (texto.startsWith("[")) JSONArray(texto) else JSONObject(texto)
        } catch (e: org.json.JSONException) {
            throw ErrorApi("La PC mandó una respuesta que no se entiende", 502)
        }
    }

    private fun Throwable.causas(): Sequence<Throwable> = generateSequence(this) { it.cause }

    companion object {
        val JSON = "application/json".toMediaType()
        fun esCertificado(e: Throwable) = e is ErrorApi && e.codigo == CODIGO_CERTIFICADO
    }
}
