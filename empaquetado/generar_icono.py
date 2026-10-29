"""Genera organizador/icono.ico (varios tamaños) a partir de organizador/icono.png.

Uso: .venv\\Scripts\\python empaquetado\\generar_icono.py
"""
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "organizador" / "icono.png"
DESTINO = RAIZ / "organizador" / "icono.ico"
TAMANOS = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
CHICO = 48  # hasta este tamaño se usa el logo recortado


def reducir(imagen: QImage, lado: int) -> QImage:
    # Reducir a la mitad por pasos da bordes más limpios que un salto de 1024 a 16
    while imagen.width() >= lado * 2:
        imagen = imagen.scaled(imagen.width() // 2, imagen.height() // 2,
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return imagen.scaled(lado, lado, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def recortado(imagen: QImage) -> QImage:
    """Para los tamaños chicos (barra de título, barra de tareas): solo el anillo con la TV,
    sin la sombra ni el borde oscuro, así se ve más grande. Esquinas redondeadas."""
    lado = imagen.width()
    margen = round(lado * 160 / 1024)  # el anillo va de 182 a 842 en el logo de 1024
    recorte = imagen.copy(margen, margen, lado - 2 * margen, lado - 2 * margen)
    resultado = QImage(recorte.size(), QImage.Format_ARGB32)
    resultado.fill(Qt.transparent)
    p = QPainter(resultado)
    p.setRenderHint(QPainter.Antialiasing)
    camino = QPainterPath()
    radio = recorte.width() * 0.2
    camino.addRoundedRect(0, 0, recorte.width(), recorte.height(), radio, radio)
    p.setClipPath(camino)
    p.drawImage(0, 0, recorte)
    p.end()
    return resultado


def png_de(imagen: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    imagen.save(buffer, "PNG")
    return bytes(buffer.data())


def main():
    original = QImage(str(ORIGEN)).convertToFormat(QImage.Format_ARGB32)
    chico = recortado(original)
    imagenes = [png_de(reducir(chico if lado <= CHICO else original, lado)) for lado in TAMANOS]
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
