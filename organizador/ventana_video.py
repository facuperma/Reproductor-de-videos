"""Ventana flotante con su propio reproductor, para ver varios videos a la vez."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from .db import Biblioteca
from .subtitulos_online import buscar_para_visor
from .visor import Visor, atajos_reproductor


class VentanaVideo(QWidget):
    cerrada = Signal(object)

    def __init__(self, bib: Biblioteca, ruta: str, tipo: str, posicion_ms: int = 0):
        super().__init__(None, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.bib = bib
        self._estaba_maximizada = False

        self.visor = Visor()
        self.visor.buscar_siguiente = bib.siguiente_en_categoria
        self.visor.reproducir_siguiente.connect(lambda r: self.abrir(r, "video"))
        self.visor.subtitulos_cambiados.connect(bib.guardar_subtitulos)
        self.visor.progreso.connect(bib.guardar_progreso)
        self.visor.pedir_pantalla_completa.connect(self.alternar_pantalla_completa)
        self.visor.buscar_subtitulos_online.connect(lambda _: buscar_para_visor(self.visor, bib, self))
        self.btn_fijar = QPushButton("📌", checkable=True, toolTip="Mantener siempre visible")
        self.btn_fijar.toggled.connect(self._fijar)
        self.visor.agregar_control(self.btn_fijar)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.visor)
        atajos_reproductor(self, self.visor, self.alternar_pantalla_completa)

        self.resize(800, 500)
        self.abrir(ruta, tipo, posicion_ms)

    def abrir(self, ruta: str, tipo: str, posicion_ms: int = 0):
        self.setWindowTitle(f"{Path(ruta).name} — TVon")
        self.visor.mostrar(ruta, tipo, self.bib.subtitulos_de(ruta), posicion_ms or self.bib.posicion_guardada(ruta))

    def alternar_pantalla_completa(self):
        completa = not self.isFullScreen()
        if completa:
            self._estaba_maximizada = self.isMaximized()
            self.showFullScreen()
        elif self._estaba_maximizada:
            self.showMaximized()
        else:
            self.showNormal()
        self.visor.set_modo_completo(completa)

    def _fijar(self, activo: bool):
        # Cambiar las flags oculta la ventana: hay que volver a mostrarla
        self.setWindowFlag(Qt.WindowStaysOnTopHint, activo)
        self.show()

    def closeEvent(self, e):
        self.visor.mostrar(None, None)
        self.cerrada.emit(self)
        super().closeEvent(e)
