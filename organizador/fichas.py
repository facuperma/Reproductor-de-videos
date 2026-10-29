"""Fichas de películas y series, como en Jellyfin: póster, sinopsis, año, géneros y puntaje.

Se buscan solas, en un hilo propio, para cada título nuevo de la biblioteca:
- Con clave de TMDb (Configuración → Preferencias): The Movie Database, en español.
- Sin clave: Wikipedia en español (películas) y TVmaze (series).
- Las películas de dominio público: los datos del Internet Archive.

Una ficha es de un título, no de un archivo: «Breaking.Bad.S01E02.mkv» y «Breaking.Bad.S01E03.mkv»
comparten la de «Breaking Bad». Los pósters se guardan en la carpeta de datos de TVon («posters»).
"""
import hashlib
import html
import re
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, Signal

from .db import Biblioteca
from .red import ErrorRed, bajar_bytes, pedir_json
from .titulos import nombre_lindo, titulo_de

AGENTE = {"User-Agent": "TVon/1.7 (https://github.com/facuperma/TVon-App-de-escritorio-para-organizar-y-ver-videos)"}
REINTENTAR_DIAS = 7       # una ficha que no apareció se vuelve a buscar después de esto
PAUSA_S = 1.0             # entre búsqueda y búsqueda: los sitios gratis no quieren apuro
INTERVALO_S = 300         # revisión de títulos nuevos (además de cuando se la despierta)

GENEROS_ES = {
    "Action": "Acción", "Adventure": "Aventura", "Anime": "Anime", "Comedy": "Comedia", "Crime": "Crimen",
    "Drama": "Drama", "Family": "Familia", "Fantasy": "Fantasía", "History": "Historia", "Horror": "Terror",
    "Medical": "Médica", "Music": "Música", "Mystery": "Misterio", "Romance": "Romance",
    "Science-Fiction": "Ciencia ficción", "Sports": "Deportes", "Supernatural": "Sobrenatural",
    "Thriller": "Suspenso", "War": "Bélica", "Western": "Western", "Legal": "Judicial", "Espionage": "Espionaje",
    "Children": "Infantil", "Food": "Cocina", "Travel": "Viajes", "Nature": "Naturaleza",
}


# --- Qué es cada archivo ----------------------------------------------------------------------

def _normal(texto: str) -> str:
    """«Él Señor  de los Anillos» -> «el senor de los anillos» (para comparar títulos)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip()


def episodio(nombre: str) -> tuple[int, int] | None:
    """(temporada, capítulo) si el nombre es de un capítulo; usa lo mismo que los nombres lindos."""
    lindo = nombre_lindo(nombre)
    if m := re.search(r"· S(\d+)E(\d+)", lindo):
        return int(m.group(1)), int(m.group(2))
    if m := re.search(r"· Cap\. (\d+)", lindo):
        return 1, int(m.group(1))
    return None


def anio_de(nombre: str) -> str | None:
    m = re.search(r"\((\d{4})\)", nombre_lindo(nombre).split(" · ")[0])
    return m.group(1) if m else None


def clave_de(nombre: str) -> tuple[str, str, str | None]:
    """(clave de la ficha, título, año) para un archivo."""
    titulo = titulo_de(nombre)
    if episodio(nombre):
        return f"serie|{_normal(titulo)}", titulo, None
    anio = anio_de(nombre)
    return f"pelicula|{_normal(titulo)}|{anio or ''}", titulo, anio


def agrupar(bib: Biblioteca) -> tuple[list[dict], dict[str, dict]]:
    """Las películas (un archivo cada una) y las series (con sus capítulos) de la biblioteca."""
    peliculas, series = [], {}
    for aid, ruta, nombre, _tipo in bib.listar_archivos("video"):
        clave, titulo, anio = clave_de(nombre)
        if clave.startswith("serie|"):
            temporada, numero = episodio(nombre)
            serie = series.setdefault(clave, {"clave": clave, "titulo": titulo, "episodios": []})
            serie["episodios"].append({"id": aid, "ruta": ruta, "nombre": nombre,
                                       "temporada": temporada, "episodio": numero})
        else:
            peliculas.append({"id": aid, "ruta": ruta, "nombre": nombre, "clave": clave,
                              "titulo": titulo, "anio": anio})
    for serie in series.values():
        serie["episodios"].sort(key=lambda e: (e["temporada"], e["episodio"]))
    return peliculas, series


# --- Lectura de fichas guardadas -------------------------------------------------------------

CAMPOS = ("clave", "tipo", "titulo", "anio", "sinopsis", "generos", "puntaje", "poster", "fuente",
          "busqueda", "encontrada")


def fichas(bib: Biblioteca) -> dict[str, dict]:
    """Todas las fichas guardadas, por clave."""
    filas = bib.con.execute(f"SELECT {', '.join(CAMPOS)} FROM fichas").fetchall()
    return {f[0]: dict(zip(CAMPOS, f)) for f in filas}


def ficha(bib: Biblioteca, clave: str) -> dict | None:
    fila = bib.con.execute(f"SELECT {', '.join(CAMPOS)} FROM fichas WHERE clave = ?", (clave,)).fetchone()
    return dict(zip(CAMPOS, fila)) if fila else None


def generos(f: dict | None) -> list[str]:
    return [g for g in ((f or {}).get("generos") or "").split(",") if g]


def poster(f: dict | None) -> str | None:
    """Ruta del póster en el disco, si la ficha lo tiene y el archivo sigue ahí."""
    ruta = f and f.get("poster")
    return ruta if ruta and Path(ruta).is_file() else None


def corregir(bib: Biblioteca, clave: str, texto: str) -> None:
    """El título con el que se busca esa ficha (si la automática salió mal). La busca de nuevo."""
    tipo = clave.split("|", 1)[0]
    bib.con.execute(
        """INSERT INTO fichas (clave, tipo, busqueda, encontrada, buscada) VALUES (?, ?, ?, 0, 0)
           ON CONFLICT (clave) DO UPDATE SET busqueda = excluded.busqueda, encontrada = 0, buscada = 0""",
        (clave, tipo, texto.strip()),
    )
    bib.con.commit()


# --- Búsqueda en internet -----------------------------------------------------------------------

def _sin_html(texto: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))).strip()


class _Tmdb:
    """The Movie Database. Acepta la clave de API (v3) o el token de lectura (v4, «eyJ…»)."""
    BASE = "https://api.themoviedb.org/3"

    def __init__(self, clave: str):
        self.clave = clave
        self._generos: dict[str, dict[int, str]] = {}

    def _pedir(self, ruta: str, params: dict):
        cabeceras = dict(AGENTE)
        params = {"language": "es-ES", **params}
        if len(self.clave) > 40:
            cabeceras["Authorization"] = f"Bearer {self.clave}"
        else:
            params["api_key"] = self.clave
        return pedir_json(self.BASE + ruta, params, cabeceras=cabeceras, timeout=20)

    def _nombres_generos(self, tipo: str) -> dict[int, str]:
        if tipo not in self._generos:
            datos = self._pedir(f"/genre/{tipo}/list", {})
            self._generos[tipo] = {g["id"]: g["name"] for g in datos.get("genres", [])}
        return self._generos[tipo]

    def buscar(self, tipo: str, titulo: str, anio: str | None) -> dict | None:
        api = "movie" if tipo == "pelicula" else "tv"
        params = {"query": titulo}
        if anio:
            params["year" if api == "movie" else "first_air_date_year"] = anio
        resultados = self._pedir(f"/search/{api}", params).get("results") or []
        if not resultados and anio:
            resultados = self._pedir(f"/search/{api}", {"query": titulo}).get("results") or []
        if not resultados:
            return None
        r = resultados[0]
        nombres = self._nombres_generos(api)
        fecha = r.get("release_date") or r.get("first_air_date") or ""
        return {
            "titulo": r.get("title") or r.get("name") or titulo,
            "anio": fecha[:4] or anio,
            "sinopsis": r.get("overview") or "",
            "generos": [nombres[g] for g in r.get("genre_ids", []) if g in nombres],
            "puntaje": round(float(r["vote_average"]), 1) if r.get("vote_average") else None,
            "poster_url": f"https://image.tmdb.org/t/p/w342{r['poster_path']}" if r.get("poster_path") else None,
            "fuente": "TMDb",
        }


def _wikipedia(titulo: str, anio: str | None) -> dict | None:
    """Películas sin clave: el resumen y la imagen del artículo de Wikipedia (en español o inglés)."""
    for idioma, palabra in (("es", "película"), ("en", "film")):
        consulta = " ".join(p for p in (titulo, anio, palabra) if p)
        datos = pedir_json(f"https://{idioma}.wikipedia.org/w/api.php",
                           {"action": "query", "list": "search", "srsearch": consulta, "srlimit": 3,
                            "format": "json"}, cabeceras=AGENTE, timeout=20)
        for resultado in datos.get("query", {}).get("search", []):
            resumen = pedir_json(f"https://{idioma}.wikipedia.org/api/rest_v1/page/summary/"
                                 + quote(resultado["title"].replace(" ", "_"), safe=""),
                                 cabeceras=AGENTE, timeout=20)
            texto = resumen.get("extract") or ""
            descripcion = (resumen.get("description") or "").lower()
            # Que sea una película y no el libro, el actor o la saga
            if palabra not in descripcion and palabra not in texto[:300].lower():
                continue
            anio_texto = anio or (m.group(0) if (m := re.search(r"\b(19|20)\d{2}\b", descripcion + " " + texto[:200])) else None)
            return {
                "titulo": resumen.get("title") or titulo, "anio": anio_texto, "sinopsis": texto,
                "generos": [], "puntaje": None,
                "poster_url": (resumen.get("thumbnail") or {}).get("source"),
                "fuente": f"Wikipedia ({idioma})",
            }
    return None


def _tvmaze(titulo: str) -> dict | None:
    """Series sin clave: TVmaze (gratis, sin registrarse). La sinopsis viene en inglés."""
    try:
        r = pedir_json("https://api.tvmaze.com/singlesearch/shows", {"q": titulo}, cabeceras=AGENTE, timeout=20)
    except Exception:  # noqa: BLE001 - 404 = no la encontró
        return None
    imagen = r.get("image") or {}
    return {
        "titulo": r.get("name") or titulo,
        "anio": (r.get("premiered") or "")[:4] or None,
        "sinopsis": _sin_html(r.get("summary")),
        "generos": [GENEROS_ES.get(g, g) for g in r.get("genres", [])],
        "puntaje": (r.get("rating") or {}).get("average"),
        "poster_url": imagen.get("medium") or imagen.get("original"),
        "fuente": "TVmaze",
    }


def _archive(identificador: str) -> dict | None:
    """Película de dominio público: lo que dice el Internet Archive de ella."""
    datos = pedir_json(f"https://archive.org/metadata/{quote(identificador, safe='')}", timeout=20)
    meta = datos.get("metadata") or {}
    if not meta:
        return None
    temas = meta.get("subject") or []
    temas = [temas] if isinstance(temas, str) else temas
    descripcion = meta.get("description")
    descripcion = " ".join(descripcion) if isinstance(descripcion, list) else descripcion
    return {
        "titulo": meta.get("title") or identificador, "anio": str(meta.get("year") or "")[:4] or None,
        "sinopsis": _sin_html(descripcion)[:1500], "generos": [t.strip().capitalize() for t in temas[:4] if t.strip()],
        "puntaje": None, "poster_url": f"https://archive.org/services/img/{quote(identificador, safe='')}",
        "fuente": "Internet Archive",
    }


def buscar_en_internet(bib: Biblioteca, clave: str, titulo: str, anio: str | None,
                       identificador_archive: str | None = None) -> dict | None:
    tipo = clave.split("|", 1)[0]
    if identificador_archive:
        try:
            if encontrada := _archive(identificador_archive):
                return encontrada
        except Exception:  # noqa: BLE001 - si falla, se prueba con el título
            pass
    if clave_tmdb := bib.config("tmdb_api_key"):
        try:
            return _Tmdb(clave_tmdb).buscar(tipo, titulo, anio)
        except Exception:  # noqa: BLE001 - clave mal escrita, sin internet: se prueba sin TMDb
            pass
    return _wikipedia(titulo, anio) if tipo == "pelicula" else _tvmaze(titulo)


def guardar(bib: Biblioteca, carpeta_posters: Path, clave: str, encontrada: dict | None, busqueda: str | None):
    ruta_poster = None
    if encontrada and encontrada.get("poster_url"):
        try:
            datos = bajar_bytes(encontrada["poster_url"], timeout=30, cabeceras=AGENTE)
            carpeta_posters.mkdir(parents=True, exist_ok=True)
            destino = carpeta_posters / (hashlib.sha1(clave.encode()).hexdigest() + ".jpg")
            destino.write_bytes(datos)
            ruta_poster = str(destino)
        except Exception:  # noqa: BLE001 - la ficha sirve igual sin póster
            pass
    e = encontrada or {}
    bib.con.execute(
        """INSERT OR REPLACE INTO fichas (clave, tipo, titulo, anio, sinopsis, generos, puntaje, poster, fuente,
               busqueda, encontrada, buscada) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))""",
        (clave, clave.split("|", 1)[0], e.get("titulo"), e.get("anio"), e.get("sinopsis"),
         ",".join(e.get("generos") or []), e.get("puntaje"), ruta_poster, e.get("fuente"), busqueda,
         int(encontrada is not None)),
    )
    bib.con.commit()


# --- El hilo que las busca ------------------------------------------------------------------------

class BuscadorFichas(QObject):
    """Busca en segundo plano las fichas que faltan. Usa su propia conexión a la base."""
    nueva = Signal(str)  # clave de una ficha recién encontrada

    def __init__(self, ruta_db: Path):
        super().__init__()
        self.ruta_db = ruta_db
        self.carpeta_posters = Path(ruta_db).parent / "posters"
        self._despertar = threading.Event()
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def iniciar(self):
        self._hilo.start()

    def despertar(self):
        """Hay videos nuevos (una descarga terminó, se agregó una carpeta): buscar ya."""
        self._despertar.set()

    def detener(self):
        self._parar.set()
        self._despertar.set()

    def _bucle(self):
        bib = Biblioteca(self.ruta_db)
        while not self._parar.is_set():
            try:
                self._pasada(bib)
            except Exception:  # noqa: BLE001 - sin internet, base ocupada: la próxima vuelta
                pass
            self._despertar.wait(INTERVALO_S)
            self._despertar.clear()

    def _pendientes(self, bib: Biblioteca) -> list[tuple[str, str, str | None, str | None, str | None]]:
        """(clave, título, año, búsqueda corregida, identificador del Internet Archive) que faltan."""
        guardadas = {clave: (encontrada, buscada, busqueda) for clave, encontrada, buscada, busqueda in
                     bib.con.execute("SELECT clave, encontrada, buscada, busqueda FROM fichas")}
        ahora = bib.con.execute("SELECT julianday('now')").fetchone()[0]
        de_archive = {ruta: ident for ident, ruta in
                      bib.con.execute("SELECT identificador, ruta FROM descargas WHERE ruta IS NOT NULL")}
        peliculas, series = agrupar(bib)
        candidatos = [(p["clave"], p["titulo"], p["anio"], de_archive.get(p["ruta"])) for p in peliculas]
        candidatos += [(s["clave"], s["titulo"], None, None) for s in series.values()]
        pendientes, vistos = [], set()
        for clave, titulo, anio, ident in candidatos:
            if clave in vistos:
                continue
            vistos.add(clave)
            encontrada, buscada, busqueda = guardadas.get(clave, (None, None, None))
            if encontrada is None or (not encontrada and ahora - buscada > REINTENTAR_DIAS) or buscada == 0:
                pendientes.append((clave, titulo, anio, busqueda, ident))
        return pendientes

    def _pasada(self, bib: Biblioteca):
        for clave, titulo, anio, busqueda, ident in self._pendientes(bib):
            if self._parar.is_set():
                return
            try:
                encontrada = buscar_en_internet(bib, clave, busqueda or titulo, None if busqueda else anio,
                                                None if busqueda else ident)
            except ErrorRed as e:
                if e.codigo is None:
                    return  # sin internet: no se marca nada, se reintenta en la próxima vuelta
                encontrada = None  # el sitio dijo que no (404, 400…): se reintenta en unos días
            except Exception:  # noqa: BLE001 - una respuesta rara no frena a los demás títulos
                encontrada = None
            guardar(bib, self.carpeta_posters, clave, encontrada, busqueda)
            if encontrada:
                self.nueva.emit(clave)
            time.sleep(PAUSA_S)
