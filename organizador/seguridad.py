"""Cifrado de los datos guardados y certificado para que la conexión con el celular sea HTTPS.

- Datos guardados: las claves (OpenSubtitles, el código del QR, la clave del certificado) se
  guardan cifradas con DPAPI de Windows. Solo este usuario de Windows en esta PC puede leerlas:
  copiar biblioteca.db a otra PC no sirve para sacarlas.
- Celulares: la base guarda solo una huella (SHA-256) de cada sesión, nunca la sesión en sí.
- Conexión con el celular: TVon crea su propio certificado (ECDSA P-256, firmado por él mismo)
  y el servidor de ON va por HTTPS (TLS 1.2 o más nuevo).
"""
import base64
import ctypes
import datetime
import hashlib
import ipaddress
import secrets
import sys
from ctypes import wintypes
from pathlib import Path

PREFIJO = "dpapi:"
DISPONIBLE = sys.platform == "win32"


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


if DISPONIBLE:
    _crypt32, _kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    for _funcion in (_crypt32.CryptProtectData, _crypt32.CryptUnprotectData):
        _funcion.argtypes = [ctypes.POINTER(_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_BLOB), ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_BLOB)]
        _funcion.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _dpapi(datos: bytes, cifrar: bool) -> bytes:
    # Los buffers quedan en variables: tienen que seguir vivos mientras Windows los lee
    buffer_entrada = ctypes.create_string_buffer(datos, len(datos))
    buffer_sal = ctypes.create_string_buffer(b"TVon", 4)  # una sal propia
    entrada = _BLOB(len(datos), ctypes.cast(buffer_entrada, ctypes.POINTER(ctypes.c_char)))
    entropia = _BLOB(4, ctypes.cast(buffer_sal, ctypes.POINTER(ctypes.c_char)))
    salida = _BLOB()
    funcion = _crypt32.CryptProtectData if cifrar else _crypt32.CryptUnprotectData
    # 0x1: CRYPTPROTECT_UI_FORBIDDEN (nunca mostrar ventanas)
    if not funcion(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, 0x1, ctypes.byref(salida)):
        raise OSError("No se pudo " + ("cifrar" if cifrar else "descifrar") + " con DPAPI")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def proteger(texto: str) -> str:
    """Texto cifrado para guardar en la base (vacío queda vacío)."""
    if not texto or not DISPONIBLE or texto.startswith(PREFIJO):
        return texto
    return PREFIJO + base64.b64encode(_dpapi(texto.encode("utf-8"), True)).decode()


def desproteger(texto: str) -> str:
    """Lo guardado con proteger(); lo viejo, sin cifrar, se devuelve tal cual."""
    if not texto or not texto.startswith(PREFIJO):
        return texto
    try:
        return _dpapi(base64.b64decode(texto[len(PREFIJO):]), False).decode("utf-8")
    except (OSError, ValueError):
        return ""  # de otro usuario u otra PC: como si no estuviera


def huella_sesion(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Certificado para HTTPS ----------------------------------------------------------------

def certificado(carpeta: Path, clave_privada: str, ips: list[str]) -> tuple[Path, Path, str]:
    """El certificado de ON (lo crea la primera vez o si venció). Devuelve (certificado, clave,
    huella SHA-256 para comparar en el celular). La clave privada va cifrada con `clave_privada`."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    ruta_cert, ruta_clave = carpeta / "on_certificado.pem", carpeta / "on_clave.pem"
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if ruta_cert.exists() and ruta_clave.exists():
        cert = x509.load_pem_x509_certificate(ruta_cert.read_bytes())
        try:
            serialization.load_pem_private_key(ruta_clave.read_bytes(), clave_privada.encode())
            vigente = cert.not_valid_after_utc - ahora > datetime.timedelta(days=30)
        except (ValueError, TypeError):
            vigente = False
        if vigente:
            return ruta_cert, ruta_clave, _huella(cert)

    clave = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TVon ON")])
    alternativos = [x509.DNSName("localhost")]
    for ip in dict.fromkeys(ips + ["127.0.0.1"]):
        try:
            alternativos.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass
    cert = (x509.CertificateBuilder()
            .subject_name(nombre).issuer_name(nombre)
            .public_key(clave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - datetime.timedelta(minutes=5))
            .not_valid_after(ahora + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(alternativos), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(clave, hashes.SHA256()))
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_clave.write_bytes(clave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(clave_privada.encode())))
    ruta_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return ruta_cert, ruta_clave, _huella(cert)


def _huella(cert) -> str:
    from cryptography.hazmat.primitives import hashes
    crudo = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(crudo[i:i + 2] for i in range(0, len(crudo), 2))


def clave_nueva() -> str:
    return secrets.token_urlsafe(32)


# --- Quién puede conectarse ---------------------------------------------------------------

# La casa (redes privadas), la misma PC y Tailscale. Desde internet, nunca.
_REDES_PERMITIDAS = [ipaddress.ip_network(r) for r in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
    "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10")]


def ip_permitida(ip: str) -> bool:
    try:
        direccion = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if direccion.version == 6 and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    return any(direccion in red for red in _REDES_PERMITIDAS if red.version == direccion.version)


def host_permitido(host: str) -> bool:
    """El celular entra por la IP de la PC: un nombre de dominio cualquiera es un ataque
    de «DNS rebinding» (una página de internet haciéndose pasar por TVon)."""
    if not host:
        return False
    nombre = host
    if host.startswith("["):  # IPv6 con puerto: [::1]:8765
        nombre = host[1:host.find("]")]
    elif host.count(":") == 1:
        nombre = host.rsplit(":", 1)[0]
    if nombre == "localhost":
        return True
    try:
        ipaddress.ip_address(nombre)
        return True
    except ValueError:
        return False
