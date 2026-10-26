"""Ventana principal: filtros/categorías, lista de archivos, visor y detalles."""
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSplitter, QStyle, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .db import EXT_IMAGEN, EXT_VIDEO, Biblioteca
from .visor import Visor

ROL = Qt.UserRole


class Ventana(QMainWindow):
    def __init__(self, biblioteca: Biblioteca):
        super().__init__()
        self.bib = biblioteca
        self.filtro = ("todos", None)
        self.setWindowTitle("Organizador multimedia")
        self.resize(1400, 820)
        self.setAcceptDrops(True)

        self._crear_barra()

        # --- Columna izquierda: filtros y categorías -------------------------
        self.lista_filtros = QListWidget()
        self.lista_filtros.currentItemChanged.connect(self._filtro_cambiado)
        self.lista_filtros.itemDoubleClicked.connect(lambda _: self._renombrar_categoria())
        btn_nueva = QPushButton("+ Nueva")
        btn_renombrar = QPushButton("Renombrar")
        btn_borrar = QPushButton("Borrar")
        btn_nueva.clicked.connect(self._nueva_categoria)
        btn_renombrar.clicked.connect(self._renombrar_categoria)
        btn_borrar.clicked.connect(self._borrar_categoria)

        izq = QWidget()
        capa_izq = QVBoxLayout(izq)
        capa_izq.addWidget(QLabel("Biblioteca y categorías", objectName="titulo"))
        capa_izq.addWidget(self.lista_filtros, 1)
        fila = QHBoxLayout()
        for b in (btn_nueva, btn_renombrar, btn_borrar):
            fila.addWidget(b)
        capa_izq.addLayout(fila)

        # --- Columna central: archivos --------------------------------------
        self.lista = QTreeWidget()
        self.lista.setHeaderLabels(["Nombre", "Carpeta"])
        self.lista.setRootIsDecorated(False)
        self.lista.setUniformRowHeights(True)
        self.lista.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lista.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.lista.header().resizeSection(0, 260)
        self.lista.currentItemChanged.connect(self._archivo_cambiado)
        self.lbl_cantidad = QLabel()

        centro = QWidget()
        capa_centro = QVBoxLayout(centro)
        capa_centro.addWidget(self.lista, 1)
        capa_centro.addWidget(self.lbl_cantidad)

        # --- Columna derecha: visor y detalles ------------------------------
        self.visor = Visor()

        self.lbl_nombre = QLabel(objectName="titulo")
        self.lbl_nombre.setWordWrap(True)
        self.txt_ruta = QLineEdit(readOnly=True, placeholderText="Ubicación del archivo")
        btn_abrir = QPushButton("Abrir ubicación")
        btn_copiar = QPushButton("Copiar ruta")
        btn_abrir.clicked.connect(self._abrir_ubicacion)
        btn_copiar.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_ruta.text()))
        fila_ruta = QHBoxLayout()
        fila_ruta.addWidget(self.txt_ruta, 1)
        fila_ruta.addWidget(btn_abrir)
        fila_ruta.addWidget(btn_copiar)

        self.lista_asignar = QListWidget()
        self.lista_asignar.setMaximumHeight(150)
        self.lista_asignar.itemChanged.connect(self._asignacion_cambiada)
        grupo_cat = QGroupBox("Categorías de este archivo")
        QVBoxLayout(grupo_cat).addWidget(self.lista_asignar)

        btn_ant = QPushButton("◀ Anterior")
        btn_sig = QPushButton("Siguiente ▶")
        btn_quitar = QPushButton("Quitar de la biblioteca")
        btn_ant.clicked.connect(lambda: self._mover(-1))
        btn_sig.clicked.connect(lambda: self._mover(1))
        btn_quitar.clicked.connect(self._quitar_archivo)
        fila_nav = QHBoxLayout()
        fila_nav.addWidget(btn_ant)
        fila_nav.addWidget(btn_sig)
        fila_nav.addStretch()
        fila_nav.addWidget(btn_quitar)

        self.detalles = QWidget()
        capa_det = QVBoxLayout(self.detalles)
        capa_det.setContentsMargins(0, 0, 0, 0)
        capa_det.addWidget(self.lbl_nombre)
        capa_det.addLayout(fila_ruta)
        capa_det.addWidget(grupo_cat)
        capa_det.addLayout(fila_nav)

        der = QWidget()
        capa_der = QVBoxLayout(der)
        capa_der.addWidget(self.visor, 1)
        capa_der.addWidget(self.detalles)

        divisor = QSplitter()
        for w in (izq, centro, der):
            divisor.addWidget(w)
        divisor.setSizes([230, 430, 740])
        divisor.setStretchFactor(2, 1)
        self.setCentralWidget(divisor)

        self._atajos()
        self._cargar_filtros()
        self._mostrar_detalles(None)

    # --- Construcción -------------------------------------------------------

    def _crear_barra(self):
        barra = QToolBar("Principal", movable=False)
        self.addToolBar(barra)
        estilo = self.style()
        acc_archivos = QAction(estilo.standardIcon(QStyle.SP_FileIcon), "Agregar archivos", self)
        acc_carpeta = QAction(estilo.standardIcon(QStyle.SP_DirOpenIcon), "Agregar carpeta", self)
        acc_archivos.triggered.connect(self._agregar_archivos)
        acc_carpeta.triggered.connect(self._agregar_carpeta)
        barra.addAction(acc_archivos)
        barra.addAction(acc_carpeta)
        barra.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        espacio = QWidget()
        espacio.setFixedWidth(20)
        barra.addWidget(espacio)
        self.buscador = QLineEdit(placeholderText="Buscar por nombre…", clearButtonEnabled=True)
        self.buscador.setMaximumWidth(320)
        self.buscador.textChanged.connect(lambda _: self._cargar_archivos())
        barra.addWidget(self.buscador)

    def _atajos(self):
        for tecla, accion in (
            ("Space", self.visor.alternar_play),
            ("Right", lambda: self.visor.adelantar(5000)),
            ("Left", lambda: self.visor.adelantar(-5000)),
            ("F", self.visor.alternar_pantalla_completa),
            ("Ctrl+F", self.buscador.setFocus),
        ):
            atajo = QShortcut(QKeySequence(tecla), self)
            atajo.setContext(Qt.ApplicationShortcut)
            atajo.activated.connect(accion)

    # --- Filtros y categorías -----------------------------------------------

    def _cargar_filtros(self):
        anterior = self.filtro
        self.lista_filtros.blockSignals(True)
        self.lista_filtros.clear()
        total = len(self.bib.listar_archivos())
        fijos = [
            (f"Todos ({total})", ("todos", None)),
            ("Videos", ("video", None)),
            ("Imágenes", ("imagen", None)),
            ("Sin categoría", ("sin_categoria", None)),
        ]
        for texto, dato in fijos:
            item = QListWidgetItem(texto)
            item.setData(ROL, dato)
            self.lista_filtros.addItem(item)
        separador = QListWidgetItem("CATEGORÍAS")
        separador.setFlags(Qt.NoItemFlags)
        self.lista_filtros.addItem(separador)
        for cid, nombre, cantidad in self.bib.listar_categorias():
            item = QListWidgetItem(f"  {nombre}  ({cantidad})")
            item.setData(ROL, ("categoria", cid))
            self.lista_filtros.addItem(item)

        seleccion = 0
        for i in range(self.lista_filtros.count()):
            if self.lista_filtros.item(i).data(ROL) == anterior:
                seleccion = i
        self.lista_filtros.setCurrentRow(seleccion)
        self.filtro = self.lista_filtros.item(seleccion).data(ROL)
        self.lista_filtros.blockSignals(False)
        self._cargar_categorias_asignables()
        self._cargar_archivos()

    def _filtro_cambiado(self, item, _anterior):
        if item and item.data(ROL):
            self.filtro = item.data(ROL)
            self._cargar_archivos()

    def _categoria_actual(self) -> tuple[int, str] | None:
        item = self.lista_filtros.currentItem()
        if item and item.data(ROL) and item.data(ROL)[0] == "categoria":
            cid = item.data(ROL)[1]
            nombre = next(n for i, n, _ in self.bib.listar_categorias() if i == cid)
            return cid, nombre
        return None

    def _pedir_nombre(self, titulo: str, inicial: str = "") -> str | None:
        nombre, ok = QInputDialog.getText(self, titulo, "Nombre de la categoría:", text=inicial)
        nombre = nombre.strip()
        return nombre if ok and nombre else None

    def _nueva_categoria(self):
        if nombre := self._pedir_nombre("Nueva categoría"):
            try:
                self.bib.crear_categoria(nombre)
            except Exception:
                QMessageBox.warning(self, "Categoría", f"Ya existe una categoría llamada «{nombre}».")
            self._cargar_filtros()

    def _renombrar_categoria(self):
        actual = self._categoria_actual()
        if not actual:
            QMessageBox.information(self, "Categoría", "Seleccioná una categoría de la lista.")
            return
        cid, nombre = actual
        if nuevo := self._pedir_nombre("Renombrar categoría", nombre):
            try:
                self.bib.renombrar_categoria(cid, nuevo)
            except Exception:
                QMessageBox.warning(self, "Categoría", f"Ya existe una categoría llamada «{nuevo}».")
            self._cargar_filtros()

    def _borrar_categoria(self):
        actual = self._categoria_actual()
        if not actual:
            QMessageBox.information(self, "Categoría", "Seleccioná una categoría de la lista.")
            return
        cid, nombre = actual
        if QMessageBox.question(
            self, "Borrar categoría",
            f"¿Borrar la categoría «{nombre}»?\nLos archivos no se borran, solo pierden esta etiqueta.",
        ) == QMessageBox.Yes:
            self.bib.borrar_categoria(cid)
            self.filtro = ("todos", None)
            self._cargar_filtros()

    # --- Archivos -------------------------------------------------------------

    def _cargar_archivos(self):
        actual = self._archivo_actual()
        id_actual = actual[0] if actual else None
        filtro, cid = self.filtro
        filas = self.bib.listar_archivos(filtro, cid, self.buscador.text().strip())

        estilo = self.style()
        icono_video = estilo.standardIcon(QStyle.SP_MediaPlay)
        icono_imagen = estilo.standardIcon(QStyle.SP_FileDialogContentsView)
        gris = QBrush(QColor("#7a8599"))

        self.lista.blockSignals(True)
        self.lista.clear()
        seleccionar = None
        for aid, ruta, nombre, tipo in filas:
            carpeta = str(Path(ruta).parent)
            item = QTreeWidgetItem([nombre, carpeta])
            item.setIcon(0, icono_video if tipo == "video" else icono_imagen)
            item.setData(0, ROL, (aid, ruta, tipo))
            item.setToolTip(0, ruta)
            item.setToolTip(1, ruta)
            if not Path(ruta).exists():
                item.setForeground(0, gris)
                item.setText(1, f"{carpeta}  (no encontrado)")
            self.lista.addTopLevelItem(item)
            if aid == id_actual:
                seleccionar = item
        self.lista.blockSignals(False)
        self.lbl_cantidad.setText(f"{len(filas)} archivo(s)")

        if seleccionar:
            self.lista.setCurrentItem(seleccionar)
        else:
            self.visor.mostrar(None, None)
            self._mostrar_detalles(None)

    def _archivo_actual(self) -> tuple[int, str, str] | None:
        item = self.lista.currentItem()
        return item.data(0, ROL) if item else None

    def _archivo_cambiado(self, item, _anterior):
        datos = item.data(0, ROL) if item else None
        if datos:
            _, ruta, tipo = datos
            self.visor.mostrar(ruta, tipo)
        else:
            self.visor.mostrar(None, None)
        self._mostrar_detalles(datos)

    def _mostrar_detalles(self, datos):
        self.detalles.setEnabled(datos is not None)
        if datos is None:
            self.lbl_nombre.setText("Ningún archivo seleccionado")
            self.txt_ruta.clear()
        else:
            aid, ruta, tipo = datos
            self.lbl_nombre.setText(("🎬 " if tipo == "video" else "🖼 ") + Path(ruta).name)
            self.txt_ruta.setText(ruta)
            self.txt_ruta.setCursorPosition(0)
        self._marcar_categorias_asignadas()

    def _cargar_categorias_asignables(self):
        self.lista_asignar.blockSignals(True)
        self.lista_asignar.clear()
        for cid, nombre, _ in self.bib.listar_categorias():
            item = QListWidgetItem(nombre)
            item.setData(ROL, cid)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.lista_asignar.addItem(item)
        if self.lista_asignar.count() == 0:
            vacio = QListWidgetItem("Creá categorías con «+ Nueva»")
            vacio.setFlags(Qt.NoItemFlags)
            self.lista_asignar.addItem(vacio)
        self.lista_asignar.blockSignals(False)
        self._marcar_categorias_asignadas()

    def _marcar_categorias_asignadas(self):
        actual = self._archivo_actual()
        asignadas = self.bib.categorias_de(actual[0]) if actual else set()
        self.lista_asignar.blockSignals(True)
        for i in range(self.lista_asignar.count()):
            item = self.lista_asignar.item(i)
            if item.data(ROL) is not None:
                item.setCheckState(Qt.Checked if item.data(ROL) in asignadas else Qt.Unchecked)
        self.lista_asignar.blockSignals(False)

    def _asignacion_cambiada(self, item: QListWidgetItem):
        actual = self._archivo_actual()
        if not actual:
            return
        self.bib.asignar(actual[0], item.data(ROL), item.checkState() == Qt.Checked)
        self._actualizar_conteos()

    def _actualizar_conteos(self):
        """Refresca los números de la columna izquierda sin recargar la lista de archivos."""
        conteos = {cid: (nombre, n) for cid, nombre, n in self.bib.listar_categorias()}
        for i in range(self.lista_filtros.count()):
            item = self.lista_filtros.item(i)
            dato = item.data(ROL)
            if dato and dato[0] == "categoria" and dato[1] in conteos:
                nombre, n = conteos[dato[1]]
                item.setText(f"  {nombre}  ({n})")

    def _mover(self, paso: int):
        total = self.lista.topLevelItemCount()
        if total == 0:
            return
        actual = self.lista.indexOfTopLevelItem(self.lista.currentItem()) if self.lista.currentItem() else -1
        self.lista.setCurrentItem(self.lista.topLevelItem((actual + paso) % total))

    def _quitar_archivo(self):
        actual = self._archivo_actual()
        if actual and QMessageBox.question(
            self, "Quitar archivo",
            "¿Quitar este archivo de la biblioteca?\nEl archivo NO se borra del disco.",
        ) == QMessageBox.Yes:
            self.visor.mostrar(None, None)
            self.bib.quitar_archivo(actual[0])
            self._cargar_filtros()

    def _abrir_ubicacion(self):
        ruta = self.txt_ruta.text()
        if not ruta:
            return
        if not Path(ruta).exists():
            QMessageBox.warning(self, "Ubicación", "El archivo ya no está en esa ubicación.")
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", ruta])
        else:
            subprocess.Popen(["xdg-open", str(Path(ruta).parent)])

    # --- Importar -------------------------------------------------------------

    def _agregar_archivos(self):
        patrones = " ".join(f"*{e}" for e in sorted(EXT_VIDEO | EXT_IMAGEN))
        rutas, _ = QFileDialog.getOpenFileNames(self, "Agregar archivos", "", f"Videos e imágenes ({patrones})")
        if rutas:
            self._importado(self.bib.agregar_archivos([Path(r) for r in rutas]))

    def _agregar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Agregar carpeta (incluye subcarpetas)")
        if carpeta:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                nuevos = self.bib.agregar_carpeta(Path(carpeta))
            finally:
                QApplication.restoreOverrideCursor()
            self._importado(nuevos)

    def _importado(self, nuevos: int):
        self._cargar_filtros()
        self.statusBar().showMessage(f"{nuevos} archivo(s) nuevo(s) agregado(s)", 5000)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        archivos, nuevos = [], 0
        for url in e.mimeData().urls():
            ruta = Path(url.toLocalFile())
            if ruta.is_dir():
                nuevos += self.bib.agregar_carpeta(ruta)
            elif ruta.is_file():
                archivos.append(ruta)
        nuevos += self.bib.agregar_archivos(archivos)
        self._importado(nuevos)
