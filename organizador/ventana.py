"""Ventana principal: filtros/categorías, lista de archivos, visor y detalles."""
import platform
from html import escape
import subprocess
import sys
from pathlib import Path

from PySide6 import __version__ as VERSION_QT
from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, QTimer, QUrl, QUrlQuery
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter, QStyle, QToolBar,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .aviso import AvisoFlotante
from .db import CATEGORIA_DOMINIO_PUBLICO, CATEGORIA_FAVORITOS, EXT_IMAGEN, EXT_VIDEO, Biblioteca
from .descargas import GestorDescargas
from .dialogo_config import DialogoConfig
from .dialogo_on import DialogoOn
from .dominio_publico import VentanaDominioPublico, eliminar_video
from .remoto import Remoto
from .subtitulos import EXT_SUBTITULOS
from .titulos import titulo_de
from .torrents import GestorTorrents
from .descargas import nombre_seguro
from .vigilancia import Vigilante, borrar_carpetas_vacias, en_uso, mover_video
from .subtitulos_online import buscar_para_visor, subtitulos_automaticos
from .ventana_torrents import VentanaTorrents
from .ventana_video import VentanaVideo
from .visor import REPRODUCIR, VISTA_PREVIA, Visor, atajos_reproductor

ROL = Qt.UserRole
FILTROS_FIJOS = {
    ("todos", None): "Todos",
    ("video", None): "Videos",
    ("imagen", None): "Imágenes",
    ("sin_categoria", None): "Sin categoría",
}
REPOSITORIO = "https://github.com/facuperma/Reproductor-de-videos"
AUTOR = "Faierwall"


class Ventana(QMainWindow):
    def __init__(self, biblioteca: Biblioteca):
        super().__init__()
        self.bib = biblioteca
        self.filtro = ("todos", None)
        # Cómo arranca el video al elegirlo en la lista: con un clic, solo vista previa
        self._modo_seleccion = VISTA_PREVIA
        self.ventanas_video: list[VentanaVideo] = []
        self.ventana_dominio: VentanaDominioPublico | None = None
        self.ventana_torrents: VentanaTorrents | None = None
        self.aviso: AvisoFlotante | None = None
        self.dialogo_on: DialogoOn | None = None
        # (aviso, [segundos que faltan], botón «Apagar ahora») mientras corre la cuenta para apagar
        self.apagado_pendiente = None
        self.gestor = GestorDescargas(biblioteca.ruta_db)
        self.gestor.pelicula_lista.connect(self._pelicula_descargada)
        self.vigilante = Vigilante(biblioteca.ruta_db)
        self.vigilante.archivos_nuevos.connect(self._videos_encontrados)
        self.vigilante.movido.connect(self._video_movido)
        self.vigilante.descargado.connect(lambda ruta: self._buscar_subtitulos_solos([ruta]))
        self.vigilante.subtitulo_listo.connect(self._subtitulo_listo)
        self.vigilante.subtitulo_fallido.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self.gestor.mensaje.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self.torrents = GestorTorrents(biblioteca.ruta_db)
        self.torrents.terminado.connect(self._torrent_terminado)
        self.torrents.estado.connect(self._insignia_torrents)
        self.torrents.mensaje.connect(lambda m: self.statusBar().showMessage(m, 8000))
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
        self.lista.itemDoubleClicked.connect(lambda item: self.abrir_en_ventana([item.data(0, ROL)]))
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
        self.visor.pedir_pantalla_completa.connect(self.alternar_pantalla_completa)
        self.visor.subtitulos_cambiados.connect(self.bib.guardar_subtitulos)
        self.visor.buscar_siguiente = self.bib.siguiente_en_categoria
        self.visor.reproducir_siguiente.connect(self.reproducir)
        self.visor.buscar_subtitulos_online.connect(lambda _: buscar_para_visor(self.visor, self.bib, self))
        self.visor.buscar_subtitulos_subdivx.connect(self._buscar_en_subdivx)
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
        btn_abrir.clicked.connect(lambda: self.abrir_ubicacion())
        btn_copiar.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_ruta.text()))
        fila_ruta = QHBoxLayout()
        fila_ruta.addWidget(self.txt_ruta, 1)
        fila_ruta.addWidget(btn_abrir)
        fila_ruta.addWidget(btn_copiar)

        # Solo las categorías del archivo; se cambian desde el menú «Editar»
        self.chips = QWidget()
        self.chips.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.capa_chips = QHBoxLayout(self.chips)
        self.capa_chips.setContentsMargins(0, 0, 0, 0)
        self.btn_editar_cat = QToolButton(text="✎ Editar", popupMode=QToolButton.InstantPopup,
                                          toolTip="Asignar o quitar categorías")
        self.menu_editar_cat = QMenu(self)
        self.menu_editar_cat.aboutToShow.connect(self._armar_menu_categorias)
        self.btn_editar_cat.setMenu(self.menu_editar_cat)
        grupo_cat = QGroupBox("Categorías de este archivo")
        capa_cat = QHBoxLayout(grupo_cat)
        capa_cat.addWidget(self.chips, 1)
        capa_cat.addWidget(self.btn_editar_cat)

        btn_ant = QPushButton("◀ Anterior")
        btn_sig = QPushButton("Siguiente ▶")
        btn_ventana = QPushButton("⧉ Abrir en ventana", toolTip="Abrir en una ventana aparte (o doble clic en la lista)")
        btn_quitar = QPushButton("Quitar de la biblioteca")
        btn_ant.clicked.connect(lambda: self.mover(-1))
        btn_sig.clicked.connect(lambda: self.mover(1))
        btn_ventana.clicked.connect(lambda: self.abrir_en_ventana([self.archivo_actual()]))
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

        self._crear_menu()
        self._atajos()
        self._crear_on()
        self.cargar_filtros()
        self._mostrar_detalles(None)
        self.gestor.iniciar()
        self.vigilante.iniciar()
        self.torrents.iniciar()

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
        self.acc_torrents = barra.addAction("🧲 Torrents", self._abrir_torrents)
        self.acc_torrents.setToolTip("Descargar películas con un link magnet o un archivo .torrent")
        barra.addAction("⚙ Configuración", self._abrir_configuracion)
        self.acc_on = barra.addAction("📱 OFF", self._abrir_on)
        self.acc_on.setToolTip("Manejar TVon desde el celular")
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

    def _crear_menu(self):
        barra = self.menuBar()

        archivo = barra.addMenu("&Archivo")
        archivo.addAction("Agregar archivos…", QKeySequence("Ctrl+O"), self._agregar_archivos)
        archivo.addAction("Agregar carpeta…", QKeySequence("Ctrl+Shift+O"), self._agregar_carpeta)
        archivo.addSeparator()
        archivo.addAction("Abrir ubicación del archivo", self.abrir_ubicacion)
        archivo.addAction("Películas de dominio público…", self._abrir_dominio_publico)
        archivo.addAction("Torrents…", self._abrir_torrents)
        archivo.addSeparator()
        archivo.addAction("Salir", QKeySequence("Ctrl+Q"), self.close)

        vista = barra.addMenu("&Vista")
        # El atajo F ya lo maneja el reproductor: acá solo se muestra
        vista.addAction("Pantalla completa\tF", self.alternar_pantalla_completa)
        vista.addAction("Buscar\tCtrl+F", self._enfocar_buscador)
        vista.addSeparator()
        self._paneles = {}
        for texto, panel in (("Barra de herramientas", self.barra_herramientas),
                             ("Panel de categorías", self.izq),
                             ("Detalles del archivo", self.detalles),
                             ("Barra de estado", self.statusBar())):
            accion = vista.addAction(texto)
            accion.setCheckable(True)
            accion.setChecked(True)
            accion.toggled.connect(panel.setVisible)
            self._paneles[panel] = accion

        config = barra.addMenu("&Configuración")
        config.addAction("Preferencias…", self._abrir_configuracion)
        config.addAction("📱 ON: manejar desde el celular…", self._abrir_on)
        apagar = config.addAction("Apagar la PC al terminar el video")
        apagar.setCheckable(True)
        apagar.toggled.connect(self.chk_apagar.setChecked)
        self.chk_apagar.toggled.connect(apagar.setChecked)

        barra.addAction("Acerca de", self._acerca_de)
        barra.addAction("Reportar un bug", self._reportar_bug)

    def _acerca_de(self):
        caja = QMessageBox(self)
        caja.setWindowTitle("Acerca de TVon")
        caja.setIconPixmap(QApplication.windowIcon().pixmap(72, 72))
        caja.setTextFormat(Qt.RichText)
        caja.setText(
            f"<h2>TVon</h2><p>Versión <b>{QApplication.applicationVersion()}</b></p>"
            "<p>Organizador y reproductor de videos e imágenes.</p>"
            f"<p>Hecho por <b>{AUTOR}</b></p>"
            f"<p>© 2026 {AUTOR} · Licencia MIT<br>"
            f"<a href='{REPOSITORIO}' style='color:#9fc2ff'>{REPOSITORIO.removeprefix('https://')}</a></p>"
        )
        caja.setInformativeText(f"Qt {VERSION_QT} · Python {platform.python_version()}")
        caja.exec()

    def _reportar_bug(self):
        """Abre un issue nuevo en GitHub con la versión y el sistema ya completos."""
        cuerpo = (
            "**¿Qué pasó?**\n\n\n"
            "**¿Qué esperabas que pasara?**\n\n\n"
            "**Pasos para reproducirlo**\n1. \n2. \n\n"
            f"---\nTVon {QApplication.applicationVersion()} · {platform.system()} {platform.release()} "
            f"({platform.version()}) · Qt {VERSION_QT}"
        )
        consulta = QUrlQuery()
        consulta.addQueryItem("title", "[Bug] ")
        consulta.addQueryItem("body", cuerpo)
        url = QUrl(f"{REPOSITORIO}/issues/new")
        url.setQuery(consulta)
        QDesktopServices.openUrl(url)
        self.statusBar().showMessage("Se abrió el formulario de reporte en el navegador", 8000)

    def _atajos(self):
        atajos_reproductor(self, self.visor, self.alternar_pantalla_completa)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._enfocar_buscador)

    def _enfocar_buscador(self):
        if self.isFullScreen():
            self.alternar_pantalla_completa()
        self.buscador.setFocus()

    def alternar_pantalla_completa(self):
        """Pantalla completa propia: se oculta todo menos el visor."""
        completa = not self.isFullScreen()
        for w in (self.izq, self.centro, self.detalles, self.barra_herramientas, self.statusBar(),
                  self.menuBar()):
            # Al salir, los paneles que se ocultaron desde el menú Vista siguen ocultos
            w.setVisible(not completa and (w not in self._paneles or self._paneles[w].isChecked()))
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

    def cargar_filtros(self):
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
        self._cargar_archivos()

    def _filtro_cambiado(self, item, _anterior):
        if item and item.data(ROL):
            self.filtro = item.data(ROL)
            self._cargar_archivos()
            # Categoría: se elige el primer video en vista previa (sin arrancar),
            # salvo que el que se está viendo también esté en ella
            if self.filtro[0] == "categoria" and self.lista.currentItem() is None:
                items = (self.lista.topLevelItem(i) for i in range(self.lista.topLevelItemCount()))
                if primero := next((it for it in items if it.data(0, ROL)[2] == "video"), None):
                    self._seleccionar(primero, VISTA_PREVIA)
                    self.lista.scrollToItem(primero)

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
            self.cargar_filtros()

    def _renombrar_categoria(self):
        actual = self._categoria_actual()
        if not actual:
            QMessageBox.information(self, "Categoría", "Seleccioná una categoría de la lista.")
            return
        cid, nombre = actual
        if cid == self.bib.favoritos:
            QMessageBox.information(self, "Categoría", "«Favoritos» es una categoría fija: no se puede renombrar.")
            return
        if nuevo := self._pedir_nombre("Renombrar categoría", nombre):
            try:
                self.bib.renombrar_categoria(cid, nuevo)
            except Exception:
                QMessageBox.warning(self, "Categoría", f"Ya existe una categoría llamada «{nuevo}».")
            self.cargar_filtros()

    def _borrar_categoria(self):
        actual = self._categoria_actual()
        if not actual:
            QMessageBox.information(self, "Categoría", "Seleccioná una categoría de la lista.")
            return
        cid, nombre = actual
        if cid == self.bib.favoritos:
            QMessageBox.information(self, "Categoría", "«Favoritos» es una categoría fija: no se puede borrar.")
            return
        if QMessageBox.question(
            self, "Borrar categoría",
            f"¿Borrar la categoría «{nombre}»?\nLos archivos no se borran, solo pierden esta etiqueta.",
        ) == QMessageBox.Yes:
            self.bib.borrar_categoria(cid)
            self.filtro = ("todos", None)
            self.cargar_filtros()

    # --- Archivos -------------------------------------------------------------

    def _cargar_archivos(self):
        """Recarga la lista según el filtro, conservando la selección que siga visible."""
        actual = self.archivo_actual()
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
            self._mostrar_categorias_archivo()
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
        menu.addAction(f"⧉ Abrir en ventana nueva ({n})", lambda: self.abrir_en_ventana(seleccion))
        videos = [ruta for _aid, ruta, tipo in seleccion if tipo == "video"]
        menu.addAction(f"☰ Agregar a la cola ({len(videos)})", lambda: self.encolar(videos)).setEnabled(bool(videos))
        menu.addSeparator()
        if all(self.bib.favoritos in self.bib.categorias_de(a) for a in ids):
            menu.addAction(f"☆ Quitar de {CATEGORIA_FAVORITOS} ({n})", lambda: self.asignar_seleccion(
                ids, self.bib.favoritos, CATEGORIA_FAVORITOS, False))
        else:
            menu.addAction(f"★ Agregar a {CATEGORIA_FAVORITOS} ({n})", lambda: self.asignar_seleccion(
                ids, self.bib.favoritos, CATEGORIA_FAVORITOS, True))
        asignar = menu.addMenu(f"Asignar a categoría ({n})")
        for cid, nombre, _ in categorias:
            asignar.addAction(nombre, lambda c=cid, nom=nombre: self.asignar_seleccion(ids, c, nom, True))
        if categorias:
            asignar.addSeparator()
        asignar.addAction("Nueva categoría…", lambda: self._asignar_a_nueva(ids))

        # Solo ofrece quitar las categorías que tenga algún archivo seleccionado
        presentes = set().union(*(self.bib.categorias_de(a) for a in ids))
        quitar = menu.addMenu(f"Quitar de categoría ({n})")
        for cid, nombre, _ in categorias:
            if cid in presentes:
                quitar.addAction(nombre, lambda c=cid, nom=nombre: self.asignar_seleccion(ids, c, nom, False))
        quitar.setEnabled(bool(presentes))

        menu.addSeparator()
        if n == 1:
            menu.addAction(self.btn_categoria_titulo.text(), self._categoria_desde_titulo)
            menu.addAction("Abrir ubicación", lambda: self.abrir_ubicacion(seleccion[0][1]))
        menu.addAction(f"Quitar de la biblioteca ({n})", self._quitar_archivo)
        menu.addAction(f"🗑 Eliminar del disco ({n})…", self._eliminar_del_disco)
        menu.exec(self.lista.viewport().mapToGlobal(pos))

    def asignar_seleccion(self, ids: list[int], cid: int, nombre: str, activa: bool):
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
        self.cargar_filtros()
        self.statusBar().showMessage(f"{len(ids)} archivo(s) asignado(s) a «{nombre}»", 5000)

    def archivo_actual(self) -> tuple[int, str, str] | None:
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
        self._mostrar_categorias_archivo()

    def _nombre_categoria(self, cid: int, nombre: str) -> str:
        return f"★ {nombre}" if cid == self.bib.favoritos else nombre

    def _mostrar_categorias_archivo(self):
        while self.capa_chips.count():
            if w := self.capa_chips.takeAt(0).widget():
                w.deleteLater()
        actual = self.archivo_actual()
        if not actual:
            return
        asignadas = self.bib.categorias_de(actual[0])
        nombres = [self._nombre_categoria(cid, nombre)
                   for cid, nombre, _ in self.bib.listar_categorias() if cid in asignadas]
        for nombre in nombres:
            self.capa_chips.addWidget(QLabel(nombre, objectName="chip"))
        if not nombres:
            self.capa_chips.addWidget(QLabel("Sin categoría", objectName="pista"))
        self.capa_chips.addStretch()
        self.chips.setToolTip(", ".join(nombres))

    def _armar_menu_categorias(self):
        m = self.menu_editar_cat
        m.clear()
        actual = self.archivo_actual()
        if not actual:
            return
        asignadas = self.bib.categorias_de(actual[0])
        for cid, nombre, _ in self.bib.listar_categorias():
            accion = m.addAction(self._nombre_categoria(cid, nombre))
            accion.setCheckable(True)
            accion.setChecked(cid in asignadas)
            accion.toggled.connect(lambda activa, c=cid: self._alternar_categoria(c, activa))
        m.addSeparator()
        m.addAction("Nueva categoría…", lambda: self._asignar_a_nueva([actual[0]]))

    def _alternar_categoria(self, cid: int, activa: bool):
        actual = self.archivo_actual()
        if not actual:
            return
        self.bib.asignar(actual[0], cid, activa)
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
                item.setText(f"  {self._nombre_categoria(dato[1], nombre)}  ({n})")

    def mover(self, paso: int):
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
            self.quitar_de_biblioteca(ids)

    def quitar_de_biblioteca(self, ids: list[int]):
        self.bib.quitar_archivos(ids)
        self.cargar_filtros()

    def eliminar_archivos(self, seleccion: list[tuple[int, str, str]]) -> tuple[int, list[str]]:
        """Manda a la Papelera los archivos (id, ruta, tipo) con sus subtítulos y los quita de la biblioteca.
        Devuelve (cuántos se borraron, nombres de los que no se pudieron mover)."""
        fallidos, borrados = [], []
        for aid, ruta, _tipo in seleccion:
            self._soltar_archivo(ruta)
            fallidos += eliminar_video(ruta)
            if not Path(ruta).exists():
                borrados.append(aid)
                self.bib.marcar_descarga_eliminada(ruta)
        self.bib.quitar_archivos(borrados)
        self.cargar_filtros()
        self.statusBar().showMessage(f"{len(borrados)} archivo(s) enviado(s) a la Papelera", 8000)
        return len(borrados), fallidos

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
        _borrados, fallidos = self.eliminar_archivos(seleccion)
        if fallidos:
            QMessageBox.warning(self, "Eliminar del disco",
                                "No se pudieron mover a la Papelera (¿están abiertos en otro programa?):\n\n"
                                + "\n".join(fallidos))

    def encolar(self, rutas: list[str]):
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
        btn_ahora = aviso.addButton("Apagar ahora", QMessageBox.AcceptRole)
        reloj = QTimer(aviso, interval=1000)
        apagando = [False]

        def apagar():
            if not apagando[0]:
                apagando[0] = True
                reloj.stop()
                self._ejecutar_apagado()

        def tic():
            if segundos[0] <= 0:
                # El apagado sale desde acá: no depende de que el diálogo se cierre
                apagar()
                aviso.done(QMessageBox.AcceptRole)
                return
            aviso.setText(f"Terminó el video. La computadora se apaga en {segundos[0]} s.")
            segundos[0] -= 1

        reloj.timeout.connect(tic)
        tic()
        reloj.start()
        # Para que el celular (modo ON) pueda ver la cuenta y cancelarla
        self.apagado_pendiente = (aviso, segundos, btn_ahora)
        try:
            aviso.exec()
        finally:
            self.apagado_pendiente = None
        reloj.stop()
        if apagando[0]:
            return
        if aviso.clickedButton() is btn_ahora:
            apagar()
        else:
            self.statusBar().showMessage("Apagado cancelado", 5000)

    def _ejecutar_apagado(self):
        if sys.platform == "win32":
            # /f: cierra los programas abiertos en vez de quedarse esperando que alguien confirme
            comando = ["shutdown", "/s", "/f", "/t", "0"]
            opciones = {"creationflags": subprocess.CREATE_NO_WINDOW, "encoding": "oem"}
        else:
            comando, opciones = ["systemctl", "poweroff"], {"text": True}
        try:
            resultado = subprocess.run(comando, capture_output=True, errors="replace", timeout=30, **opciones)
            error = resultado.returncode and (resultado.stderr or resultado.stdout or "").strip()
        except (OSError, subprocess.SubprocessError) as e:
            error = str(e)
        if error:
            QMessageBox.warning(self, "Apagar la computadora", f"No se pudo apagar la computadora:\n\n{error}")

    def reproducir(self, ruta: str, tipo: str = "video"):
        """Muestra el archivo seleccionándolo en la lista, si está visible (p. ej. el siguiente capítulo)."""
        for i in range(self.lista.topLevelItemCount()):
            item = self.lista.topLevelItem(i)
            if item.data(0, ROL)[1] == ruta and item is not self.lista.currentItem():
                self._seleccionar(item, REPRODUCIR)
                self.lista.scrollToItem(item)
                return
        # Con un filtro o búsqueda que lo oculta, se reproduce igual
        self.visor.mostrar(ruta, tipo, self.bib.subtitulos_de(ruta))

    # --- Ventanas flotantes ---------------------------------------------------

    def abrir_en_ventana(self, archivos: list):
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
            ventana.visor.buscar_subtitulos_subdivx.connect(self._buscar_en_subdivx)
            # En cascada para que no queden una encima de la otra
            desplazamiento = 40 * (len(self.ventanas_video) % 8)
            ventana.move(self.pos() + QPoint(120 + desplazamiento, 100 + desplazamiento))
            self.ventanas_video.append(ventana)
            ventana.show()

    def closeEvent(self, e):
        # Una descarga a medias queda en cola y se retoma al volver a abrir TVon
        self.gestor.detener()
        self.vigilante.detener()
        self.torrents.detener()  # los torrents a medias se retoman al volver a abrir TVon
        self.remoto.detener()
        for ventana in [*self.ventanas_video, self.ventana_dominio, self.ventana_torrents, self.dialogo_on, self.aviso]:
            if ventana:
                ventana.close()
        super().closeEvent(e)

    # --- Dominio público --------------------------------------------------------

    def _abrir_dominio_publico(self):
        if self.ventana_dominio is None:
            self.ventana_dominio = VentanaDominioPublico(self.bib, self.gestor)
            self.ventana_dominio.pelicula_por_eliminar.connect(self._soltar_archivo)
            self.ventana_dominio.biblioteca_cambiada.connect(self.cargar_filtros)
        self.ventana_dominio.show()
        self.ventana_dominio.raise_()
        self.ventana_dominio.activateWindow()

    # --- Torrents y subtítulos automáticos -----------------------------------------

    def _abrir_torrents(self) -> VentanaTorrents:
        if self.ventana_torrents is None:
            self.ventana_torrents = VentanaTorrents(self.torrents)
        self.ventana_torrents.show()
        self.ventana_torrents.raise_()
        self.ventana_torrents.activateWindow()
        return self.ventana_torrents

    def _insignia_torrents(self, descargas: list):
        """Número de descargas en la esquina del botón; el detalle, al pasar el mouse."""
        boton = self.barra_herramientas.widgetForAction(self.acc_torrents)
        if not hasattr(self, "_insignia"):
            self._insignia = QLabel(boton, objectName="insignia", alignment=Qt.AlignCenter)
            self._insignia.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._insignia.setText(str(len(descargas)))
        self._insignia.adjustSize()
        self._insignia.setMinimumWidth(self._insignia.height())
        self._insignia.move(boton.width() - self._insignia.width() - 1, 1)
        self._insignia.setVisible(bool(descargas))
        lineas = []
        for d in descargas:
            progreso = f"{100 * d['recibido'] / d['total']:.0f} %" if d["total"] else "…"
            restante = VentanaTorrents._tiempo_restante(d)
            estado = {"active": restante and f"faltan {restante}", "paused": "en pausa",
                      "waiting": "en cola", "error": "error"}.get(d["estado"], "")
            lineas.append(f"{d['nombre'] or 'Link magnet'}: {progreso}" + (f" · {estado}" if estado else ""))
        self.acc_torrents.setToolTip("\n".join(lineas) if lineas
                                     else "Descargar películas con un link magnet o un archivo .torrent")

    def _torrent_terminado(self, videos: list, nombre: str):
        nuevos = self.bib.agregar_archivos([Path(v) for v in videos])
        self.cargar_filtros()
        self.statusBar().showMessage(f"Torrent terminado: {nombre} ({nuevos} video(s) en la biblioteca)", 10000)
        self._buscar_subtitulos_solos(videos)

    def _buscar_subtitulos_solos(self, videos: list):
        subtitulos_automaticos(self.bib, videos, lambda m: self.statusBar().showMessage(m, 10000))

    def _buscar_en_subdivx(self, ruta_video: str):
        """subdivx no tiene API ni acepta la búsqueda en el link: se abre en el navegador con el
        título copiado, y el subtítulo que se baje a Descargas en los próximos minutos se coloca
        solo junto a este video."""
        if not ruta_video:
            return
        titulo = titulo_de(Path(ruta_video).name)  # como en las categorías: «Coyote Vs Acme»
        QApplication.clipboard().setText(titulo)
        QDesktopServices.openUrl(QUrl("https://subdivx.com/"))
        self.vigilante.esperar_subtitulo(ruta_video)
        if self.aviso is None:
            self.aviso = AvisoFlotante()
        self.aviso.mostrar(f"📋 Tocá el buscador de subdivx y pegá con <b>Ctrl+V</b>:<br><b>{escape(titulo)}</b><br>"
                           "<span style='color:#cfe0ff'>El subtítulo que bajes se pone solo en el video.</span>")
        self.statusBar().showMessage(f"Pegá «{titulo}» en el buscador de subdivx con Ctrl+V", 30000)

    def _subtitulo_listo(self, ruta_video: str, ruta_sub: str):
        if self.aviso:
            self.aviso.hide()
        for visor in [self.visor, *(v.visor for v in self.ventanas_video)]:
            if visor.ruta_video == ruta_video:
                visor.cargar_subtitulos(ruta_sub)
        self.statusBar().showMessage(f"Subtítulo listo: {Path(ruta_sub).name}", 10000)

    # --- Modo ON (el celular) -----------------------------------------------------

    def _crear_on(self):
        self.remoto = Remoto(self)
        self.remoto.estado_cambiado.connect(self._mostrar_on)
        self.remoto.transmisiones.connect(self._mostrar_transmision)
        self.remoto.celular_conectado.connect(
            lambda nombre: self.statusBar().showMessage(f"📱 Se conectó un celular: {nombre}", 8000))
        # Aviso fijo mientras el celular ve la pantalla, con un botón para cortar
        self.aviso_pantalla = QWidget()
        capa = QHBoxLayout(self.aviso_pantalla)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(QLabel("🔴 El celular está viendo la pantalla", objectName="enVivo"))
        btn_cortar = QPushButton("Dejar de compartir", objectName="chico")
        btn_cortar.clicked.connect(self.remoto.dejar_de_compartir)
        capa.addWidget(btn_cortar)
        self.aviso_pantalla.hide()
        self.statusBar().addPermanentWidget(self.aviso_pantalla)
        if self.remoto.al_iniciar and not self.remoto.iniciar():
            self.statusBar().showMessage(f"No se pudo encender ON: {self.remoto.error}", 10000)
        self._mostrar_on()

    def _abrir_on(self):
        # Se abre ya encendido, con el código QR a la vista (si falla, la ventana muestra el motivo)
        if not self.remoto.activo:
            self.remoto.iniciar()
        if self.dialogo_on is None:
            self.dialogo_on = DialogoOn(self.remoto, self)
        self.dialogo_on.show()
        self.dialogo_on.raise_()
        self.dialogo_on.activateWindow()

    def _mostrar_on(self):
        boton = self.barra_herramientas.widgetForAction(self.acc_on)
        boton.setProperty("encendido", self.remoto.activo)
        boton.style().polish(boton)
        # Solo el botón de la barra dice OFF; el menú sigue diciendo «ON: manejar desde el celular»
        self.acc_on.setText("📱 ON" if self.remoto.activo else "📱 OFF")
        self.acc_on.setToolTip(f"ON encendido: {self.remoto.url}" if self.remoto.activo
                               else "ON apagado: tocá para encenderlo y ver el código QR")

    def _mostrar_transmision(self, cantidad: int):
        self.aviso_pantalla.setVisible(cantidad > 0)

    # --- Biblioteca automática ----------------------------------------------------

    def _abrir_configuracion(self):
        if DialogoConfig(self.bib, self).exec():
            self.vigilante.despertar()

    def _videos_encontrados(self, cantidad: int):
        self.cargar_filtros()
        self.statusBar().showMessage(f"{cantidad} video(s) nuevo(s) en tus carpetas", 8000)

    def _video_movido(self, ruta: str):
        self.cargar_filtros()
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
        if len(seleccion) == 1:
            self.categoria_desde_titulo(seleccion[0].text(0))

    def categoria_desde_titulo(self, nombre_archivo: str) -> str:
        """Crea (o completa) la categoría con el título de la película o serie; devuelve el aviso."""
        titulo = titulo_de(nombre_archivo)
        existia = any(nombre.lower() == titulo.lower() for _, nombre, _ in self.bib.listar_categorias())
        cid = self.bib.categoria_id(titulo)
        # También los demás capítulos de la misma serie (mismo título)
        archivos = [(aid, ruta, tipo) for aid, ruta, nombre, tipo in self.bib.listar_archivos()
                    if titulo_de(nombre).lower() == titulo.lower()]
        ids = [aid for aid, _ruta, _tipo in archivos]
        self.bib.asignar_varios(ids, cid, True)
        movidos, quedaron = self._organizar_en_carpeta([r for _a, r, t in archivos if t == "video"], titulo)
        self.cargar_filtros()
        accion = "Se sumaron a la categoría" if existia else "Categoría creada"
        aviso = f"{accion} «{titulo}»: {len(ids)} archivo(s)"
        if movidos:
            aviso += f" · {movidos} movido(s) a Peliculas\\{nombre_seguro(titulo)}"
        if quedaron:
            aviso += f" · {quedaron} {'quedó' if quedaron == 1 else 'quedaron'} donde estaba(n) (en uso u otro disco)"
        self.statusBar().showMessage(aviso, 8000)
        return aviso

    def _organizar_en_carpeta(self, rutas: list[str], categoria: str) -> tuple[int, int]:
        """Mueve los videos (con sus subtítulos) a Videos\\Peliculas\\<categoría>.
        No toca los que se están reproduciendo, los que otro programa tiene abiertos ni los que
        están en otro disco (sería copiar gigas). Devuelve (movidos, los que quedaron)."""
        raiz = Path(self.bib.config("carpeta_videos"))
        destino = raiz / "Peliculas" / nombre_seguro(categoria)
        reproduciendo = {Path(v.ruta_video).resolve() for v in [self.visor, *(w.visor for w in self.ventanas_video)]
                         if v.ruta_video}
        movidos = quedaron = 0
        for ruta in rutas:
            video = Path(ruta)
            if not video.exists() or video.parent.resolve() == destino.resolve():
                continue
            if (video.resolve() in reproduciendo or en_uso(video)
                    or video.resolve().drive.lower() != destino.resolve().drive.lower()):
                quedaron += 1
                continue
            try:
                nuevo, subtitulos = mover_video(video, destino)
            except OSError:
                quedaron += 1
                continue
            self.bib.mover_ruta(video.resolve(), nuevo, subtitulos)
            borrar_carpetas_vacias(video.parent, raiz)
            movidos += 1
        return movidos, quedaron

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
        self.cargar_filtros()
        self.statusBar().showMessage(f"Descargada y agregada a la biblioteca: {Path(ruta).stem}", 8000)

    def abrir_ubicacion(self, ruta: str | None = None):
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
        self.cargar_filtros()
        self.statusBar().showMessage(f"{nuevos} archivo(s) nuevo(s) agregado(s)", 5000)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        archivos, nuevos = [], 0
        for url in e.mimeData().urls():
            ruta = Path(url.toLocalFile())
            # Un .srt/.vtt soltado se carga como subtítulo del video actual
            if ruta.suffix.lower() == ".torrent":
                self._abrir_torrents().agregar(str(ruta))
                continue
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
