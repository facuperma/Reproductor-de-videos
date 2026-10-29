package io.github.facuperma.tvon

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Una PC emparejada: dirección (https://ip:puerto), huella SHA-256 de su certificado y la sesión. */
data class Conexion(val base: String, val huella: String, val token: String)

/**
 * Lo que la app recuerda. Las sesiones se guardan cifradas con una clave AES del Android Keystore,
 * que nunca sale del chip de seguridad del celular: copiar los datos de la app a otro equipo no sirve.
 */
class Almacen(contexto: Context) {
    private val prefs = contexto.getSharedPreferences("tvon", Context.MODE_PRIVATE)

    fun conexiones(): List<Conexion> = try {
        val lista = JSONArray(prefs.getString("conexiones", "[]"))
        (0 until lista.length()).mapNotNull { i ->
            val o = lista.getJSONObject(i)
            val token = descifrar(o.getString("token")) ?: return@mapNotNull null
            Conexion(o.getString("base"), o.getString("huella"), token)
        }
    } catch (e: Exception) {
        emptyList()
    }

    /** La conexión que anduvo queda primera: es la que se prueba al abrir la app. */
    fun guardar(conexion: Conexion) {
        val resto = conexiones().filter { it.base != conexion.base }
        escribir(listOf(conexion) + resto)
    }

    fun preferir(conexion: Conexion) {
        val lista = conexiones()
        if (lista.firstOrNull()?.base != conexion.base) escribir(listOf(conexion) + lista.filter { it.base != conexion.base })
    }

    fun quitar(base: String) = escribir(conexiones().filter { it.base != base })

    fun quitarTodas() = escribir(emptyList())

    private fun escribir(lista: List<Conexion>) {
        val json = JSONArray()
        for (c in lista) json.put(JSONObject().put("base", c.base).put("huella", c.huella).put("token", cifrar(c.token)))
        prefs.edit().putString("conexiones", json.toString()).apply()
    }

    var velocidad: Float
        get() = prefs.getFloat("velocidad", 1.75f)
        set(v) = prefs.edit().putFloat("velocidad", v).apply()

    var teclasVolumen: Boolean
        get() = prefs.getBoolean("teclas_volumen", true)
        set(v) = prefs.edit().putBoolean("teclas_volumen", v).apply()

    /** Qué videos muestra la biblioteca: «sin_ver», «vistos» o «todos». */
    var mostrar: String
        get() = prefs.getString("mostrar", "sin_ver") ?: "sin_ver"
        set(v) = prefs.edit().putString("mostrar", v).apply()

    var calidad: Int
        get() = prefs.getInt("calidad", 1)
        set(v) = prefs.edit().putInt("calidad", v).apply()

    // --- Cifrado con el Keystore -------------------------------------------------------------

    private fun clave(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generador = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generador.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generador.generateKey()
    }

    private fun cifrar(texto: String): String {
        val cifrador = Cipher.getInstance("AES/GCM/NoPadding")
        cifrador.init(Cipher.ENCRYPT_MODE, clave())
        val datos = cifrador.iv + cifrador.doFinal(texto.toByteArray())
        return Base64.encodeToString(datos, Base64.NO_WRAP)
    }

    private fun descifrar(texto: String): String? = try {
        val datos = Base64.decode(texto, Base64.NO_WRAP)
        val cifrador = Cipher.getInstance("AES/GCM/NoPadding")
        cifrador.init(Cipher.DECRYPT_MODE, clave(), GCMParameterSpec(128, datos, 0, 12))
        String(cifrador.doFinal(datos, 12, datos.size - 12))
    } catch (e: Exception) {
        null // la clave se perdió (p. ej. se borró el bloqueo de pantalla): hay que volver a emparejar
    }

    private companion object {
        const val ALIAS = "tvon_sesiones"
    }
}
