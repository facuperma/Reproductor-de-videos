"""Buscar subtítulos en OpenSubtitles para el video que muestra un visor."""
from PySide6.QtWidgets import QMessageBox, QWidget

from .db import Biblioteca
from .dialogo_config import DialogoConfig
from .opensubtitles import OpenSubtitles, idiomas_de
from .red import ErrorRed
from .tareas import en_segundo_plano


def buscar_para_visor(visor, bib: Biblioteca, parent: QWidget):
    ruta = visor.ruta_video
    if not ruta:
        return
    if not bib.config("os_api_key"):
        if QMessageBox.question(
            parent, "Subtítulos",
            "Para buscar subtítulos en internet hace falta una clave de API de OpenSubtitles (es gratis).\n"
            "¿Abrir la configuración?",
        ) == QMessageBox.Yes:
            DialogoConfig(bib, parent).exec()
        if not bib.config("os_api_key"):
            return
    # Los valores se leen acá: el hilo de trabajo no debe tocar la base
    datos = (bib.config("os_api_key"), bib.config("os_usuario"), bib.config("os_clave"))
    idiomas = idiomas_de(bib)
    visor.pantalla.mostrar_osd("Buscando subtítulos…")

    def trabajo():
        cliente = OpenSubtitles(*datos)
        bajados, errores = [], []
        for idioma in idiomas:
            try:
                if r := cliente.descargar(ruta, idioma):
                    bajados.append(r)
                else:
                    errores.append(f"{idioma}: no se encontraron")
            except (ErrorRed, KeyError, OSError) as e:
                errores.append(f"{idioma}: {e}")
        return bajados, errores

    def listo(resultado):
        bajados, errores = resultado
        if bajados and visor.ruta_video == ruta:
            visor.cargar_subtitulos(bajados[0])  # el primer idioma configurado (español)
        if not bajados:
            QMessageBox.warning(parent, "Subtítulos", "No se pudieron conseguir subtítulos:\n" + "\n".join(errores))
        elif errores:
            visor.pantalla.mostrar_osd("Faltaron: " + "; ".join(errores))

    en_segundo_plano(trabajo, listo, lambda e: QMessageBox.warning(parent, "Subtítulos", e))
