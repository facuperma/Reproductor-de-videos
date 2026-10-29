"""Panel que muestra una imagen o reproduce un video con sus controles y subtítulos."""
import math
import re
from pathlib import Path

from PySide6.QtCore import QLocale, QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaMetaData, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QSizePolicy, QSlider, QStackedWidget, QStyle, QToolButton, QVBoxLayout, QWidget,
)

from .db import RETOMAR_DESDE_MS
from .subtitulos import Subtitulos, buscar_junto_a, descripcion, subtitulos_junto_a

TAMANOS_SUB = [("Chico", 0.75), ("Normal", 1.0), ("Grande", 1.3), ("Muy grande", 1.6)]

# Cómo arranca un video al mostrarlo
REPRODUCIR = "reproducir"
VISTA_PREVIA = "vista_previa"   # un cuadro de muestra, hasta que se aprieta reproducir
SI_ES_LARGO = "si_es_largo"     # vista previa, salvo que dure más que DURACION_LARGA_MS
DURACION_LARGA_MS = 3_600_000
# Volumen con el que arranca TVon (antes 70 %: ahora 20 puntos menos)
VOLUMEN_INICIAL = 50

LOGO = Path(__file__).parent / "icono.png"

# Líneas que los sitios agregan al final de los subtítulos: no son diálogo
PUBLICIDAD_SUB = re.compile(
    r"(?i)opensubtitles|subdivx|addic7ed|www\.|\.com\b|\.org\b|\.net\b|subt[ií]tul|subtitle|"
    r"traduc|sincroniza|synced|corrected|ripped|advertise|support us")


def texto_sincronia(ms: int) -> str:
    """-1500 -> «1,5 s antes», 300 -> «0,3 s después», 0 -> «sincronizados»."""
    if not ms:
        return "sincronizados"
    segundos = f"{abs(ms) / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{segundos} s {'después' if ms > 0 else 'antes'}"


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
        # Como en VLC: G muestra los subtítulos antes, H después
        ("G", lambda: visor.ajustar_retraso(-100)),
        ("H", lambda: visor.ajustar_retraso(100)),
        ("N", visor.siguiente_capitulo),
        ("Home", lambda: visor.ir_a(0)),
    ):
        QShortcut(QKeySequence(tecla), ventana).activated.connect(accion)


def formato_tiempo(ms: int) -> str:
    s = ms // 1000
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def texto_progreso(progreso: tuple[int, int, bool] | None) -> str:
    """Columna «Visto»: ✓, dónde quedó o vacío."""
    if not progreso:
        return ""
    posicion, duracion, visto = progreso
    if visto:
        return "✓"
    if posicion >= RETOMAR_DESDE_MS and duracion:
        return f"{posicion * 100 // duracion} % · {formato_tiempo(posicion)}"
    return ""


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
    clic = Signal()
    mouse_movido = Signal()

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        # Tocar el video le saca el foco al buscador: así Espacio pausa en vez de escribir
        self.setFocusPolicy(Qt.ClickFocus)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.portada = False  # vista previa: dibuja el botón de reproducir encima
        self._frame = None
        self._texto = ""
        self._osd = ""
        self.escala_sub = 1.0
        self.panel: QWidget | None = None  # aviso flotante abajo a la derecha
        self._timer_osd = QTimer(self, singleShot=True, interval=1500)
        self._timer_osd.timeout.connect(lambda: self._set_osd(""))
        # El clic simple espera por si llega el segundo de un doble clic (pantalla completa),
        # así el doble clic no pausa y reanuda de paso
        self._timer_clic = QTimer(self, singleShot=True, interval=QApplication.doubleClickInterval())
        self._timer_clic.timeout.connect(self.clic)

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

    def cuadro(self):
        """El cuadro que se está mostrando, como QImage (o None)."""
        if self._frame is None or not self._frame.isValid():
            return None
        img = self._frame.toImage()
        return None if img.isNull() else img

    def colocar_panel(self):
        if self.panel is not None:
            self.panel.adjustSize()
            self.panel.move(self.width() - self.panel.width() - 24, self.height() - self.panel.height() - 24)

    def resizeEvent(self, e):
        self.colocar_panel()

    def mouseDoubleClickEvent(self, e):
        self._timer_clic.stop()
        self.doble_clic.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._timer_clic.start()

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
        if self.portada:
            self._dibujar_portada(p)
        elif self._texto:
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

    def _dibujar_portada(self, p: QPainter):
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))
        radio = max(28, min(self.width(), self.height()) // 9)
        centro = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(61, 123, 253, 220))
        p.drawEllipse(centro, radio, radio)
        r = radio * 0.45
        p.setBrush(QColor("white"))
        p.drawPolygon([QPointF(centro.x() - r * 0.6, centro.y() - r), QPointF(centro.x() - r * 0.6, centro.y() + r),
                       QPointF(centro.x() + r, centro.y())])
        fuente = QFont(self.font())
        fuente.setPixelSize(max(12, radio // 3))
        p.setFont(fuente)
        p.setPen(QColor("white"))
        p.drawText(QRectF(0, centro.y() + radio + 8, self.width(), radio), Qt.AlignHCenter | Qt.AlignTop,
                   "Clic o Espacio para reproducir")

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


class Bienvenida(QWidget):
    """Pantalla sin archivo: el logo de TVon, tenue, sobre el aviso."""

    def __init__(self, texto: str):
        super().__init__(objectName="vacio")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.logo = QLabel(alignment=Qt.AlignCenter)
        self.logo.setPixmap(self._logo_tenue(150, 0.35))
        self.texto = QLabel(texto, alignment=Qt.AlignCenter, wordWrap=True)
        capa = QVBoxLayout(self)
        capa.addStretch()
        capa.addWidget(self.logo)
        capa.addSpacing(12)
        capa.addWidget(self.texto)
        capa.addStretch()

    @staticmethod
    def _logo_tenue(tamano: int, opacidad: float) -> QPixmap:
        escala = QApplication.instance().devicePixelRatio()
        original = QPixmap(str(LOGO)).scaled(round(tamano * escala), round(tamano * escala),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
        tenue = QPixmap(original.size())
        tenue.fill(Qt.transparent)
        p = QPainter(tenue)
        p.setOpacity(opacidad)
        p.drawPixmap(0, 0, original)
        p.end()
        tenue.setDevicePixelRatio(escala)
        return tenue

    def setText(self, texto: str):
        self.texto.setText(texto)


class Visor(QWidget):
    pedir_pantalla_completa = Signal()
    # (ruta del video, ruta del subtítulo o None, retraso en ms)
    subtitulos_cambiados = Signal(str, object, int)
    # Ruta del capítulo que hay que reproducir a continuación
    reproducir_siguiente = Signal(str)
    # Pide buscar subtítulos en internet para este video (lo resuelve quien usa el visor)
    buscar_subtitulos_online = Signal(str)
    buscar_subtitulos_subdivx = Signal(str)
    # Terminó el video con «Apagar al terminar» marcado
    pedir_apagado = Signal()
    # (ruta del video, posición ms, duración ms): hasta dónde se vio, para retomarlo
    progreso = Signal(str, int, int)
    # Tamaño en píxeles del video que se acaba de abrir (con el primer cuadro)
    tamano_video = Signal(QSize)

    # El aviso del siguiente capítulo aparece cuando falta esto para el final
    AVISO_SIGUIENTE_MS = 5_000
    # Con subtítulos, aparece antes: cuando termina el último diálogo (arrancan los créditos),
    # si después quedan al menos estos milisegundos de video
    CREDITOS_MINIMO_MS = 20_000

    def __init__(self):
        super().__init__()
        # Función (ruta del video) -> ruta del siguiente capítulo o None; la asigna quien usa el visor
        self.buscar_siguiente = None
        self._ruta_siguiente: str | None = None
        self._siguiente_cancelado = False
        # Videos pedidos a mano para después del actual: van antes que el siguiente capítulo
        self.cola: list[str] = []
        self.apagar_al_terminar = False
        self.ruta_video: str | None = None
        self._posicion_pendiente = 0
        self._ultimo_guardado = 0
        self._modo = REPRODUCIR
        self._vista_previa = False
        self._inicio_ms = 0  # desde dónde arranca al salir de la vista previa
        self.subs: Subtitulos | None = None
        self.ruta_sub: str | None = None
        self.retraso_ms = 0
        self._fin_dialogo: int | None = None  # fin del último subtítulo que es diálogo
        self._tamano_avisado = False
        self._es_video = False
        self._modo_completo = False

        self.reproductor = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.reproductor.setAudioOutput(self.audio)
        self.audio.setVolume(VOLUMEN_INICIAL / 100)
        self.sink = QVideoSink(self)
        self.reproductor.setVideoSink(self.sink)
        # Sin esto, al cambiar la salida de Windows (auriculares, parlantes, HDMI)
        # el sonido sigue yendo a la anterior hasta reiniciar TVon
        self._dispositivos = QMediaDevices(self)
        self._dispositivos.audioOutputsChanged.connect(self._salida_audio_cambiada)

        self.pantalla = PantallaVideo()
        self.imagen = ImagenEscalada()
        self.vacio = Bienvenida("Elegí un archivo de la lista")
        self.pila = QStackedWidget()
        for w in (self.vacio, self.imagen, self.pantalla):
            self.pila.addWidget(w)

        # Controles de reproducción
        estilo = self.style()
        self.btn_play = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaPlay), toolTip="Reproducir / pausar (Espacio o clic en el video)")
        self.btn_stop = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaStop), toolTip="Detener")
        self.btn_siguiente = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaSkipForward),
                                         toolTip="Siguiente de la cola o capítulo de la categoría (N)")
        self.btn_atras15 = QPushButton("↺ 15", toolTip="Retroceder 15 segundos (Shift+←)")
        self.btn_adelante15 = QPushButton("15 ↻", toolTip="Adelantar 15 segundos (Shift+→)")
        self.barra = QSlider(Qt.Horizontal)
        self.lbl_tiempo = QLabel("0:00 / 0:00")
        self.btn_mute = QPushButton(icon=estilo.standardIcon(QStyle.SP_MediaVolume), toolTip="Silenciar")
        self.volumen = QSlider(Qt.Horizontal, maximum=100, value=VOLUMEN_INICIAL)
        self.volumen.setFixedWidth(60)
        self.lbl_volumen = QLabel(f"{VOLUMEN_INICIAL} %", toolTip="Volumen")
        self.lbl_volumen.setMinimumWidth(QFontMetrics(self.lbl_volumen.font()).horizontalAdvance("100 %"))
        self.btn_subs = QToolButton(text="CC", toolTip="Subtítulos", popupMode=QToolButton.InstantPopup)
        self.menu_subs = QMenu(self)
        self.menu_subs.aboutToShow.connect(self._armar_menu_subs)
        self.btn_subs.setMenu(self.menu_subs)
        self.btn_completa = QPushButton("⛶", toolTip="Pantalla completa (F o doble clic)")
        self.btn_cola = QToolButton(toolTip="Videos en cola para después de este",
                                    popupMode=QToolButton.InstantPopup)
        self.menu_cola = QMenu(self)
        self.menu_cola.aboutToShow.connect(self._armar_menu_cola)
        self.btn_cola.setMenu(self.menu_cola)

        # Botones compactos (estilo en tema.py) para que la barra del video quede más larga.
        # Sin ancho mínimo: la ventana se puede achicar todo lo que se quiera
        self.controles = QWidget(objectName="controles")
        self.controles.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._fila_controles = fila = QHBoxLayout(self.controles)
        fila.setContentsMargins(4, 4, 4, 0)
        fila.setSpacing(3)
        for w in (self.btn_atras15, self.btn_play, self.btn_adelante15, self.btn_stop, self.btn_siguiente):
            fila.addWidget(w)
        fila.addWidget(self.barra, 1)
        for w in (self.lbl_tiempo, self.btn_mute, self.volumen, self.lbl_volumen, self.btn_cola, self.btn_subs,
                  self.btn_completa):
            fila.addWidget(w)

        # Barra de sincronización, visible con un archivo de subtítulos cargado.
        # En palabras («1,5 s antes») en vez de un retraso con signo, que confunde.
        self.lbl_sub = QLabel()
        self.lbl_sincronia = QLabel(alignment=Qt.AlignCenter, minimumWidth=120)
        self.lbl_sincronia.setToolTip("Cómo salen los subtítulos respecto del archivo original")
        self.barra_subs = QWidget()
        self.barra_subs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        fila_subs = QHBoxLayout(self.barra_subs)
        fila_subs.setContentsMargins(4, 2, 4, 0)
        fila_subs.setSpacing(4)
        fila_subs.addWidget(self.lbl_sub, 1)
        fila_subs.addWidget(QLabel("Sincronía:"))
        botones = [("◀◀", -500, "Mostrar los subtítulos 0,5 s antes"),
                   ("◀", -100, "Mostrar los subtítulos 0,1 s antes (G)"), (None, 0, ""),
                   ("▶", 100, "Mostrar los subtítulos 0,1 s después (H)"),
                   ("▶▶", 500, "Mostrar los subtítulos 0,5 s después")]
        botones_sinc = []
        for texto, ms, ayuda in botones:
            if texto is None:
                fila_subs.addWidget(self.lbl_sincronia)
                continue
            boton = QPushButton(texto, objectName="chico", toolTip=ayuda)
            boton.clicked.connect(lambda _=False, d=ms: self.ajustar_retraso(d))
            fila_subs.addWidget(boton)
            botones_sinc.append(boton)
        btn_sinc_ahora = QPushButton("🎯 Ahora", objectName="chico", toolTip=(
            "Tocalo justo cuando alguien empieza a hablar:\n"
            "el subtítulo más cercano se acomoda a ese momento"))
        btn_sinc_ahora.clicked.connect(self.sincronizar_ahora)
        btn_cero = QPushButton("↺", objectName="chico", toolTip="Sin ajuste (como viene el archivo)")
        btn_cero.clicked.connect(lambda: self.fijar_retraso(0))
        fila_subs.addWidget(btn_sinc_ahora)
        fila_subs.addWidget(btn_cero)
        botones_sinc += [btn_sinc_ahora, btn_cero]

        # Aviso de siguiente capítulo, sobre el video
        self.panel_sig = QFrame(self.pantalla, objectName="panelSiguiente")
        self.lbl_sig_cuenta = QLabel(objectName="titulo")
        self.lbl_sig_nombre = QLabel()
        btn_ahora = QPushButton("▶ Reproducir ahora")
        btn_cancelar = QPushButton("Cancelar")
        btn_ahora.clicked.connect(self.siguiente_ahora)
        btn_cancelar.clicked.connect(self.cancelar_siguiente)
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
                  self.btn_adelante15, self.btn_mute, self.btn_subs, self.btn_cola,
                  self.btn_completa, *botones_sinc, self.barra, self.volumen, btn_ahora, btn_cancelar):
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
        self.pantalla.clic.connect(self.alternar_play)
        self.imagen.doble_clic.connect(self.pedir_pantalla_completa)
        self.pantalla.mouse_movido.connect(self._actividad)
        self.btn_mute.clicked.connect(self.alternar_mute)
        self.volumen.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.volumen.valueChanged.connect(lambda v: self.lbl_volumen.setText(f"{v} %"))
        self.barra.sliderMoved.connect(self.reproductor.setPosition)
        self.sink.videoFrameChanged.connect(self._nuevo_frame)
        self.sink.subtitleTextChanged.connect(self._texto_pista_interna)
        self.reproductor.positionChanged.connect(self._posicion)
        self.reproductor.durationChanged.connect(self._duracion)
        self.reproductor.playbackStateChanged.connect(self._estado)
        self.reproductor.mediaStatusChanged.connect(self._estado_medio)
        self.reproductor.errorOccurred.connect(lambda _e, msg: self.lbl_tiempo.setText(f"Error: {msg}"))
        self._actualizar_controles()
        self._actualizar_cola()

    # --- Mostrar archivos ---------------------------------------------------

    def agregar_control(self, widget: QWidget):
        """Suma un botón a la barra de controles, antes del de pantalla completa."""
        widget.setFocusPolicy(Qt.NoFocus)
        self._fila_controles.insertWidget(self._fila_controles.indexOf(self.btn_completa), widget)

    def mostrar(self, ruta: str | None, tipo: str | None, config_sub: tuple | None = None,
                posicion_ms: int = 0, aviso_vacio: str = "Elegí un archivo de la lista",
                modo: str = REPRODUCIR):
        """config_sub: (ruta del subtítulo o None, retraso ms) guardado para este video,
        o None si nunca se configuró (entonces se buscan subtítulos junto al video).
        posicion_ms: punto desde el que arranca el video.
        modo: REPRODUCIR, VISTA_PREVIA o SI_ES_LARGO."""
        self.guardar_progreso()
        self._reiniciar_siguiente()
        self.reproductor.stop()
        self.reproductor.setSource(QUrl())
        self.pantalla.limpiar()
        self._descartar_subtitulos()
        self.ruta_video = None
        self._es_video = False
        self._tamano_avisado = False
        self._modo = modo
        self._vista_previa = modo != REPRODUCIR
        self.pantalla.portada = False
        self._inicio_ms = posicion_ms
        self._ultimo_guardado = posicion_ms
        self._posicion_pendiente = 0 if self._vista_previa else posicion_ms
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
            if self._vista_previa:
                # En pausa: al cargar se salta a un punto de muestra y se dibuja ese cuadro, sin sonido
                self.pantalla.portada = True
                self.reproductor.pause()
            else:
                self.reproductor.play()
                self.pantalla.setFocus()
        self._actualizar_controles()

    def empezar(self):
        """Sale de la vista previa y reproduce desde el principio (o la posición pedida)."""
        self._vista_previa = False
        self.pantalla.portada = False
        self.pantalla.update()
        if self.reproductor.mediaStatus() in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia,
                                              QMediaPlayer.BufferedMedia):
            self.reproductor.setPosition(self._inicio_ms)
            self._avisar_retomado(self._inicio_ms)
        else:
            self._posicion_pendiente = self._inicio_ms
        self.reproductor.play()
        self.pantalla.setFocus()

    def _avisar_retomado(self, ms: int):
        if ms:
            self.pantalla.mostrar_osd(f"Sigue desde {formato_tiempo(ms)} · Inicio = desde el principio")

    def guardar_progreso(self):
        """Avisa hasta dónde se vio el video actual (en vista previa todavía no se vio nada)."""
        if self._es_video and self.ruta_video and not self._vista_previa:
            pos, dur = self.reproductor.position(), self.reproductor.duration()
            if pos > 0 and dur > 0:
                self._ultimo_guardado = pos
                self.progreso.emit(self.ruta_video, pos, dur)

    def posicion_actual(self) -> int:
        """Posición para retomar el video (en vista previa, todavía no empezó)."""
        return self._inicio_ms if self._vista_previa else self.reproductor.position()

    @property
    def es_video(self) -> bool:
        return self._es_video

    @property
    def en_vista_previa(self) -> bool:
        return self._vista_previa

    def ir_a(self, ms: int):
        """Salta a ese punto; desde la vista previa, empieza a reproducir ahí."""
        if not self._es_video:
            return
        ms = max(0, min(ms, self.reproductor.duration()))
        if self._vista_previa:
            self._inicio_ms = ms
            self.empezar()
        else:
            self.reproductor.setPosition(ms)

    def alternar_play(self):
        if not self._es_video:
            return
        if self._vista_previa:
            self.empezar()
        elif self.reproductor.playbackState() == QMediaPlayer.PlayingState:
            self.reproductor.pause()
            self.pantalla.mostrar_osd("⏸ Pausa")
        else:
            self.reproductor.play()
            self.pantalla.mostrar_osd("▶ Reproduciendo")

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
        en_uso = (self.controles.underMouse() or self.barra_subs.underMouse()
                  or self.menu_subs.isVisible() or self.menu_cola.isVisible())
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
        self._fin_dialogo = max((b for _a, b, t in subs.cues if not PUBLICIDAD_SUB.search(t)), default=None)
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
        """Negativo: los subtítulos salen antes; positivo: después."""
        if self.subs is not None:
            self.fijar_retraso(self.retraso_ms + delta_ms)
        elif self._es_video:
            self.pantalla.mostrar_osd("No hay un archivo de subtítulos cargado")

    def fijar_retraso(self, ms: int):
        if self.subs is None:
            return
        self._poner_retraso(max(-600_000, min(600_000, int(ms))))
        self._actualizar_subtitulo()
        self._guardar_subtitulos()
        self.pantalla.mostrar_osd(f"Subtítulos: {texto_sincronia(self.retraso_ms)}")

    def sincronizar_ahora(self):
        """Se toca cuando alguien empieza a hablar: el subtítulo que empieza más cerca de este
        momento (con el ajuste actual) pasa a empezar justo ahora."""
        if self.subs is None or not self.subs.cues:
            self.pantalla.mostrar_osd("No hay un archivo de subtítulos cargado")
            return
        ahora = self.reproductor.position()
        inicio = min((c[0] for c in self.subs.cues), key=lambda a: abs(a + self.retraso_ms - ahora))
        self.fijar_retraso(ahora - inicio)

    def _descartar_subtitulos(self):
        self.subs = self.ruta_sub = None
        self._fin_dialogo = None
        self._poner_retraso(0)
        self.pantalla.set_texto("")

    def _poner_retraso(self, ms: int):
        self.retraso_ms = ms
        self.lbl_sincronia.setText(texto_sincronia(ms))

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

    def usar_pista_interna(self, indice: int):
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

    def archivos_subtitulos(self) -> list[tuple[str, str]]:
        """(ruta, descripción) de los subtítulos que se pueden elegir para el video actual."""
        junto = subtitulos_junto_a(self.ruta_video) if self.ruta_video else []
        if self.ruta_sub and self.ruta_sub not in junto:
            junto.append(self.ruta_sub)
        return [(ruta, descripcion(ruta, self.ruta_video)) for ruta in junto]

    def pistas_subtitulos(self) -> list[tuple[str, bool]]:
        """(nombre, activa) de las pistas de subtítulos que trae el video."""
        activa = self.reproductor.activeSubtitleTrack()
        return [(self._nombre_pista(datos, i), i == activa and self.subs is None)
                for i, datos in enumerate(self.reproductor.subtitleTracks())]

    def _armar_menu_subs(self):
        m = self.menu_subs
        m.clear()
        m.addAction("Cargar archivo de subtítulos…", self._elegir_archivo_subs).setEnabled(self._es_video)
        m.addAction("🌐 Buscar en internet (OpenSubtitles)",
                    lambda: self.buscar_subtitulos_online.emit(self.ruta_video)).setEnabled(self._es_video)
        m.addAction("🌐 Buscar en subdivx…",
                    lambda: self.buscar_subtitulos_subdivx.emit(self.ruta_video)).setEnabled(self._es_video)
        archivos = self.archivos_subtitulos()
        if archivos:
            m.addSection("Archivos de subtítulos")
        for ruta, texto in archivos:
            accion = m.addAction(texto, lambda r=ruta: self.cargar_subtitulos(r))
            accion.setCheckable(True)
            accion.setChecked(ruta == self.ruta_sub)
        pistas = self.pistas_subtitulos()
        if pistas:
            m.addSection("Pistas incluidas en el video")
        for i, (nombre, activa) in enumerate(pistas):
            accion = m.addAction(nombre, lambda i=i: self.usar_pista_interna(i))
            accion.setCheckable(True)
            accion.setChecked(activa)
        m.addSeparator()
        m.addAction("Desactivar subtítulos", self.quitar_subtitulos).setEnabled(
            self.subs is not None or self.reproductor.activeSubtitleTrack() >= 0)
        tamanos = m.addMenu("Tamaño del texto")
        for nombre, escala in TAMANOS_SUB:
            accion = tamanos.addAction(nombre, lambda e=escala: self.cambiar_tamano_sub(e))
            accion.setCheckable(True)
            accion.setChecked(self.pantalla.escala_sub == escala)

    def cambiar_tamano_sub(self, escala: float):
        self.pantalla.escala_sub = escala
        self.pantalla.update()

    # --- Reproducción ---------------------------------------------------------

    def _nuevo_frame(self, frame):
        self._actualizar_subtitulo()
        self.pantalla.set_frame(frame)
        if not self._tamano_avisado and self._es_video and frame.isValid():
            self._tamano_avisado = True
            self.tamano_video.emit(frame.size())

    def _salida_audio_cambiada(self):
        self.audio.setDevice(QMediaDevices.defaultAudioOutput())

    def alternar_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        icono = QStyle.SP_MediaVolumeMuted if self.audio.isMuted() else QStyle.SP_MediaVolume
        self.btn_mute.setIcon(self.style().standardIcon(icono))

    def _posicion(self, pos: int):
        if not self.barra.isSliderDown():
            self.barra.setValue(pos)
        self.lbl_tiempo.setText(f"{formato_tiempo(pos)} / {formato_tiempo(self.reproductor.duration())}")
        self._actualizar_subtitulo()
        self._revisar_siguiente(pos)
        if abs(pos - self._ultimo_guardado) >= 10_000:
            self.guardar_progreso()

    def _estado_medio(self, estado):
        if self._vista_previa:
            self._preparar_vista_previa()
        # La posición inicial solo se puede aplicar cuando el video terminó de cargar
        elif self._posicion_pendiente and estado in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self.reproductor.setPosition(self._posicion_pendiente)
            self._avisar_retomado(self._posicion_pendiente)
            self._posicion_pendiente = 0
        elif estado == QMediaPlayer.EndOfMedia:
            if self.ruta_video and (dur := self.reproductor.duration()) > 0:
                self.progreso.emit(self.ruta_video, dur, dur)
            self._fin_del_video()

    # --- Siguiente capítulo ---------------------------------------------------

    def _buscar_siguiente(self) -> str | None:
        if self.cola:
            return self.cola[0]
        if self.buscar_siguiente and self.ruta_video:
            return self.buscar_siguiente(self.ruta_video)
        return None

    def pasar_a(self, ruta: str):
        if ruta in self.cola:
            self.cola.remove(ruta)
            self._actualizar_cola()
        self.reproducir_siguiente.emit(ruta)

    def siguiente_capitulo(self):
        if not self._es_video:
            return
        if siguiente := self._buscar_siguiente():
            self.pasar_a(siguiente)
        else:
            self.pantalla.mostrar_osd("No hay videos en la cola ni un capítulo siguiente")

    # --- Cola -------------------------------------------------------------------

    def encolar(self, rutas: list[str]) -> int:
        """Suma videos a la cola. Si no se está viendo nada, arranca el primero ya."""
        nuevas = [r for r in dict.fromkeys(rutas) if r != self.ruta_video and r not in self.cola]
        self.cola.extend(nuevas)
        # Lo agregado cambia lo que sigue, aunque se hubiera cancelado el aviso
        self._siguiente_cancelado = False
        self._ruta_siguiente = None
        self._actualizar_cola()
        if self.cola and (not self._es_video or self.reproductor.mediaStatus() == QMediaPlayer.EndOfMedia):
            self.pasar_a(self.cola[0])
        return len(nuevas)

    def quitar_de_cola(self, ruta: str):
        if ruta in self.cola:
            self.cola.remove(ruta)
            self._ruta_siguiente = None
            self._actualizar_cola()

    def _actualizar_cola(self):
        self.btn_cola.setText(f"☰ Cola ({len(self.cola)})")
        self.btn_cola.setVisible(bool(self.cola))

    def _armar_menu_cola(self):
        m = self.menu_cola
        m.clear()
        m.addSection("A continuación")
        for i, ruta in enumerate(self.cola, 1):
            sub = m.addMenu(f"{i}. {Path(ruta).stem}")
            sub.addAction("▶ Reproducir ahora", lambda r=ruta: self.pasar_a(r))
            sub.addAction("Quitar de la cola", lambda r=ruta: self.quitar_de_cola(r))
        m.addSeparator()
        m.addAction("Vaciar la cola", self.vaciar_cola)

    def vaciar_cola(self):
        self.cola.clear()
        self._ruta_siguiente = None
        self._actualizar_cola()

    def _revisar_siguiente(self, pos: int):
        """Muestra el aviso en los últimos segundos; la cuenta sigue al video,
        así que se frena con la pausa y desaparece si se retrocede."""
        dur = self.reproductor.duration()
        if (not self._es_video or dur <= 0 or self._vista_previa or self._siguiente_cancelado
                or self.apagar_al_terminar):
            self.panel_sig.hide()
            return
        restante = dur - pos
        if restante > self.AVISO_SIGUIENTE_MS and not self._en_creditos(pos, dur):
            self.panel_sig.hide()
            return
        if self._ruta_siguiente is None:
            self._ruta_siguiente = self._buscar_siguiente()
            if self._ruta_siguiente is None:
                self._siguiente_cancelado = True  # no hay siguiente: no volver a buscar
                return
            self.lbl_sig_nombre.setText(Path(self._ruta_siguiente).stem)
        que = "Siguiente de la cola" if self._ruta_siguiente in self.cola else "Siguiente capítulo"
        # Durante los créditos queda a mano; la cuenta regresiva, solo en los últimos segundos
        if restante > self.AVISO_SIGUIENTE_MS:
            self.lbl_sig_cuenta.setText(que)
        else:
            self.lbl_sig_cuenta.setText(f"{que} en {max(1, math.ceil(restante / 1000))} s")
        if not self.panel_sig.isVisible():
            self.panel_sig.show()
        self.pantalla.colocar_panel()

    def _en_creditos(self, pos: int, dur: int) -> bool:
        """Ya terminó el último diálogo de los subtítulos: lo que queda son los créditos.
        Solo si eso pasa en el último tercio, para no confundir un final sin diálogos."""
        if self._fin_dialogo is None:
            return False
        fin = self._fin_dialogo + self.retraso_ms
        return dur * 2 // 3 <= fin <= dur - self.CREDITOS_MINIMO_MS and pos >= fin

    def _fin_del_video(self):
        if self.apagar_al_terminar:
            self.pedir_apagado.emit()
        elif not self._siguiente_cancelado:
            self.siguiente_ahora()

    def siguiente_ahora(self):
        if ruta := self._ruta_siguiente or self._buscar_siguiente():
            self.pasar_a(ruta)

    def cancelar_siguiente(self):
        self._siguiente_cancelado = True
        self.panel_sig.hide()

    def _reiniciar_siguiente(self):
        self._siguiente_cancelado = False
        self._ruta_siguiente = None
        self.panel_sig.hide()

    def _preparar_vista_previa(self):
        """Una vez cargado y con la duración conocida (en algunos .mkv llega después),
        arranca si es largo o salta al cuadro de muestra."""
        dur = self.reproductor.duration()
        # En BufferingMedia todavía puede no estar listo: un play() ahí se pierde con algunos .mkv
        cargado = self.reproductor.mediaStatus() in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia)
        if not cargado or dur <= 0 or self.reproductor.position() > 0:
            return
        if self._modo == SI_ES_LARGO and dur > DURACION_LARGA_MS:
            # Fuera de la señal del reproductor: un play() dentro de ella se ignora
            QTimer.singleShot(0, self.empezar)
        else:
            # Cuadro de muestra: al 10 % del video, como mucho a los 5 minutos
            self.reproductor.setPosition(self._inicio_ms or min(dur // 10, 300_000))

    def _duracion(self, dur: int):
        self.barra.setRange(0, dur)
        if self._vista_previa:
            self._preparar_vista_previa()

    def _estado(self, estado):
        icono = QStyle.SP_MediaPause if estado == QMediaPlayer.PlayingState else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icono))
        if estado == QMediaPlayer.PausedState:
            self.guardar_progreso()
        if self._modo_completo:
            self._actividad()
