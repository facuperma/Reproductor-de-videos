"""Configuración de descargas y de OpenSubtitles."""
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from .db import Biblioteca


class DialogoConfig(QDialog):
    def __init__(self, bib: Biblioteca, parent=None):
        super().__init__(parent)
        self.bib = bib
        self.setWindowTitle("Configuración — TVon")
        self.setMinimumWidth(560)

        self.carpeta = QLineEdit(bib.config("carpeta_descargas"))
        btn_carpeta = QPushButton("Elegir…")
        btn_carpeta.clicked.connect(self._elegir_carpeta)
        fila_carpeta = QWidget()
        capa_carpeta = QHBoxLayout(fila_carpeta)
        capa_carpeta.setContentsMargins(0, 0, 0, 0)
        capa_carpeta.addWidget(self.carpeta, 1)
        capa_carpeta.addWidget(btn_carpeta)

        self.idiomas = QLineEdit(bib.config("idiomas_subtitulos"), placeholderText="es,en")
        self.api_key = QLineEdit(bib.config("os_api_key"))
        self.usuario = QLineEdit(bib.config("os_usuario"), placeholderText="Opcional: da más descargas por día")
        self.clave = QLineEdit(bib.config("os_clave"), echoMode=QLineEdit.Password)

        ayuda = QLabel(
            'Para los subtítulos creá una cuenta gratis en '
            '<a href="https://www.opensubtitles.com">opensubtitles.com</a> y pedí una clave de API en '
            '<a href="https://www.opensubtitles.com/consumers">opensubtitles.com/consumers</a>.<br>'
            'La contraseña se guarda solo en esta computadora (archivo biblioteca.db).',
            openExternalLinks=True, wordWrap=True, objectName="pista",
        )

        form = QFormLayout()
        form.addRow("Carpeta de descargas:", fila_carpeta)
        form.addRow("Idiomas de subtítulos:", self.idiomas)
        form.addRow("OpenSubtitles – clave de API:", self.api_key)
        form.addRow("OpenSubtitles – usuario:", self.usuario)
        form.addRow("OpenSubtitles – contraseña:", self.clave)

        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)

        capa = QVBoxLayout(self)
        capa.addLayout(form)
        capa.addWidget(ayuda)
        capa.addWidget(botones)

    def _elegir_carpeta(self):
        if carpeta := QFileDialog.getExistingDirectory(self, "Carpeta de descargas", self.carpeta.text()):
            self.carpeta.setText(carpeta)

    def _guardar(self):
        for clave, campo in (("carpeta_descargas", self.carpeta), ("idiomas_subtitulos", self.idiomas),
                             ("os_api_key", self.api_key), ("os_usuario", self.usuario),
                             ("os_clave", self.clave)):
            self.bib.guardar_config(clave, campo.text().strip())
        self.accept()
