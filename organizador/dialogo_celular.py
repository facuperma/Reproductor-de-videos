"""Ventana «Pantalla del celular»: verlo y manejarlo en la PC con scrcpy, sin Miracast."""
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from .celular_pantalla import ErrorCelular, PantallaCelular


class DialogoCelular(QDialog):
    def __init__(self, pantalla: PantallaCelular, ip_celular=None, parent=None):
        super().__init__(parent)
        self.pantalla = pantalla
        self.ip_celular = ip_celular  # función: la IP del último celular que habló por ON
        self.setWindowTitle("📲 Pantalla del celular en la PC")
        self.setMinimumWidth(520)

        pasos = QLabel(wordWrap=True, objectName="pista")
        pasos.setText(
            "Ves el celular (Android) en una ventana de la PC y lo manejás con el mouse y el teclado. "
            "Va por la misma wifi o por cable, <b>sin Miracast</b>.<br><br>"
            "<b>Una sola vez, en el celular:</b> Ajustes → Acerca del teléfono → tocá 7 veces "
            "<i>Número de compilación</i>. Después, en <i>Opciones de desarrollador</i>, activá "
            "<b>Depuración USB</b>.<br>"
            "<b>Con cable:</b> conectalo y tocá el botón (la primera vez, en el celular tocá <i>Permitir</i>). "
            "Queda listo para la wifi: podés desenchufarlo y sigue andando hasta que lo reinicies.<br>"
            "<b>Sin cable:</b> con ON conectado, el botón usa la IP del celular.")
        self.btn_ver = QPushButton("📲 Ver el celular en la PC", objectName="interruptor")
        self.btn_ver.clicked.connect(self._ver)
        self.lbl_estado = QLabel(wordWrap=True)

        # Android 11+: sin cable nunca, con «Depuración inalámbrica»
        grupo = QGroupBox("Sin cable nunca (Android 11 o más nuevo)")
        ayuda = QLabel(wordWrap=True, objectName="pista")
        ayuda.setText("En <i>Opciones de desarrollador → Depuración inalámbrica</i>: activala y tocá "
                      "<i>Vincular dispositivo con código</i>. Copiá acá lo que muestra:")
        self.txt_vincular = QLineEdit(placeholderText="IP y puerto para vincular, p. ej. 192.168.0.20:37123")
        self.txt_codigo = QLineEdit(placeholderText="Código de 6 números", maxLength=6)
        self.txt_puerto = QLineEdit(placeholderText="Puerto de «Dirección IP y puerto» (pantalla anterior)")
        btn_vincular = QPushButton("Vincular y ver")
        btn_vincular.clicked.connect(self._vincular)
        formulario = QFormLayout(grupo)
        formulario.addRow(ayuda)
        formulario.addRow("Vincular:", self.txt_vincular)
        formulario.addRow("Código:", self.txt_codigo)
        formulario.addRow("Puerto:", self.txt_puerto)
        formulario.addRow(btn_vincular)

        capa = QVBoxLayout(self)
        capa.addWidget(pasos)
        capa.addWidget(self.btn_ver)
        capa.addWidget(self.lbl_estado)
        capa.addWidget(grupo)

        pantalla.mensaje.connect(self.lbl_estado.setText)
        self.lbl_estado.setText(pantalla.ultimo)

    def _ver(self):
        try:
            self.pantalla.mostrar(self.ip_celular() if self.ip_celular else None)
        except ErrorCelular as e:
            QMessageBox.warning(self, "Pantalla del celular", str(e))

    def _vincular(self):
        try:
            self.pantalla.emparejar(self.txt_vincular.text().strip(), self.txt_codigo.text().strip(),
                                    self.txt_puerto.text().strip())
        except ErrorCelular as e:
            QMessageBox.warning(self, "Pantalla del celular", str(e))
