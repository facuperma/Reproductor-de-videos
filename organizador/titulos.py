"""Título limpio de una película o serie a partir del nombre del archivo.

«Breaking.Bad.S01E02.720p.WEB-DL.mkv» -> «Breaking Bad»
«The.Matrix.1999.1080p.BluRay.x264.mkv» -> «The Matrix»
«Serie Cap 10.mp4» -> «Serie»
"""
import re
from pathlib import Path

# Etiquetas de calidad, origen o idioma que suelen ir después del título
_ETIQUETAS = (
    r"2160p|1080p|720p|480p|4k|uhd|hdr|bluray|blu-ray|brrip|bdrip|webrip|web-dl|webdl|hdtv|dvdrip|"
    r"dvd|xvid|x264|x265|h264|h265|hevc|aac|ac3|dts|remux|proper|repack|extended|unrated|"
    r"subtitulado|latino|castellano|dual|multi"
)
# Donde empieza lo que no es título: episodio, temporada, año, paréntesis o etiqueta
_CORTE = re.compile(
    r"(?i)\b(s\d{1,2}\s?e\d{1,3}|s\d{1,2}|\d{1,2}x\d{1,3}|season|temporada|episod(?:e|io)|"
    r"cap(?:[ií]tulo)?|chapter|ep|e\d{1,3})\b|\(|\b(?:19|20)\d{2}\b|\b(?:" + _ETIQUETAS + r")\b"
)


def _limpio(nombre_archivo: str) -> str:
    t = re.sub(r"[._]+", " ", Path(nombre_archivo).stem)
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", t)).strip()


def nombre_lindo(nombre_archivo: str) -> str:
    """Cómo se muestra un archivo en la lista: el título limpio (como la categoría rápida) más
    el capítulo, el año y la calidad, si el nombre los trae.

    «Breaking.Bad.S01E02.720p.WEB-DL.mkv» -> «Breaking Bad · S01E02 · 720p»
    «The.Matrix.1999.1080p.BluRay.x264.mkv» -> «The Matrix (1999) · 1080p»
    «Serie Cap 10.mp4» -> «Serie · Cap. 10»
    """
    titulo = titulo_de(nombre_archivo)
    t = _limpio(nombre_archivo)
    # Lo que viene después del título: ahí están el capítulo, el año y la calidad
    resto = t[len(titulo):] if t.lower().startswith(titulo.lower()) else t
    capitulo = ""
    if m := re.search(r"(?i)\bs(\d{1,2})\s?e(\d{1,3})\b", resto) or re.search(r"\b(\d{1,2})x(\d{1,3})\b", resto):
        capitulo = f"S{int(m.group(1)):02}E{int(m.group(2)):02}"
    elif m := re.search(r"(?i)\b(?:cap(?:[ií]tulo)?|episod(?:e|io)|ep|chapter)\.?\s*(\d{1,4})\b", resto):
        capitulo = f"Cap. {int(m.group(1))}"
    elif m := re.search(r"(?i)\b(?:s|season|temporada)\s*(\d{1,2})\b", resto):
        capitulo = f"Temporada {int(m.group(1))}"
    elif (m := re.match(r"[\s\-–:#]*(\d{1,4})\b(?!p)", resto)) and not re.fullmatch(r"19\d\d|20\d\d", m.group(1)):
        capitulo = f"Cap. {int(m.group(1))}"  # «Serie 3», «Serie - 1001»
    anio = m.group(1) if (m := re.search(r"\b(19[2-9]\d|20[0-4]\d)\b", resto)) else ""
    calidad = ""
    # En todo el nombre: a veces va entre corchetes, «[1080p]»
    if m := re.search(r"(?i)(?<![a-z0-9])(2160p|1080p|720p|480p|4k|uhd)(?![a-z0-9])", Path(nombre_archivo).stem):
        calidad = "4K" if m.group(1).lower() in ("2160p", "4k", "uhd") else m.group(1).lower()
    partes = [f"{titulo} ({anio})" if anio else titulo, capitulo, calidad]
    return " · ".join(p for p in partes if p)


def titulo_de(nombre_archivo: str) -> str:
    original = Path(nombre_archivo).stem
    t = re.sub(r"[._]+", " ", original)
    t = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", t)  # [grupo], {etiquetas}
    # Un marcador al principio («2001 …») es parte del título: se corta en el primero que venga después
    corte = next((m for m in _CORTE.finditer(t) if m.start() > 0), None)
    if corte:
        t = t[:corte.start()]
    t = re.sub(r"[\s\-–:#]+\d{1,4}\s*$", "", t)  # número de capítulo al final: «Show 3», «Serie - 1001»
    t = re.sub(r"\s+", " ", t).strip(" -–:#")
    if not t:
        return original
    return t.title() if t.islower() or t.isupper() else t
