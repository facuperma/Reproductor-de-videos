"""Ventana de torrents: pegar un link magnet o abrir un .torrent, y seguir la cola."""
from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .dominio_publico import formato_tamano
from .torrents import ErrorTorrent, GestorTorrents

ROL = Qt.UserRole
ESTADOS = {"active": "Descargando", "waiting": "En cola", "paused": "En pausa", "error": "Error"}


def formato_tiempo(segundos: float) -> str:
    if segundos < 60:
        return f"{max(1, int(segundos))} s"
    m = int(segundos // 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


class VentanaTorrents(QWidget):
    def __init__(self, gestor: GestorTorrents):
        super().__init__(None, Qt.Window)
        self.gestor = gestor
        self.setWindowTitle("Torrents — TVon")
        self.resize(900, 520)
        self._filas: dict[str, tuple[QTreeWidgetItem, QProgressBar]] = {}
        self._agregados: set[str] = set()

        self.enlace = QLineEdit(placeholderText="Pegá acá el link magnet (magnet:?xt=…)", clearButtonEnabled=True)
        self.enlace.returnPressed.connect(self._agregar_enlace)
        btn_agregar = QPushButton("⬇ Descargar", objectName="primario")
        btn_agregar.clicked.connect(self._agregar_enlace)
        btn_archivo = QPushButton("Abrir .torrent…")
        btn_archivo.clicked.connect(self._elegir_archivo)
        btn_buscar = QPushButton("🌐 Buscar películas")
        btn_buscar.setToolTip("Abre ext.to en el navegador: copiá el link magnet y volvé acá")
        btn_buscar.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://ext.to/")))
        fila = QHBoxLayout()
        fila.addWidget(self.enlace, 1)
        fila.addWidget(btn_agregar)
        fila.addWidget(btn_archivo)
        fila.addWidget(btn_buscar)

        self.cola = QTreeWidget()
        self.cola.setHeaderLabels(["Nombre", "Estado", "Tamaño", "Progreso", "Velocidad", "Tiempo restante",
                                   "Fuentes"])
        self.cola.setRootIsDecorated(False)
        self.cola.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cola.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cola.header().resizeSection(3, 200)
        self.lbl_vacia = QLabel("No hay descargas. Pegá un link magnet arriba o arrastrá un .torrent a TVon.",
                                objectName="pista", alignment=Qt.AlignCenter)

        btn_pausar = QPushButton("⏸ Pausar")
        btn_reanudar = QPushButton("▶ Reanudar")
        btn_cancelar = QPushButton("✕ Cancelar")
        btn_cancelar.setToolTip("Saca la descarga y borra lo que había bajado")
        btn_pausar.clicked.connect(lambda: self._a_seleccion(self.gestor.pausar))
        btn_reanudar.clicked.connect(lambda: self._a_seleccion(self.gestor.reanudar))
        btn_cancelar.clicked.connect(self._cancelar)
        fila_botones = QHBoxLayout()
        fila_botones.addStretch()
        for b in (btn_pausar, btn_reanudar, btn_cancelar):
            fila_botones.addWidget(b)

        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addWidget(self.cola, 1)
        capa.addWidget(self.lbl_vacia)
        capa.addLayout(fila_botones)
        capa.addWidget(QLabel(
            "Al terminar, la película pasa a tu carpeta de Videos, aparece en la biblioteca y se le buscan "
            "subtítulos. Mientras baja, también se comparte con otros (así funciona BitTorrent).",
            wordWrap=True, objectName="pista"))

        gestor.estado.connect(self._mostrar)
        # Un magnet copiado mientras la ventana existe se pega solo, aunque estés en el navegador
        QGuiApplication.clipboard().dataChanged.connect(self._pegar_magnet)

    def showEvent(self, e):
        self._pegar_magnet()
        super().showEvent(e)

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._pegar_magnet()  # volviste del navegador
        super().changeEvent(e)

    def _pegar_magnet(self):
        """Si copiaste un link magnet, queda pegado solo. Reemplaza otro magnet, pero no lo que
        estés escribiendo, ni vuelve a pegar uno que ya agregaste."""
        texto = QGuiApplication.clipboard().text().strip()
        actual = self.enlace.text().strip()
        if (texto.lower().startswith("magnet:?") and texto not in self._agregados
                and (not actual or actual.lower().startswith("magnet:?"))):
            self.enlace.setText(texto)

    def agregar(self, texto: str) -> bool:
        try:
            self.gestor.agregar(texto)
        except ErrorTorrent as e:
            QMessageBox.warning(self, "Torrents", str(e))
            return False
        self._agregados.add(texto.strip())
        return True

    def _agregar_enlace(self):
        if self.enlace.text().strip() and self.agregar(self.enlace.text()):
            self.enlace.clear()

    def _elegir_archivo(self):
        rutas, _ = QFileDialog.getOpenFileNames(self, "Abrir archivos .torrent", "", "Torrents (*.torrent)")
        for ruta in rutas:
            self.agregar(ruta)

    def _seleccion(self) -> list[str]:
        return [i.data(0, ROL) for i in self.cola.selectedItems()]

    def _a_seleccion(self, accion):
        try:
            for gid in self._seleccion():
                accion(gid)
        except ErrorTorrent as e:
            QMessageBox.warning(self, "Torrents", str(e))

    def _cancelar(self):
        if self._seleccion() and QMessageBox.question(
                self, "Cancelar", "¿Cancelar las descargas seleccionadas y borrar lo que bajaron?") == QMessageBox.Yes:
            self._a_seleccion(self.gestor.cancelar)

    @staticmethod
    def _tiempo_restante(d: dict) -> str:
        """Con la velocidad actual; sin velocidad todavía no se puede estimar."""
        if d["estado"] != "active":
            return ""
        if not d["total"] or not d["velocidad"]:
            return "calculando…"
        return formato_tiempo((d["total"] - d["recibido"]) / d["velocidad"])

    def _mostrar(self, descargas: list):
        """Actualiza las filas en el lugar (sin rearmar la lista, así no se pierde la selección)."""
        vistos = set()
        for d in descargas:
            vistos.add(d["gid"])
            if d["gid"] not in self._filas:
                item = QTreeWidgetItem()
                item.setData(0, ROL, d["gid"])
                barra = QProgressBar(maximum=1000, textVisible=True)
                self.cola.addTopLevelItem(item)
                self.cola.setItemWidget(item, 3, barra)
                self._filas[d["gid"]] = (item, barra)
            item, barra = self._filas[d["gid"]]
            item.setText(0, d["nombre"] or "Buscando los datos del link magnet…")
            estado = ESTADOS.get(d["estado"], d["estado"])
            if d["estado"] == "active" and not d["conexiones"]:
                estado += " · buscando fuentes…"
            if d["error"]:
                estado = f"Error: {d['error']}"
                item.setToolTip(1, d["error"])
            item.setText(1, estado)
            item.setText(2, formato_tamano(d["total"]))
            item.setText(4, f"{d['velocidad'] / 1024**2:.1f} MB/s" if d["estado"] == "active" else "")
            item.setText(5, self._tiempo_restante(d))
            item.setText(6, str(d["fuentes"] or d["conexiones"] or "") if d["estado"] == "active" else "")
            progreso = d["recibido"] / d["total"] if d["total"] else 0
            barra.setValue(int(1000 * progreso))
            barra.setFormat(f"{100 * progreso:.0f} %")
        for gid in set(self._filas) - vistos:
            item, _ = self._filas.pop(gid)
            self.cola.takeTopLevelItem(self.cola.indexOfTopLevelItem(item))
        self.lbl_vacia.setVisible(not self._filas)
