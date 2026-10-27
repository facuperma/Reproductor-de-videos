"""Panel que muestra una imagen o reproduce un video con sus controles y subtítulos."""
import math
from pathlib import Path

from PySide6.QtCore import QLocale, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QSizePolicy, QSlider, QStackedWidget, QStyle, QToolButton, QVBoxLayout, QWidget,
)

from .subtitulos import Subtitulos, buscar_junto_a, descripcion, subtitulos_junto_a

TAMANOS_SUB = [("Chico", 0.75), ("Normal", 1.0), ("Grande", 1.3), ("Muy grande", 1.6)]


def atajos_reproductor(ventana: QWidget, visor: "Visor", alternar_completa):
    """Atajos de teclado del reproductor, propios de cada ventana."""
    for tecla, accion in (
        ("Space", visor.alternar_play),
        ("Right", lambda: visor.adelantar(5000)),
        ("Left", lambda: visor.adelantar(-5000)),
        ("Shift+Right", lambda: visor.adelantar(15000)),
        ("Shift+Left", lambda: visor.adelantar(-15000)),
        ("F", alternar_completa),
        ("Escape", lambda: ventana.isFullScreen() and alternar_completa()),
        # Igual que VLC: G adelanta los subtítulos, H los atrasa (50 ms)
        ("G", lambda: visor.ajustar_retraso(-50)),
        ("H", lambda: visor.ajustar_retraso(50)),
        ("N", visor.siguiente_capitulo),
    ):
        QShortcut(QKeySequence(tecla), ventana).activated.connect(accion)


def formato_tiempo(ms: int) -> str:
    s = ms // 1000
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def _envolver(texto: str, fm: QFontMetrics, ancho: float) -> list[str]:
    lineas = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split():
            prueba = f"{actual} {palabra}".strip()
            if actual and fm.horizontalAdvance(prueba) > ancho:
                lineas.append(actual)
                actual = palabra
            else:
                actual = prueba
        lineas.append(actual)
    return lineas


class PantallaVideo(QWidget):
    """Dibuja los cuadros del video, los subtítulos con contorno y avisos en pantalla."""
    doble_clic = Signal()
    mouse_movido = Signal()

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._frame = None
        self._texto = ""
        self._osd = ""
        self.escala_sub = 1.0
        self.panel: QWidget | None = None  # aviso flotante abajo a la derecha
        self._timer_osd = QTimer(self, singleShot=True, interval=1500)
        self._timer_osd.timeout.connect(lambda: self._set_osd(""))

    def set_frame(self, frame):
        self._frame = frame
        self.update()

    def set_texto(self, texto: str):
        if texto != self._texto:
            self._texto = texto
            self.update()

    def mostrar_osd(self, texto: str):
        self._set_osd(texto)
        self._timer_osd.start()

    def _set_osd(self, texto: str):
        self._osd = texto
        self.update()

    def limpiar(self):
        self._frame = None
        self._texto = ""
        self.update()

    def colocar_panel(self):
        if self.panel is not None:
            self.panel.adjustSize()
            self.panel.move(self.width() - self.panel.width() - 24, self.height() - self.panel.height() - 24)

    def resizeEvent(self, e):
        self.colocar_panel()

    def mouseDoubleClickEvent(self, e):
        self.doble_clic.emit()

    def mouseMoveEvent(self, e):
        self.mouse_movido.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        zona = QRectF(self.rect())
        if self._frame is not None and self._frame.isValid():
            img = self._frame.toImage()
            if not img.isNull():
                tam = img.size().scaled(self.size(), Qt.KeepAspectRatio)
                zona = QRectF((self.width() - tam.width()) / 2, (self.height() - tam.height()) / 2,
                              tam.width(), tam.height())
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.drawImage(zona, img)
        p.setRenderHint(QPainter.Antialiasing)
        if self._texto:
            self._dibujar_subtitulo(p, zona)
        if self._osd:
            self._dibujar_osd(p)

    def _dibujar_subtitulo(self, p: QPainter, zona: QRectF):
        fuente = QFont(self.font())
        fuente.setPixelSize(max(14, int(zona.height() * 0.055 * self.escala_sub)))
        fuente.setWeight(QFont.DemiBold)
        fm = QFontMetrics(fuente)
        lineas = _envolver(self._texto, fm, zona.width() * 0.9)
        contorno = QPen(QColor(0, 0, 0, 230), max(2.0, fuente.pixelSize() / 7),
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        y = zona.bottom() - zona.height() * 0.06 - fm.descent()
        for linea in reversed(lineas):
            camino = QPainterPath()
            x = zona.center().x() - fm.horizontalAdvance(linea) / 2
            camino.addText(x, y, fuente, linea)
            p.strokePath(camino, contorno)
            p.fillPath(camino, QColor("white"))
            y -= fm.lineSpacing()

    def _dibujar_osd(self, p: QPainter):
        fuente = QFont(self.font())
        fuente.setPixelSize(max(13, self.height() // 30))
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        caja = QRectF(0, 0, fm.horizontalAdvance(self._osd) + 24, fm.height() + 14)
        caja.moveTopRight(QPointF(self.width() - 16, 16))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(caja, 6, 6)
        p.setPen(QColor("white"))
        p.drawText(caja, Qt.AlignCenter, self._osd)


class ImagenEscalada(QLabel):
    """Etiqueta que reescala la imagen al tamaño disponible."""
    doble_clic = Signal()

    def __init__(self):
        super().__init__(alignment=Qt.AlignCenter)
        self._pixmap = QPixmap()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def mostrar(self, ruta: str):
        self._pixmap = QPixmap(ruta)
        if self._pixmap.isNull():
            self.setText("No se pudo abrir la imagen")
        self._reescalar()

    def mouseDoubleClickEvent(self, e):
        self.doble_clic.emit()

    def resizeEvent(self, e):
        self._reescalar()

    def _reescalar(self):
        if not self._pixmap.isNull():
            self.setPixmap(self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class Visor(QWidget):
    pedir_pantalla_completa = Signal()
    # (ruta del video, ruta del subtítulo o None, retraso en ms)
    subtitulos_cambiados = Signal(str, object, int)
    # Ruta del capítulo que hay que reproducir a continuación
    reproducir_siguiente = Signal(str)
    # Pide buscar subtítulos en internet para este video (lo resuelve quien usa el visor)
    buscar_subtitulos_online = Signal(str)

    # El aviso del siguiente capítulo aparece cuando falta esto para el final
    AVISO_SIGUIENTE_MS = 10_000

    def __init__(self):
        super().__init__()
        # Función (ruta del video) -> ruta del siguiente capítulo o None; la asigna quien usa el visor
        self.buscar_siguiente = None
        self._ruta_siguiente: str | None = None
        self._siguiente_cancelado = False
        self.ruta_video: str | None = None
        self._posicion_pendiente = 0
        self.subs: Subtitulos | None = None
        self.ruta_sub: str | None = None
        self.retraso_ms = 0
        self._es_video = False
        self._modo_completo = False

        self.reproductor = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.reproductor.setAudioOutput(self.audio)
        self.audio.setVolume(0.7)
        self.sink = QVideoSink(self)
        self.reproductor.setVideoSink(self.sink)

        self.pantalla = PantallaVideo()
        self.imagen = ImagenEscalada()
        self.vacio = QLabel("Elegí un archivo de la lista", alignment=Qt.AlignCenter)
        self.vacio.setObjectName("vacio")
        self.pila = QStackedWidget()
        for w in (self.vacio, self.imagen, self.pantalla):
            self.pila.addWidget(w)

        # Controles de reproducción
        estilo = self.style()
        self.btn_play = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaPlay), toolTip="Reproducir / pausar (Espacio)")
        self.btn_stop = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaStop), toolTip="Detener")
        self.btn_siguiente = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaSkipForward),
                                         toolTip="Siguiente capítulo de la categoría (N)")
        self.btn_atras15 = QPushButton("↺ 15", toolTip="Retroceder 15 segundos (Shift+←)")
        self.btn_adelante15 = QPushButton("15 ↻", toolTip="Adelantar 15 segundos (Shift+→)")
        self.barra = QSlider(Qt.Horizontal)
        self.lbl_tiempo = QLabel("0:00 / 0:00")
        self.btn_mute = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaVolume), toolTip="Silenciar")
        self.volumen = QSlider(Qt.Horizontal, maximum=100, value=70)
        self.volumen.setFixedWidth(90)
        self.btn_subs = QToolButton(text="CC", toolTip="Subtítulos", popupMode=QToolButton.InstantPopup)
        self.menu_subs = QMenu(self)
        self.menu_subs.aboutToShow.connect(self._armar_menu_subs)
        self.btn_subs.setMenu(self.menu_subs)
        self.btn_completa = QPushButton("⛶", toolTip="Pantalla completa (F o doble clic)")

        self.controles = QWidget()
        self._fila_controles = fila = QHBoxLayout(self.controles)
        fila.setContentsMargins(4, 4, 4, 0)
        for w in (self.btn_atras15, self.btn_play, self.btn_adelante15, self.btn_stop, self.btn_siguiente):
            fila.addWidget(w)
        fila.addWidget(self.barra, 1)
        for w in (self.lbl_tiempo, self.btn_mute, self.volumen, self.btn_subs, self.btn_completa):
            fila.addWidget(w)

        # Barra de sincronización, visible con un archivo de subtítulos cargado
        self.lbl_sub = QLabel()
        self.spin_retraso = QDoubleSpinBox(decimals=2, singleStep=0.05, minimum=-600, maximum=600, suffix=" s")
        self.spin_retraso.setToolTip("Positivo: los subtítulos aparecen más tarde.\nNegativo: aparecen antes.")
        self.spin_retraso.valueChanged.connect(self._retraso_cambiado)
        btn_reiniciar = QPushButton("Reiniciar", toolTip="Volver a 0")
        btn_reiniciar.clicked.connect(lambda: self.spin_retraso.setValue(0))
        self.barra_subs = QWidget()
        fila_subs = QHBoxLayout(self.barra_subs)
        fila_subs.setContentsMargins(4, 2, 4, 0)
        fila_subs.addWidget(self.lbl_sub, 1)
        fila_subs.addWidget(QLabel("Retraso de subtítulos:"))
        fila_subs.addWidget(self.spin_retraso)
        fila_subs.addWidget(btn_reiniciar)
        fila_subs.addWidget(QLabel("(G / H)", objectName="pista"))

        # Aviso de siguiente capítulo, sobre el video
        self.panel_sig = QFrame(self.pantalla, objectName="panelSiguiente")
        self.lbl_sig_cuenta = QLabel(objectName="titulo")
        self.lbl_sig_nombre = QLabel()
        btn_ahora = QPushButton("▶ Reproducir ahora")
        btn_cancelar = QPushButton("Cancelar")
        btn_ahora.clicked.connect(self._reproducir_siguiente)
        btn_cancelar.clicked.connect(self._cancelar_siguiente)
        capa_sig = QVBoxLayout(self.panel_sig)
        capa_sig.setContentsMargins(16, 12, 16, 12)
        capa_sig.addWidget(self.lbl_sig_cuenta)
        capa_sig.addWidget(self.lbl_sig_nombre)
        fila_sig = QHBoxLayout()
        fila_sig.addWidget(btn_ahora)
        fila_sig.addWidget(btn_cancelar)
        capa_sig.addLayout(fila_sig)
        self.panel_sig.hide()
        self.pantalla.panel = self.panel_sig

        for b in (self.btn_play, self.btn_stop, self.btn_siguiente, self.btn_atras15,
                  self.btn_adelante15, self.btn_mute, self.btn_subs,
                  self.btn_completa, btn_reiniciar, self.barra, self.volumen, btn_ahora, btn_cancelar):
            b.setFocusPolicy(Qt.NoFocus)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        capa.addWidget(self.pila, 1)
        capa.addWidget(self.controles)
        capa.addWidget(self.barra_subs)

        # En pantalla completa los controles se ocultan tras unos segundos sin mover el mouse
        self._timer_ocultar = QTimer(self, singleShot=True, interval=2500)
        self._timer_ocultar.timeout.connect(self._ocultar_controles)

        self.btn_play.clicked.connect(self.alternar_play)
        self.btn_stop.clicked.connect(self.reproductor.stop)
        self.btn_siguiente.clicked.connect(self.siguiente_capitulo)
        self.btn_atras15.clicked.connect(lambda: self.adelantar(-15000))
        self.btn_adelante15.clicked.connect(lambda: self.adelantar(15000))
        self.btn_completa.clicked.connect(self.pedir_pantalla_completa)
        self.pantalla.doble_clic.connect(self.pedir_pantalla_completa)
        self.imagen.doble_clic.connect(self.pedir_pantalla_completa)
        self.pantalla.mouse_movido.connect(self._actividad)
        self.btn_mute.clicked.connect(self._alternar_mute)
        self.volumen.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.barra.sliderMoved.connect(self.reproductor.setPosition)
        self.sink.videoFrameChanged.connect(self._nuevo_frame)
        self.sink.subtitleTextChanged.connect(self._texto_pista_interna)
        self.reproductor.positionChanged.connect(self._posicion)
        self.reproductor.durationChanged.connect(self._duracion)
        self.reproductor.playbackStateChanged.connect(self._estado)
        self.reproductor.mediaStatusChanged.connect(self._estado_medio)
        self.reproductor.errorOccurred.connect(lambda _e, msg: self.lbl_tiempo.setText(f"Error: {msg}"))
        self._actualizar_controles()

    # --- Mostrar archivos ---------------------------------------------------

    def agregar_control(self, widget: QWidget):
        """Suma un botón a la barra de controles, antes del de pantalla completa."""
        widget.setFocusPolicy(Qt.NoFocus)
        self._fila_controles.insertWidget(self._fila_controles.indexOf(self.btn_completa), widget)

    def mostrar(self, ruta: str | None, tipo: str | None, config_sub: tuple | None = None,
                posicion_ms: int = 0, aviso_vacio: str = "Elegí un archivo de la lista"):
        """config_sub: (ruta del subtítulo o None, retraso ms) guardado para este video,
        o None si nunca se configuró (entonces se buscan subtítulos junto al video).
        posicion_ms: punto desde el que arranca el video."""
        self._reiniciar_siguiente()
        self.reproductor.stop()
        self.reproductor.setSource(QUrl())
        self.pantalla.limpiar()
        self._descartar_subtitulos()
        self.ruta_video = None
        self._es_video = False
        self._posicion_pendiente = posicion_ms
        if ruta is None:
            self.vacio.setText(aviso_vacio)
            self.pila.setCurrentWidget(self.vacio)
        elif not Path(ruta).exists():
            self.vacio.setText("El archivo ya no está en esa ubicación")
            self.pila.setCurrentWidget(self.vacio)
        elif tipo == "imagen":
            self.imagen.mostrar(ruta)
            self.pila.setCurrentWidget(self.imagen)
        else:
            self.ruta_video = ruta
            self._es_video = True
            self.pila.setCurrentWidget(self.pantalla)
            if config_sub is None:
                if auto := buscar_junto_a(ruta):
                    self.cargar_subtitulos(auto, 0, guardar=False)
            elif config_sub[0]:
                self.cargar_subtitulos(config_sub[0], config_sub[1], guardar=False)
            self.reproductor.setSource(QUrl.fromLocalFile(ruta))
            self.reproductor.play()
        self._actualizar_controles()

    def alternar_play(self):
        if not self._es_video:
            return
        if self.reproductor.playbackState() == QMediaPlayer.PlayingState:
            self.reproductor.pause()
        else:
            self.reproductor.play()

    def adelantar(self, ms: int):
        if self._es_video:
            destino = self.reproductor.position() + ms
            self.reproductor.setPosition(max(0, min(destino, self.reproductor.duration())))

    # --- Pantalla completa ----------------------------------------------------

    def set_modo_completo(self, activo: bool):
        self._modo_completo = activo
        if activo:
            self._actividad()
        else:
            self._timer_ocultar.stop()
            self.pantalla.unsetCursor()
            self._actualizar_controles()

    def _actividad(self):
        if self._modo_completo:
            self.pantalla.unsetCursor()
            self._actualizar_controles()
            self._timer_ocultar.start()

    def _ocultar_controles(self):
        en_uso = self.controles.underMouse() or self.barra_subs.underMouse() or self.menu_subs.isVisible()
        if not self._modo_completo:
            return
        if en_uso or self.reproductor.playbackState() != QMediaPlayer.PlayingState:
            self._timer_ocultar.start()
            return
        self.controles.hide()
        self.barra_subs.hide()
        self.pantalla.setCursor(Qt.BlankCursor)

    def _actualizar_controles(self):
        self.controles.setVisible(self._es_video)
        self.barra_subs.setVisible(self._es_video and self.subs is not None)

    # --- Subtítulos -----------------------------------------------------------

    def cargar_subtitulos(self, ruta_sub: str, retraso_ms: int = 0, guardar: bool = True) -> bool:
        if not self.ruta_video:
            return False
        try:
            subs = Subtitulos(ruta_sub)
        except OSError as e:
            if guardar:
                QMessageBox.warning(self, "Subtítulos", f"No se pudo leer el archivo:\n{e}")
            return False
        self.reproductor.setActiveSubtitleTrack(-1)
        self.subs, self.ruta_sub = subs, ruta_sub
        self.lbl_sub.setText(f"Subtítulos: {Path(ruta_sub).name}")
        self.lbl_sub.setToolTip(ruta_sub)
        self._poner_retraso(retraso_ms)
        self._actualizar_controles()
        self._actualizar_subtitulo()
        if guardar:
            self._guardar_subtitulos()
            self.pantalla.mostrar_osd(f"Subtítulos: {Path(ruta_sub).name}")
        return True

    def quitar_subtitulos(self):
        self._descartar_subtitulos()
        self.reproductor.setActiveSubtitleTrack(-1)
        self._actualizar_controles()
        if self.ruta_video:
            self._guardar_subtitulos()
            self.pantalla.mostrar_osd("Subtítulos desactivados")

    def ajustar_retraso(self, delta_ms: int):
        if self.subs is not None:
            self.spin_retraso.setValue(self.spin_retraso.value() + delta_ms / 1000)
        elif self._es_video:
            self.pantalla.mostrar_osd("No hay un archivo de subtítulos cargado")

    def _descartar_subtitulos(self):
        self.subs = self.ruta_sub = None
        self._poner_retraso(0)
        self.pantalla.set_texto("")

    def _poner_retraso(self, ms: int):
        self.retraso_ms = ms
        self.spin_retraso.blockSignals(True)
        self.spin_retraso.setValue(ms / 1000)
        self.spin_retraso.blockSignals(False)

    def _retraso_cambiado(self, segundos: float):
        self.retraso_ms = round(segundos * 1000)
        self._actualizar_subtitulo()
        self._guardar_subtitulos()
        self.pantalla.mostrar_osd(f"Retraso de subtítulos: {self.retraso_ms:+d} ms")

    def _guardar_subtitulos(self):
        self.subtitulos_cambiados.emit(self.ruta_video, self.ruta_sub, self.retraso_ms)

    def _actualizar_subtitulo(self):
        if self.subs is not None:
            self.pantalla.set_texto(self.subs.texto_en(self.reproductor.position() - self.retraso_ms))

    def _texto_pista_interna(self, texto: str):
        if self.subs is None and self.reproductor.activeSubtitleTrack() >= 0:
            self.pantalla.set_texto(texto)

    def _elegir_archivo_subs(self):
        inicio = str(Path(self.ruta_video).parent) if self.ruta_video else ""
        ruta, _ = QFileDialog.getOpenFileName(self, "Cargar subtítulos", inicio, "Subtítulos (*.srt *.vtt)")
        if ruta:
            self.cargar_subtitulos(ruta)

    def _usar_pista_interna(self, indice: int):
        self._descartar_subtitulos()
        self._actualizar_controles()
        self.reproductor.setActiveSubtitleTrack(indice)

    def _nombre_pista(self, datos: QMediaMetaData, indice: int) -> str:
        partes = []
        idioma = datos.value(QMediaMetaData.Language)
        if isinstance(idioma, QLocale.Language) and idioma != QLocale.AnyLanguage:
            partes.append(QLocale.languageToString(idioma))
        if titulo := datos.stringValue(QMediaMetaData.Title):
            partes.append(titulo)
        return f"Pista {indice + 1}" + (f": {' – '.join(partes)}" if partes else "")

    def _armar_menu_subs(self):
        m = self.menu_subs
        m.clear()
        m.addAction("Cargar archivo de subtítulos…", self._elegir_archivo_subs).setEnabled(self._es_video)
        m.addAction("🌐 Buscar en internet (OpenSubtitles)",
                    lambda: self.buscar_subtitulos_online.emit(self.ruta_video)).setEnabled(self._es_video)
        junto = subtitulos_junto_a(self.ruta_video) if self.ruta_video else []
        if self.ruta_sub and self.ruta_sub not in junto:
            junto.append(self.ruta_sub)
        if junto:
            m.addSection("Archivos de subtítulos")
        for ruta in junto:
            accion = m.addAction(descripcion(ruta, self.ruta_video), lambda r=ruta: self.cargar_subtitulos(r))
            accion.setCheckable(True)
            accion.setChecked(ruta == self.ruta_sub)
        pistas = self.reproductor.subtitleTracks()
        activa = self.reproductor.activeSubtitleTrack()
        if pistas:
            m.addSection("Pistas incluidas en el video")
        for i, datos in enumerate(pistas):
            accion = m.addAction(self._nombre_pista(datos, i), lambda i=i: self._usar_pista_interna(i))
            accion.setCheckable(True)
            accion.setChecked(i == activa and self.subs is None)
        m.addSeparator()
        m.addAction("Desactivar subtítulos", self.quitar_subtitulos).setEnabled(
            self.subs is not None or activa >= 0)
        tamanos = m.addMenu("Tamaño del texto")
        for nombre, escala in TAMANOS_SUB:
            accion = tamanos.addAction(nombre, lambda e=escala: self._cambiar_tamano(e))
            accion.setCheckable(True)
            accion.setChecked(self.pantalla.escala_sub == escala)

    def _cambiar_tamano(self, escala: float):
        self.pantalla.escala_sub = escala
        self.pantalla.update()

    # --- Reproducción ---------------------------------------------------------

    def _nuevo_frame(self, frame):
        self._actualizar_subtitulo()
        self.pantalla.set_frame(frame)

    def _alternar_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        icono = QStyle.SP_MediaVolumeMuted if self.audio.isMuted() else QStyle.SP_MediaVolume
        self.btn_mute.setIcon(self.style().standardIcon(icono))

    def _posicion(self, pos: int):
        if not self.barra.isSliderDown():
            self.barra.setValue(pos)
        self.lbl_tiempo.setText(f"{formato_tiempo(pos)} / {formato_tiempo(self.reproductor.duration())}")
        self._actualizar_subtitulo()
        self._revisar_siguiente(pos)

    def _estado_medio(self, estado):
        # La posición inicial solo se puede aplicar cuando el video terminó de cargar
        if self._posicion_pendiente and estado in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self.reproductor.setPosition(self._posicion_pendiente)
            self._posicion_pendiente = 0
        elif estado == QMediaPlayer.EndOfMedia:
            self._fin_del_video()

    # --- Siguiente capítulo ---------------------------------------------------

    def _buscar_siguiente(self) -> str | None:
        if self.buscar_siguiente and self.ruta_video:
            return self.buscar_siguiente(self.ruta_video)
        return None

    def siguiente_capitulo(self):
        if not self._es_video:
            return
        if siguiente := self._buscar_siguiente():
            self.reproducir_siguiente.emit(siguiente)
        else:
            self.pantalla.mostrar_osd("No hay un capítulo siguiente en esta categoría")

    def _revisar_siguiente(self, pos: int):
        """Muestra el aviso en los últimos segundos; la cuenta sigue al video,
        así que se frena con la pausa y desaparece si se retrocede."""
        dur = self.reproductor.duration()
        if not self._es_video or dur <= 0 or self._siguiente_cancelado:
            return
        restante = dur - pos
        if restante > self.AVISO_SIGUIENTE_MS:
            self.panel_sig.hide()
            return
        if self._ruta_siguiente is None:
            self._ruta_siguiente = self._buscar_siguiente()
            if self._ruta_siguiente is None:
                self._siguiente_cancelado = True  # no hay siguiente: no volver a buscar
                return
            self.lbl_sig_nombre.setText(Path(self._ruta_siguiente).stem)
        self.lbl_sig_cuenta.setText(f"Siguiente capítulo en {max(1, math.ceil(restante / 1000))} s")
        if not self.panel_sig.isVisible():
            self.panel_sig.show()
            self.pantalla.colocar_panel()

    def _fin_del_video(self):
        if not self._siguiente_cancelado:
            self._reproducir_siguiente()

    def _reproducir_siguiente(self):
        if ruta := self._ruta_siguiente or self._buscar_siguiente():
            self.reproducir_siguiente.emit(ruta)

    def _cancelar_siguiente(self):
        self._siguiente_cancelado = True
        self.panel_sig.hide()

    def _reiniciar_siguiente(self):
        self._siguiente_cancelado = False
        self._ruta_siguiente = None
        self.panel_sig.hide()

    def _duracion(self, dur: int):
        self.barra.setRange(0, dur)

    def _estado(self, estado):
        icono = QStyle.SP_MediaPause if estado == QMediaPlayer.PlayingState else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icono))
        if self._modo_completo:
            self._actividad()
