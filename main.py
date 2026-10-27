import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from organizador.db import Biblioteca
from organizador.tema import ESTILO
from organizador.ventana import Ventana


def main():
    if sys.platform == "win32":
        # Sin esto, Windows agrupa la app con Python y muestra el ícono de Python en la barra de tareas
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TVon")
    app = QApplication(sys.argv)
    app.setApplicationName("TVon")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "organizador" / "icono.png")))
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)
    biblioteca = Biblioteca(Path(__file__).parent / "biblioteca.db")
    ventana = Ventana(biblioteca)
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
