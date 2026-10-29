"""Configuración: biblioteca automática, descargas y OpenSubtitles."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from .db import SEPARADOR_CARPETAS, Biblioteca


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
        self.tmdb = QLineEdit(bib.config("tmdb_api_key"), placeholderText="Opcional: pósters y sinopsis en español")

        ayuda = QLabel(
            'Para los subtítulos creá una cuenta gratis en '
            '<a href="https://www.opensubtitles.com">opensubtitles.com</a> y pedí una clave de API en '
            '<a href="https://www.opensubtitles.com/consumers">opensubtitles.com/consumers</a>.<br>'
            'Con la clave, TVon baja solo el subtítulo (en el primer idioma) de cada película nueva.<br>'
            'La contraseña se guarda solo en esta computadora (archivo biblioteca.db).<br><br>'
            'Fichas de películas y series (póster, sinopsis, géneros): TVon las busca solas en Wikipedia y '
            'TVmaze. Con una clave gratis de <a href="https://www.themoviedb.org/settings/api">TMDb</a> salen '
            'mejores y en español. Clic derecho en un video → <i>Corregir ficha</i> si alguna salió mal.',
            openExternalLinks=True, wordWrap=True, objectName="pista",
        )

        form = QFormLayout()
        form.addRow("Carpeta para películas de dominio público:", fila_carpeta)
        form.addRow("Idiomas de subtítulos:", self.idiomas)
        form.addRow("OpenSubtitles – clave de API:", self.api_key)
        form.addRow("OpenSubtitles – usuario:", self.usuario)
        form.addRow("OpenSubtitles – contraseña:", self.clave)
        form.addRow("TMDb – clave de API:", self.tmdb)

        # --- Biblioteca automática ---------------------------------------------
        self.lista_carpetas = QListWidget()
        self.lista_carpetas.addItems(bib.carpetas_biblioteca())
        self.lista_carpetas.setMaximumHeight(90)
        btn_agregar = QPushButton("Agregar…")
        btn_quitar = QPushButton("Quitar")
        btn_agregar.clicked.connect(self._agregar_carpeta_biblioteca)
        btn_quitar.clicked.connect(lambda: [self.lista_carpetas.takeItem(self.lista_carpetas.row(i))
                                            for i in self.lista_carpetas.selectedItems()])
        botones_carpetas = QVBoxLayout()
        botones_carpetas.addWidget(btn_agregar)
        botones_carpetas.addWidget(btn_quitar)
        botones_carpetas.addStretch()
        fila_carpetas = QHBoxLayout()
        fila_carpetas.addWidget(self.lista_carpetas, 1)
        fila_carpetas.addLayout(botones_carpetas)

        self.chk_mover = QCheckBox("Mover los videos terminados de esta carpeta de descargas:")
        self.chk_mover.setChecked(bib.config("mover_descargas") == "1")
        self.descargas_sistema = QLineEdit(bib.config("carpeta_descargas_sistema"))
        self.carpeta_videos = QLineEdit(bib.config("carpeta_videos"))
        form_mover = QFormLayout()
        form_mover.addRow(self.chk_mover)
        form_mover.addRow("Desde:", self.descargas_sistema)
        form_mover.addRow("A:", self.carpeta_videos)

        grupo_auto = QGroupBox("Biblioteca automática")
        capa_auto = QVBoxLayout(grupo_auto)
        capa_auto.addWidget(QLabel("Carpetas que se revisan solas (con subcarpetas) para sumar videos nuevos:"))
        capa_auto.addLayout(fila_carpetas)
        capa_auto.addLayout(form_mover)
        capa_auto.addWidget(QLabel(
            "Se mueven cuando terminaron de bajarse; las carpetas de torrents recientes también, "
            "apenas el programa de torrents las suelta. "
            "Los subtítulos con el mismo nombre se mueven junto con el video.",
            wordWrap=True, objectName="pista"))

        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)

        capa = QVBoxLayout(self)
        capa.addWidget(grupo_auto)
        capa.addLayout(form)
        capa.addWidget(ayuda)
        capa.addWidget(botones)

    def _elegir_carpeta(self):
        if carpeta := QFileDialog.getExistingDirectory(self, "Carpeta de descargas", self.carpeta.text()):
            self.carpeta.setText(carpeta)

    def _agregar_carpeta_biblioteca(self):
        if carpeta := QFileDialog.getExistingDirectory(self, "Carpeta de la biblioteca"):
            carpeta = str(Path(carpeta))
            if not self.lista_carpetas.findItems(carpeta, Qt.MatchFixedString):
                self.lista_carpetas.addItem(carpeta)

    def _guardar(self):
        for clave, campo in (("carpeta_descargas", self.carpeta), ("idiomas_subtitulos", self.idiomas),
                             ("os_api_key", self.api_key), ("os_usuario", self.usuario),
                             ("os_clave", self.clave), ("tmdb_api_key", self.tmdb),
                             ("carpeta_descargas_sistema", self.descargas_sistema),
                             ("carpeta_videos", self.carpeta_videos)):
            self.bib.guardar_config(clave, campo.text().strip())
        self.bib.guardar_config("mover_descargas", "1" if self.chk_mover.isChecked() else "0")
        carpetas = [self.lista_carpetas.item(i).text() for i in range(self.lista_carpetas.count())]
        self.bib.guardar_config("carpetas_biblioteca", SEPARADOR_CARPETAS.join(carpetas))
        self.accept()
