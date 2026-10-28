"""Compartir la pantalla con el celular (modo ON): capturar un monitor y simular mouse y teclado.

Solo Windows. Usa GDI y SendInput con ctypes, así la captura corre en el hilo del servidor sin
frenar la interfaz. Las coordenadas son píxeles físicos: Qt deja el proceso con DPI por monitor.
"""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

DISPONIBLE = sys.platform == "win32"

# Teclas especiales que se pueden mandar desde el celular: nombre -> (código virtual, extendida)
TECLAS = {
    "enter": (0x0D, False), "esc": (0x1B, False), "retroceso": (0x08, False), "tab": (0x09, False),
    "espacio": (0x20, False), "izquierda": (0x25, True), "arriba": (0x26, True), "derecha": (0x27, True),
    "abajo": (0x28, True), "suprimir": (0x2E, True), "inicio": (0x24, True), "fin": (0x23, True),
    "repag": (0x21, True), "avpag": (0x22, True), "ctrl": (0x11, False), "alt": (0x12, False),
    "shift": (0x10, False), "win": (0x5B, True), "volumen_mas": (0xAF, True), "volumen_menos": (0xAE, True),
    "silencio": (0xAD, True), "play_pausa": (0xB3, True),
    **{f"f{n}": (0x6F + n, False) for n in range(1, 13)},
}

if DISPONIBLE:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    class _CURSORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("hCursor", wintypes.HANDLE), ("ptScreenPos", wintypes.POINT)]

    class _ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                    ("hbmMask", wintypes.HANDLE), ("hbmColor", wintypes.HANDLE)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _UNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]

    _ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    for nombre, argumentos, resultado in (
        ("EnumDisplayMonitors", [wintypes.HDC, ctypes.c_void_p, _ENUM, wintypes.LPARAM], wintypes.BOOL),
        ("GetMonitorInfoW", [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)], wintypes.BOOL),
        ("MonitorFromWindow", [wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
        ("GetDC", [wintypes.HWND], wintypes.HDC),
        ("ReleaseDC", [wintypes.HWND, wintypes.HDC], ctypes.c_int),
        ("GetCursorInfo", [ctypes.POINTER(_CURSORINFO)], wintypes.BOOL),
        ("GetIconInfo", [wintypes.HANDLE, ctypes.POINTER(_ICONINFO)], wintypes.BOOL),
        ("DrawIconEx", [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE, ctypes.c_int, ctypes.c_int,
                        wintypes.UINT, wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        ("SetCursorPos", [ctypes.c_int, ctypes.c_int], wintypes.BOOL),
        ("GetCursorPos", [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        ("SendInput", [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int], wintypes.UINT),
    ):
        funcion = getattr(_user32, nombre)
        funcion.argtypes, funcion.restype = argumentos, resultado
    for nombre, argumentos, resultado in (
        ("CreateCompatibleDC", [wintypes.HDC], wintypes.HDC),
        ("CreateCompatibleBitmap", [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HANDLE),
        ("SelectObject", [wintypes.HDC, wintypes.HANDLE], wintypes.HANDLE),
        ("BitBlt", [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD], wintypes.BOOL),
        ("GetDIBits", [wintypes.HDC, wintypes.HANDLE, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                       ctypes.POINTER(_BITMAPINFOHEADER), wintypes.UINT], ctypes.c_int),
        ("DeleteObject", [wintypes.HANDLE], wintypes.BOOL),
        ("DeleteDC", [wintypes.HDC], wintypes.BOOL),
    ):
        funcion = getattr(_gdi32, nombre)
        funcion.argtypes, funcion.restype = argumentos, resultado


class SinPantalla(Exception):
    pass


def _exigir():
    if not DISPONIBLE:
        raise SinPantalla("Compartir la pantalla solo funciona en Windows")


def monitores() -> list[dict]:
    """Monitores conectados: {"x", "y", "ancho", "alto", "principal"}, el principal primero."""
    _exigir()
    lista = []

    def agregar(hmonitor, _hdc, _rect, _dato):
        info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
        _user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        r = info.rcMonitor
        lista.append({"x": r.left, "y": r.top, "ancho": r.right - r.left, "alto": r.bottom - r.top,
                      "principal": bool(info.dwFlags & 1)})
        return True

    _user32.EnumDisplayMonitors(None, None, _ENUM(agregar), 0)
    lista.sort(key=lambda m: not m["principal"])
    return lista


def monitor_de_ventana(hwnd: int) -> int:
    """Índice (en `monitores()`) del monitor donde está la ventana."""
    _exigir()
    info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
    _user32.GetMonitorInfoW(_user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # 2: el más cercano
    r = info.rcMonitor
    for i, m in enumerate(monitores()):
        if (m["x"], m["y"]) == (r.left, r.top):
            return i
    return 0


def capturar(monitor: dict) -> QImage:
    """Lo que se ve en el monitor, con el puntero del mouse dibujado encima."""
    _exigir()
    x, y, ancho, alto = monitor["x"], monitor["y"], monitor["ancho"], monitor["alto"]
    pantalla = _user32.GetDC(None)
    dc = _gdi32.CreateCompatibleDC(pantalla)
    mapa = _gdi32.CreateCompatibleBitmap(pantalla, ancho, alto)
    anterior = _gdi32.SelectObject(dc, mapa)
    try:
        _gdi32.BitBlt(dc, 0, 0, ancho, alto, pantalla, x, y, 0x00CC0020)  # SRCCOPY
        _dibujar_puntero(dc, x, y)
        # Altura negativa: filas de arriba hacia abajo, como las espera QImage
        cabecera = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=ancho, biHeight=-alto,
                                     biPlanes=1, biBitCount=32, biCompression=0)
        datos = ctypes.create_string_buffer(ancho * alto * 4)
        _gdi32.GetDIBits(dc, mapa, 0, alto, datos, ctypes.byref(cabecera), 0)
    finally:
        _gdi32.SelectObject(dc, anterior)
        _gdi32.DeleteObject(mapa)
        _gdi32.DeleteDC(dc)
        _user32.ReleaseDC(None, pantalla)
    return QImage(datos.raw, ancho, alto, ancho * 4, QImage.Format_RGB32).copy()


def _dibujar_puntero(dc, x0: int, y0: int):
    info = _CURSORINFO(cbSize=ctypes.sizeof(_CURSORINFO))
    if not _user32.GetCursorInfo(ctypes.byref(info)) or not info.flags & 1 or not info.hCursor:
        return  # oculto (p. ej. un video en pantalla completa)
    icono = _ICONINFO()
    if not _user32.GetIconInfo(info.hCursor, ctypes.byref(icono)):
        return
    for mapa in (icono.hbmMask, icono.hbmColor):
        if mapa:
            _gdi32.DeleteObject(mapa)
    _user32.DrawIconEx(dc, info.ptScreenPos.x - x0 - icono.xHotspot, info.ptScreenPos.y - y0 - icono.yHotspot,
                       info.hCursor, 0, 0, 0, None, 3)  # DI_NORMAL


def jpeg(imagen: QImage, ancho_max: int, calidad: int) -> bytes:
    if imagen.width() > ancho_max:
        imagen = imagen.scaledToWidth(ancho_max, Qt.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    imagen.save(buffer, "JPG", calidad)
    return bytes(buffer.data())


# --- Mouse y teclado -----------------------------------------------------------

def _enviar(*entradas):
    arreglo = (_INPUT * len(entradas))(*entradas)
    _user32.SendInput(len(entradas), arreglo, ctypes.sizeof(_INPUT))


def _mouse(banderas: int, datos: int = 0):
    return _INPUT(type=0, u=_UNION(mi=_MOUSEINPUT(mouseData=datos & 0xFFFFFFFF, dwFlags=banderas)))


def _tecla(vk: int = 0, unicode: int = 0, soltar: bool = False, extendida: bool = False):
    banderas = (2 if soltar else 0) | (1 if extendida else 0) | (4 if unicode else 0)
    return _INPUT(type=1, u=_UNION(ki=_KEYBDINPUT(wVk=vk, wScan=unicode, dwFlags=banderas)))


def punto(monitor: dict, x: float, y: float) -> tuple[int, int]:
    """De coordenadas relativas (0 a 1) sobre la imagen a píxeles de la pantalla."""
    x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
    return (monitor["x"] + min(int(x * monitor["ancho"]), monitor["ancho"] - 1),
            monitor["y"] + min(int(y * monitor["alto"]), monitor["alto"] - 1))


def mover(monitor: dict, x: float, y: float):
    _exigir()
    _user32.SetCursorPos(*punto(monitor, x, y))


def clic(monitor: dict, x: float, y: float, boton: str = "izquierdo", veces: int = 1):
    mover(monitor, x, y)
    abajo, arriba = (0x0008, 0x0010) if boton == "derecho" else (0x0002, 0x0004)
    _enviar(*[_mouse(b) for _ in range(veces) for b in (abajo, arriba)])


def presionar(monitor: dict, x: float, y: float, apretado: bool):
    """Mantener apretado el botón izquierdo (para arrastrar) o soltarlo."""
    mover(monitor, x, y)
    _enviar(_mouse(0x0002 if apretado else 0x0004))


# Touchpad: el puntero se mueve desde donde está, sin coordenadas de la imagen

_BOTONES = {"izquierdo": (0x0002, 0x0004), "derecho": (0x0008, 0x0010), "medio": (0x0020, 0x0040)}


def desplazar(dx: int, dy: int):
    """Mover el puntero dx, dy píxeles. Windows lo frena en el borde del escritorio."""
    _exigir()
    actual = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(actual))
    _user32.SetCursorPos(actual.x + dx, actual.y + dy)


def clic_aqui(boton: str = "izquierdo", veces: int = 1):
    _exigir()
    abajo, arriba = _BOTONES[boton]
    _enviar(*[_mouse(b) for _ in range(veces) for b in (abajo, arriba)])


def boton(boton: str, apretado: bool):
    """Apretar o soltar un botón donde está el puntero (para arrastrar desde el touchpad)."""
    _exigir()
    _enviar(_mouse(_BOTONES[boton][0 if apretado else 1]))


def rueda(pasos: int):
    """Positivo: hacia arriba."""
    _exigir()
    _enviar(_mouse(0x0800, 120 * pasos))


def teclas(combinacion: str):
    """Una tecla o combinación: «enter», «ctrl+c», «alt+f4», «win+d»."""
    _exigir()
    codigos = []
    for parte in combinacion.lower().split("+"):
        if parte in TECLAS:
            codigos.append(TECLAS[parte])
        elif len(parte) == 1 and parte.isascii() and parte.isalnum():
            codigos.append((ord(parte.upper()), False))
        else:
            raise ValueError(f"Tecla desconocida: {parte}")
    _enviar(*[_tecla(vk, extendida=ext) for vk, ext in codigos],
            *[_tecla(vk, soltar=True, extendida=ext) for vk, ext in reversed(codigos)])


def editar(borrar: int, texto: str):
    """Lo que cambió en el teclado en vivo del celular: borrar caracteres y escribir los nuevos."""
    _exigir()
    if borrar:
        _enviar(*[t for _ in range(borrar) for t in (_tecla(0x08), _tecla(0x08, soltar=True))])
    escribir(texto)


def escribir(texto: str):
    _exigir()
    entradas = []
    for caracter in texto:
        if caracter == "\n":
            entradas += [_tecla(0x0D), _tecla(0x0D, soltar=True)]
            continue
        datos = caracter.encode("utf-16-le")
        for i in range(0, len(datos), 2):  # los emojis van en dos partes (pares sustitutos)
            unidad = int.from_bytes(datos[i:i + 2], "little")
            entradas += [_tecla(unicode=unidad), _tecla(unicode=unidad, soltar=True)]
    if entradas:
        _enviar(*entradas)
