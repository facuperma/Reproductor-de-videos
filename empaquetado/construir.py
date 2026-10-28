"""Genera TVon.exe (PyInstaller) y el instalador TVon-Setup-<versión>.exe (Inno Setup).

Uso, desde la carpeta del proyecto:
    .venv\\Scripts\\pip install pyinstaller
    .venv\\Scripts\\python empaquetado\\construir.py

Requiere Inno Setup 6 (https://jrsoftware.org/isinfo.php o `winget install JRSoftware.InnoSetup`).
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "compilado"
APP = SALIDA / "dist" / "TVon"
QT = APP / "_internal" / "PySide6"

# Partes de Qt que TVon no usa (teclado virtual táctil, QML/Quick, PDF, OpenGL por software)
SOBRANTES = [
    "opengl32sw.dll", "Qt6Quick.dll", "Qt6Qml.dll", "Qt6QmlMeta.dll", "Qt6QmlModels.dll",
    "Qt6QmlWorkerScript.dll", "Qt6VirtualKeyboard.dll", "Qt6OpenGL.dll", "Qt6Pdf.dll",
    "plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll", "plugins/imageformats/qpdf.dll",
]


def version() -> str:
    return re.search(r'VERSION = "(.+?)"', (RAIZ / "main.py").read_text(encoding="utf-8")).group(1)


def iscc() -> Path:
    candidatos = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for ruta in candidatos:
        if ruta.exists():
            return ruta
    sys.exit("No se encontró Inno Setup 6 (ISCC.exe). Instalalo con: winget install JRSoftware.InnoSetup")


def main():
    v = version()
    print("== Ícono")
    subprocess.run([sys.executable, str(RAIZ / "empaquetado" / "generar_icono.py")], check=True)
    print(f"== TVon {v}: ejecutable")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "TVon",
        "--icon", str(RAIZ / "organizador" / "icono.ico"),
        "--add-data", f"{RAIZ / 'organizador' / 'icono.png'};organizador",
        # La app del celular (modo ON)
        "--add-data", f"{RAIZ / 'organizador' / 'web'};organizador/web",
        "--distpath", str(SALIDA / "dist"), "--workpath", str(SALIDA / "build"),
        "--specpath", str(SALIDA), str(RAIZ / "main.py"),
    ], check=True)

    print("== Recortando partes de Qt que no se usan")
    for nombre in SOBRANTES:
        (QT / nombre).unlink(missing_ok=True)
    for qm in (QT / "translations").glob("*.qm"):
        if not qm.stem.endswith("_es"):
            qm.unlink()
    tamano = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file())
    print(f"   {tamano / 1024**2:.0f} MB")

    print("== Instalador")
    subprocess.run([str(iscc()), f"/DVersion={v}", f"/DOrigen={APP}", f"/O{SALIDA}",
                    str(RAIZ / "empaquetado" / "TVon.iss")], check=True)
    instalador = SALIDA / f"TVon-Setup-{v}.exe"
    print(f"\nListo: {instalador} ({instalador.stat().st_size / 1024**2:.0f} MB)")


if __name__ == "__main__":
    main()
