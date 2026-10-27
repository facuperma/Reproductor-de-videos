"""Biblioteca automática, en un hilo propio:

- Mueve los videos terminados de Descargas a la carpeta de videos.
- Revisa las carpetas de la biblioteca (Videos y Documentos) y suma los videos nuevos.
"""
import glob
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .db import EXT_VIDEO, Biblioteca
from .subtitulos import EXT_SUBTITULOS

INTERVALO_S = 10            # revisión de Descargas
INTERVALO_ESCANEO_S = 60    # revisión de las carpetas de la biblioteca
QUIETO_S = 20               # un archivo sin cambios hace este tiempo se considera terminado
# Carpetas que no se recorren (además de las que empiezan con «.» o «$»)
IGNORAR = {"node_modules", "__pycache__", "appdata", "site-packages", "venv", "env"}


def en_uso(ruta: Path) -> bool:
    """True si otro programa tiene el archivo abierto (p. ej. todavía lo está descargando)."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = wintypes.HANDLE
    # Abrir sin compartir (dwShareMode=0) falla si alguien más lo tiene abierto
    manejador = kernel32.CreateFileW(str(ruta), 0x80000000 | 0x40000000, 0, None, 3, 0x80, None)
    if manejador in (None, ctypes.c_void_p(-1).value):
        return True
    kernel32.CloseHandle(manejador)
    return False


def destino_libre(destino: Path) -> Path:
    """«video.mp4» -> «video (2).mp4» si ya existe."""
    n = 2
    candidato = destino
    while candidato.exists():
        candidato = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        n += 1
    return candidato


class Vigilante(QObject):
    archivos_nuevos = Signal(int)
    movido = Signal(str)  # ruta nueva del video

    def __init__(self, ruta_db: Path):
        super().__init__()
        self.ruta_db = ruta_db
        self._despertar = threading.Event()
        self._parar = threading.Event()
        self._escanear_ya = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def iniciar(self):
        self._hilo.start()

    def despertar(self):
        """Revisar ya (p. ej. después de cambiar la configuración)."""
        self._escanear_ya = True
        self._despertar.set()

    def detener(self):
        self._parar.set()
        self._despertar.set()

    def _bucle(self):
        bib = Biblioteca(self.ruta_db)
        vistos: dict[Path, tuple] = {}
        ultimo_escaneo = 0.0
        while not self._parar.is_set():
            try:
                if bib.config("mover_descargas") == "1":
                    self._revisar_descargas(bib, vistos)
                if self._escanear_ya or time.monotonic() - ultimo_escaneo > INTERVALO_ESCANEO_S:
                    self._escanear_ya = False
                    ultimo_escaneo = time.monotonic()
                    if nuevos := self._escanear(bib):
                        self.archivos_nuevos.emit(nuevos)
            except OSError:
                pass  # carpeta inaccesible o archivo que desapareció: se reintenta en la próxima vuelta
            self._despertar.wait(INTERVALO_S)
            self._despertar.clear()

    def _revisar_descargas(self, bib: Biblioteca, vistos: dict):
        origen = Path(bib.config("carpeta_descargas_sistema"))
        destino = Path(bib.config("carpeta_videos"))
        if not origen.is_dir() or origen.resolve() == destino.resolve():
            return
        actuales = {}
        for archivo in origen.iterdir():
            if not archivo.is_file() or archivo.suffix.lower() not in EXT_VIDEO:
                continue
            info = archivo.stat()
            firma = (info.st_size, info.st_mtime)
            actuales[archivo] = firma
            # Terminado: mismo tamaño que en la vuelta anterior, quieto hace un rato y nadie lo tiene abierto
            if (vistos.get(archivo) == firma and info.st_size > 0
                    and time.time() - info.st_mtime > QUIETO_S and not en_uso(archivo)):
                nuevo = self._mover(archivo, destino)
                bib.agregar_archivos([nuevo])
                self.movido.emit(str(nuevo))
        vistos.clear()
        vistos.update(actuales)

    def _mover(self, video: Path, carpeta: Path) -> Path:
        carpeta.mkdir(parents=True, exist_ok=True)
        nuevo = destino_libre(carpeta / video.name)
        # Los subtítulos con el mismo nombre viajan con el video
        for sub in video.parent.glob(glob.escape(video.stem) + "*"):
            if sub.suffix.lower() in EXT_SUBTITULOS and (sub.stem == video.stem or sub.stem.startswith(video.stem + ".")):
                shutil.move(str(sub), str(carpeta / (nuevo.stem + sub.name[len(video.stem):])))
        shutil.move(str(video), str(nuevo))
        return nuevo

    def _escanear(self, bib: Biblioteca) -> int:
        conocidas = bib.rutas_conocidas()
        nuevas = []
        for carpeta in bib.carpetas_biblioteca():
            raiz = Path(carpeta)
            if not raiz.is_dir():
                continue
            for actual, subcarpetas, archivos in os.walk(raiz.resolve()):
                if self._parar.is_set():
                    return 0
                subcarpetas[:] = [d for d in subcarpetas
                                  if not d.startswith((".", "$")) and d.lower() not in IGNORAR]
                for nombre in archivos:
                    if Path(nombre).suffix.lower() in EXT_VIDEO:
                        ruta = os.path.join(actual, nombre)
                        if ruta not in conocidas:
                            nuevas.append(Path(ruta))
        return bib.agregar_archivos(nuevas) if nuevas else 0
