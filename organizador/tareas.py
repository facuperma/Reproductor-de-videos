"""Ejecutar trabajo de red en segundo plano y recibir el resultado en el hilo de la interfaz."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

_activas: set = set()


class _Senales(QObject):
    listo = Signal(object)
    fallo = Signal(str)


class _Tarea(QRunnable):
    def __init__(self, funcion, senales: _Senales):
        super().__init__()
        self.funcion = funcion
        self.senales = senales

    def run(self):
        try:
            resultado = self.funcion()
        except Exception as e:  # noqa: BLE001 - cualquier error se informa en la interfaz
            self.senales.fallo.emit(str(e))
        else:
            self.senales.listo.emit(resultado)


def en_segundo_plano(funcion, listo, fallo=None):
    senales = _Senales()
    _activas.add(senales)
    senales.listo.connect(listo)
    if fallo:
        senales.fallo.connect(fallo)
    senales.listo.connect(lambda _: _activas.discard(senales))
    senales.fallo.connect(lambda _: _activas.discard(senales))
    QThreadPool.globalInstance().start(_Tarea(funcion, senales))
