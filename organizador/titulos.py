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
