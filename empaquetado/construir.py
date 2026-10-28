"""Genera TVon.exe (PyInstaller) y el instalador TVon-Setup-<versión>.exe (Inno Setup).

Uso, desde la carpeta del proyecto:
    .venv\\Scripts\\pip install pyinstaller
    .venv\\Scripts\\python empaquetado\\construir.py

Requiere Inno Setup 6 (https://jrsoftware.org/isinfo.php o `winget install JRSoftware.InnoSetup`).
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

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


# Motor de torrents (GPL v2, https://aria2.github.io): se baja una vez y se verifica la huella
ARIA2_URL = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
ARIA2_SHA256 = "67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288"
BIN = RAIZ / "organizador" / "bin"


def bajar_aria2():
    if (BIN / "aria2c.exe").exists():
        return
    print("== Bajando aria2")
    datos = urlopen(ARIA2_URL, timeout=120).read()
    if hashlib.sha256(datos).hexdigest() != ARIA2_SHA256:
        sys.exit("La huella de aria2 no coincide: no se usa")
    BIN.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(datos)) as z:
        for nombre in z.namelist():
            if nombre.endswith("/aria2c.exe"):
                (BIN / "aria2c.exe").write_bytes(z.read(nombre))
            elif nombre.endswith("/COPYING"):
                (BIN / "aria2-LICENCIA.txt").write_bytes(z.read(nombre))


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
    bajar_aria2()
    print(f"== TVon {v}: ejecutable")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "TVon",
        "--icon", str(RAIZ / "organizador" / "icono.ico"),
        "--add-data", f"{RAIZ / 'organizador' / 'icono.png'};organizador",
        # La app del celular (modo ON)
        "--add-data", f"{RAIZ / 'organizador' / 'web'};organizador/web",
        # Torrents
        "--add-data", f"{BIN};organizador/bin",
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
