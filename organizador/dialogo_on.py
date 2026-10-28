"""Ventana del modo ON: encenderlo, el QR para conectar el celular y los permisos."""
import segno
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout,
)

from .remoto import Remoto


def pixmap_qr(texto: str, lado: int = 260) -> QPixmap:
    """El QR dibujado con módulos nítidos, negro sobre blanco (con su margen)."""
    filas = [list(fila) for fila in segno.make(texto, error="m").matrix_iter(border=4)]
    modulo = max(1, lado // len(filas))
    imagen = QImage(modulo * len(filas), modulo * len(filas), QImage.Format_RGB32)
    imagen.fill(QColor("white"))
    p = QPainter(imagen)
    for y, fila in enumerate(filas):
        for x, negro in enumerate(fila):
            if negro:
                p.fillRect(QRectF(x * modulo, y * modulo, modulo, modulo), QColor("black"))
    p.end()
    return QPixmap.fromImage(imagen)


def hace(segundos: float | None) -> str:
    if segundos is None:
        return "sin actividad desde que se abrió TVon"
    if segundos < 10:
        return "conectado ahora"
    if segundos < 3600:
        return f"visto hace {int(segundos // 60) or 1} min"
    return f"visto hace {int(segundos // 3600)} h"


class DialogoOn(QDialog):
    def __init__(self, remoto: Remoto, parent=None):
        super().__init__(parent)
        self.remoto = remoto
        self.setWindowTitle("ON — Manejar TVon desde el celular")
        self.setMinimumWidth(520)

        self.btn_interruptor = QPushButton(objectName="interruptor", checkable=True)
        self.btn_interruptor.clicked.connect(self._alternar)
        self.lbl_estado = QLabel(wordWrap=True)
        self.lbl_qr = QLabel(alignment=Qt.AlignCenter)
        self.lbl_url = QLabel(alignment=Qt.AlignCenter, textInteractionFlags=Qt.TextSelectableByMouse)
        self.lbl_pasos = QLabel(wordWrap=True, objectName="pista")
        self.lbl_pasos.setText(
            "1. Conectá el celular a la misma red wifi que esta PC.<br>"
            "2. Escaneá el código con la cámara (o Google Lens) y abrí el enlace en Chrome.<br>"
            "3. Para tenerlo como app: en Chrome, menú ⋮ → <b>Agregar a la pantalla principal</b>.<br>"
            "La primera vez, si Windows pregunta por el firewall, tocá <b>Permitir</b>.")
        self.btn_remoto = QPushButton(checkable=True)
        self.btn_remoto.toggled.connect(self._mostrar)
        self.lbl_remoto = QLabel(wordWrap=True, objectName="pista", openExternalLinks=True)

        self.chk_pantalla = QCheckBox("Permitir compartir la pantalla de la PC con el celular")
        self.chk_control = QCheckBox("Permitir manejar el mouse y el teclado desde el celular (touchpad y teclado)")
        self.chk_inicio = QCheckBox("Encender ON cada vez que se abre TVon")
        self.chk_pantalla.setChecked(remoto.permite_pantalla)
        self.chk_control.setChecked(remoto.permite_control)
        self.chk_inicio.setChecked(remoto.al_iniciar)
        self.chk_pantalla.toggled.connect(lambda v: self._opcion("on_pantalla", v))
        self.chk_control.toggled.connect(lambda v: self._opcion("on_control", v))
        self.chk_inicio.toggled.connect(lambda v: remoto.guardar_opcion("on_activo", v))
        grupo_opciones = QGroupBox("Opciones")
        capa_opciones = QVBoxLayout(grupo_opciones)
        for chk in (self.chk_pantalla, self.chk_control, self.chk_inicio):
            capa_opciones.addWidget(chk)

        self.lista_celulares = QListWidget()
        self.lista_celulares.setMaximumHeight(90)
        btn_desconectar = QPushButton("Desconectar todos")
        btn_desconectar.setToolTip("Los celulares tienen que volver a escanear el código")
        btn_desconectar.clicked.connect(remoto.desconectar_todos)
        btn_codigo = QPushButton("Cambiar el código QR")
        btn_codigo.setToolTip("Hace un código nuevo. Los celulares ya conectados siguen conectados")
        btn_codigo.clicked.connect(remoto.cambiar_codigo)
        grupo_celulares = QGroupBox("Celulares conectados")
        capa_celulares = QVBoxLayout(grupo_celulares)
        capa_celulares.addWidget(self.lista_celulares)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(btn_codigo)
        fila.addWidget(btn_desconectar)
        capa_celulares.addLayout(fila)

        capa = QVBoxLayout(self)
        capa.addWidget(self.btn_interruptor)
        capa.addWidget(self.lbl_estado)
        capa.addWidget(self.lbl_qr)
        capa.addWidget(self.lbl_url)
        capa.addWidget(self.lbl_pasos)
        capa.addWidget(self.btn_remoto)
        capa.addWidget(self.lbl_remoto)
        capa.addWidget(grupo_opciones)
        capa.addWidget(grupo_celulares)

        remoto.estado_cambiado.connect(self._mostrar)
        # «Visto hace…» se actualiza solo
        self._reloj = QTimer(self, interval=5000, timeout=self._mostrar_celulares)
        self._reloj.start()
        self._mostrar()

    def _opcion(self, clave: str, activa: bool):
        self.remoto.guardar_opcion(clave, activa)

    def _alternar(self):
        if self.remoto.activo:
            self.remoto.detener()
        else:
            self.remoto.iniciar()

    def _mostrar(self):
        activo = self.remoto.activo
        self.btn_interruptor.setChecked(activo)
        self.btn_interruptor.setText("● ON encendido — tocá para apagar" if activo else "Encender ON")
        self.lbl_qr.setVisible(activo)
        self.lbl_url.setVisible(activo)
        self.lbl_pasos.setVisible(activo)
        self.btn_remoto.setVisible(activo)
        self.lbl_remoto.setVisible(activo)
        if activo:
            remota = self.remoto.url_remota()
            fuera = self.btn_remoto.isChecked()
            self.btn_remoto.setText("🏠 Volver al código para la wifi de casa" if fuera else "🌍 Usarlo fuera de casa…")
            if fuera and remota:
                self.lbl_estado.setText("Para fuera de casa (Tailscale): escaneá este código con el celular "
                                        "estando conectado a Tailscale. Queda como otra conexión, aparte de la de casa:")
                url, url_emparejar = remota, f"{remota}?c={self.remoto.codigo}"
            else:
                self.lbl_estado.setText("Usarlo fuera de casa:" if fuera else "Escaneá este código con el celular:")
                url, url_emparejar = self.remoto.url, self.remoto.url_emparejar
            self.lbl_qr.setPixmap(pixmap_qr(url_emparejar))
            self.lbl_url.setText(f"<span style='color:#9fc2ff'>{url}</span>")
            self.lbl_qr.setVisible(not fuera or bool(remota))
            self.lbl_url.setVisible(not fuera or bool(remota))
            self.lbl_pasos.setVisible(not fuera)
            self.lbl_remoto.setVisible(fuera)
            self.lbl_remoto.setText(
                "Tailscale está conectado en esta PC. En el celular instalá la app Tailscale, entrá con la misma "
                "cuenta y dejala conectada: así TVon anda desde cualquier lado, con la conexión cifrada.<br>"
                "Si no conecta, permití TVon también en redes públicas en el Firewall de Windows." if remota else
                "Para manejar TVon desde fuera de casa hace falta <a href='https://tailscale.com/download' "
                "style='color:#9fc2ff'>Tailscale</a> (gratis): una red privada y cifrada entre tus dispositivos.<br>"
                "1. Instalalo en esta PC y en el celular (Play Store) y entrá con la misma cuenta en los dos.<br>"
                "2. Volvé a abrir esta ventana: aparece el código para fuera de casa.<br>"
                "No abras el puerto de TVon en el router: la conexión no está cifrada.")
        elif self.remoto.error:
            self.lbl_estado.setText(f"<span style='color:#ff8080'>No se pudo encender: {self.remoto.error}</span>")
        else:
            self.lbl_estado.setText(
                "Con ON encendido, desde el celular manejás TVon: la biblioteca, el reproductor, la cola, "
                "los subtítulos, las categorías y las descargas. Y si hace falta, ves la pantalla de la PC y "
                "la manejás con el dedo.")
        self._mostrar_celulares()
        self.adjustSize()

    def _mostrar_celulares(self):
        self.lista_celulares.clear()
        celulares = self.remoto.celulares()
        for c in celulares:
            self.lista_celulares.addItem(f"📱 {c['nombre']} — {hace(c['visto'])} (desde el {c['creada']})")
        if not celulares:
            self.lista_celulares.addItem("Ninguno todavía")
