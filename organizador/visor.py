"""Panel que muestra una imagen o reproduce un video con sus controles."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QStackedWidget,
    QStyle, QVBoxLayout, QWidget,
)


def formato_tiempo(ms: int) -> str:
    s = ms // 1000
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


class VideoPantalla(QVideoWidget):
    """Video que alterna pantalla completa con doble clic o Esc."""
    alternar_completa = Signal()

    def mouseDoubleClickEvent(self, e):
        self.alternar_completa.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.isFullScreen():
            self.alternar_completa.emit()
        else:
            super().keyPressEvent(e)


class ImagenEscalada(QLabel):
    """Etiqueta que reescala la imagen al tamaño disponible."""

    def __init__(self):
        super().__init__(alignment=Qt.AlignCenter)
        self._pixmap = QPixmap()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def mostrar(self, ruta: str):
        self._pixmap = QPixmap(ruta)
        if self._pixmap.isNull():
            self.setText("No se pudo abrir la imagen")
        self._reescalar()

    def resizeEvent(self, e):
        self._reescalar()

    def _reescalar(self):
        if not self._pixmap.isNull():
            self.setPixmap(self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class Visor(QWidget):
    def __init__(self):
        super().__init__()
        self.reproductor = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.reproductor.setAudioOutput(self.audio)
        self.audio.setVolume(0.7)

        self.pantalla_video = VideoPantalla()
        self.pantalla_video.alternar_completa.connect(self.alternar_pantalla_completa)
        self.reproductor.setVideoOutput(self.pantalla_video)
        self.imagen = ImagenEscalada()
        self.vacio = QLabel("Elegí un archivo de la lista", alignment=Qt.AlignCenter)
        self.vacio.setObjectName("vacio")

        self.pila = QStackedWidget()
        for w in (self.vacio, self.imagen, self.pantalla_video):
            self.pila.addWidget(w)

        # Controles de reproducción
        estilo = self.style()
        self.btn_play = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaPlay), toolTip="Reproducir / pausar (Espacio)")
        self.btn_stop = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaStop), toolTip="Detener")
        self.btn_completa = QPushButton("⛶", toolTip="Pantalla completa (doble clic en el video)")
        self.barra = QSlider(Qt.Horizontal)
        self.lbl_tiempo = QLabel("0:00 / 0:00")
        self.btn_mute = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaVolume), toolTip="Silenciar")
        self.volumen = QSlider(Qt.Horizontal, maximum=100, value=70)
        self.volumen.setFixedWidth(90)

        self.controles = QWidget()
        fila = QHBoxLayout(self.controles)
        fila.setContentsMargins(0, 4, 0, 0)
        for w in (self.btn_play, self.btn_stop):
            fila.addWidget(w)
        fila.addWidget(self.barra, 1)
        for w in (self.lbl_tiempo, self.btn_mute, self.volumen, self.btn_completa):
            fila.addWidget(w)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.pila, 1)
        capa.addWidget(self.controles)
        self.controles.hide()

        self.btn_play.clicked.connect(self.alternar_play)
        self.btn_stop.clicked.connect(self.reproductor.stop)
        self.btn_completa.clicked.connect(self.alternar_pantalla_completa)
        self.btn_mute.clicked.connect(self._alternar_mute)
        self.volumen.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.barra.sliderMoved.connect(self.reproductor.setPosition)
        self.reproductor.positionChanged.connect(self._posicion)
        self.reproductor.durationChanged.connect(self._duracion)
        self.reproductor.playbackStateChanged.connect(self._estado)
        self.reproductor.errorOccurred.connect(lambda _e, msg: self.lbl_tiempo.setText(f"Error: {msg}"))

    def mostrar(self, ruta: str | None, tipo: str | None):
        self.reproductor.stop()
        self.reproductor.setSource(QUrl())
        if ruta is None:
            self.pila.setCurrentWidget(self.vacio)
            self.controles.hide()
        elif not Path(ruta).exists():
            self.vacio.setText("El archivo ya no está en esa ubicación")
            self.pila.setCurrentWidget(self.vacio)
            self.controles.hide()
        elif tipo == "imagen":
            self.imagen.mostrar(ruta)
            self.pila.setCurrentWidget(self.imagen)
            self.controles.hide()
        else:
            self.pila.setCurrentWidget(self.pantalla_video)
            self.controles.show()
            self.reproductor.setSource(QUrl.fromLocalFile(ruta))
            self.reproductor.play()

    def alternar_play(self):
        if self.pila.currentWidget() is not self.pantalla_video:
            return
        if self.reproductor.playbackState() == QMediaPlayer.PlayingState:
            self.reproductor.pause()
        else:
            self.reproductor.play()

    def adelantar(self, ms: int):
        if self.pila.currentWidget() is self.pantalla_video:
            self.reproductor.setPosition(max(0, self.reproductor.position() + ms))

    def alternar_pantalla_completa(self):
        v = self.pantalla_video
        v.setFullScreen(not v.isFullScreen())
        if v.isFullScreen():
            v.setFocus()

    def _alternar_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        icono = QStyle.SP_MediaVolumeMuted if self.audio.isMuted() else QStyle.SP_MediaVolume
        self.btn_mute.setIcon(self.style().standardIcon(icono))

    def _posicion(self, pos: int):
        if not self.barra.isSliderDown():
            self.barra.setValue(pos)
        self.lbl_tiempo.setText(f"{formato_tiempo(pos)} / {formato_tiempo(self.reproductor.duration())}")

    def _duracion(self, dur: int):
        self.barra.setRange(0, dur)

    def _estado(self, estado):
        icono = QStyle.SP_MediaPause if estado == QMediaPlayer.PlayingState else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icono))
