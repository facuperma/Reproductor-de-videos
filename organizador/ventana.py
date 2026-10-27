"""Ventana principal: filtros/categorías, lista de archivos, visor y detalles."""
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QStyle, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .db import CATEGORIA_DOMINIO_PUBLICO, EXT_IMAGEN, EXT_VIDEO, Biblioteca
from .descargas import GestorDescargas
from .dialogo_config import DialogoConfig
from .dominio_publico import VentanaDominioPublico, eliminar_video
from .subtitulos import EXT_SUBTITULOS
from .titulos import titulo_de
from .vigilancia import Vigilante
from .subtitulos_online import buscar_para_visor
from .ventana_video import VentanaVideo
from .visor import REPRODUCIR, SI_ES_LARGO, VISTA_PREVIA, Visor, atajos_reproductor

ROL = Qt.UserRole
FILTROS_FIJOS = {
    ("todos", None): "Todos",
    ("video", None): "Videos",
    ("imagen", None): "Imágenes",
    ("sin_categoria", None): "Sin categoría",
}


class Ventana(QMainWindow):
    def __init__(self, biblioteca: Biblioteca):
        super().__init__()
        self.bib = biblioteca
        self.filtro = ("todos", None)
        # Cómo arranca el video al elegirlo en la lista: con un clic, solo vista previa
        self._modo_seleccion = VISTA_PREVIA
        self.ventanas_video: list[VentanaVideo] = []
        self.ventana_dominio: VentanaDominioPublico | None = None
        self.gestor = GestorDescargas(biblioteca.ruta_db)
        self.gestor.pelicula_lista.connect(self._pelicula_descargada)
        self.vigilante = Vigilante(biblioteca.ruta_db)
        self.vigilante.archivos_nuevos.connect(self._videos_encontrados)
        self.vigilante.movido.connect(self._video_movido)
        self.gestor.mensaje.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self.setWindowTitle("TVon")
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

        self.izq = izq = QWidget()
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
        # Arrastrar con el mouse (o Ctrl/Shift + clic) selecciona varios archivos
        self.lista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lista.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.lista.header().resizeSection(0, 260)
        self.lista.currentItemChanged.connect(self._archivo_cambiado)
        self.lista.itemDoubleClicked.connect(lambda item: self._abrir_en_ventana([item.data(0, ROL)]))
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu_archivos)
        self.lista.itemSelectionChanged.connect(self._actualizar_boton_titulo)
        self.lbl_cantidad = QLabel()
        # Con un solo archivo seleccionado: crear una categoría con el título de la película o serie
        self.btn_categoria_titulo = QPushButton(objectName="chico")
        self.btn_categoria_titulo.clicked.connect(self._categoria_desde_titulo)
        self.btn_categoria_titulo.hide()
        self.btn_eliminar = QPushButton("🗑 Eliminar", objectName="chico",
                                        toolTip="Mandar los archivos seleccionados a la Papelera de reciclaje (Supr)")
        self.btn_eliminar.clicked.connect(self._eliminar_del_disco)
        self.btn_eliminar.hide()
        QShortcut(QKeySequence.Delete, self.lista, activated=self._eliminar_del_disco,
                  context=Qt.WidgetShortcut)

        self.centro = centro = QWidget()
        capa_centro = QVBoxLayout(centro)
        capa_centro.addWidget(self.lista, 1)
        fila_pie = QHBoxLayout()
        fila_pie.addWidget(self.lbl_cantidad, 1)
        fila_pie.addWidget(self.btn_categoria_titulo)
        fila_pie.addWidget(self.btn_eliminar)
        capa_centro.addLayout(fila_pie)

        # --- Columna derecha: visor y detalles ------------------------------
        self.visor = Visor()
        self.visor.pedir_pantalla_completa.connect(self._alternar_pantalla_completa)
        self.visor.subtitulos_cambiados.connect(self.bib.guardar_subtitulos)
        self.visor.buscar_siguiente = self.bib.siguiente_en_categoria
        self.visor.reproducir_siguiente.connect(self._reproducir_capitulo)
        self.visor.buscar_subtitulos_online.connect(lambda _: buscar_para_visor(self.visor, self.bib, self))
        self.visor.pedir_apagado.connect(self._apagar_computadora)
        self.chk_apagar = QCheckBox("⏻ Apagar al terminar",
                                    toolTip="Apaga la computadora cuando termine el video que se está viendo")
        self.chk_apagar.toggled.connect(self._apagar_al_terminar)
        self.visor.agregar_control(self.chk_apagar)

        self.lbl_nombre = QLabel(objectName="titulo")
        self.lbl_nombre.setWordWrap(True)
        self.txt_ruta = QLineEdit(readOnly=True, placeholderText="Ubicación del archivo")
        btn_abrir = QPushButton("Abrir ubicación")
        btn_copiar = QPushButton("Copiar ruta")
        btn_abrir.clicked.connect(lambda: self._abrir_ubicacion())
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
        btn_ventana = QPushButton("⧉ Abrir en ventana", toolTip="Abrir en una ventana aparte (o doble clic en la lista)")
        btn_quitar = QPushButton("Quitar de la biblioteca")
        btn_ant.clicked.connect(lambda: self._mover(-1))
        btn_sig.clicked.connect(lambda: self._mover(1))
        btn_ventana.clicked.connect(lambda: self._abrir_en_ventana([self._archivo_actual()]))
        btn_quitar.clicked.connect(self._quitar_archivo)
        fila_nav = QHBoxLayout()
        fila_nav.addWidget(btn_ant)
        fila_nav.addWidget(btn_sig)
        fila_nav.addWidget(btn_ventana)
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
        self.capa_der = capa_der = QVBoxLayout(der)
        self._margenes_der = capa_der.contentsMargins()
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
        self.gestor.iniciar()
        self.vigilante.iniciar()

    # --- Construcción -------------------------------------------------------

    def _crear_barra(self):
        self.barra_herramientas = barra = QToolBar("Principal", movable=False)
        self.addToolBar(barra)
        estilo = self.style()
        acc_archivos = QAction(estilo.standardIcon(QStyle.SP_FileIcon), "Agregar archivos", self)
        acc_carpeta = QAction(estilo.standardIcon(QStyle.SP_DirOpenIcon), "Agregar carpeta", self)
        acc_archivos.triggered.connect(self._agregar_archivos)
        acc_carpeta.triggered.connect(self._agregar_carpeta)
        barra.addAction(acc_archivos)
        barra.addAction(acc_carpeta)
        barra.addSeparator()
        barra.addAction("🎞 Dominio público", self._abrir_dominio_publico)
        barra.addAction("⚙ Configuración", self._abrir_configuracion)
        barra.addSeparator()
        # Accesos a páginas externas: se abren en el navegador
        for texto, url in (("🌐 Películas", "https://ext.to/"), ("🌐 Subtítulos", "https://subdivx.com/")):
            accion = barra.addAction(texto, lambda u=url: QDesktopServices.openUrl(QUrl(u)))
            accion.setToolTip(f"Abrir {url} en el navegador")
        barra.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        espacio = QWidget()
        espacio.setFixedWidth(20)
        barra.addWidget(espacio)
        self.buscador = QLineEdit(placeholderText="Buscar por nombre…", clearButtonEnabled=True)
        self.buscador.setMaximumWidth(320)
        self.buscador.textChanged.connect(lambda _: self._cargar_archivos())
        barra.addWidget(self.buscador)

    def _atajos(self):
        atajos_reproductor(self, self.visor, self._alternar_pantalla_completa)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._enfocar_buscador)

    def _enfocar_buscador(self):
        if self.isFullScreen():
            self._alternar_pantalla_completa()
        self.buscador.setFocus()

    def _alternar_pantalla_completa(self):
        """Pantalla completa propia: se oculta todo menos el visor."""
        completa = not self.isFullScreen()
        for w in (self.izq, self.centro, self.detalles, self.barra_herramientas, self.statusBar()):
            w.setVisible(not completa)
        if completa:
            self._estaba_maximizada = self.isMaximized()
            self.capa_der.setContentsMargins(0, 0, 0, 0)
            self.showFullScreen()
        else:
            self.capa_der.setContentsMargins(self._margenes_der)
            if self._estaba_maximizada:
                self.showMaximized()
            else:
                self.showNormal()
        self.visor.set_modo_completo(completa)

    # --- Filtros y categorías -----------------------------------------------

    def _cargar_filtros(self):
        anterior = self.filtro
        self.lista_filtros.blockSignals(True)
        self.lista_filtros.clear()
        for dato in FILTROS_FIJOS:
            item = QListWidgetItem()
            item.setData(ROL, dato)
            self.lista_filtros.addItem(item)
        separador = QListWidgetItem("CATEGORÍAS")
        separador.setFlags(Qt.NoItemFlags)
        self.lista_filtros.addItem(separador)
        for cid, _nombre, _cantidad in self.bib.listar_categorias():
            item = QListWidgetItem()
            item.setData(ROL, ("categoria", cid))
            self.lista_filtros.addItem(item)
        self._actualizar_conteos()

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
            # Categoría con un solo video (una película): se elige sola y, si dura más de una hora, arranca
            if self.filtro[0] == "categoria" and self.lista.topLevelItemCount() == 1:
                unico = self.lista.topLevelItem(0)
                if unico.data(0, ROL)[2] == "video" and unico is not self.lista.currentItem():
                    self._seleccionar(unico, SI_ES_LARGO)

    def _seleccionar(self, item: QTreeWidgetItem, modo: str):
        self._modo_seleccion = modo
        try:
            self.lista.setCurrentItem(item)
        finally:
            self._modo_seleccion = VISTA_PREVIA

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
        """Recarga la lista según el filtro, conservando la selección que siga visible."""
        actual = self._archivo_actual()
        id_actual = actual[0] if actual else None
        ids_seleccionados = set(self._ids_seleccionados())
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
            if aid in ids_seleccionados:
                item.setSelected(True)
        # Con las señales bloqueadas, si el archivo actual sigue en la lista
        # el video no se reinicia.
        if seleccionar:
            self.lista.setCurrentItem(seleccionar, 0, QItemSelectionModel.NoUpdate)
        self.lista.blockSignals(False)
        self.lbl_cantidad.setText(f"{len(filas)} archivo(s)")

        if seleccionar:
            self._marcar_categorias_asignadas()
        else:
            self.visor.mostrar(None, None)
            self._mostrar_detalles(None)

    def _ids_seleccionados(self) -> list[int]:
        return [item.data(0, ROL)[0] for item in self.lista.selectedItems()]

    def _menu_archivos(self, pos):
        item = self.lista.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            # Seleccionar sin cambiar el archivo actual, así no se corta el video que se está viendo
            self.lista.clearSelection()
            item.setSelected(True)
        ids = self._ids_seleccionados()
        n = len(ids)
        categorias = self.bib.listar_categorias()

        menu = QMenu(self)
        seleccion = [i.data(0, ROL) for i in self.lista.selectedItems()]
        menu.addAction(f"⧉ Abrir en ventana nueva ({n})", lambda: self._abrir_en_ventana(seleccion))
        videos = [ruta for _aid, ruta, tipo in seleccion if tipo == "video"]
        menu.addAction(f"☰ Agregar a la cola ({len(videos)})", lambda: self._encolar(videos)).setEnabled(bool(videos))
        menu.addSeparator()
        asignar = menu.addMenu(f"Asignar a categoría ({n})")
        for cid, nombre, _ in categorias:
            asignar.addAction(nombre, lambda c=cid, nom=nombre: self._asignar_seleccion(ids, c, nom, True))
        if categorias:
            asignar.addSeparator()
        asignar.addAction("Nueva categoría…", lambda: self._asignar_a_nueva(ids))

        # Solo ofrece quitar las categorías que tenga algún archivo seleccionado
        presentes = set().union(*(self.bib.categorias_de(a) for a in ids))
        quitar = menu.addMenu(f"Quitar de categoría ({n})")
        for cid, nombre, _ in categorias:
            if cid in presentes:
                quitar.addAction(nombre, lambda c=cid, nom=nombre: self._asignar_seleccion(ids, c, nom, False))
        quitar.setEnabled(bool(presentes))

        menu.addSeparator()
        if n == 1:
            menu.addAction(self.btn_categoria_titulo.text(), self._categoria_desde_titulo)
            menu.addAction("Abrir ubicación", lambda: self._abrir_ubicacion(seleccion[0][1]))
        menu.addAction(f"Quitar de la biblioteca ({n})", self._quitar_archivo)
        menu.addAction(f"🗑 Eliminar del disco ({n})…", self._eliminar_del_disco)
        menu.exec(self.lista.viewport().mapToGlobal(pos))

    def _asignar_seleccion(self, ids: list[int], cid: int, nombre: str, activa: bool):
        self.bib.asignar_varios(ids, cid, activa)
        self._actualizar_conteos()
        self._cargar_archivos()
        verbo = "asignado(s) a" if activa else "quitado(s) de"
        self.statusBar().showMessage(f"{len(ids)} archivo(s) {verbo} «{nombre}»", 5000)

    def _asignar_a_nueva(self, ids: list[int]):
        if not (nombre := self._pedir_nombre("Nueva categoría")):
            return
        try:
            self.bib.crear_categoria(nombre)
        except Exception:
            QMessageBox.warning(self, "Categoría", f"Ya existe una categoría llamada «{nombre}».")
            return
        cid = next(c for c, n, _ in self.bib.listar_categorias() if n == nombre)
        self.bib.asignar_varios(ids, cid, True)
        self._cargar_filtros()
        self.statusBar().showMessage(f"{len(ids)} archivo(s) asignado(s) a «{nombre}»", 5000)

    def _archivo_actual(self) -> tuple[int, str, str] | None:
        item = self.lista.currentItem()
        return item.data(0, ROL) if item else None

    def _archivo_cambiado(self, item, _anterior):
        datos = item.data(0, ROL) if item else None
        if datos:
            _, ruta, tipo = datos
            self.visor.mostrar(ruta, tipo, self.bib.subtitulos_de(ruta), modo=self._modo_seleccion)
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
        self._cargar_archivos()

    def _actualizar_conteos(self):
        """Refresca los números de la columna izquierda sin recargar la lista de archivos."""
        conteos = {cid: (nombre, n) for cid, nombre, n in self.bib.listar_categorias()}
        for i in range(self.lista_filtros.count()):
            item = self.lista_filtros.item(i)
            dato = item.data(ROL)
            if dato in FILTROS_FIJOS:
                n = len(self.bib.listar_archivos(dato[0]))
                item.setText(f"{FILTROS_FIJOS[dato]}  ({n})")
            elif dato and dato[0] == "categoria" and dato[1] in conteos:
                nombre, n = conteos[dato[1]]
                item.setText(f"  {nombre}  ({n})")

    def _mover(self, paso: int):
        total = self.lista.topLevelItemCount()
        if total == 0:
            return
        actual = self.lista.indexOfTopLevelItem(self.lista.currentItem()) if self.lista.currentItem() else -1
        self.lista.setCurrentItem(self.lista.topLevelItem((actual + paso) % total))

    def _quitar_archivo(self):
        ids = self._ids_seleccionados()
        if ids and QMessageBox.question(
            self, "Quitar archivos",
            f"¿Quitar {len(ids)} archivo(s) de la biblioteca?\nLos archivos NO se borran del disco.",
        ) == QMessageBox.Yes:
            self.visor.mostrar(None, None)
            self.bib.quitar_archivos(ids)
            self._cargar_filtros()

    def _eliminar_del_disco(self):
        seleccion = [i.data(0, ROL) for i in self.lista.selectedItems()]
        if not seleccion:
            return
        nombres = "\n".join(f"• {Path(ruta).name}" for _aid, ruta, _tipo in seleccion[:8])
        if len(seleccion) > 8:
            nombres += f"\n… y {len(seleccion) - 8} más"
        if QMessageBox.question(
            self, "Eliminar del disco",
            f"¿Mandar {len(seleccion)} archivo(s) a la Papelera de reciclaje?\n\n{nombres}\n\n"
            "También se borran sus subtítulos y se quitan de la biblioteca. "
            "Se pueden recuperar desde la Papelera.",
        ) != QMessageBox.Yes:
            return
        fallidos, borrados = [], []
        for aid, ruta, _tipo in seleccion:
            self._soltar_archivo(ruta)
            fallidos += eliminar_video(ruta)
            if not Path(ruta).exists():
                borrados.append(aid)
                self.bib.marcar_descarga_eliminada(ruta)
        self.bib.quitar_archivos(borrados)
        self._cargar_filtros()
        self.statusBar().showMessage(f"{len(borrados)} archivo(s) enviado(s) a la Papelera", 8000)
        if fallidos:
            QMessageBox.warning(self, "Eliminar del disco",
                                "No se pudieron mover a la Papelera (¿están abiertos en otro programa?):\n\n"
                                + "\n".join(fallidos))

    def _encolar(self, rutas: list[str]):
        agregados = self.visor.encolar(rutas)
        self.statusBar().showMessage(
            f"{agregados} video(s) agregado(s) a la cola · {len(self.visor.cola)} en espera", 6000)

    # --- Apagar al terminar -------------------------------------------------------

    def _apagar_al_terminar(self, activo: bool):
        for visor in [self.visor, *(v.visor for v in self.ventanas_video)]:
            visor.apagar_al_terminar = activo
            visor.panel_sig.hide()
        self.visor.pantalla.mostrar_osd("La computadora se apagará al terminar el video" if activo
                                        else "Apagado automático desactivado")

    def _apagar_computadora(self):
        """Cuenta regresiva con opción de cancelar antes de apagar."""
        self.chk_apagar.setChecked(False)  # es para una sola vez
        segundos = [60]
        aviso = QMessageBox(QMessageBox.Warning, "Apagar la computadora", "", parent=self)
        aviso.setWindowFlag(Qt.WindowStaysOnTopHint)
        aviso.setStandardButtons(QMessageBox.Cancel)
        aviso.addButton("Apagar ahora", QMessageBox.AcceptRole)
        reloj = QTimer(aviso, interval=1000)

        def tic():
            if segundos[0] <= 0:
                reloj.stop()
                aviso.done(QMessageBox.AcceptRole)
                return
            aviso.setText(f"Terminó el video. La computadora se apaga en {segundos[0]} s.")
            segundos[0] -= 1

        reloj.timeout.connect(tic)
        tic()
        reloj.start()
        aviso.exec()
        reloj.stop()
        if aviso.clickedButton() is aviso.button(QMessageBox.Cancel):
            self.statusBar().showMessage("Apagado cancelado", 5000)
            return
        if sys.platform == "win32":
            subprocess.Popen(["shutdown", "/s", "/t", "0"])
        else:
            subprocess.Popen(["systemctl", "poweroff"])

    def _reproducir_capitulo(self, ruta: str):
        """Pasa al siguiente capítulo seleccionándolo en la lista, si está visible."""
        for i in range(self.lista.topLevelItemCount()):
            item = self.lista.topLevelItem(i)
            if item.data(0, ROL)[1] == ruta:
                self._seleccionar(item, REPRODUCIR)
                self.lista.scrollToItem(item)
                return
        # Con un filtro o búsqueda que lo oculta, se reproduce igual
        self.visor.mostrar(ruta, "video", self.bib.subtitulos_de(ruta))

    # --- Ventanas flotantes ---------------------------------------------------

    def _abrir_en_ventana(self, archivos: list):
        archivos = [a for a in archivos if a]
        if len(archivos) > 4 and QMessageBox.question(
            self, "Abrir en ventanas", f"¿Abrir {len(archivos)} ventanas a la vez?"
        ) != QMessageBox.Yes:
            return
        for _aid, ruta, tipo in archivos:
            posicion = 0
            # Si es el video del visor principal, sigue desde el mismo punto en la ventana
            if ruta == self.visor.ruta_video:
                posicion = self.visor.posicion_actual()
                self.visor.mostrar(None, None, aviso_vacio="Se está reproduciendo en una ventana aparte")
            ventana = VentanaVideo(self.bib, ruta, tipo, posicion)
            ventana.cerrada.connect(self.ventanas_video.remove)
            ventana.visor.apagar_al_terminar = self.chk_apagar.isChecked()
            ventana.visor.pedir_apagado.connect(self._apagar_computadora)
            # En cascada para que no queden una encima de la otra
            desplazamiento = 40 * (len(self.ventanas_video) % 8)
            ventana.move(self.pos() + QPoint(120 + desplazamiento, 100 + desplazamiento))
            self.ventanas_video.append(ventana)
            ventana.show()

    def closeEvent(self, e):
        # Una descarga a medias queda en cola y se retoma al volver a abrir TVon
        self.gestor.detener()
        self.vigilante.detener()
        for ventana in [*self.ventanas_video, self.ventana_dominio]:
            if ventana:
                ventana.close()
        super().closeEvent(e)

    # --- Dominio público --------------------------------------------------------

    def _abrir_dominio_publico(self):
        if self.ventana_dominio is None:
            self.ventana_dominio = VentanaDominioPublico(self.bib, self.gestor)
            self.ventana_dominio.pelicula_por_eliminar.connect(self._soltar_archivo)
            self.ventana_dominio.biblioteca_cambiada.connect(self._cargar_filtros)
        self.ventana_dominio.show()
        self.ventana_dominio.raise_()
        self.ventana_dominio.activateWindow()

    # --- Biblioteca automática ----------------------------------------------------

    def _abrir_configuracion(self):
        if DialogoConfig(self.bib, self).exec():
            self.vigilante.despertar()

    def _videos_encontrados(self, cantidad: int):
        self._cargar_filtros()
        self.statusBar().showMessage(f"{cantidad} video(s) nuevo(s) en tus carpetas", 8000)

    def _video_movido(self, ruta: str):
        self._cargar_filtros()
        self.statusBar().showMessage(f"Movido de Descargas a {Path(ruta).parent.name}: {Path(ruta).name}", 8000)

    # --- Categoría desde el título -------------------------------------------------

    def _actualizar_boton_titulo(self):
        seleccion = self.lista.selectedItems()
        self.btn_eliminar.setVisible(bool(seleccion))
        self.btn_eliminar.setText(f"🗑 Eliminar ({len(seleccion)})" if len(seleccion) > 1 else "🗑 Eliminar")
        if len(seleccion) == 1:
            titulo = titulo_de(seleccion[0].text(0))
            self.btn_categoria_titulo.setText(f"＋ Categoría: {titulo}")
            self.btn_categoria_titulo.setToolTip(
                f"Crea la categoría «{titulo}» y le asigna este archivo y los demás con el mismo título")
            self.btn_categoria_titulo.show()
        else:
            self.btn_categoria_titulo.hide()

    def _categoria_desde_titulo(self):
        seleccion = self.lista.selectedItems()
        if len(seleccion) != 1:
            return
        titulo = titulo_de(seleccion[0].text(0))
        existia = any(nombre.lower() == titulo.lower() for _, nombre, _ in self.bib.listar_categorias())
        cid = self.bib.categoria_id(titulo)
        # También los demás capítulos de la misma serie (mismo título)
        ids = [aid for aid, _ruta, nombre, _tipo in self.bib.listar_archivos()
               if titulo_de(nombre).lower() == titulo.lower()]
        self.bib.asignar_varios(ids, cid, True)
        self._cargar_filtros()
        accion = "Se sumaron a la categoría" if existia else "Categoría creada"
        self.statusBar().showMessage(f"{accion} «{titulo}»: {len(ids)} archivo(s)", 8000)

    def _soltar_archivo(self, ruta: str):
        """Deja de reproducir un archivo que se va a borrar (Windows no deja borrar uno abierto)."""
        objetivo = Path(ruta).resolve()
        for visor in [self.visor, *(v.visor for v in self.ventanas_video)]:
            visor.quitar_de_cola(ruta)
        if self.visor.ruta_video and Path(self.visor.ruta_video).resolve() == objetivo:
            self.visor.mostrar(None, None)
        for ventana in list(self.ventanas_video):
            if ventana.visor.ruta_video and Path(ventana.visor.ruta_video).resolve() == objetivo:
                ventana.close()
        QApplication.processEvents()  # que el reproductor termine de cerrar el archivo

    def _pelicula_descargada(self, ruta: str):
        self.bib.agregar_archivos([Path(ruta)])
        if (aid := self.bib.id_de_ruta(str(Path(ruta).resolve()))) is not None:
            self.bib.asignar(aid, self.bib.categoria_id(CATEGORIA_DOMINIO_PUBLICO), True)
        self._cargar_filtros()
        self.statusBar().showMessage(f"Descargada y agregada a la biblioteca: {Path(ruta).stem}", 8000)

    def _abrir_ubicacion(self, ruta: str | None = None):
        ruta = ruta or self.txt_ruta.text()
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
            # Un .srt/.vtt soltado se carga como subtítulo del video actual
            if ruta.suffix.lower() in EXT_SUBTITULOS:
                if not self.visor.cargar_subtitulos(str(ruta)):
                    self.statusBar().showMessage("Abrí un video antes de soltar los subtítulos", 5000)
                continue
            if ruta.is_dir():
                nuevos += self.bib.agregar_carpeta(ruta)
            elif ruta.is_file():
                archivos.append(ruta)
        nuevos += self.bib.agregar_archivos(archivos)
        if nuevos or archivos:
            self._importado(nuevos)
