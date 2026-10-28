"""Cartelito flotante en una esquina de la pantalla, encima de todo (incluso del navegador)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel


class AvisoFlotante(QLabel):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # no le saca el foco al navegador
        self.setWordWrap(True)
        self.setMaximumWidth(380)
        self.setStyleSheet("QLabel { background: #1f3566; color: #ffffff; border: 1px solid #3d7bfd;"
                           " border-radius: 10px; padding: 12px 16px; font-size: 11pt; }")
        self._reloj = QTimer(self, singleShot=True, timeout=self.hide)

    def mostrar(self, texto: str, segundos: int = 60):
        self.setText(texto)
        self.adjustSize()
        zona = QGuiApplication.primaryScreen().availableGeometry()
        self.move(zona.right() - self.width() - 24, zona.bottom() - self.height() - 24)
        self.show()
        self._reloj.start(segundos * 1000)

    def mousePressEvent(self, e):
        self.hide()  # un clic lo cierra
