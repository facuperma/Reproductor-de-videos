"""Cliente de la API REST de OpenSubtitles (https://www.opensubtitles.com).

Requiere una clave de API gratuita. Con usuario y contraseña se obtiene más cupo diario de descargas.
"""
import os
import re
import struct
from pathlib import Path

from .red import ErrorRed, bajar_bytes, pedir_json

API = "https://api.opensubtitles.com/api/v1"


def hash_pelicula(ruta: str) -> str:
    """Hash de OpenSubtitles: tamaño + sumas de los primeros y últimos 64 KB."""
    tamano = os.path.getsize(ruta)
    h = tamano
    bloque = 65536
    with open(ruta, "rb") as f:
        for inicio in (0, max(0, tamano - bloque)):
            f.seek(inicio)
            datos = f.read(bloque)
            for (n,) in struct.iter_unpack("<Q", datos[: len(datos) // 8 * 8]):
                h = (h + n) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def titulo_desde_nombre(ruta: str) -> str:
    """«The.Movie_1950 (HD).mp4» -> «The Movie 1950»."""
    nombre = re.sub(r"[._]+", " ", Path(ruta).stem)
    return re.split(r"[\[({]", nombre)[0].strip() or nombre


class OpenSubtitles:
    def __init__(self, api_key: str, usuario: str = "", clave: str = ""):
        if not api_key:
            raise ErrorRed("Falta la clave de API de OpenSubtitles (Configuración)")
        self.api_key = api_key
        self.base = API
        self.token = None
        if usuario and clave:
            r = self._pedir("/login", cuerpo={"username": usuario, "password": clave})
            self.token = r["token"]
            if r.get("base_url"):
                self.base = f"https://{r['base_url']}/api/v1"

    def _pedir(self, ruta: str, params: dict | None = None, cuerpo: dict | None = None):
        cabeceras = {"Api-Key": self.api_key}
        if self.token:
            cabeceras["Authorization"] = f"Bearer {self.token}"
        # La API exige parámetros en orden alfabético y en minúsculas (si no, redirige)
        ordenados = sorted((k, str(v).lower()) for k, v in (params or {}).items())
        try:
            return pedir_json(self.base + ruta, ordenados, cuerpo, cabeceras)
        except ErrorRed as e:
            if e.codigo in (401, 403):
                raise ErrorRed("clave de API, usuario o contraseña de OpenSubtitles incorrectos", e.codigo) from e
            if e.codigo == 406:
                raise ErrorRed("se terminó el cupo diario de descargas de OpenSubtitles", e.codigo) from e
            raise

    def _buscar(self, idioma: str, hash_: str | None, titulo: str | None) -> int | None:
        intentos = []
        if hash_:
            intentos.append({"languages": idioma, "moviehash": hash_})
        if titulo:
            intentos.append({"languages": idioma, "query": titulo})
        for params in intentos:
            resultados = self._pedir("/subtitles", params).get("data", [])
            candidatos = [r["attributes"] for r in resultados if r["attributes"].get("files")]
            if candidatos:
                # Mejor: coincide el hash (queda sincronizado) y luego el más descargado
                mejor = max(candidatos, key=lambda a: (bool(a.get("moviehash_match")),
                                                       a.get("download_count", 0)))
                return mejor["files"][0]["file_id"]
        return None

    def descargar(self, ruta_video: str, idioma: str, titulo: str | None = None) -> str | None:
        """Descarga el subtítulo junto al video como «nombre.<idioma>.srt». Devuelve la ruta o None."""
        destino = Path(ruta_video).with_suffix(f".{idioma}.srt")
        if destino.exists():
            return str(destino)
        file_id = self._buscar(idioma, hash_pelicula(ruta_video), titulo or titulo_desde_nombre(ruta_video))
        if file_id is None:
            return None
        enlace = self._pedir("/download", cuerpo={"file_id": file_id})["link"]
        destino.write_bytes(bajar_bytes(enlace))
        return str(destino)


def cliente_desde_config(bib) -> OpenSubtitles:
    return OpenSubtitles(bib.config("os_api_key"), bib.config("os_usuario"), bib.config("os_clave"))


def idiomas_de(bib) -> list[str]:
    return [i.strip().lower() for i in bib.config("idiomas_subtitulos").split(",") if i.strip()]
