"""Cola de descargas del Internet Archive, en un hilo propio.

El hilo usa su propia conexión a la base; la integración con la biblioteca
(agregar el archivo, asignar la categoría) la hace la ventana al recibir `pelicula_lista`.
"""
import re
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import archive
from .db import Biblioteca
from .opensubtitles import OpenSubtitles, idiomas_de
from .red import ErrorRed, abrir_descarga, bajar_bytes

ESPACIO_LIBRE_MINIMO = 5 * 1024**3  # nunca llenar el disco por debajo de 5 GB libres


class Cancelada(Exception):
    pass


class Detenida(Exception):
    pass


def nombre_seguro(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto).strip(" .")[:120] or "pelicula"


class GestorDescargas(QObject):
    cola_cambiada = Signal()
    progreso = Signal(str, int, int)        # identificador, recibido, total
    pelicula_lista = Signal(str)             # ruta del video descargado
    mensaje = Signal(str)

    def __init__(self, ruta_db: Path):
        super().__init__()
        self.ruta_db = ruta_db
        self._despertar = threading.Event()
        self._parar = threading.Event()
        self._cancelar: set[str] = set()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def iniciar(self):
        self._hilo.start()

    def despertar(self):
        self._despertar.set()

    def cancelar(self, identificador: str):
        self._cancelar.add(identificador)

    def detener(self):
        self._parar.set()
        self._despertar.set()

    # --- Hilo de trabajo ------------------------------------------------------

    def _bucle(self):
        bib = Biblioteca(self.ruta_db)
        bib.reiniciar_descargas_interrumpidas()
        self.cola_cambiada.emit()
        while not self._parar.is_set():
            tarea = bib.siguiente_descarga()
            if tarea is None and bib.config("auto_activa") == "1":
                try:
                    if self._encolar_automatica(bib):
                        continue
                except ErrorRed as e:
                    self.mensaje.emit(f"Descarga automática: {e}")
            if tarea is None:
                self._despertar.wait(60)
                self._despertar.clear()
                continue
            self._procesar(bib, dict(tarea))

    def _encolar_automatica(self, bib: Biblioteca) -> bool:
        """Agrega a la cola la película más popular que falte, si entra en los límites."""
        max_peliculas = int(bib.config("auto_max_peliculas") or 0)
        max_bytes = float(bib.config("auto_max_gb") or 0) * 1024**3
        cantidad, usados = bib.resumen_descargas()
        if cantidad >= max_peliculas:
            return False
        conocidas = bib.estados_descarga()
        for pagina in range(1, 51):
            _total, peliculas = archive.buscar("", pagina, 100)
            if not peliculas:
                return False
            for p in peliculas:
                if p["identificador"] in conocidas or self._parar.is_set():
                    continue
                info = archive.archivos_de(p["identificador"])
                if info is None:
                    bib.agregar_descarga(p["identificador"], p["titulo"], p["anio"], estado="omitida")
                    continue
                if usados + info["video"]["tamano"] > max_bytes:
                    self.mensaje.emit("Descarga automática: se alcanzó el límite de espacio")
                    return False
                bib.agregar_descarga(p["identificador"], p["titulo"], p["anio"], info["video"]["tamano"])
                self.cola_cambiada.emit()
                return True
        return False

    def _procesar(self, bib: Biblioteca, tarea: dict):
        ident = tarea["identificador"]
        self._cancelar.discard(ident)
        bib.actualizar_descarga(ident, estado="descargando", error=None)
        self.cola_cambiada.emit()
        parcial = None
        try:
            info = archive.archivos_de(ident)
            if info is None:
                raise ErrorRed("El ítem no tiene un video descargable")
            video = info["video"]
            bib.actualizar_descarga(ident, tamano=video["tamano"])
            self.cola_cambiada.emit()  # con el tamaño ya se puede mostrar la barra de progreso

            base = nombre_seguro(f"{tarea['titulo']} ({tarea['anio']})" if tarea["anio"] else tarea["titulo"])
            carpeta = Path(bib.config("carpeta_descargas")) / base
            carpeta.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(carpeta).free - video["tamano"] < ESPACIO_LIBRE_MINIMO:
                raise ErrorRed("No hay espacio suficiente en el disco")
            destino = carpeta / (base + Path(video["nombre"]).suffix.lower())

            if not destino.exists():
                parcial = destino.with_name(destino.name + ".part")
                self._bajar(archive.url_de(ident, video["nombre"]), parcial, ident, bib)
                parcial.replace(destino)

            self._subtitulos(bib, ident, info, destino, tarea["titulo"])
            bib.actualizar_descarga(ident, estado="completa", ruta=str(destino))
            self.pelicula_lista.emit(str(destino))
        except Cancelada:
            if parcial:
                parcial.unlink(missing_ok=True)
            bib.actualizar_descarga(ident, estado="cancelada")
        except Detenida:
            bib.actualizar_descarga(ident, estado="pendiente")  # se retoma al volver a abrir la app
        except (ErrorRed, OSError) as e:
            bib.actualizar_descarga(ident, estado="error", error=str(e))
            self.mensaje.emit(f"Error al descargar «{tarea['titulo']}»: {e}")
        self.cola_cambiada.emit()

    def _bajar(self, url: str, parcial: Path, ident: str, bib: Biblioteca):
        """Descarga con reanudación: si quedó un .part, pide solo lo que falta."""
        ya = parcial.stat().st_size if parcial.exists() else 0
        with abrir_descarga(url, ya) as respuesta:
            if ya and respuesta.status != 206:
                ya = 0  # el servidor no permite retomar: se empieza de nuevo
            total = ya + int(respuesta.headers.get("Content-Length") or 0)
            ultimo_aviso = 0.0
            with open(parcial, "ab" if ya else "wb") as f:
                while bloque := respuesta.read(1024 * 1024):
                    if self._parar.is_set():
                        raise Detenida
                    if ident in self._cancelar:
                        raise Cancelada
                    f.write(bloque)
                    ya += len(bloque)
                    if time.monotonic() - ultimo_aviso > 0.5:
                        ultimo_aviso = time.monotonic()
                        self.progreso.emit(ident, ya, total)
            bib.actualizar_descarga(ident, recibido=ya)

    def _subtitulos(self, bib: Biblioteca, ident: str, info: dict, video: Path, titulo: str):
        """Subtítulos en los idiomas configurados: primero OpenSubtitles; para inglés,
        si no hay, los del propio Internet Archive (pueden ser transcripción automática)."""
        cliente = None
        if bib.config("os_api_key"):
            try:
                cliente = OpenSubtitles(bib.config("os_api_key"), bib.config("os_usuario"), bib.config("os_clave"))
            except ErrorRed as e:
                self.mensaje.emit(f"OpenSubtitles: {e}")
        faltantes = []
        for idioma in idiomas_de(bib):
            destino = video.with_suffix(f".{idioma}.srt")
            if destino.exists():
                continue
            if cliente:
                try:
                    if cliente.descargar(str(video), idioma, titulo):
                        continue
                except (ErrorRed, KeyError, OSError) as e:
                    self.mensaje.emit(f"Subtítulos ({idioma}) de «{titulo}»: {e}")
            if idioma == "en" and info["subtitulos"]:
                # Preferir subtítulos hechos por personas antes que la transcripción automática (.asr.srt)
                nombre = sorted(info["subtitulos"], key=lambda n: ".asr." in n.lower())[0]
                try:
                    destino.write_bytes(bajar_bytes(archive.url_de(ident, nombre)))
                    continue
                except (ErrorRed, OSError) as e:
                    self.mensaje.emit(f"Subtítulos (en) de «{titulo}»: {e}")
            faltantes.append(idioma)
        if faltantes:
            motivo = "" if cliente else " — configurá la clave de OpenSubtitles para conseguirlos"
            self.mensaje.emit(f"«{titulo}» quedó sin subtítulos en: {', '.join(faltantes)}{motivo}")
