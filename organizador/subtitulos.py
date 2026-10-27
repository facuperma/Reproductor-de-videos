"""Lectura de subtítulos externos (.srt y .vtt)."""
import glob
import re
from bisect import bisect_right
from pathlib import Path

EXT_SUBTITULOS = {".srt", ".vtt"}

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
