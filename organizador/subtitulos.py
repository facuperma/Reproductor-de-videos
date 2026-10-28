"""Lectura de subtítulos externos (.srt y .vtt)."""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from bisect import bisect_right
from pathlib import Path

EXT_SUBTITULOS = {".srt", ".vtt"}
# Así vienen los de subdivx. El tar de Windows (bsdtar) abre los tres.
EXT_COMPRIMIDOS = {".zip", ".rar", ".7z"}

_TIEMPO = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})")
# Etiquetas HTML (<i>, <font ...>) y de estilo ASS ({\an8})
_ETIQUETAS = re.compile(r"<[^>]+>|\{\\[^}]*\}")


def _a_ms(texto: str) -> int | None:
    m = _TIEMPO.search(texto)
    if not m:
        return None
    h, mi, s, frac = m.groups()
    return ((int(h or 0) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def _leer_texto(ruta: Path) -> str:
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            pass
    return datos.decode("latin-1")


class Subtitulos:
    def __init__(self, ruta: str | Path):
        texto = _leer_texto(Path(ruta)).replace("\r\n", "\n").replace("\r", "\n")
        cues = []
        for bloque in re.split(r"\n\s*\n", texto):
            lineas = bloque.strip("\n").split("\n")
            for i, linea in enumerate(lineas):
                if "-->" not in linea:
                    continue
                ini, fin = linea.split("-->", 1)
                a, b = _a_ms(ini), _a_ms(fin)
                cuerpo = _ETIQUETAS.sub("", "\n".join(lineas[i + 1:])).strip()
                if a is not None and b is not None and cuerpo:
                    cues.append((a, b, cuerpo))
                break
        cues.sort()
        self.cues = cues
        self._inicios = [c[0] for c in cues]

    def texto_en(self, ms: int) -> str:
        """Texto visible en el instante ms (puede haber varias líneas superpuestas)."""
        i = bisect_right(self._inicios, ms)
        return "\n".join(t for a, b, t in self.cues[max(0, i - 5):i] if a <= ms < b)


IDIOMAS = {"es": "Español", "spa": "Español", "en": "Inglés", "eng": "Inglés"}


def subtitulos_junto_a(ruta_video: str) -> list[str]:
    """Subtítulos con el mismo nombre del video, como hace VLC (video.srt, video.es.srt, …).
    Orden de preferencia: nombre exacto, español, el resto alfabético."""
    video = Path(ruta_video)
    candidatos = [
        p for p in video.parent.glob(glob.escape(video.stem) + "*")
        if p.suffix.lower() in EXT_SUBTITULOS
        and (p.stem == video.stem or p.stem.startswith(video.stem + "."))
    ]
    candidatos.sort(key=lambda p: (p.stem != video.stem,
                                   IDIOMAS.get(p.stem.rsplit(".", 1)[-1].lower()) != "Español",
                                   p.name.lower()))
    return [str(p) for p in candidatos]


def buscar_junto_a(ruta_video: str) -> str | None:
    candidatos = subtitulos_junto_a(ruta_video)
    return candidatos[0] if candidatos else None


def descripcion(ruta_sub: str, ruta_video: str) -> str:
    """«video.es.srt» -> «Español (video.es.srt)»."""
    extra = Path(ruta_sub).stem[len(Path(ruta_video).stem):].strip(".")
    nombre = Path(ruta_sub).name
    return f"{IDIOMAS.get(extra.lower(), extra)} ({nombre})" if extra else nombre


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", texto.lower()))


def colocar_subtitulo(archivo: Path, ruta_video: str, idioma: str = "es") -> str | None:
    """Pone un subtítulo descargado (suelto o comprimido) junto al video, como «video.es.srt».
    Si el comprimido trae varios, elige el que más se parece al nombre del video.
    Devuelve la ruta nueva, o None si no había subtítulos."""
    video = Path(ruta_video)
    with tempfile.TemporaryDirectory() as carpeta:
        if archivo.suffix.lower() in EXT_COMPRIMIDOS:
            tar = Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
            try:
                subprocess.run([str(tar) if tar.exists() else "tar", "-xf", str(archivo), "-C", carpeta],
                               capture_output=True, timeout=60,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            except subprocess.TimeoutExpired:
                return None
            candidatos = [p for p in Path(carpeta).rglob("*") if p.suffix.lower() in EXT_SUBTITULOS]
        else:
            candidatos = [archivo]
        if not candidatos:
            return None
        nombre = _palabras(video.stem)
        elegido = max(candidatos, key=lambda p: (len(_palabras(p.stem) & nombre), p.stat().st_size))
        destino = video.with_name(f"{video.stem}.{idioma}{elegido.suffix.lower()}")
        n = 2
        while destino.exists():
            destino = video.with_name(f"{video.stem}.{idioma}{n}{elegido.suffix.lower()}")
            n += 1
        shutil.copyfile(elegido, destino)
    archivo.unlink(missing_ok=True)  # ya está junto al video: no queda suelto en Descargas
    return str(destino)
