import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from organizador.db import Biblioteca
from organizador.tema import ESTILO
from organizador.ventana import Ventana


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TVon")
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)
    biblioteca = Biblioteca(Path(__file__).parent / "biblioteca.db")
    ventana = Ventana(biblioteca)
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
