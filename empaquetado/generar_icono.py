"""Genera organizador/icono.ico (varios tamaños) a partir de organizador/icono.png.

Uso: .venv\\Scripts\\python empaquetado\\generar_icono.py
"""
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "organizador" / "icono.png"
DESTINO = RAIZ / "organizador" / "icono.ico"
TAMANOS = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def reducir(imagen: QImage, lado: int) -> QImage:
    # Reducir a la mitad por pasos da bordes más limpios que un salto de 1024 a 16
    while imagen.width() >= lado * 2:
        imagen = imagen.scaled(imagen.width() // 2, imagen.height() // 2,
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return imagen.scaled(lado, lado, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def png_de(imagen: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    imagen.save(buffer, "PNG")
    return bytes(buffer.data())


def main():
    original = QImage(str(ORIGEN)).convertToFormat(QImage.Format_ARGB32)
    imagenes = [png_de(reducir(original, lado)) for lado in TAMANOS]
    # Formato ICO: cabecera, una entrada de 16 bytes por tamaño y los PNG a continuación
    cabecera = struct.pack("<HHH", 0, 1, len(TAMANOS))
    desplazamiento = len(cabecera) + 16 * len(TAMANOS)
    entradas = b""
    for lado, datos in zip(TAMANOS, imagenes):
        entradas += struct.pack("<BBBBHHII", lado % 256, lado % 256, 0, 0, 1, 32, len(datos), desplazamiento)
        desplazamiento += len(datos)
    DESTINO.write_bytes(cabecera + entradas + b"".join(imagenes))
    print(f"{DESTINO.name}: {len(TAMANOS)} tamaños, {DESTINO.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
