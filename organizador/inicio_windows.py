"""Arrancar TVon con Windows, escondido junto al reloj y con ON encendido.

Así el celular siempre encuentra a TVon y puede abrirlo en la PC. Se anota en
HKEY_CURRENT_USER\\...\\Run (solo para este usuario, sin permisos de administrador).
"""
import ctypes
import sys
from pathlib import Path

ARGUMENTO = "--segundo-plano"
_CLAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NOMBRE = "TVon"
DISPONIBLE = sys.platform == "win32"

if DISPONIBLE:
    import winreg


def comando() -> str:
    """Instalado, el .exe; desde el código fuente, pythonw con main.py."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {ARGUMENTO}'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{pythonw}" "{main}" {ARGUMENTO}'


def activo() -> bool:
    if not DISPONIBLE:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CLAVE) as clave:
            winreg.QueryValueEx(clave, _NOMBRE)
        return True
    except OSError:
        return False


def activar(si: bool):
    if not DISPONIBLE:
        raise OSError("Solo funciona en Windows")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CLAVE, 0, winreg.KEY_SET_VALUE) as clave:
        if si:
            winreg.SetValueEx(clave, _NOMBRE, 0, winreg.REG_SZ, comando())
        else:
            try:
                winreg.DeleteValue(clave, _NOMBRE)
            except FileNotFoundError:
                pass


def traer_al_frente(ventana):
    """Pone la ventana adelante de todo. Windows no deja que un programa en segundo plano
    se adelante solo (cuando lo pide el celular): una pulsación de Alt lo habilita."""
    ventana.raise_()
    ventana.activateWindow()
    if DISPONIBLE:
        usuario = ctypes.windll.user32
        usuario.keybd_event(0x12, 0, 0, 0)  # Alt apretada
        usuario.keybd_event(0x12, 0, 2, 0)  # Alt suelta
        usuario.SetForegroundWindow(int(ventana.winId()))
