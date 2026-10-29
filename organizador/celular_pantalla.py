"""Ver y manejar la pantalla del celular (Android) en la PC, con scrcpy.

Va por la red común (la misma wifi, o Tailscale) o por cable USB, sin Miracast.
scrcpy (Apache 2.0, https://github.com/Genymobile/scrcpy) viene incluido con su adb.

En el celular hace falta, una sola vez, activar las Opciones de desarrollador y la
Depuración USB. Después:
- Con cable: TVon lo muestra y además deja el celular listo para la red (adb tcpip), así
  que se puede desenchufar y seguir por wifi hasta que el celular se reinicie.
- Sin cable: TVon se conecta a la IP del celular (la sabe porque el celular le habla por ON).
- Android 11 o más nuevo, sin cable nunca: «Depuración inalámbrica» con un código de vinculación.
"""
import re
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

CARPETA = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent)) / "organizador" / "bin" / "scrcpy"
SCRCPY = CARPETA / "scrcpy.exe"
ADB = CARPETA / "adb.exe"
TITULO = "Celular — TVon"
# Sin la ventanita negra de consola de adb y scrcpy
SIN_CONSOLA = 0x08000000 if sys.platform == "win32" else 0


class ErrorCelular(Exception):
    pass


def disponible() -> bool:
    return SCRCPY.exists() and ADB.exists()


def _adb(*argumentos: str, espera: float = 15) -> str:
    try:
        r = subprocess.run([str(ADB), *argumentos], capture_output=True, text=True, timeout=espera,
                           creationflags=SIN_CONSOLA)
    except subprocess.TimeoutExpired:
        raise ErrorCelular("El celular no respondió a tiempo") from None
    return (r.stdout + r.stderr).strip()


def dispositivos() -> list[tuple[str, str]]:
    """(serie, estado) de los celulares que ve adb: «device», «unauthorized» u «offline»."""
    salida = _adb("devices")
    return [tuple(linea.split()[:2]) for linea in salida.splitlines()[1:] if len(linea.split()) >= 2]


class PantallaCelular(QObject):
    """Abre scrcpy en un hilo aparte (adb puede tardar) y avisa cómo le fue."""
    mensaje = Signal(str)

    def __init__(self):
        super().__init__()
        self.proceso: subprocess.Popen | None = None
        self.ultimo = ""  # el último aviso, para el celular
        self.mensaje.connect(lambda m: setattr(self, "ultimo", m))

    @property
    def abierta(self) -> bool:
        return self.proceso is not None and self.proceso.poll() is None

    def mostrar(self, ip: str | None = None):
        if not disponible():
            raise ErrorCelular(f"Falta scrcpy en {CARPETA}")
        if self.abierta:
            self.mensaje.emit("La pantalla del celular ya está abierta en la PC")
            return
        self.mensaje.emit("Conectando con el celular…")
        threading.Thread(target=self._mostrar, args=(ip,), daemon=True).start()

    def emparejar(self, ip_puerto: str, codigo: str, puerto_conexion: str):
        """Android 11+: «Depuración inalámbrica» → «Vincular con código». Una sola vez por PC."""
        if not re.fullmatch(r"[\w.\-:\[\]]+:\d+", ip_puerto) or not re.fullmatch(r"\d{6}", codigo):
            raise ErrorCelular("Poné la IP y el puerto como aparecen (p. ej. 192.168.0.20:37123) "
                               "y el código de 6 números")
        if not re.fullmatch(r"\d{2,5}", puerto_conexion):
            raise ErrorCelular("Falta el puerto de la pantalla «Depuración inalámbrica» (el de arriba)")
        self.mensaje.emit("Vinculando…")

        def trabajo():
            try:
                salida = _adb("pair", ip_puerto, codigo, espera=20)
                if "success" not in salida.lower():
                    self.mensaje.emit(f"No se pudo vincular: {salida.splitlines()[-1] if salida else 'sin respuesta'}")
                    return
                ip = ip_puerto.rsplit(":", 1)[0]
                self._mostrar(f"{ip}:{puerto_conexion}")
            except (ErrorCelular, OSError) as e:
                self.mensaje.emit(f"No se pudo vincular: {e}")
        threading.Thread(target=trabajo, daemon=True).start()

    def _mostrar(self, ip: str | None):
        try:
            conectados = [(s, e) for s, e in dispositivos()]
            por_cable = [s for s, e in conectados if e == "device" and ":" not in s]
            sin_permiso = [s for s, e in conectados if e == "unauthorized"]
            if sin_permiso and not por_cable:
                self.mensaje.emit("En el celular apareció «¿Permitir depuración USB?»: tocá Permitir "
                                  "(y «Permitir siempre desde esta computadora») y probá de nuevo")
                return
            if por_cable:
                # Con cable: --tcpip lo deja listo para la red y se conecta por wifi
                argumentos = ["--tcpip", "-s", por_cable[0]]
            elif ip:
                argumentos = [f"--tcpip={ip}"]
            else:
                self.mensaje.emit("No encontré el celular: conectalo por cable una vez o usá "
                                  "«Depuración inalámbrica» (Android 11+)")
                return
            self.proceso = subprocess.Popen(
                [str(SCRCPY), *argumentos, "--window-title", TITULO, "--stay-awake"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=SIN_CONSOLA)
            try:
                salida, _ = self.proceso.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                # Sigue abierto: la ventana del celular ya está en la PC
                self.mensaje.emit("📲 La pantalla del celular está en la PC (ventana «Celular — TVon»)")
                threading.Thread(target=self.proceso.communicate, daemon=True).start()
                return
            self.mensaje.emit(self._explicar(salida or ""))
        except (ErrorCelular, OSError) as e:
            self.mensaje.emit(f"No se pudo mostrar el celular: {e}")

    @staticmethod
    def _explicar(salida: str) -> str:
        """El error de scrcpy, en criollo."""
        texto = salida.lower()
        if "could not connect" in texto or "failed to connect" in texto or "connection refused" in texto:
            return ("No se pudo conectar por wifi: conectá el celular por cable una vez (con Depuración USB) "
                    "o usá «Depuración inalámbrica». Después del cable sigue por wifi hasta que el celular se reinicie")
        if "unauthorized" in texto:
            return "En el celular tocá «Permitir» en el aviso de depuración USB y probá de nuevo"
        if "no device" in texto or "device not found" in texto:
            return "No encontré el celular: ¿está activada la Depuración USB en las Opciones de desarrollador?"
        ultima = next((l for l in reversed(salida.splitlines()) if l.strip()), "se cerró")
        return f"La pantalla del celular se cerró: {ultima}"

    def cerrar(self):
        """Al salir de TVon: cierra la ventana del celular y el adb que quedó corriendo."""
        if self.abierta:
            self.proceso.terminate()
        if disponible():
            try:
                subprocess.run([str(ADB), "kill-server"], timeout=5, capture_output=True, creationflags=SIN_CONSOLA)
            except (OSError, subprocess.TimeoutExpired):
                pass
