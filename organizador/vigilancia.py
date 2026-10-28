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
from .subtitulos import EXT_COMPRIMIDOS, EXT_SUBTITULOS, colocar_subtitulo

INTERVALO_S = 10            # revisión de Descargas
INTERVALO_ESCANEO_S = 60    # revisión de las carpetas de la biblioteca
QUIETO_S = 20               # un archivo sin cambios hace este tiempo se considera terminado
RECIENTE_S = 30 * 24 * 3600  # subcarpetas de Descargas creadas en el último mes (torrents)
MUESTRA_MAX = 300 * 1024 * 1024
ESPERA_SUBTITULO_S = 15 * 60  # cuánto se espera el subtítulo pedido a subdivx
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


def borrar_carpetas_vacias(carpeta: Path, raiz: Path):
    """Saca las carpetas que quedaron vacías, de `carpeta` hacia arriba sin llegar a `raiz`
    (si quedan .txt o .nfo, las deja)."""
    raiz = raiz.resolve()
    carpeta = carpeta.resolve()
    while carpeta != raiz and raiz in carpeta.parents:
        try:
            carpeta.rmdir()
        except OSError:
            return
        carpeta = carpeta.parent


def mover_video(video: Path, carpeta: Path) -> tuple[Path, dict[str, str]]:
    """Mueve el video y sus subtítulos; devuelve la ruta nueva y {sub viejo: sub nuevo}."""
    carpeta.mkdir(parents=True, exist_ok=True)
    carpeta = carpeta.resolve()  # misma forma de ruta que guarda la biblioteca
    nuevo = destino_libre(carpeta / video.name)
    subtitulos = {}
    # Los subtítulos con el mismo nombre viajan con el video
    for sub in video.parent.glob(glob.escape(video.stem) + "*"):
        if sub.suffix.lower() in EXT_SUBTITULOS and (sub.stem == video.stem or sub.stem.startswith(video.stem + ".")):
            sub_nuevo = carpeta / (nuevo.stem + sub.name[len(video.stem):])
            shutil.move(str(sub), str(sub_nuevo))
            subtitulos[str(sub)] = str(sub_nuevo)
    shutil.move(str(video), str(nuevo))
    return nuevo, subtitulos


class Vigilante(QObject):
    archivos_nuevos = Signal(int)
    movido = Signal(str)  # ruta nueva del video
    descargado = Signal(str)  # video que acaba de bajar (para buscarle subtítulos)
    subtitulo_listo = Signal(str, str)  # video, subtítulo colocado junto a él
    subtitulo_fallido = Signal(str)  # mensaje

    def __init__(self, ruta_db: Path):
        super().__init__()
        self.ruta_db = ruta_db
        self._despertar = threading.Event()
        self._parar = threading.Event()
        self._escanear_ya = True
        self._esperando: tuple[str, float] | None = None  # (video, desde cuándo) esperando subtítulo
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def iniciar(self):
        self._hilo.start()

    def despertar(self):
        """Revisar ya (p. ej. después de cambiar la configuración)."""
        self._escanear_ya = True
        self._despertar.set()

    def esperar_subtitulo(self, ruta_video: str):
        """El subtítulo que se baje a Descargas en los próximos minutos es para este video."""
        self._esperando = (ruta_video, time.time())
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
                if self._esperando:
                    self._buscar_subtitulo(bib)
                if bib.config("mover_descargas") == "1":
                    self._revisar_descargas(bib, vistos)
                if self._escanear_ya or time.monotonic() - ultimo_escaneo > INTERVALO_ESCANEO_S:
                    self._escanear_ya = False
                    ultimo_escaneo = time.monotonic()
                    if nuevos := self._escanear(bib):
                        self.archivos_nuevos.emit(nuevos)
            except OSError:
                pass  # carpeta inaccesible o archivo que desapareció: se reintenta en la próxima vuelta
            # Esperando un subtítulo, se mira más seguido
            self._despertar.wait(2 if self._esperando else INTERVALO_S)
            self._despertar.clear()

    def _revisar_descargas(self, bib: Biblioteca, vistos: dict):
        origen = Path(bib.config("carpeta_descargas_sistema")).resolve()
        destino = Path(bib.config("carpeta_videos"))
        if not origen.is_dir() or origen == destino.resolve():
            return
        actuales = {}
        for archivo, info in self._videos_descargas(origen):
            firma = (info.st_size, info.st_mtime)
            actuales[archivo] = firma
            # Terminado: mismo tamaño que en la vuelta anterior y quieto hace un rato
            # (uTorrent y los navegadores usan otra extensión mientras bajan: .!ut, .crdownload, .part)
            if vistos.get(archivo) != firma or info.st_size == 0 or time.time() - info.st_mtime <= QUIETO_S:
                continue
            try:
                if en_uso(archivo):
                    # El programa de torrents lo sigue compartiendo (o se está mirando):
                    # se muestra ya desde Descargas y se mueve cuando lo suelte
                    if bib.agregar_archivos([archivo]):
                        self.archivos_nuevos.emit(1)
                        self.descargado.emit(str(archivo))
                    continue
                nuevo, subtitulos = mover_video(archivo, destino / archivo.parent.relative_to(origen))
                if bib.id_de_ruta(str(archivo)) is None:
                    bib.agregar_archivos([nuevo])
                    self.descargado.emit(str(nuevo))
                else:
                    bib.mover_ruta(archivo, nuevo, subtitulos)
                borrar_carpetas_vacias(archivo.parent, origen)
                self.movido.emit(str(nuevo))
            except OSError:
                pass  # se reintenta en la próxima vuelta, sin frenar a los demás
        vistos.clear()
        vistos.update(actuales)

    def _buscar_subtitulo(self, bib: Biblioteca):
        video, desde = self._esperando
        if time.time() - desde > ESPERA_SUBTITULO_S:
            self._esperando = None
            return
        origen = Path(bib.config("carpeta_descargas_sistema"))
        for archivo in origen.iterdir():
            if (archivo.suffix.lower() not in EXT_SUBTITULOS | EXT_COMPRIMIDOS or not archivo.is_file()
                    or archivo.stat().st_ctime < desde - 5):
                continue
            if time.time() - archivo.stat().st_mtime < 2 or en_uso(archivo):
                continue  # el navegador lo está terminando de guardar
            self._esperando = None
            if sub := colocar_subtitulo(archivo, video):
                self.subtitulo_listo.emit(video, sub)
            else:
                self.subtitulo_fallido.emit(f"{archivo.name} no tiene subtítulos (.srt o .vtt) adentro")
            return

    def _videos_descargas(self, origen: Path):
        """(ruta, stat) de los videos de Descargas: los sueltos y los de las carpetas
        recientes (los torrents bajan cada película en su carpeta)."""
        for actual, subcarpetas, archivos in os.walk(origen):
            if Path(actual) == origen:
                # Las carpetas viejas son del usuario, no descargas en curso: no se tocan
                subcarpetas[:] = [d for d in subcarpetas if not d.startswith((".", "$"))
                                  and d.lower() not in IGNORAR
                                  and time.time() - os.stat(os.path.join(actual, d)).st_ctime < RECIENTE_S]
            for nombre in archivos:
                archivo = Path(actual, nombre)
                if archivo.suffix.lower() not in EXT_VIDEO:
                    continue
                info = archivo.stat()
                # Los torrents suelen traer un «sample» de un minuto
                if actual != str(origen) and "sample" in archivo.stem.lower() and info.st_size < MUESTRA_MAX:
                    continue
                yield archivo, info

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
