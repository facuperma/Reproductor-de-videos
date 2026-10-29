package io.github.facuperma.tvon

import org.json.JSONArray
import org.json.JSONObject

// Lo que devuelve la API de ON (organizador/remoto.py), ya leído

data class Archivo(val id: Int, val nombre: String, val tipo: String)

data class Reproduccion(
    val estado: String, val posicion: Long, val duracion: Long, val volumen: Int, val silencio: Boolean,
)

data class SubArchivo(val ruta: String, val texto: String, val activo: Boolean)
data class Pista(val texto: String, val activa: Boolean)
data class Tamano(val texto: String, val escala: Double)

data class Subtitulos(
    val archivos: List<SubArchivo>, val pistas: List<Pista>, val activos: Boolean, val retraso: Int,
    val escala: Double, val tamanos: List<Tamano>,
)

data class EnCola(val ruta: String, val nombre: String)
data class Siguiente(val texto: String, val nombre: String)

data class Estado(
    val version: String,
    val archivo: Archivo?,
    val reproduccion: Reproduccion?,
    val subtitulos: Subtitulos?,
    val cola: List<EnCola>,
    val siguiente: Siguiente?,
    val apagarAlTerminar: Boolean,
    val apagadoSegundos: Int?,
    val ventanaVisible: Boolean,
    val arrancaConWindows: Boolean,
    val moverDescargas: Boolean,
    val opensubtitles: Boolean,
) {
    companion object {
        fun de(o: JSONObject) = Estado(
            version = o.optString("version"),
            archivo = o.optJSONObject("archivo")?.let { Archivo(it.optInt("id"), it.optString("nombre"), it.optString("tipo")) },
            reproduccion = o.optJSONObject("reproduccion")?.let {
                Reproduccion(it.optString("estado"), it.optLong("posicion"), it.optLong("duracion"),
                    it.optInt("volumen"), it.optBoolean("silencio"))
            },
            subtitulos = o.optJSONObject("subtitulos")?.let { s ->
                Subtitulos(
                    archivos = s.optJSONArray("archivos").objetos { SubArchivo(it.optString("ruta"), it.optString("texto"), it.optBoolean("activo")) },
                    pistas = s.optJSONArray("pistas").objetos { Pista(it.optString("texto"), it.optBoolean("activa")) },
                    activos = s.optBoolean("activos"),
                    retraso = s.optInt("retraso"),
                    escala = s.optDouble("escala", 1.0),
                    tamanos = s.optJSONArray("tamanos").objetos { Tamano(it.optString("texto"), it.optDouble("escala")) },
                )
            },
            cola = o.optJSONArray("cola").objetos { EnCola(it.optString("ruta"), it.optString("nombre")) },
            siguiente = o.optJSONObject("siguiente")?.let { Siguiente(it.optString("texto"), it.optString("nombre")) },
            apagarAlTerminar = o.optBoolean("apagar_al_terminar"),
            apagadoSegundos = o.optJSONObject("apagado")?.optInt("segundos"),
            ventanaVisible = o.optBoolean("ventana_visible", true),
            arrancaConWindows = o.optBoolean("arranca_con_windows"),
            moverDescargas = o.optBoolean("mover_descargas"),
            opensubtitles = o.optBoolean("opensubtitles"),
        )
    }
}

data class Filtro(val filtro: String, val nombre: String, val cantidad: Int)

data class Categoria(
    val id: Int, val nombre: String, val cantidad: Int, val fija: Boolean, val estado: String?,
    val sinPendiente: Boolean, val enFavoritos: Boolean,
)

data class Biblioteca(val filtros: List<Filtro>, val categorias: List<Categoria>, val favoritos: Int) {
    fun nombre(c: Categoria) = if (c.id == favoritos) "★ ${c.nombre}" else c.nombre

    companion object {
        fun de(o: JSONObject) = Biblioteca(
            filtros = o.optJSONArray("filtros").objetos { Filtro(it.optString("filtro"), it.optString("nombre"), it.optInt("cantidad")) },
            categorias = o.optJSONArray("categorias").objetos {
                Categoria(it.optInt("id"), it.optString("nombre"), it.optInt("cantidad"), it.optBoolean("fija"),
                    it.textoONull("estado"), it.optBoolean("sin_pendiente"), it.optBoolean("en_favoritos"))
            },
            favoritos = o.optInt("favoritos", -1),
        )
    }
}

data class ArchivoBib(
    val id: Int, val nombre: String, val titulo: String, val carpeta: String, val tipo: String,
    val existe: Boolean, val categorias: List<Int>, val visto: String,
) {
    companion object {
        fun de(o: JSONObject) = ArchivoBib(
            o.optInt("id"), o.optString("nombre"), o.optString("titulo").ifBlank { o.optString("nombre") },
            o.optString("carpeta"), o.optString("tipo"), o.optBoolean("existe", true),
            o.optJSONArray("categorias").let { a -> (0 until (a?.length() ?: 0)).map { a!!.getInt(it) } },
            o.optString("visto"),
        )
    }
}

data class Pelicula(
    val identificador: String, val titulo: String, val anio: String?, val descargas: Long, val estadoTexto: String,
) {
    companion object {
        fun de(o: JSONObject) = Pelicula(
            o.optString("identificador"), o.optString("titulo"), o.textoONull("anio"), o.optLong("descargas"),
            o.optString("estado_texto"),
        )
    }
}

data class Descarga(
    val identificador: String, val titulo: String, val anio: String?, val estado: String, val estadoTexto: String,
    val error: String?, val tamano: Long, val recibido: Long, val total: Long,
)

data class Descargas(
    val lista: List<Descarga>, val cantidad: Int, val bytes: Long,
    val autoActiva: Boolean, val autoPeliculas: Int, val autoGb: Int,
) {
    companion object {
        fun de(o: JSONObject): Descargas {
            val auto = o.optJSONObject("auto") ?: JSONObject()
            return Descargas(
                o.optJSONArray("descargas").objetos {
                    Descarga(it.optString("identificador"), it.optString("titulo"), it.textoONull("anio"),
                        it.optString("estado"), it.optString("estado_texto"), it.textoONull("error"),
                        it.optLong("tamano"), it.optLong("recibido"), it.optLong("total"))
                },
                o.optInt("cantidad"), o.optLong("bytes"),
                auto.optBoolean("activa"), auto.optInt("max_peliculas"), auto.optInt("max_gb"),
            )
        }
    }
}

data class Torrent(
    val gid: String, val nombre: String, val estado: String, val estadoTexto: String, val total: Long,
    val recibido: Long, val velocidad: Long, val restante: String, val error: String?,
) {
    companion object {
        fun de(o: JSONObject) = Torrent(
            o.optString("gid"), o.optString("nombre"), o.optString("estado"), o.optString("estado_texto"),
            o.optLong("total"), o.optLong("recibido"), o.optLong("velocidad"), o.optString("restante"),
            o.textoONull("error"),
        )
    }
}

data class Monitor(val ancho: Int, val alto: Int, val principal: Boolean)
data class Monitores(val lista: List<Monitor>, val tvon: Int, val pantalla: Boolean, val control: Boolean) {
    companion object {
        fun de(o: JSONObject) = Monitores(
            o.optJSONArray("monitores").objetos { Monitor(it.optInt("ancho"), it.optInt("alto"), it.optBoolean("principal")) },
            o.optInt("tvon"), o.optBoolean("pantalla"), o.optBoolean("control"),
        )
    }
}

// --- Ver en el celular: catálogo y fichas (como Jellyfin) --------------------------------------

private fun JSONObject.textos(clave: String): List<String> =
    optJSONArray(clave)?.let { a -> (0 until a.length()).map { a.optString(it) } } ?: emptyList()

private fun JSONObject.decimalONull(clave: String): Double? = if (isNull(clave) || !has(clave)) null else optDouble(clave)

/** Una película, una serie o un capítulo, como se muestra en el inicio (con su póster). */
data class Cartel(
    val tipo: String, val id: Int?, val clave: String, val titulo: String, val anio: String?, val sub: String,
    val poster: Boolean, val generos: List<String>, val puntaje: Double?, val visto: Boolean, val progreso: Float?,
    val episodios: Int, val sinVer: Int, val favorito: Boolean,
) {
    companion object {
        fun de(o: JSONObject) = Cartel(
            o.optString("tipo"), if (o.isNull("id")) null else o.optInt("id"), o.optString("clave"),
            o.optString("titulo"), o.textoONull("anio"), o.optString("sub"), o.optBoolean("poster"),
            o.textos("generos"), o.decimalONull("puntaje"), o.optBoolean("visto"),
            o.decimalONull("progreso")?.toFloat(), o.optInt("episodios"), o.optInt("sin_ver"), o.optBoolean("favorito"),
        )
    }
}

data class Inicio(
    val seguir: List<Cartel>, val siguientes: List<Cartel>, val recientes: List<Cartel>, val favoritos: List<Cartel>,
    val peliculas: Int, val series: Int, val generos: List<String>, val conversion: Boolean,
) {
    companion object {
        fun de(o: JSONObject) = Inicio(
            o.optJSONArray("seguir").objetos(Cartel::de), o.optJSONArray("siguientes").objetos(Cartel::de),
            o.optJSONArray("recientes").objetos(Cartel::de), o.optJSONArray("favoritos").objetos(Cartel::de),
            o.optInt("peliculas"), o.optInt("series"), o.textos("generos"), o.optBoolean("conversion"),
        )
    }
}

data class Episodio(val id: Int, val titulo: String, val episodio: Int, val visto: Boolean, val existe: Boolean, val progreso: Float?)
data class Temporada(val numero: Int, val episodios: List<Episodio>)

data class SerieDet(
    val clave: String, val titulo: String, val anio: String?, val sinopsis: String, val generos: List<String>,
    val puntaje: Double?, val poster: Boolean, val fuente: String, val temporadas: List<Temporada>, val seguir: Int?,
) {
    companion object {
        fun de(o: JSONObject) = SerieDet(
            o.optString("clave"), o.optString("titulo"), o.textoONull("anio"), o.optString("sinopsis"),
            o.textos("generos"), o.decimalONull("puntaje"), o.optBoolean("poster"), o.optString("fuente"),
            o.optJSONArray("temporadas").objetos { t ->
                Temporada(t.optInt("numero"), t.optJSONArray("episodios").objetos {
                    Episodio(it.optInt("id"), it.optString("titulo"), it.optInt("episodio"), it.optBoolean("visto"),
                        it.optBoolean("existe", true), it.decimalONull("progreso")?.toFloat())
                })
            },
            if (o.isNull("seguir")) null else o.optInt("seguir"),
        )
    }
}

data class SubCelular(val n: Int, val texto: String, val elegido: Boolean)

/** Todo lo que hace falta para ver un video en el celular. */
data class FichaVideo(
    val id: Int, val clave: String, val nombre: String, val nombreLindo: String, val serie: Boolean,
    val titulo: String, val anio: String?, val sinopsis: String, val generos: List<String>, val puntaje: Double?,
    val poster: Boolean, val fuente: String, val existe: Boolean, val posicion: Long, val duracion: Long,
    val visto: Boolean, val subtitulos: List<SubCelular>, val siguiente: Int?, val conversion: Boolean,
    val favorito: Boolean,
) {
    companion object {
        fun de(o: JSONObject) = FichaVideo(
            o.optInt("id"), o.optString("clave"), o.optString("nombre"), o.optString("nombre_lindo"),
            o.optBoolean("serie"), o.optString("titulo"), o.textoONull("anio"), o.optString("sinopsis"),
            o.textos("generos"), o.decimalONull("puntaje"), o.optBoolean("poster"), o.optString("fuente"),
            o.optBoolean("existe", true), o.optLong("posicion"), o.optLong("duracion"), o.optBoolean("visto"),
            o.optJSONArray("subtitulos").objetos { SubCelular(it.optInt("n"), it.optString("texto"), it.optBoolean("elegido")) },
            if (o.isNull("siguiente")) null else o.optInt("siguiente"), o.optBoolean("conversion"),
            o.optBoolean("favorito"),
        )
    }
}

/** Lo que se ve encima de las pestañas: una serie, la ficha de un video. */
sealed interface Detalle {
    data class DeSerie(val serie: SerieDet) : Detalle
    data class DeVideo(val ficha: FichaVideo) : Detalle
}

// --- Utilidades ---------------------------------------------------------------------------------

fun <T> JSONArray?.objetos(leer: (JSONObject) -> T): List<T> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it)?.let(leer) }

/** optString devuelve "null" para un null de JSON: esto devuelve null de verdad. */
fun JSONObject.textoONull(clave: String): String? =
    if (isNull(clave)) null else optString(clave).takeIf { it.isNotEmpty() }

fun tiempo(ms: Long): String {
    val s = ms / 1000
    val h = s / 3600
    val m = (s % 3600) / 60
    val r = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, r) else "%d:%02d".format(m, r)
}

fun tamano(n: Long): String = when {
    n <= 0 -> ""
    n >= 1L shl 30 -> "%.1f GB".format(n / (1L shl 30).toDouble())
    else -> "${n / (1L shl 20)} MB"
}

/** -1500 → «1,5 s antes», 300 → «0,3 s después» (igual que en la PC). */
fun textoSincronia(ms: Int): String {
    if (ms == 0) return "sincronizados"
    val s = "%.2f".format(kotlin.math.abs(ms) / 1000.0).trimEnd('0').trimEnd('.', ',').replace('.', ',')
    return "$s s ${if (ms > 0) "después" else "antes"}"
}

fun miles(n: Long): String = "%,d".format(n).replace(',', '.')
