"""Descargas por BitTorrent (links magnet y archivos .torrent) con aria2.

aria2c.exe (https://aria2.github.io, GPL v2) corre oculto mientras haya descargas y TVon esté
abierto; se maneja por JSON-RPC en localhost. Baja a una carpeta oculta dentro de la carpeta de
videos y, al terminar, la película pasa a la carpeta de videos. La integración con la biblioteca
(agregar el archivo, buscar subtítulos) la hace la ventana al recibir `terminado`.
"""
import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal

from .db import EXT_VIDEO, Biblioteca
from .vigilancia import MUESTRA_MAX, destino_libre

ARIA2 = Path(__file__).parent / "bin" / "aria2c.exe"
# Empieza con «.»: el escaneo de la biblioteca no entra, así no aparecen películas a medio bajar
CARPETA_TEMPORAL = ".torrents (descargando)"
CAMPOS = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed",
          "numSeeders", "connections", "errorMessage", "followedBy", "files", "bittorrent", "dir", "infoHash"]


class ErrorTorrent(Exception):
    pass


def disponible() -> bool:
    return ARIA2.exists()


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ocultar(carpeta: Path):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(carpeta), 0x2)  # FILE_ATTRIBUTE_HIDDEN


class Aria2:
    """El proceso aria2c y las llamadas RPC."""

    def __init__(self, carpeta_temporal: Path, carpeta_datos: Path):
        self.puerto = _puerto_libre()
        self.secreto = secrets.token_hex(16)
        sesion = carpeta_datos / "torrents.sesion"  # descargas sin terminar: se retoman al volver a abrir
        sesion.touch()
        argumentos = [
            str(ARIA2), "--enable-rpc", f"--rpc-listen-port={self.puerto}", f"--rpc-secret={self.secreto}",
            f"--dir={carpeta_temporal}", f"--input-file={sesion}", f"--save-session={sesion}",
            "--save-session-interval=30", f"--dht-file-path={carpeta_datos / 'torrents.dht'}",
            # Al terminar suelta los archivos (no sigue compartiendo) para poder moverlos
            "--seed-time=0", "--follow-torrent=mem", "--max-concurrent-downloads=3",
            "--file-allocation=falloc", "--quiet=true",
            # Si TVon se cierra de golpe, aria2 también
            f"--stop-with-process={os.getpid()}",
        ]
        banderas = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proceso = subprocess.Popen(argumentos, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, creationflags=banderas)
        for _ in range(50):
            try:
                self.llamar("getVersion")
                return
            except ErrorTorrent:
                if self.proceso.poll() is not None:
                    raise ErrorTorrent("aria2 no pudo arrancar") from None
                time.sleep(0.1)
        raise ErrorTorrent("aria2 no responde")

    def llamar(self, metodo: str, *params):
        cuerpo = json.dumps({"jsonrpc": "2.0", "id": "tvon", "method": f"aria2.{metodo}",
                             "params": [f"token:{self.secreto}", *params]}).encode()
        pedido = Request(f"http://127.0.0.1:{self.puerto}/jsonrpc", cuerpo, {"Content-Type": "application/json"})
        try:
            with urlopen(pedido, timeout=10) as r:
                return json.load(r)["result"]
        except HTTPError as e:
            try:
                mensaje = json.load(e)["error"]["message"]
            except (ValueError, KeyError):
                mensaje = str(e)
            raise ErrorTorrent(mensaje) from e
        except (URLError, OSError) as e:
            raise ErrorTorrent(f"aria2 no responde: {e}") from e

    def cerrar(self):
        try:
            self.llamar("shutdown")  # guarda la sesión
            self.proceso.wait(5)
        except (ErrorTorrent, subprocess.TimeoutExpired):
            self.proceso.kill()


def raices(descarga: dict, carpeta_temporal: Path) -> list[Path]:
    """Lo que creó el torrent en la carpeta temporal: su carpeta o, si es un solo archivo, ese archivo."""
    resultado = []
    for archivo in descarga.get("files", []):
        if not archivo.get("path"):
            continue
        try:
            relativa = Path(archivo["path"]).resolve().relative_to(carpeta_temporal.resolve())
        except ValueError:
            continue
        raiz = carpeta_temporal / relativa.parts[0]
        if raiz not in resultado:
            resultado.append(raiz)
    return resultado


def nombre_de(descarga: dict) -> str:
    info = (descarga.get("bittorrent") or {}).get("info") or {}
    return info.get("name") or ""


def videos_en(ruta: Path) -> list[Path]:
    """Videos de lo que bajó el torrent, sin los «sample»."""
    archivos = [ruta] if ruta.is_file() else sorted(ruta.rglob("*"))
    return [a for a in archivos if a.suffix.lower() in EXT_VIDEO and a.is_file()
            and not ("sample" in a.stem.lower() and a.stat().st_size < MUESTRA_MAX)]


class GestorTorrents(QObject):
    estado = Signal(list)          # descargas: [{gid, nombre, estado, total, recibido, velocidad, …}]
    terminado = Signal(list, str)  # rutas de los videos ya en la carpeta de videos, nombre del torrent
    mensaje = Signal(str)

    def __init__(self, ruta_db: Path):
        super().__init__()
        self.ruta_db = ruta_db
        self.carpeta_datos = ruta_db.parent
        self.aria2: Aria2 | None = None
        self.temporal = self.videos = None  # se leen de la configuración al arrancar aria2
        self._cerrojo = threading.Lock()
        self._parar = threading.Event()
        self._despertar = threading.Event()
        self._por_borrar: list[Path] = []  # archivos de descargas canceladas (aria2 los suelta enseguida)
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def iniciar(self):
        self._hilo.start()

    def detener(self):
        self._parar.set()
        self._despertar.set()
        with self._cerrojo:
            if self.aria2:
                self.aria2.cerrar()
                self.aria2 = None

    def _asegurar(self) -> Aria2:
        """Arranca aria2 la primera vez que hace falta."""
        with self._cerrojo:
            if self.aria2 is None:
                if not disponible():
                    raise ErrorTorrent(f"Falta {ARIA2.name} en {ARIA2.parent}")
                self.videos = Path(Biblioteca(self.ruta_db).config("carpeta_videos"))
                self.temporal = self.videos / CARPETA_TEMPORAL
                self.temporal.mkdir(parents=True, exist_ok=True)
                _ocultar(self.temporal)
                self.aria2 = Aria2(self.temporal, self.carpeta_datos)
                self._recuperar_terminadas()
            self._despertar.set()
            return self.aria2

    # --- Acciones (desde la interfaz) ---------------------------------------------

    def agregar(self, texto: str) -> str:
        """Un link magnet o la ruta de un archivo .torrent. Devuelve el gid."""
        texto = texto.strip()
        if texto.lower().startswith("magnet:?"):
            return self._asegurar().llamar("addUri", [texto])
        ruta = Path(texto)
        if ruta.suffix.lower() == ".torrent" and ruta.is_file():
            return self._asegurar().llamar("addTorrent", base64.b64encode(ruta.read_bytes()).decode())
        raise ErrorTorrent("Pegá un link magnet (empieza con «magnet:?») o elegí un archivo .torrent")

    def pausar(self, gid: str):
        self._asegurar().llamar("forcePause", gid)

    def reanudar(self, gid: str):
        self._asegurar().llamar("unpause", gid)

    def cancelar(self, gid: str):
        """Saca la descarga y borra lo que había bajado."""
        aria2 = self._asegurar()
        descarga = aria2.llamar("tellStatus", gid, ["status", "files", "followedBy", "infoHash"])
        for hijo in descarga.get("followedBy", []):
            self.cancelar(hijo)
        with self._cerrojo:
            for raiz in raices(descarga, self.temporal):
                self._por_borrar += [raiz, raiz.with_name(raiz.name + ".aria2")]
            if descarga.get("infoHash"):
                self._por_borrar.append(self.temporal / f"{descarga['infoHash']}.torrent")
        if descarga["status"] in ("active", "waiting", "paused"):
            aria2.llamar("forceRemove", gid)
        else:
            aria2.llamar("removeDownloadResult", gid)

    # --- Hilo que sigue el progreso -------------------------------------------------

    def _bucle(self):
        # Si quedaron descargas de la vez anterior, se retoman solas
        sesion = self.carpeta_datos / "torrents.sesion"
        if sesion.exists() and sesion.stat().st_size > 0:
            try:
                self._asegurar()
            except ErrorTorrent as e:
                self.mensaje.emit(f"Torrents: {e}")
        while not self._parar.is_set():
            if self.aria2 is not None:
                try:
                    self._revisar()
                except (ErrorTorrent, OSError) as e:
                    self.mensaje.emit(f"Torrents: {e}")
            self._despertar.wait(1 if self.aria2 else 30)
            self._despertar.clear()

    def _revisar(self):
        aria2 = self.aria2
        if aria2 is None:
            return
        temporal, videos = self.temporal, self.videos
        todas = (aria2.llamar("tellActive", CAMPOS) + aria2.llamar("tellWaiting", 0, 1000, CAMPOS)
                 + aria2.llamar("tellStopped", 0, 1000, CAMPOS))
        lista = []
        for d in todas:
            nombre = nombre_de(d)
            if d.get("followedBy"):
                # Era la búsqueda de los datos de un magnet: sigue con otro gid, el torrent de verdad
                if d["status"] not in ("active", "waiting", "paused"):
                    aria2.llamar("removeDownloadResult", d["gid"])
                continue
            if d["status"] == "complete" and nombre:
                self._terminar(aria2, d, temporal, videos)
                continue
            if d["status"] in ("removed", "complete"):
                aria2.llamar("removeDownloadResult", d["gid"])
                continue
            lista.append({
                "gid": d["gid"], "nombre": nombre, "estado": d["status"],
                "total": int(d["totalLength"]), "recibido": int(d["completedLength"]),
                "velocidad": int(d["downloadSpeed"]), "subida": int(d["uploadSpeed"]),
                "fuentes": int(d.get("numSeeders") or 0), "conexiones": int(d["connections"]),
                "error": d.get("errorMessage", ""),
            })
        self._borrar_canceladas()
        self.estado.emit(lista)

    def _terminar(self, aria2: Aria2, descarga: dict, temporal: Path, videos: Path):
        nuevos = []
        for raiz in raices(descarga, temporal):
            destino = destino_libre(videos / raiz.name)
            shutil.move(str(raiz), str(destino))
            nuevos += videos_en(destino)
        aria2.llamar("removeDownloadResult", descarga["gid"])
        # Copia del .torrent que aria2 guarda para retomar la descarga: ya no hace falta
        (temporal / f"{descarga.get('infoHash')}.torrent").unlink(missing_ok=True)
        self.terminado.emit([str(v.resolve()) for v in nuevos], nombre_de(descarga))

    def _recuperar_terminadas(self):
        """Lo que terminó de bajar mientras TVon se cerraba: queda en la carpeta temporal sin su
        archivo de control (.aria2) y aria2 ya no lo tiene en la lista."""
        temporal, videos = self.temporal, self.videos
        en_curso = set()
        for metodo, params in (("tellActive", ()), ("tellWaiting", (0, 1000)), ("tellStopped", (0, 1000))):
            for d in self.aria2.llamar(metodo, *params, ["files"]):
                en_curso.update(raices(d, temporal))
        for raiz in temporal.iterdir():
            if (raiz in en_curso or raiz.suffix in (".aria2", ".torrent")
                    or raiz.with_name(raiz.name + ".aria2").exists()):
                continue
            destino = destino_libre(videos / raiz.name)
            shutil.move(str(raiz), str(destino))
            if encontrados := videos_en(destino):
                self.terminado.emit([str(v.resolve()) for v in encontrados], raiz.name)

    def _borrar_canceladas(self):
        with self._cerrojo:
            rutas, self._por_borrar = self._por_borrar, []
        pendientes = []
        for ruta in rutas:
            try:
                if ruta.is_dir():
                    shutil.rmtree(ruta)
                else:
                    ruta.unlink(missing_ok=True)
            except OSError:
                pendientes.append(ruta)  # aria2 todavía lo tiene abierto: se reintenta
        with self._cerrojo:
            self._por_borrar += pendientes
