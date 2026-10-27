"""Utilidades HTTP comunes (sin dependencias externas)."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AGENTE = "TVon v1.0"
REINTENTOS = 3


class ErrorRed(Exception):
    def __init__(self, mensaje: str, codigo: int | None = None):
        super().__init__(mensaje)
        self.codigo = codigo


def _abrir(req: Request, timeout: int):
    """urlopen con reintentos ante errores temporales del servidor (5xx)."""
    for intento in range(REINTENTOS):
        try:
            return urlopen(req, timeout=timeout)
        except HTTPError as e:
            if e.code < 500 or intento == REINTENTOS - 1:
                try:
                    detalle = json.loads(e.read()).get("message") or e.reason
                except (ValueError, AttributeError):
                    detalle = e.reason
                raise ErrorRed(f"{detalle} (HTTP {e.code})", e.code) from e
            time.sleep(2 * (intento + 1))
        except URLError as e:
            raise ErrorRed(f"Sin conexión: {e.reason}") from e


def pedir_json(url: str, params: list | dict | None = None, cuerpo: dict | None = None,
               cabeceras: dict | None = None, timeout: int = 30):
    if params:
        url += "?" + urlencode(params)
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    encabezado = {"User-Agent": AGENTE, "Accept": "application/json", **(cabeceras or {})}
    if datos is not None:
        encabezado["Content-Type"] = "application/json"
    with _abrir(Request(url, datos, encabezado), timeout) as r:
        return json.load(r)


def bajar_bytes(url: str, timeout: int = 60) -> bytes:
    with _abrir(Request(url, headers={"User-Agent": AGENTE}), timeout) as r:
        return r.read()


def abrir_descarga(url: str, desde: int = 0, timeout: int = 60):
    """Respuesta HTTP abierta para descargar por partes; `desde` pide continuar desde ese byte."""
    cabeceras = {"User-Agent": AGENTE}
    if desde:
        cabeceras["Range"] = f"bytes={desde}-"
    return _abrir(Request(url, headers=cabeceras), timeout)
