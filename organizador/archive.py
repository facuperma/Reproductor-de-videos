"""Películas de dominio público del Internet Archive (colección feature_films)."""
import re
from urllib.parse import quote

from .red import pedir_json

BUSQUEDA = "https://archive.org/advancedsearch.php"
# Descarta entradas vacías o de prueba (menos de 100 MB)
CONSULTA_BASE = "collection:feature_films AND mediatype:movies AND item_size:[100000000 TO 9999999999999]"

# Preferencia de formatos de video, de mejor a peor
FORMATOS = ["h.264", "h.264 HD", "MPEG4", "512Kb MPEG4", "Matroska", "Ogg Video", "MPEG2"]


# Clave -> (texto para mostrar, orden de la API)
ORDENES = {
    "populares": ("Más populares", "downloads desc"),
    "titulo": ("Título (A → Z)", "titleSorter asc"),
    "titulo_desc": ("Título (Z → A)", "titleSorter desc"),
    "anio_desc": ("Año (más nuevas)", "year desc"),
    "anio": ("Año (más viejas)", "year asc"),
}


def buscar(texto: str = "", pagina: int = 1, filas: int = 50,
           orden: str = "populares") -> tuple[int, list[dict]]:
    """Devuelve (total, películas). Sin texto = toda la colección."""
    consulta = CONSULTA_BASE
    palabras = re.sub(r'[^\w\s]', " ", texto).split()
    if palabras:
        consulta += f" AND title:({' '.join(palabras)})"
    if orden.startswith("anio"):
        consulta += " AND year:[1800 TO 2100]"  # sin esto, las que no tienen año quedan primero
    params = [("q", consulta), ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "year"),
              ("fl[]", "downloads"), ("sort[]", ORDENES[orden][1]), ("rows", filas),
              ("page", pagina), ("output", "json")]
    resp = pedir_json(BUSQUEDA, params)["response"]
    peliculas = [
        {
            "identificador": d["identifier"],
            "titulo": str(d.get("title") or d["identifier"]).strip(),
            "anio": str(d["year"]) if d.get("year") else None,
            "descargas": d.get("downloads", 0),
        }
        for d in resp["docs"]
    ]
    return resp["numFound"], peliculas


def archivos_de(identificador: str) -> dict | None:
    """Elige el mejor video del ítem y sus subtítulos.

    Devuelve {"video": {"nombre", "tamano"}, "subtitulos": [nombres .srt]} o None si no hay video.
    """
    datos = pedir_json(f"https://archive.org/metadata/{quote(identificador)}")
    archivos = datos.get("files", [])
    videos = [f for f in archivos if f.get("format") in FORMATOS]
    if not videos:
        return None
    # Mejor formato y, dentro del formato, el más grande (evita tráilers o fragmentos)
    mejor = min(videos, key=lambda f: (FORMATOS.index(f["format"]), -int(f.get("size") or 0)))
    subtitulos = [f["name"] for f in archivos if f["name"].lower().endswith(".srt")]
    return {"video": {"nombre": mejor["name"], "tamano": int(mejor.get("size") or 0)},
            "subtitulos": subtitulos}


def url_de(identificador: str, nombre: str) -> str:
    return f"https://archive.org/download/{quote(identificador)}/{quote(nombre)}"
