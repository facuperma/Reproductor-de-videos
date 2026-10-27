import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from organizador.db import Biblioteca
from organizador.tema import ESTILO
from organizador.ventana import Ventana

VERSION = "1.0.1"

# Empaquetado con PyInstaller, los recursos están en sys._MEIPASS
RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


def carpeta_datos() -> Path:
    """Dónde se guarda la biblioteca. Instalada, la carpeta del programa no admite escritura,
    así que se usa %LOCALAPPDATA%\\TVon; desde el código fuente, la carpeta del proyecto."""
    if getattr(sys, "frozen", False):
        carpeta = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TVon"
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta
    return Path(__file__).parent


def main():
    if sys.platform == "win32":
        # Sin esto, Windows agrupa la app con Python y muestra el ícono de Python en la barra de tareas
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TVon")
    app = QApplication(sys.argv)
    app.setApplicationName("TVon")
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(QIcon(str(RECURSOS / "organizador" / "icono.png")))
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)
    biblioteca = Biblioteca(carpeta_datos() / "biblioteca.db")
    ventana = Ventana(biblioteca)
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
