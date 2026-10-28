"""Ventana para buscar y descargar películas de dominio público del Internet Archive."""
from pathlib import Path

from PySide6.QtCore import QFile, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import archive
from .db import Biblioteca
from .descargas import GestorDescargas
from .dialogo_config import DialogoConfig
from .subtitulos import subtitulos_junto_a
from .tareas import en_segundo_plano

ROL = Qt.UserRole
ESTADOS = {
    "pendiente": "En cola", "descargando": "Descargando", "completa": "✔ En la biblioteca",
    "archivada": "✔ En la biblioteca", "error": "Error", "cancelada": "Cancelada", "omitida": "Omitida",
    "eliminada": "Eliminada",
}


def formato_tamano(n: int | None) -> str:
    if not n:
        return ""
    return f"{n / 1024**3:.1f} GB" if n >= 1024**3 else f"{n / 1024**2:.0f} MB"


def eliminar_archivos(ruta_video: str) -> list[str]:
    """Manda a la Papelera el video y los archivos que empiezan con su nombre (subtítulos, .part).
    Borra la carpeta si queda vacía. Devuelve los que no se pudieron mover."""
    video = Path(ruta_video)
    if not video.parent.exists():
        return []
    fallidos = [archivo.name for archivo in video.parent.iterdir()
                if archivo.name.startswith(video.stem) and not a_la_papelera(archivo)]
    if not any(video.parent.iterdir()):
        video.parent.rmdir()
    return fallidos


def a_la_papelera(archivo: Path) -> bool:
    resultado = QFile.moveToTrash(str(archivo))
    return resultado[0] if isinstance(resultado, tuple) else resultado


def eliminar_video(ruta_video: str) -> list[str]:
    """Manda a la Papelera un video de la biblioteca y sus subtítulos (video.srt, video.es.srt…),
    sin tocar otros archivos de la carpeta. Devuelve los que no se pudieron mover."""
    archivos = [Path(ruta_video), *map(Path, subtitulos_junto_a(ruta_video))]
    return [a.name for a in archivos if a.exists() and not a_la_papelera(a)]


def cancelar_descargas(bib: Biblioteca, gestor: GestorDescargas, identificadores: list[str]):
    estados = bib.estados_descarga()
    for ident in identificadores:
        if estados.get(ident) == "descargando":
            gestor.cancelar(ident)
        elif estados.get(ident) == "pendiente":
            bib.actualizar_descarga(ident, estado="cancelada")


def reintentar_descargas(bib: Biblioteca, gestor: GestorDescargas, identificadores: list[str]):
    estados = bib.estados_descarga()
    for ident in identificadores:
        if estados.get(ident) in ("error", "cancelada"):
            bib.actualizar_descarga(ident, estado="pendiente", error=None)
    gestor.despertar()


def quitar_descargas(bib: Biblioteca, identificadores: list[str]):
    # No se borra el registro: así la descarga automática no la vuelve a bajar
    estados = bib.estados_descarga()
    for ident in identificadores:
        if estados.get(ident) == "completa":
            bib.actualizar_descarga(ident, estado="archivada")
        elif estados.get(ident) != "descargando":
            bib.actualizar_descarga(ident, estado="omitida")


def peliculas_borrables(bib: Biblioteca, identificadores: list[str]) -> list[str]:
    """Las que ya están descargadas (las demás no tienen nada que borrar)."""
    estados = bib.estados_descarga()
    return [i for i in identificadores if estados.get(i) in ("completa", "archivada")]


def eliminar_peliculas(bib: Biblioteca, identificadores: list[str], soltar) -> list[str]:
    """Manda a la Papelera las películas descargadas y las saca de la biblioteca; la descarga
    automática no las vuelve a bajar. `soltar(ruta)` deja de reproducirla antes de borrarla.
    Devuelve los archivos que no se pudieron mover."""
    fallidos = []
    for ident in identificadores:
        if ruta := bib.ruta_descarga(ident):
            soltar(ruta)
            fallidos += eliminar_archivos(ruta)
            if (aid := bib.id_de_ruta(str(Path(ruta).resolve()))) is not None:
                bib.quitar_archivos([aid])
        bib.actualizar_descarga(ident, estado="eliminada")
    return fallidos


class VentanaDominioPublico(QWidget):
    # Ruta de una película que se va a borrar: hay que dejar de reproducirla antes
    pelicula_por_eliminar = Signal(str)
    biblioteca_cambiada = Signal()

    def __init__(self, bib: Biblioteca, gestor: GestorDescargas):
        super().__init__(None, Qt.Window)
        self.bib = bib
        self.gestor = gestor
        self.setWindowTitle("Películas de dominio público — TVon")
        self.resize(1000, 720)
        self._texto = ""
        self._orden = "populares"
        self._pagina = 1
        self._barras: dict[str, QProgressBar] = {}

        # --- Búsqueda -------------------------------------------------------
        self.buscador = QLineEdit(placeholderText="Buscar por título (vacío = las más populares)…",
                                  clearButtonEnabled=True)
        self.buscador.returnPressed.connect(self.buscar)
        self.combo_orden = QComboBox()
        for clave, (texto, _api) in archive.ORDENES.items():
            self.combo_orden.addItem(texto, clave)
        self.combo_orden.currentIndexChanged.connect(lambda _: self.buscar())
        btn_buscar = QPushButton("Buscar")
        btn_buscar.clicked.connect(self.buscar)
        btn_config = QPushButton("⚙ Configuración")
        btn_config.clicked.connect(lambda: DialogoConfig(self.bib, self).exec())
        fila_busqueda = QHBoxLayout()
        fila_busqueda.addWidget(self.buscador, 1)
        fila_busqueda.addWidget(QLabel("Ordenar por:"))
        fila_busqueda.addWidget(self.combo_orden)
        fila_busqueda.addWidget(btn_buscar)
        fila_busqueda.addWidget(btn_config)

        self.resultados = QTreeWidget()
        self.resultados.setHeaderLabels(["Título", "Año", "Descargas en archive.org", "Estado"])
        self.resultados.setRootIsDecorated(False)
        self.resultados.setSelectionMode(QAbstractItemView.ExtendedSelection)
        encabezado = self.resultados.header()
        encabezado.setSectionResizeMode(0, QHeaderView.Stretch)
        encabezado.setSectionsClickable(True)
        encabezado.setSortIndicatorShown(True)
        encabezado.sectionClicked.connect(self._orden_por_columna)
        self.resultados.itemDoubleClicked.connect(lambda _: self._descargar_seleccion())
        self.lbl_resultados = QLabel(objectName="pista")
        self.btn_mas = QPushButton("Cargar más")
        self.btn_mas.clicked.connect(lambda: self._cargar_pagina(self._pagina + 1))
        btn_descargar = QPushButton("⬇ Descargar seleccionadas")
        btn_descargar.clicked.connect(self._descargar_seleccion)
        btn_eliminar_res = QPushButton("🗑 Eliminar película")
        btn_eliminar_res.setToolTip("Borra del disco las películas seleccionadas que ya descargaste")
        btn_eliminar_res.clicked.connect(
            lambda: self._eliminar([i.data(0, ROL)["identificador"] for i in self.resultados.selectedItems()]))
        fila_res = QHBoxLayout()
        fila_res.addWidget(self.lbl_resultados, 1)
        fila_res.addWidget(self.btn_mas)
        fila_res.addWidget(btn_eliminar_res)
        fila_res.addWidget(btn_descargar)

        arriba = QWidget()
        capa_arriba = QVBoxLayout(arriba)
        capa_arriba.setContentsMargins(0, 0, 0, 0)
        capa_arriba.addLayout(fila_busqueda)
        capa_arriba.addWidget(self.resultados, 1)
        capa_arriba.addLayout(fila_res)

        # --- Cola de descargas ------------------------------------------------
        self.cola = QTreeWidget()
        self.cola.setHeaderLabels(["Descargas", "Estado", "Tamaño", "Progreso"])
        self.cola.setRootIsDecorated(False)
        self.cola.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cola.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cola.header().resizeSection(3, 220)
        btn_cancelar = QPushButton("Cancelar")
        btn_reintentar = QPushButton("Reintentar")
        btn_quitar = QPushButton("Quitar de la lista")
        btn_eliminar = QPushButton("🗑 Eliminar película")
        btn_eliminar.setToolTip("Manda la película y sus subtítulos a la Papelera y la saca de la biblioteca")
        btn_cancelar.clicked.connect(self._cancelar)
        btn_reintentar.clicked.connect(self._reintentar)
        btn_quitar.clicked.connect(self._quitar)
        btn_eliminar.clicked.connect(lambda: self._eliminar(self._seleccion_cola()))
        fila_cola = QHBoxLayout()
        fila_cola.addStretch()
        for b in (btn_cancelar, btn_reintentar, btn_quitar, btn_eliminar):
            fila_cola.addWidget(b)

        abajo = QWidget()
        capa_abajo = QVBoxLayout(abajo)
        capa_abajo.setContentsMargins(0, 0, 0, 0)
        capa_abajo.addWidget(self.cola, 1)
        capa_abajo.addLayout(fila_cola)

        # --- Descarga automática ---------------------------------------------
        self.chk_auto = QCheckBox("Descargar automáticamente las más populares, hasta:")
        self.chk_auto.setChecked(bib.config("auto_activa") == "1")
        self.spin_peliculas = QSpinBox(minimum=1, maximum=30000, suffix=" películas",
                                       value=int(bib.config("auto_max_peliculas")))
        self.spin_gb = QSpinBox(minimum=1, maximum=100000, suffix=" GB", value=int(float(bib.config("auto_max_gb"))))
        self.chk_auto.toggled.connect(lambda v: self._guardar_auto("auto_activa", "1" if v else "0"))
        self.spin_peliculas.valueChanged.connect(lambda v: self._guardar_auto("auto_max_peliculas", str(v)))
        self.spin_gb.valueChanged.connect(lambda v: self._guardar_auto("auto_max_gb", str(v)))
        self.lbl_uso = QLabel(objectName="pista")
        grupo_auto = QGroupBox("Descarga automática")
        capa_auto = QVBoxLayout(grupo_auto)
        fila_auto = QHBoxLayout()
        fila_auto.addWidget(self.chk_auto)
        fila_auto.addWidget(self.spin_peliculas)
        fila_auto.addWidget(QLabel("o"))
        fila_auto.addWidget(self.spin_gb)
        fila_auto.addStretch()
        capa_auto.addLayout(fila_auto)
        capa_auto.addWidget(QLabel(
            "La colección completa tiene unas 25.000 películas (más de 10 TB). "
            "Siempre se dejan al menos 5 GB libres en el disco. Las descargas siguen mientras TVon esté abierto.",
            wordWrap=True, objectName="pista"))
        capa_auto.addWidget(self.lbl_uso)

        divisor = QSplitter(Qt.Vertical)
        divisor.addWidget(arriba)
        divisor.addWidget(abajo)
        divisor.setSizes([420, 260])
        capa = QVBoxLayout(self)
        capa.addWidget(divisor, 1)
        capa.addWidget(grupo_auto)

        gestor.cola_cambiada.connect(self._refrescar_cola)
        gestor.progreso.connect(self._progreso)
        self._refrescar_cola()
        self.buscar()

    # --- Búsqueda -------------------------------------------------------------

    def buscar(self):
        self._texto = self.buscador.text().strip()
        self._orden = self.combo_orden.currentData()
        self.resultados.clear()
        columna, sentido = {
            "titulo": (0, Qt.AscendingOrder), "titulo_desc": (0, Qt.DescendingOrder),
            "anio": (1, Qt.AscendingOrder), "anio_desc": (1, Qt.DescendingOrder),
        }.get(self._orden, (2, Qt.DescendingOrder))
        self.resultados.header().setSortIndicator(columna, sentido)
        self._cargar_pagina(1)

    def _orden_por_columna(self, columna: int):
        """Clic en un encabezado: ordena por esa columna; otro clic invierte el sentido."""
        actual = self.combo_orden.currentData()
        nuevo = {
            0: "titulo_desc" if actual == "titulo" else "titulo",
            1: "anio" if actual == "anio_desc" else "anio_desc",
        }.get(columna, "populares")
        self.combo_orden.setCurrentIndex(self.combo_orden.findData(nuevo))
        if nuevo == actual:
            self.buscar()  # el combo no cambió (p. ej. «populares»): igual se restablece el indicador

    def _cargar_pagina(self, pagina: int):
        self._pagina = pagina
        self.lbl_resultados.setText("Buscando…")
        self.btn_mas.setEnabled(False)
        consulta = (self._texto, self._orden)
        en_segundo_plano(lambda: archive.buscar(consulta[0], pagina, orden=consulta[1]),
                         lambda r: self._mostrar_resultados(consulta, *r),
                         lambda e: self.lbl_resultados.setText(f"Error: {e}"))

    def _mostrar_resultados(self, consulta: tuple, total: int, peliculas: list[dict]):
        if consulta != (self._texto, self._orden):
            return  # llegó tarde una búsqueda anterior
        estados = self.bib.estados_descarga()
        for p in peliculas:
            item = QTreeWidgetItem([p["titulo"], p["anio"] or "", f"{p['descargas']:,}".replace(",", "."),
                                    ESTADOS.get(estados.get(p["identificador"]), "")])
            item.setData(0, ROL, p)
            item.setToolTip(0, f"archive.org/details/{p['identificador']}")
            self.resultados.addTopLevelItem(item)
        cargadas = self.resultados.topLevelItemCount()
        self.lbl_resultados.setText(f"{cargadas} de {total:,} películas".replace(",", "."))
        self.btn_mas.setEnabled(cargadas < total)

    def _descargar_seleccion(self):
        nuevas = 0
        for item in self.resultados.selectedItems():
            p = item.data(0, ROL)
            if self.bib.agregar_descarga(p["identificador"], p["titulo"], p["anio"]):
                nuevas += 1
            item.setText(3, ESTADOS["pendiente"])
        if nuevas:
            self.gestor.despertar()
            self._refrescar_cola()

    # --- Cola -------------------------------------------------------------------

    def _refrescar_cola(self):
        seleccion = {i.data(0, ROL) for i in self.cola.selectedItems()}
        self.cola.clear()
        self._barras.clear()
        for fila in self.bib.listar_descargas():
            titulo = f"{fila['titulo']} ({fila['anio']})" if fila["anio"] else fila["titulo"]
            estado = ESTADOS.get(fila["estado"], fila["estado"])
            item = QTreeWidgetItem([titulo, estado, formato_tamano(fila["tamano"])])
            item.setData(0, ROL, fila["identificador"])
            if fila["error"]:
                item.setToolTip(1, fila["error"])
                item.setText(1, f"Error: {fila['error']}")
            self.cola.addTopLevelItem(item)
            if fila["estado"] in ("descargando", "pendiente") and fila["tamano"]:
                barra = QProgressBar(maximum=1000, textVisible=True)
                barra.setValue(int(1000 * fila["recibido"] / fila["tamano"]))
                barra.setFormat(f"{barra.value() / 10:.0f} %")
                self.cola.setItemWidget(item, 3, barra)
                self._barras[fila["identificador"]] = barra
            item.setSelected(fila["identificador"] in seleccion)
        n, usados = self.bib.resumen_descargas()
        self.lbl_uso.setText(f"Descargadas o en cola: {n} películas · {formato_tamano(usados) or '0 MB'}")
        self._actualizar_estados_resultados()

    def _actualizar_estados_resultados(self):
        estados = self.bib.estados_descarga()
        for i in range(self.resultados.topLevelItemCount()):
            item = self.resultados.topLevelItem(i)
            item.setText(3, ESTADOS.get(estados.get(item.data(0, ROL)["identificador"]), ""))

    def _progreso(self, ident: str, recibido: int, total: int):
        if (barra := self._barras.get(ident)) and total:
            barra.setValue(int(1000 * recibido / total))
            barra.setFormat(f"{100 * recibido / total:.0f} %  ·  {formato_tamano(recibido)} de {formato_tamano(total)}")

    def _seleccion_cola(self) -> list[str]:
        return [i.data(0, ROL) for i in self.cola.selectedItems()]

    def _cancelar(self):
        cancelar_descargas(self.bib, self.gestor, self._seleccion_cola())
        self._refrescar_cola()

    def _reintentar(self):
        reintentar_descargas(self.bib, self.gestor, self._seleccion_cola())
        self._refrescar_cola()

    def _quitar(self):
        quitar_descargas(self.bib, self._seleccion_cola())
        self._refrescar_cola()

    def _eliminar(self, identificadores: list[str]):
        borrables = peliculas_borrables(self.bib, identificadores)
        if not borrables:
            QMessageBox.information(self, "Eliminar película", "Seleccioná películas que ya estén descargadas.")
            return
        if QMessageBox.question(
            self, "Eliminar película",
            f"¿Eliminar {len(borrables)} película(s)?\n\n"
            "Se mandan a la Papelera de reciclaje junto con sus subtítulos y se quitan de la biblioteca. "
            "La descarga automática no las vuelve a bajar.",
        ) != QMessageBox.Yes:
            return
        # La ventana principal suelta el archivo si lo está mostrando
        fallidos = eliminar_peliculas(self.bib, borrables, self.pelicula_por_eliminar.emit)
        self.biblioteca_cambiada.emit()
        self._refrescar_cola()
        if fallidos:
            QMessageBox.warning(self, "Eliminar película",
                                "No se pudieron mover a la Papelera:\n" + "\n".join(fallidos))

    def _guardar_auto(self, clave: str, valor: str):
        self.bib.guardar_config(clave, valor)
        self.gestor.despertar()
