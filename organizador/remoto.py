"""Modo ON: manejar TVon desde el celular, en la misma red wifi.

TVon levanta un servidor HTTP en la red local. Sirve la app del celular (carpeta `web`) y una API
JSON. El celular se empareja escaneando un QR que lleva el código de emparejamiento; a cambio recibe
una sesión propia (cookie), que se puede revocar desde la PC.

El servidor atiende cada pedido en un hilo propio. Todo lo que toca la ventana o la base pasa por
`_Puente`, que lo ejecuta en el hilo de la interfaz y espera el resultado.
"""
import ipaddress
import json
import re
import secrets
import socket
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sqlite3 import IntegrityError
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QImageReader
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from . import archive, pantalla_remota
from .db import CATEGORIA_FAVORITOS
from .dominio_publico import (
    ESTADOS, cancelar_descargas, eliminar_peliculas, peliculas_borrables, quitar_descargas,
    reintentar_descargas,
)
from .subtitulos_online import buscar_para_visor
from .visor import TAMANOS_SUB, texto_progreso

WEB = Path(__file__).parent / "web"
ICONO = Path(__file__).parent / "icono.png"
PUERTO = 8765
COOKIE = "tvon_sesion"
ESPERA_INTERFAZ = 15  # segundos: si la ventana está trabada más que esto, el pedido falla
SITIOS = {"peliculas": "https://ext.to/", "subtitulos": "https://subdivx.com/"}
TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".webmanifest": "application/manifest+json", ".png": "image/png"}
# La página solo carga lo propio; la API no se puede incrustar en otros sitios
SEGURIDAD = {"Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'",
             "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


class ErrorRemoto(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def ip_local() -> str:
    """La IP de esta PC en la red local (la de la interfaz que sale a internet)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.168.0.1", 9))  # UDP: no manda nada, solo elige la interfaz
            return s.getsockname()[0]
        except OSError:
            return socket.gethostbyname(socket.gethostname())


TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


def ip_tailscale() -> str | None:
    """La IP de esta PC en Tailscale (VPN para entrar desde fuera de casa), si está instalado y conectado."""
    try:
        direcciones = {d[4][0] for d in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        return None
    return next((ip for ip in sorted(direcciones) if ipaddress.ip_address(ip) in TAILSCALE), None)


def nombre_dispositivo(agente: str) -> str:
    """«Android · SM-A546E» a partir del User-Agent del navegador."""
    if m := re.search(r"Android [\d.]+; ([^;)]+)", agente):
        modelo = m.group(1).strip()
        return f"Android · {modelo}" if modelo != "K" else "Android"
    for clave, nombre in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Mac OS", "Mac")):
        if clave in agente:
            return nombre
    return "Navegador"


class _Pedido:
    def __init__(self, funcion):
        self.funcion = funcion
        self.listo = threading.Event()
        self.resultado = None
        self.error: Exception | None = None


class _Puente(QObject):
    """Ejecuta funciones en el hilo de la interfaz y le devuelve el resultado al hilo que las pidió."""
    _pedido = Signal(object)

    def __init__(self):
        super().__init__()
        self._pedido.connect(self._ejecutar)

    def _ejecutar(self, pedido: _Pedido):
        try:
            pedido.resultado = pedido.funcion()
        except Exception as e:  # noqa: BLE001 - el error vuelve al hilo del servidor
            pedido.error = e
        pedido.listo.set()

    def llamar(self, funcion):
        pedido = _Pedido(funcion)
        self._pedido.emit(pedido)
        if not pedido.listo.wait(ESPERA_INTERFAZ):
            raise ErrorRemoto("TVon está ocupado en la PC (¿hay una ventana abierta esperando respuesta?)", 503)
        if pedido.error:
            raise pedido.error
        return pedido.resultado


class Remoto(QObject):
    """El modo ON de una ventana de TVon: servidor, sesiones y permisos."""
    estado_cambiado = Signal()          # se encendió o apagó, o cambiaron los celulares conectados
    transmisiones = Signal(int)         # cuántos celulares están viendo la pantalla
    celular_conectado = Signal(str)     # nombre del dispositivo que se acaba de emparejar

    def __init__(self, ventana):
        super().__init__()
        self.ventana = ventana
        self.bib = ventana.bib
        self.puente = _Puente()
        self.control = _Control(self)
        self.servidor: ThreadingHTTPServer | None = None
        self.puerto = 0
        self.error = ""
        self._sesiones: dict[str, dict] = {}
        self._vistas: dict[str, float] = {}
        self._cerrojo = threading.Lock()
        self._transmisiones = 0
        self._corte = 0  # sube al dejar de compartir desde la PC: cierra las transmisiones abiertas
        self.progreso: dict[str, tuple[int, int]] = {}
        ventana.gestor.progreso.connect(self._progreso)
        # Copia en memoria de la configuración: el servidor la lee desde sus hilos y la base no se comparte
        self._config = {clave: self.bib.config(clave) for clave in ("on_codigo", "on_pantalla", "on_control", "on_activo")}
        try:
            for s in json.loads(self.bib.config("on_sesiones") or "[]"):
                self._sesiones[s["token"]] = s
        except (ValueError, KeyError, TypeError):
            pass
        if not self._config["on_codigo"]:
            self.cambiar_codigo()

    # --- Configuración -----------------------------------------------------------

    def _opcion(self, clave: str, defecto: str = "1") -> bool:
        return (self._config[clave] or defecto) == "1"

    @property
    def permite_pantalla(self) -> bool:
        return self._opcion("on_pantalla")

    @property
    def permite_control(self) -> bool:
        return self._opcion("on_control")

    @property
    def al_iniciar(self) -> bool:
        return self._opcion("on_activo", "0")

    def guardar_opcion(self, clave: str, activa: bool):
        self._config[clave] = "1" if activa else "0"
        self.bib.guardar_config(clave, self._config[clave])
        if clave == "on_pantalla" and not activa:
            self.dejar_de_compartir()

    @property
    def codigo(self) -> str:
        return self._config["on_codigo"]

    def cambiar_codigo(self):
        """Código nuevo para el QR: los celulares ya conectados siguen conectados."""
        self._config["on_codigo"] = secrets.token_urlsafe(16)
        self.bib.guardar_config("on_codigo", self._config["on_codigo"])
        self.estado_cambiado.emit()

    # --- Servidor --------------------------------------------------------------------

    @property
    def activo(self) -> bool:
        return self.servidor is not None

    @property
    def url(self) -> str:
        return f"http://{ip_local()}:{self.puerto}/" if self.activo else ""

    @property
    def url_emparejar(self) -> str:
        return f"{self.url}?c={self.codigo}" if self.activo else ""

    def url_remota(self) -> str:
        """Dirección para fuera de casa, por Tailscale ("" si no está)."""
        ip = ip_tailscale() if self.activo else None
        return f"http://{ip}:{self.puerto}/" if ip else ""

    def iniciar(self) -> bool:
        if self.activo:
            return True
        self.error = ""
        for puerto in range(PUERTO, PUERTO + 10):
            try:
                self.servidor = _Servidor(("0.0.0.0", puerto), _Manejador, self)
                break
            except OSError:
                continue
        else:
            self.error = f"No hay un puerto libre entre {PUERTO} y {PUERTO + 9}"
            self.estado_cambiado.emit()
            return False
        self.puerto = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.estado_cambiado.emit()
        return True

    def detener(self):
        if self.servidor is None:
            return
        self.dejar_de_compartir()
        servidor, self.servidor = self.servidor, None
        servidor.shutdown()
        servidor.server_close()
        self.estado_cambiado.emit()

    # --- Sesiones ----------------------------------------------------------------------

    def emparejar(self, codigo: str, agente: str) -> str | None:
        """Si el código es el del QR, crea una sesión y devuelve su token."""
        if not secrets.compare_digest(codigo.encode(), self.codigo.encode()):
            return None
        token = secrets.token_urlsafe(32)
        nombre = nombre_dispositivo(agente)
        with self._cerrojo:
            self._sesiones[token] = {"token": token, "nombre": nombre, "creada": time.strftime("%d/%m/%Y %H:%M")}
        self._guardar_sesiones()
        self.celular_conectado.emit(nombre)
        self.estado_cambiado.emit()
        return token

    def sesion_valida(self, token: str | None) -> bool:
        with self._cerrojo:
            if not token or token not in self._sesiones:
                return False
            self._vistas[token] = time.time()
            return True

    def cerrar_sesion(self, token: str):
        with self._cerrojo:
            self._sesiones.pop(token, None)
        self._guardar_sesiones()
        self.estado_cambiado.emit()

    def desconectar_todos(self):
        with self._cerrojo:
            self._sesiones.clear()
        self._guardar_sesiones()
        self.dejar_de_compartir()
        self.estado_cambiado.emit()

    def celulares(self) -> list[dict]:
        """Los emparejados, con hace cuántos segundos se los vio por última vez (None: nunca en esta sesión)."""
        with self._cerrojo:
            ahora = time.time()
            return [{**s, "visto": (ahora - self._vistas[t]) if t in self._vistas else None}
                    for t, s in self._sesiones.items()]

    def _guardar_sesiones(self):
        # La base es del hilo de la interfaz: desde el servidor se guarda a través del puente
        # (sin el cerrojo tomado: la interfaz también lo usa y se trabarían)
        with self._cerrojo:
            datos = json.dumps(list(self._sesiones.values()))
        if threading.current_thread() is threading.main_thread():
            self.bib.guardar_config("on_sesiones", datos)
        else:
            self.puente.llamar(lambda: self.bib.guardar_config("on_sesiones", datos))

    # --- Pantalla compartida ---------------------------------------------------------

    def dejar_de_compartir(self):
        self._corte += 1

    def _sumar_transmision(self, cantidad: int) -> int:
        with self._cerrojo:
            self._transmisiones += cantidad
            total = self._transmisiones
        self.transmisiones.emit(total)
        return self._corte

    def _progreso(self, ident: str, recibido: int, total: int):
        self.progreso[ident] = (recibido, total)


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True
    # En Windows, SO_REUSEADDR deja que otro programa use el mismo puerto a la vez
    allow_reuse_address = False

    def __init__(self, direccion, manejador, remoto: Remoto):
        self.remoto = remoto
        super().__init__(direccion, manejador)


class _Manejador(BaseHTTPRequestHandler):
    server: _Servidor
    server_version = "TVon"
    sys_version = ""

    def log_message(self, *args):
        pass  # sin consola (pythonw): escribir en stderr fallaría

    @property
    def remoto(self) -> Remoto:
        return self.server.remoto

    # --- Respuestas ------------------------------------------------------------------

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str, cabeceras: dict | None = None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for clave, valor in {**SEGURIDAD, **(cabeceras or {})}.items():
            self.send_header(clave, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def _json(self, datos, codigo: int = 200, cabeceras: dict | None = None):
        self._responder(codigo, json.dumps(datos, ensure_ascii=False).encode(), "application/json; charset=utf-8",
                        {"Cache-Control": "no-store", **(cabeceras or {})})

    def _error(self, mensaje: str, codigo: int):
        self._json({"error": mensaje}, codigo)

    def _token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[COOKIE].value if COOKIE in cookie else None

    def _cuerpo(self) -> dict:
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > 64 * 1024:
            raise ErrorRemoto("Pedido demasiado grande", 413)
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except ValueError:
            raise ErrorRemoto("JSON inválido") from None
        if not isinstance(datos, dict):
            raise ErrorRemoto("JSON inválido")
        return datos

    # --- Rutas ------------------------------------------------------------------------

    def do_GET(self):
        self._atender(self._get)

    def do_POST(self):
        self._atender(self._post)

    def _atender(self, rutas):
        url = urlparse(self.path)
        consulta = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            rutas(url.path, consulta)
        except ErrorRemoto as e:
            self._error(str(e), e.codigo)
        except pantalla_remota.SinPantalla as e:
            self._error(str(e), 501)
        except ValueError as e:  # un número mal escrito en la consulta
            self._error(f"Dato inválido: {e}", 400)
        except (ConnectionError, TimeoutError):
            pass  # el celular cortó
        except Exception as e:  # noqa: BLE001 - un error no debe tirar el servidor
            try:
                self._error(f"Error en TVon: {e}", 500)
            except OSError:
                pass

    def _get(self, ruta: str, consulta: dict):
        if not ruta.startswith("/api/"):
            return self._estatico(ruta)
        self._exigir_sesion()
        control = self.remoto.control
        if ruta == "/api/estado":
            self._json(self.remoto.puente.llamar(control.estado))
        elif ruta == "/api/biblioteca":
            self._json(self.remoto.puente.llamar(control.biblioteca))
        elif ruta == "/api/archivos":
            self._json(self.remoto.puente.llamar(lambda: control.archivos(
                consulta.get("filtro", "todos"), consulta.get("categoria"), consulta.get("q", ""))))
        elif ruta == "/api/miniatura":
            self._miniatura(_entero(consulta.get("id")))
        elif ruta == "/api/cuadro.jpg":
            self._cuadro()
        elif ruta == "/api/dp/buscar":
            self._json(self._buscar_peliculas(consulta))
        elif ruta == "/api/dp/cola":
            self._json(self.remoto.puente.llamar(control.descargas))
        elif ruta == "/api/pantalla/monitores":
            self._json(self._monitores())
        elif ruta == "/api/pantalla.mjpg":
            self._transmitir(consulta)
        else:
            raise ErrorRemoto("No existe", 404)

    def _post(self, ruta: str, _consulta: dict):
        if ruta == "/api/emparejar":
            return self._emparejar()
        token = self._exigir_sesion()
        # Una cabecera propia: otro sitio no puede mandarla sin permiso (CORS), así no hay CSRF
        if self.headers.get("X-TVon") != "1":
            raise ErrorRemoto("Falta la cabecera X-TVon", 403)
        datos = self._cuerpo()
        if ruta == "/api/accion":
            accion = str(datos.pop("accion", ""))
            self._json(self.remoto.puente.llamar(lambda: self.remoto.control.ejecutar(accion, datos)) or {})
        elif ruta == "/api/pantalla/entrada":
            self._entrada(datos)
            self._json({})
        elif ruta == "/api/salir":
            self.remoto.cerrar_sesion(token)
            self._json({}, cabeceras={"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
        else:
            raise ErrorRemoto("No existe", 404)

    def _exigir_sesion(self) -> str:
        token = self._token()
        if not self.remoto.sesion_valida(token):
            raise ErrorRemoto("Este celular no está conectado: escaneá el código QR de TVon (botón ON)", 401)
        return token

    def _emparejar(self):
        datos = self._cuerpo()
        token = self.remoto.emparejar(str(datos.get("codigo", "")), self.headers.get("User-Agent", ""))
        if token is None:
            raise ErrorRemoto("El código no es válido: escaneá de nuevo el QR que muestra TVon (botón ON)", 403)
        un_anio = 365 * 24 * 3600
        self._json({"ok": True}, cabeceras={
            "Set-Cookie": f"{COOKIE}={token}; Max-Age={un_anio}; Path=/; HttpOnly; SameSite=Strict"})

    def _estatico(self, ruta: str):
        if ruta in ("/", ""):
            ruta = "/index.html"
        if m := re.fullmatch(r"/icono-(192|512)\.png", ruta):
            return self._responder(200, _icono(int(m.group(1))), "image/png", {"Cache-Control": "max-age=86400"})
        nombre = ruta.lstrip("/")
        archivo = WEB / nombre
        # Solo archivos sueltos de la carpeta web, nada fuera de ella
        if "/" in nombre or "\\" in nombre or not archivo.is_file() or archivo.suffix not in TIPOS:
            raise ErrorRemoto("No existe", 404)
        self._responder(200, archivo.read_bytes(), TIPOS[archivo.suffix], {"Cache-Control": "no-cache"})

    # --- Imágenes ----------------------------------------------------------------------

    def _miniatura(self, archivo_id: int):
        filas = self.remoto.puente.llamar(lambda: self.remoto.bib.archivos_por_id([archivo_id]))
        if not filas or filas[0][2] != "imagen":
            raise ErrorRemoto("No existe", 404)
        lector = QImageReader(filas[0][1])
        lector.setAutoTransform(True)
        tamano = lector.size()
        if tamano.isValid() and tamano.width() > 320:
            lector.setScaledSize(tamano.scaled(320, 320, Qt.KeepAspectRatio))
        imagen = lector.read()
        if imagen.isNull():
            raise ErrorRemoto("No se pudo leer la imagen", 404)
        self._responder(200, pantalla_remota.jpeg(imagen, 320, 75), "image/jpeg",
                        {"Cache-Control": "private, max-age=3600"})

    def _cuadro(self):
        imagen: QImage | None = self.remoto.puente.llamar(self.remoto.ventana.visor.pantalla.cuadro)
        if imagen is None:
            self.send_response(204)
            self.end_headers()
            return
        self._responder(200, pantalla_remota.jpeg(imagen, 640, 70), "image/jpeg", {"Cache-Control": "no-store"})

    # --- Dominio público ----------------------------------------------------------------

    def _buscar_peliculas(self, consulta: dict) -> dict:
        orden = consulta.get("orden", "populares")
        if orden not in archive.ORDENES:
            raise ErrorRemoto("Orden desconocido")
        pagina = max(1, _entero(consulta.get("pagina", 1)))
        try:
            total, peliculas = archive.buscar(consulta.get("q", ""), pagina, 30, orden)
        except Exception as e:  # noqa: BLE001 - sin internet, archive.org caído…
            raise ErrorRemoto(f"No se pudo buscar en archive.org: {e}", 502) from e
        estados = self.remoto.puente.llamar(self.remoto.bib.estados_descarga)
        for p in peliculas:
            p["estado"] = estados.get(p["identificador"])
            p["estado_texto"] = ESTADOS.get(p["estado"], "")
        return {"total": total, "peliculas": peliculas, "ordenes": {k: v[0] for k, v in archive.ORDENES.items()}}

    # --- Pantalla compartida -------------------------------------------------------------

    def _monitores(self) -> dict:
        lista = pantalla_remota.monitores()
        hwnd = self.remoto.puente.llamar(lambda: int(self.remoto.ventana.winId()))
        return {"monitores": lista, "tvon": pantalla_remota.monitor_de_ventana(hwnd),
                "pantalla": self.remoto.permite_pantalla, "control": self.remoto.permite_control}

    def _monitor(self, indice) -> dict:
        lista = pantalla_remota.monitores()
        try:
            return lista[int(indice)]
        except (ValueError, IndexError):
            raise ErrorRemoto("Ese monitor no existe") from None

    def _transmitir(self, consulta: dict):
        if not self.remoto.permite_pantalla:
            raise ErrorRemoto("Compartir la pantalla está desactivado en TVon (ON → opciones)", 403)
        monitor = self._monitor(consulta.get("monitor", 0))
        ancho = min(max(int(consulta.get("ancho", 1280)), 320), 3840)
        calidad = min(max(int(consulta.get("calidad", 60)), 20), 95)
        pausa = 1 / min(max(float(consulta.get("fps", 8)), 1), 20)
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=cuadro")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"--cuadro\r\n")
        corte = self.remoto._sumar_transmision(1)
        try:
            while self.remoto.activo and self.remoto._corte == corte and self.remoto.permite_pantalla:
                inicio = time.monotonic()
                cuadro = pantalla_remota.jpeg(pantalla_remota.capturar(monitor), ancho, calidad)
                # El separador va enseguida: así el navegador muestra el cuadro sin esperar el próximo
                self.wfile.write(b"Content-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(cuadro)
                                 + cuadro + b"\r\n--cuadro\r\n")
                self.wfile.flush()
                time.sleep(max(0.0, pausa - (time.monotonic() - inicio)))
        except OSError:
            pass  # el celular cerró la transmisión
        finally:
            self.remoto._sumar_transmision(-1)
        self.close_connection = True

    def _entrada(self, datos: dict):
        if not self.remoto.permite_control:
            raise ErrorRemoto("Manejar el mouse y el teclado está desactivado en TVon (ON → opciones)", 403)
        tipo = datos.get("tipo")
        try:
            if tipo == "desplazar":
                limite = 3000
                pantalla_remota.desplazar(max(-limite, min(limite, int(datos["dx"]))),
                                          max(-limite, min(limite, int(datos["dy"]))))
            elif tipo == "clic_aqui":
                pantalla_remota.clic_aqui(_boton(datos), max(1, min(3, int(datos.get("veces", 1)))))
            elif tipo == "boton":
                pantalla_remota.boton(_boton(datos), bool(datos["apretado"]))
            elif tipo == "editar":
                pantalla_remota.editar(max(0, min(200, int(datos.get("borrar", 0)))), str(datos.get("texto", ""))[:2000])
            elif tipo in ("clic", "doble", "derecho", "mover", "apretar", "soltar"):
                monitor = self._monitor(datos.get("monitor", 0))
                x, y = float(datos["x"]), float(datos["y"])
                if tipo == "mover":
                    pantalla_remota.mover(monitor, x, y)
                elif tipo in ("apretar", "soltar"):
                    pantalla_remota.presionar(monitor, x, y, tipo == "apretar")
                else:
                    pantalla_remota.clic(monitor, x, y, "derecho" if tipo == "derecho" else "izquierdo",
                                         2 if tipo == "doble" else 1)
            elif tipo == "rueda":
                pantalla_remota.rueda(max(-20, min(20, int(datos["pasos"]))))
            elif tipo == "teclas":
                pantalla_remota.teclas(str(datos["teclas"]))
            elif tipo == "texto":
                pantalla_remota.escribir(str(datos["texto"])[:2000])
            else:
                raise ErrorRemoto("Entrada desconocida")
        except (KeyError, ValueError, TypeError) as e:
            raise ErrorRemoto(f"Entrada inválida: {e}") from e


def _boton(datos: dict) -> str:
    boton = datos.get("boton", "izquierdo")
    if boton not in ("izquierdo", "derecho", "medio"):
        raise ErrorRemoto("Botón desconocido")
    return boton


def _entero(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErrorRemoto("Falta un número válido") from None


_iconos: dict[int, bytes] = {}


def _icono(tamano: int) -> bytes:
    if tamano not in _iconos:
        imagen = QImage(str(ICONO)).scaled(tamano, tamano, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        imagen.save(buffer, "PNG")
        _iconos[tamano] = bytes(buffer.data())
    return _iconos[tamano]


class _Control:
    """Lo que el celular puede leer y hacer. Corre siempre en el hilo de la interfaz."""

    def __init__(self, remoto: Remoto):
        self.remoto = remoto

    @property
    def ventana(self):
        return self.remoto.ventana

    @property
    def visor(self):
        return self.remoto.ventana.visor

    @property
    def bib(self):
        return self.remoto.bib

    # --- Lectura -----------------------------------------------------------------------

    def estado(self) -> dict:
        v, ventana = self.visor, self.ventana
        r = v.reproductor
        archivo = None
        if v.ruta_video:
            archivo = {"id": self.bib.id_de_ruta(v.ruta_video), "nombre": Path(v.ruta_video).name, "tipo": "video"}
        elif actual := ventana.archivo_actual():
            archivo = {"id": actual[0], "nombre": Path(actual[1]).name, "tipo": actual[2]}
        estado_rep = {QMediaPlayer.PlayingState: "reproduciendo", QMediaPlayer.PausedState: "pausa"}.get(
            r.playbackState(), "detenido")
        apagado = ventana.apagado_pendiente
        return {
            "version": QApplication.applicationVersion(),
            "archivo": archivo,
            "reproduccion": {
                "estado": "vista_previa" if v.en_vista_previa else estado_rep,
                "posicion": v.posicion_actual(), "duracion": max(0, r.duration()),
                "volumen": v.volumen.value(), "silencio": v.audio.isMuted(),
            } if v.es_video else None,
            "subtitulos": {
                "archivos": [{"ruta": ruta, "texto": texto, "activo": ruta == v.ruta_sub}
                             for ruta, texto in v.archivos_subtitulos()],
                "pistas": [{"texto": texto, "activa": activa} for texto, activa in v.pistas_subtitulos()],
                "activos": v.subs is not None or r.activeSubtitleTrack() >= 0,
                "retraso": v.retraso_ms,
                "escala": v.pantalla.escala_sub,
                "tamanos": [{"texto": t, "escala": e} for t, e in TAMANOS_SUB],
            } if v.es_video else None,
            "cola": [{"ruta": ruta, "nombre": Path(ruta).stem} for ruta in v.cola],
            "siguiente": {"texto": v.lbl_sig_cuenta.text(), "nombre": v.lbl_sig_nombre.text()}
            if not v.panel_sig.isHidden() else None,
            "apagar_al_terminar": ventana.chk_apagar.isChecked(),
            "apagado": {"segundos": max(0, apagado[1][0])} if apagado else None,
            "pantalla_completa": ventana.isFullScreen(),
            "ventanas": len(ventana.ventanas_video),
            "mover_descargas": self.bib.config("mover_descargas") == "1",
            "opensubtitles": bool(self.bib.config("os_api_key")),
        }

    def biblioteca(self) -> dict:
        from .ventana import FILTROS_FIJOS
        return {
            "filtros": [{"filtro": f, "nombre": nombre, "cantidad": len(self.bib.listar_archivos(f))}
                        for (f, _), nombre in FILTROS_FIJOS.items()],
            "categorias": [{"id": cid, "nombre": nombre, "cantidad": n, "fija": cid == self.bib.favoritos}
                           for cid, nombre, n in self.bib.listar_categorias()],
            "favoritos": self.bib.favoritos,
        }

    def archivos(self, filtro: str, categoria, texto: str) -> list[dict]:
        if filtro not in ("todos", "video", "imagen", "sin_categoria", "categoria"):
            raise ErrorRemoto("Filtro desconocido")
        cid = int(categoria) if filtro == "categoria" and categoria else None
        por_archivo = self.bib.categorias_por_archivo()
        progresos = self.bib.progresos()
        return [{"id": aid, "nombre": nombre, "carpeta": str(Path(ruta).parent), "tipo": tipo,
                 "existe": Path(ruta).exists(), "categorias": por_archivo.get(aid, []),
                 "visto": texto_progreso(progresos.get(ruta))}
                for aid, ruta, nombre, tipo in self.bib.listar_archivos(filtro, cid, texto.strip())]

    def descargas(self) -> dict:
        lista = []
        for fila in self.bib.listar_descargas():
            recibido, total = self.remoto.progreso.get(fila["identificador"], (fila["recibido"], fila["tamano"]))
            lista.append({"identificador": fila["identificador"], "titulo": fila["titulo"], "anio": fila["anio"],
                          "estado": fila["estado"], "estado_texto": ESTADOS.get(fila["estado"], fila["estado"]),
                          "error": fila["error"], "tamano": fila["tamano"], "recibido": recibido or 0,
                          "total": total or 0})
        n, usados = self.bib.resumen_descargas()
        return {"descargas": lista, "cantidad": n, "bytes": usados,
                "auto": {"activa": self.bib.config("auto_activa") == "1",
                         "max_peliculas": int(self.bib.config("auto_max_peliculas") or 0),
                         "max_gb": int(float(self.bib.config("auto_max_gb") or 0))}}

    # --- Acciones ---------------------------------------------------------------------

    def ejecutar(self, accion: str, datos: dict):
        metodo = getattr(self, f"accion_{accion}", None)
        if not re.fullmatch(r"[a-z_]+", accion) or metodo is None:
            raise ErrorRemoto(f"Acción desconocida: {accion}")
        try:
            return metodo(**datos)
        except (TypeError, ValueError) as e:
            raise ErrorRemoto(f"Datos inválidos para «{accion}»: {e}") from e

    def _archivos(self, ids) -> list[tuple[int, str, str]]:
        filas = self.bib.archivos_por_id([int(i) for i in ids])
        if not filas:
            raise ErrorRemoto("Esos archivos ya no están en la biblioteca", 404)
        return filas

    def _requiere_video(self):
        if not self.visor.es_video:
            raise ErrorRemoto("No hay un video abierto en TVon", 409)

    # Reproductor

    def accion_reproducir(self, id):
        (aid, ruta, tipo), = self._archivos([id])
        if not Path(ruta).exists():
            raise ErrorRemoto("El archivo ya no está en esa ubicación", 404)
        if self.visor.ruta_video != ruta:
            self.ventana.reproducir(ruta, tipo)
        elif self.visor.en_vista_previa:
            self.visor.empezar()
        else:
            self.visor.reproductor.play()

    def accion_play_pausa(self):
        self._requiere_video()
        self.visor.alternar_play()

    def accion_detener(self):
        self._requiere_video()
        self.visor.reproductor.stop()

    def accion_adelantar(self, ms):
        self._requiere_video()
        self.visor.adelantar(int(ms))

    def accion_ir_a(self, ms):
        self._requiere_video()
        self.visor.ir_a(int(ms))

    def accion_volumen(self, valor):
        self.visor.volumen.setValue(max(0, min(100, int(valor))))
        if self.visor.audio.isMuted():
            self.visor.alternar_mute()

    def accion_silencio(self):
        self.visor.alternar_mute()

    def accion_siguiente(self):
        self._requiere_video()
        self.visor.siguiente_capitulo()

    def accion_lista(self, paso):
        self.ventana.mover(1 if int(paso) > 0 else -1)

    def accion_pantalla_completa(self):
        self.ventana.alternar_pantalla_completa()

    def accion_siguiente_ahora(self):
        self.visor.siguiente_ahora()

    def accion_cancelar_siguiente(self):
        self.visor.cancelar_siguiente()

    # Subtítulos

    def accion_subtitulos(self, archivo=None, pista=None):
        self._requiere_video()
        if archivo:
            if archivo not in [r for r, _ in self.visor.archivos_subtitulos()]:
                raise ErrorRemoto("Ese subtítulo no corresponde al video")
            self.visor.cargar_subtitulos(archivo)
        elif pista is not None:
            self.visor.usar_pista_interna(int(pista))
        else:
            self.visor.quitar_subtitulos()

    def accion_retraso(self, ms=None, valor=None):
        self._requiere_video()
        if self.visor.subs is None:
            raise ErrorRemoto("El retraso solo se ajusta con un archivo de subtítulos cargado", 409)
        if valor is not None:
            self.visor.fijar_retraso(int(valor))
        else:
            self.visor.ajustar_retraso(int(ms))

    def accion_sincronizar_ahora(self):
        self._requiere_video()
        if self.visor.subs is None:
            raise ErrorRemoto("Hace falta un archivo de subtítulos cargado", 409)
        self.visor.sincronizar_ahora()

    def accion_tamano_subtitulos(self, escala):
        self.visor.cambiar_tamano_sub(float(escala))

    def accion_buscar_subtitulos(self):
        self._requiere_video()
        if not self.bib.config("os_api_key"):
            raise ErrorRemoto("Falta la clave de OpenSubtitles: cargala en ⚙ Configuración, en la PC", 409)
        buscar_para_visor(self.visor, self.bib, self.ventana)
        return {"aviso": "Buscando subtítulos… aparecen solos en unos segundos"}

    # Cola

    def accion_cola_agregar(self, ids):
        videos = [ruta for _aid, ruta, tipo in self._archivos(ids) if tipo == "video"]
        if not videos:
            raise ErrorRemoto("Solo se pueden encolar videos")
        self.ventana.encolar(videos)
        return {"aviso": f"{len(videos)} video(s) en la cola"}

    def accion_cola_reproducir(self, ruta):
        if ruta not in self.visor.cola:
            raise ErrorRemoto("Ese video ya no está en la cola", 404)
        self.visor.pasar_a(ruta)

    def accion_cola_quitar(self, ruta):
        self.visor.quitar_de_cola(ruta)

    def accion_cola_vaciar(self):
        self.visor.vaciar_cola()

    # Apagado

    def accion_apagar_al_terminar(self, activo):
        self.ventana.chk_apagar.setChecked(bool(activo))

    def accion_cancelar_apagado(self):
        if pendiente := self.ventana.apagado_pendiente:
            pendiente[0].reject()

    def accion_apagar_ahora(self):
        if not (pendiente := self.ventana.apagado_pendiente):
            raise ErrorRemoto("No hay un apagado en curso", 409)
        pendiente[2].click()

    # Biblioteca

    def accion_favoritos(self, ids, activo):
        ids = [a for a, _r, _t in self._archivos(ids)]
        self.ventana.asignar_seleccion(ids, self.bib.favoritos, CATEGORIA_FAVORITOS, bool(activo))

    def accion_asignar(self, ids, categoria, activo):
        nombre = self._nombre_categoria(int(categoria))
        ids = [a for a, _r, _t in self._archivos(ids)]
        self.ventana.asignar_seleccion(ids, int(categoria), nombre, bool(activo))

    def accion_nueva_categoria(self, nombre, ids=()):
        nombre = str(nombre).strip()
        if not nombre:
            raise ErrorRemoto("Escribí un nombre")
        try:
            self.bib.crear_categoria(nombre)
        except IntegrityError:
            raise ErrorRemoto(f"Ya existe una categoría llamada «{nombre}»", 409) from None
        cid = next(c for c, n, _ in self.bib.listar_categorias() if n == nombre)
        if ids:
            self.bib.asignar_varios([a for a, _r, _t in self._archivos(ids)], cid, True)
        self.ventana.cargar_filtros()
        return {"id": cid}

    def accion_renombrar_categoria(self, id, nombre):
        nombre = str(nombre).strip()
        self._nombre_categoria(int(id))
        if int(id) == self.bib.favoritos:
            raise ErrorRemoto("«Favoritos» es una categoría fija: no se puede renombrar", 409)
        if not nombre:
            raise ErrorRemoto("Escribí un nombre")
        try:
            self.bib.renombrar_categoria(int(id), nombre)
        except IntegrityError:
            raise ErrorRemoto(f"Ya existe una categoría llamada «{nombre}»", 409) from None
        self.ventana.cargar_filtros()

    def accion_borrar_categoria(self, id):
        self._nombre_categoria(int(id))
        if int(id) == self.bib.favoritos:
            raise ErrorRemoto("«Favoritos» es una categoría fija: no se puede borrar", 409)
        self.bib.borrar_categoria(int(id))
        if self.ventana.filtro == ("categoria", int(id)):
            self.ventana.filtro = ("todos", None)
        self.ventana.cargar_filtros()

    def _nombre_categoria(self, cid: int) -> str:
        nombre = next((n for c, n, _ in self.bib.listar_categorias() if c == cid), None)
        if nombre is None:
            raise ErrorRemoto("Esa categoría ya no existe", 404)
        return nombre

    def accion_categoria_titulo(self, id):
        (_aid, ruta, _tipo), = self._archivos([id])
        return {"aviso": self.ventana.categoria_desde_titulo(Path(ruta).name)}

    def accion_quitar(self, ids):
        seleccion = self._archivos(ids)
        if self.visor.ruta_video in [ruta for _a, ruta, _t in seleccion]:
            self.visor.mostrar(None, None)
        self.ventana.quitar_de_biblioteca([a for a, _r, _t in seleccion])
        return {"aviso": f"{len(seleccion)} archivo(s) quitado(s) de la biblioteca"}

    def accion_eliminar(self, ids):
        borrados, fallidos = self.ventana.eliminar_archivos(self._archivos(ids))
        aviso = f"{borrados} archivo(s) enviado(s) a la Papelera"
        if fallidos:
            aviso += ". No se pudieron mover (¿están abiertos en otro programa?): " + ", ".join(fallidos)
        return {"aviso": aviso}

    def accion_abrir_ventana(self, id):
        self.ventana.abrir_en_ventana(self._archivos([id]))

    def accion_abrir_ubicacion(self, id):
        (_aid, ruta, _tipo), = self._archivos([id])
        self.ventana.abrir_ubicacion(ruta)

    def accion_abrir_web(self, sitio):
        if sitio not in SITIOS:
            raise ErrorRemoto("Sitio desconocido")
        QDesktopServices.openUrl(QUrl(SITIOS[sitio]))

    def accion_mover_descargas(self, activo):
        self.bib.guardar_config("mover_descargas", "1" if activo else "0")
        self.ventana.vigilante.despertar()

    # Dominio público

    def accion_dp_descargar(self, peliculas):
        nuevas = sum(self.bib.agregar_descarga(str(p["identificador"]), str(p["titulo"]), p.get("anio"))
                     for p in peliculas)
        if nuevas:
            self.ventana.gestor.despertar()
            self.ventana.gestor.cola_cambiada.emit()
        return {"aviso": f"{nuevas} película(s) en la cola de descargas" if nuevas else "Ya estaban en la lista"}

    def accion_dp_cancelar(self, ids):
        cancelar_descargas(self.bib, self.ventana.gestor, list(ids))
        self.ventana.gestor.cola_cambiada.emit()

    def accion_dp_reintentar(self, ids):
        reintentar_descargas(self.bib, self.ventana.gestor, list(ids))
        self.ventana.gestor.cola_cambiada.emit()

    def accion_dp_quitar(self, ids):
        quitar_descargas(self.bib, list(ids))
        self.ventana.gestor.cola_cambiada.emit()

    def accion_dp_eliminar(self, ids):
        borrables = peliculas_borrables(self.bib, list(ids))
        if not borrables:
            raise ErrorRemoto("Elegí películas que ya estén descargadas")
        fallidos = eliminar_peliculas(self.bib, borrables, self.ventana._soltar_archivo)
        self.ventana.cargar_filtros()
        self.ventana.gestor.cola_cambiada.emit()
        aviso = f"{len(borrables)} película(s) enviada(s) a la Papelera"
        return {"aviso": aviso + (". No se pudieron mover: " + ", ".join(fallidos) if fallidos else "")}

    def accion_dp_auto(self, activa=None, max_peliculas=None, max_gb=None):
        for clave, valor in (("auto_activa", None if activa is None else ("1" if activa else "0")),
                             ("auto_max_peliculas", None if max_peliculas is None else str(max(1, int(max_peliculas)))),
                             ("auto_max_gb", None if max_gb is None else str(max(1, int(max_gb))))):
            if valor is not None:
                self.bib.guardar_config(clave, valor)
        self.ventana.gestor.despertar()

