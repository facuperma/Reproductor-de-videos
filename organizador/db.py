"""Persistencia en SQLite: archivos, categorías y su relación."""
import re
import sqlite3
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from . import seguridad

EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".flv", ".mpg", ".mpeg"}
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def orden_natural(nombre: str) -> list:
    """Clave para ordenar nombres respetando los números: «Cap 2» < «Cap 10»."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", nombre.lower())]


def tipo_de(ruta: Path) -> str | None:
    ext = ruta.suffix.lower()
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_IMAGEN:
        return "imagen"
    return None


def _carpeta_sistema(tipo) -> str:
    """Carpeta estándar del usuario (respeta si Windows la redirigió, p. ej. a OneDrive)."""
    return str(Path(QStandardPaths.writableLocation(tipo)))


VIDEOS = _carpeta_sistema(QStandardPaths.MoviesLocation)
DOCUMENTOS = _carpeta_sistema(QStandardPaths.DocumentsLocation)
DESCARGAS = _carpeta_sistema(QStandardPaths.DownloadLocation)
SEPARADOR_CARPETAS = "|"  # no puede aparecer en una ruta de Windows

CONFIG_DEFECTO = {
    # Carpetas que se revisan solas para sumar videos nuevos a la biblioteca
    "carpetas_biblioteca": SEPARADOR_CARPETAS.join([VIDEOS, DOCUMENTOS]),
    # Mover los videos terminados de Descargas a la carpeta de videos
    "mover_descargas": "1",
    "carpeta_descargas_sistema": DESCARGAS,
    "carpeta_videos": VIDEOS,
    # Películas de dominio público
    "carpeta_descargas": str(Path(VIDEOS) / "TVon"),
    "idiomas_subtitulos": "es,en",
    "os_api_key": "",
    "os_usuario": "",
    "os_clave": "",
    "auto_activa": "0",
    "auto_max_peliculas": "20",
    "auto_max_gb": "50",
    # Fichas (póster, sinopsis): con clave de TMDb salen de ahí; sin clave, de Wikipedia y TVmaze
    "tmdb_api_key": "",
}

# Se guardan cifrados (seguridad.proteger): claves de OpenSubtitles, TMDb y ON
SECRETOS = {"os_api_key", "os_usuario", "os_clave", "on_codigo", "on_clave_cert", "on_sesiones", "tmdb_api_key"}

CATEGORIA_DOMINIO_PUBLICO = "Dominio público"
# Un video cuenta como visto al pasar este punto (los créditos no hace falta verlos)
VISTO_DESDE = 0.9
# Por debajo de esto no se retoma: se vuelve a empezar desde el principio
RETOMAR_DESDE_MS = 30_000

# Categoría fija: se crea sola y no se puede renombrar ni borrar
CATEGORIA_FAVORITOS = "Favoritos"


class Biblioteca:
    """Acceso a la base. Cada hilo debe usar su propia instancia (SQLite no comparte conexiones)."""

    def __init__(self, ruta_db: Path):
        self.ruta_db = ruta_db
        self.con = sqlite3.connect(ruta_db, timeout=15)
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS archivos (
                id     INTEGER PRIMARY KEY,
                ruta   TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                tipo   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categorias (
                id     INTEGER PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE COLLATE NOCASE
            );
            CREATE TABLE IF NOT EXISTS archivo_categoria (
                archivo_id   INTEGER REFERENCES archivos(id) ON DELETE CASCADE,
                categoria_id INTEGER REFERENCES categorias(id) ON DELETE CASCADE,
                PRIMARY KEY (archivo_id, categoria_id)
            );
            -- ruta_sub NULL = el usuario desactivó los subtítulos de ese video
            CREATE TABLE IF NOT EXISTS subtitulos (
                ruta_video TEXT PRIMARY KEY,
                ruta_sub   TEXT,
                retraso_ms INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS config (
                clave TEXT PRIMARY KEY,
                valor TEXT
            );
            -- Películas del Internet Archive.
            -- estado: pendiente | descargando | completa | error | cancelada
            --         | omitida (no se baja) | archivada (completa, oculta de la lista)
            --         | eliminada (se borró del disco; no se vuelve a bajar sola)
            CREATE TABLE IF NOT EXISTS descargas (
                identificador TEXT PRIMARY KEY,
                titulo        TEXT NOT NULL,
                anio          TEXT,
                estado        TEXT NOT NULL DEFAULT 'pendiente',
                ruta          TEXT,
                tamano        INTEGER,
                recibido      INTEGER NOT NULL DEFAULT 0,
                error         TEXT,
                creada        REAL NOT NULL DEFAULT (julianday('now'))
            );
            -- Hasta dónde se vio cada video. visto queda en 1 al pasar el final
            -- (VISTO_DESDE), aunque después se lo vuelva a ver.
            CREATE TABLE IF NOT EXISTS progreso (
                ruta        TEXT PRIMARY KEY,
                posicion_ms INTEGER NOT NULL DEFAULT 0,
                duracion_ms INTEGER NOT NULL DEFAULT 0,
                visto       INTEGER NOT NULL DEFAULT 0,
                actualizado REAL NOT NULL DEFAULT (julianday('now'))
            );
            -- Fichas de películas y series (fichas.py): una por título, no por archivo.
            -- clave: «pelicula|the matrix|1999» o «serie|breaking bad». encontrada 0 = se buscó y no
            -- apareció (se vuelve a probar en unos días). busqueda: el título corregido a mano.
            CREATE TABLE IF NOT EXISTS fichas (
                clave      TEXT PRIMARY KEY,
                tipo       TEXT NOT NULL,
                titulo     TEXT,
                anio       TEXT,
                sinopsis   TEXT,
                generos    TEXT,
                puntaje    REAL,
                poster     TEXT,
                fuente     TEXT,
                busqueda   TEXT,
                encontrada INTEGER NOT NULL DEFAULT 0,
                buscada    REAL NOT NULL DEFAULT (julianday('now'))
            );
            """
        )
        self.con.commit()
        self.favoritos = self.categoria_id(CATEGORIA_FAVORITOS)
        # Las claves que quedaron guardadas sin cifrar (versiones anteriores) se cifran ahora
        for clave in SECRETOS:
            fila = self.con.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
            if fila and fila[0] and not fila[0].startswith(seguridad.PREFIJO):
                self.guardar_config(clave, fila[0])

    # --- Configuración ------------------------------------------------------

    def config(self, clave: str) -> str:
        fila = self.con.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
        if not fila or fila[0] is None:
            return CONFIG_DEFECTO.get(clave, "")
        return seguridad.desproteger(fila[0]) if clave in SECRETOS else fila[0]

    def guardar_config(self, clave: str, valor: str) -> None:
        if clave in SECRETOS:
            valor = seguridad.proteger(valor)  # cifrado con DPAPI: solo este usuario en esta PC
        self.con.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (clave, valor))
        self.con.commit()

    # --- Descargas ----------------------------------------------------------

    def agregar_descarga(self, identificador: str, titulo: str, anio: str | None,
                         tamano: int | None = None, estado: str = "pendiente") -> bool:
        cur = self.con.execute(
            "INSERT OR IGNORE INTO descargas (identificador, titulo, anio, tamano, estado) VALUES (?, ?, ?, ?, ?)",
            (identificador, titulo, anio, tamano, estado),
        )
        self.con.commit()
        return cur.rowcount > 0

    def actualizar_descarga(self, identificador: str, **campos) -> None:
        asignaciones = ", ".join(f"{k} = ?" for k in campos)
        self.con.execute(f"UPDATE descargas SET {asignaciones} WHERE identificador = ?",
                         (*campos.values(), identificador))
        self.con.commit()

    def listar_descargas(self) -> list[sqlite3.Row]:
        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        return cur.execute(
            "SELECT * FROM descargas WHERE estado NOT IN ('omitida', 'archivada', 'eliminada') ORDER BY "
            "CASE estado WHEN 'descargando' THEN 0 WHEN 'pendiente' THEN 1 ELSE 2 END, creada DESC"
        ).fetchall()

    def siguiente_descarga(self) -> sqlite3.Row | None:
        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        return cur.execute(
            "SELECT * FROM descargas WHERE estado = 'pendiente' ORDER BY creada LIMIT 1"
        ).fetchone()

    def estados_descarga(self) -> dict[str, str]:
        return dict(self.con.execute("SELECT identificador, estado FROM descargas"))

    def ruta_descarga(self, identificador: str) -> str | None:
        fila = self.con.execute("SELECT ruta FROM descargas WHERE identificador = ?", (identificador,)).fetchone()
        return fila[0] if fila else None

    def marcar_descarga_eliminada(self, ruta: str) -> None:
        """Si el video vino de la descarga automática, que no se vuelva a bajar."""
        self.con.execute("UPDATE descargas SET estado = 'eliminada' WHERE ruta = ?", (ruta,))
        self.con.commit()

    def resumen_descargas(self) -> tuple[int, int]:
        """(cantidad, bytes) de las películas descargadas o en cola."""
        n, total = self.con.execute(
            "SELECT COUNT(*), COALESCE(SUM(tamano), 0) FROM descargas "
            "WHERE estado IN ('pendiente', 'descargando', 'completa', 'archivada')"
        ).fetchone()
        return n, total

    def reiniciar_descargas_interrumpidas(self) -> None:
        self.con.execute("UPDATE descargas SET estado = 'pendiente' WHERE estado = 'descargando'")
        self.con.commit()

    def categoria_id(self, nombre: str) -> int:
        """Id de la categoría; la crea si no existe."""
        self.con.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (nombre,))
        self.con.commit()
        return self.con.execute("SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]

    def rutas_conocidas(self) -> set[str]:
        return {fila[0] for fila in self.con.execute("SELECT ruta FROM archivos")}

    def carpetas_biblioteca(self) -> list[str]:
        return [c for c in self.config("carpetas_biblioteca").split(SEPARADOR_CARPETAS) if c.strip()]

    def id_de_ruta(self, ruta: str) -> int | None:
        fila = self.con.execute("SELECT id FROM archivos WHERE ruta = ?", (ruta,)).fetchone()
        return fila[0] if fila else None

    # --- Archivos ---------------------------------------------------------

    def agregar_archivos(self, rutas: list[Path]) -> int:
        """Agrega archivos soportados; devuelve cuántos eran nuevos."""
        nuevos = 0
        for ruta in rutas:
            tipo = tipo_de(ruta)
            if tipo is None:
                continue
            cur = self.con.execute(
                "INSERT OR IGNORE INTO archivos (ruta, nombre, tipo) VALUES (?, ?, ?)",
                (str(ruta.resolve()), ruta.name, tipo),
            )
            nuevos += cur.rowcount
        self.con.commit()
        return nuevos

    def mover_ruta(self, vieja: Path, nueva: Path, subtitulos: dict[str, str]) -> None:
        """El archivo cambió de lugar: conserva sus categorías y subtítulos.
        subtitulos: {ruta vieja: ruta nueva} de los subtítulos que se movieron con él."""
        self.con.execute("UPDATE archivos SET ruta = ?, nombre = ? WHERE ruta = ?",
                         (str(nueva), nueva.name, str(vieja)))
        self.con.execute("UPDATE subtitulos SET ruta_video = ? WHERE ruta_video = ?", (str(nueva), str(vieja)))
        self.con.execute("UPDATE descargas SET ruta = ? WHERE ruta = ?", (str(nueva), str(vieja)))
        self.con.executemany("UPDATE subtitulos SET ruta_sub = ? WHERE ruta_sub = ?",
                             [(n, v) for v, n in subtitulos.items()])
        self.con.commit()

    def agregar_carpeta(self, carpeta: Path) -> int:
        rutas = [p for p in carpeta.rglob("*") if p.is_file() and tipo_de(p)]
        return self.agregar_archivos(rutas)

    def quitar_archivo(self, archivo_id: int) -> None:
        """Quita el archivo de la biblioteca (no lo borra del disco)."""
        self.con.execute("DELETE FROM archivos WHERE id = ?", (archivo_id,))
        self.con.commit()

    def listar_archivos(self, filtro: str = "todos", categoria_id: int | None = None,
                        texto: str = "") -> list[tuple[int, str, str, str]]:
        """Devuelve (id, ruta, nombre, tipo) según el filtro elegido.

        filtro: "todos", "video", "imagen", "sin_categoria" o "categoria".
        """
        sql = "SELECT a.id, a.ruta, a.nombre, a.tipo FROM archivos a"
        condiciones, params = [], []
        if filtro == "categoria":
            sql += " JOIN archivo_categoria ac ON ac.archivo_id = a.id"
            condiciones.append("ac.categoria_id = ?")
            params.append(categoria_id)
        elif filtro == "sin_categoria":
            condiciones.append("NOT EXISTS (SELECT 1 FROM archivo_categoria ac WHERE ac.archivo_id = a.id)")
        elif filtro in ("video", "imagen"):
            condiciones.append("a.tipo = ?")
            params.append(filtro)
        if texto:
            condiciones.append("a.nombre LIKE ?")
            params.append(f"%{texto}%")
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        filas = self.con.execute(sql, params).fetchall()
        return sorted(filas, key=lambda f: orden_natural(f[2]))

    # --- Categorías -------------------------------------------------------

    def listar_categorias(self) -> list[tuple[int, str, int]]:
        """Devuelve (id, nombre, cantidad de archivos), con Favoritos primero."""
        return self.con.execute(
            """
            SELECT c.id, c.nombre, COUNT(ac.archivo_id)
            FROM categorias c LEFT JOIN archivo_categoria ac ON ac.categoria_id = c.id
            GROUP BY c.id ORDER BY c.id = ? DESC, c.nombre COLLATE NOCASE
            """,
            (self.favoritos,),
        ).fetchall()

    def crear_categoria(self, nombre: str) -> None:
        self.con.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))
        self.con.commit()

    def renombrar_categoria(self, categoria_id: int, nombre: str) -> None:
        self.con.execute("UPDATE categorias SET nombre = ? WHERE id = ?", (nombre, categoria_id))
        self.con.commit()

    def borrar_categoria(self, categoria_id: int) -> None:
        self.con.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
        self.con.commit()

    def categorias_de(self, archivo_id: int) -> set[int]:
        filas = self.con.execute(
            "SELECT categoria_id FROM archivo_categoria WHERE archivo_id = ?", (archivo_id,)
        )
        return {f[0] for f in filas}

    def categorias_por_archivo(self) -> dict[int, list[int]]:
        """{id de archivo: [ids de sus categorías]}, de toda la biblioteca de una vez."""
        resultado: dict[int, list[int]] = {}
        for aid, cid in self.con.execute("SELECT archivo_id, categoria_id FROM archivo_categoria"):
            resultado.setdefault(aid, []).append(cid)
        return resultado

    def archivos_por_id(self, archivo_ids: list[int]) -> list[tuple[int, str, str]]:
        """(id, ruta, tipo) de esos archivos, en el mismo orden (se saltean los que no existen)."""
        filas = {f[0]: f for f in self.con.execute(
            f"SELECT id, ruta, tipo FROM archivos WHERE id IN ({','.join('?' * len(archivo_ids))})",
            archivo_ids)} if archivo_ids else {}
        return [filas[a] for a in archivo_ids if a in filas]

    def asignar(self, archivo_id: int, categoria_id: int, activa: bool) -> None:
        self.asignar_varios([archivo_id], categoria_id, activa)

    def asignar_varios(self, archivo_ids: list[int], categoria_id: int, activa: bool) -> None:
        pares = [(aid, categoria_id) for aid in archivo_ids]
        if activa:
            self.con.executemany("INSERT OR IGNORE INTO archivo_categoria VALUES (?, ?)", pares)
        else:
            self.con.executemany(
                "DELETE FROM archivo_categoria WHERE archivo_id = ? AND categoria_id = ?", pares
            )
        self.con.commit()

    def siguiente_en_categoria(self, ruta_video: str) -> str | None:
        """Siguiente capítulo: el video que sigue, en orden natural de nombre
        («Cap 2» antes que «Cap 10»), entre los que comparten categoría con este."""
        if not re.search(r"\d", Path(ruta_video).name):
            return None
        filas = self.con.execute(
            """
            SELECT DISTINCT a.ruta, a.nombre FROM archivos a
            JOIN archivo_categoria ac ON ac.archivo_id = a.id
            WHERE a.tipo = 'video' AND ac.categoria_id IN (
                SELECT ac2.categoria_id FROM archivo_categoria ac2
                JOIN archivos a2 ON a2.id = ac2.archivo_id WHERE a2.ruta = ?)
            """,
            (ruta_video,),
        ).fetchall()
        rutas = [ruta for ruta, nombre in sorted(filas, key=lambda f: orden_natural(f[1]))]
        if ruta_video not in rutas:
            return None
        return next((r for r in rutas[rutas.index(ruta_video) + 1:] if Path(r).exists()), None)

    # --- Progreso (vistos y dónde quedó cada video) ------------------------------

    def guardar_progreso(self, ruta: str, posicion_ms: int, duracion_ms: int) -> None:
        if duracion_ms <= 0:
            return
        terminado = posicion_ms >= duracion_ms * VISTO_DESDE
        # Al terminarlo ya no hay desde dónde seguir: la próxima vez arranca de cero
        self.con.execute(
            """
            INSERT INTO progreso (ruta, posicion_ms, duracion_ms, visto) VALUES (?, ?, ?, ?)
            ON CONFLICT (ruta) DO UPDATE SET posicion_ms = excluded.posicion_ms,
                duracion_ms = excluded.duracion_ms, visto = MAX(visto, excluded.visto),
                actualizado = julianday('now')
            """,
            (ruta, 0 if terminado else posicion_ms, duracion_ms, int(terminado)),
        )
        self.con.commit()

    def marcar_vistos(self, rutas: list[str], visto: bool) -> None:
        self.con.executemany(
            """
            INSERT INTO progreso (ruta, visto) VALUES (?, ?)
            ON CONFLICT (ruta) DO UPDATE SET visto = excluded.visto, posicion_ms = 0,
                actualizado = julianday('now')
            """,
            [(r, int(visto)) for r in rutas],
        )
        self.con.commit()

    def progresos(self) -> dict[str, tuple[int, int, bool]]:
        """{ruta: (posición ms, duración ms, visto)} de los videos que se empezaron a ver."""
        return {r: (p, d, bool(v)) for r, p, d, v in
                self.con.execute("SELECT ruta, posicion_ms, duracion_ms, visto FROM progreso")}

    def posicion_guardada(self, ruta: str) -> int:
        """Dónde quedó el video la última vez (0 si casi no se vio o ya se terminó)."""
        fila = self.con.execute("SELECT posicion_ms FROM progreso WHERE ruta = ?", (ruta,)).fetchone()
        return fila[0] if fila and fila[0] >= RETOMAR_DESDE_MS else 0

    def para_seguir(self, rutas: list[str]) -> str | None:
        """De una lista de capítulos en orden: el último que quedó a medias o,
        si no hay, el primero sin ver."""
        if not rutas:
            return None
        marcadores = ",".join("?" * len(rutas))
        fila = self.con.execute(
            f"""SELECT ruta FROM progreso WHERE ruta IN ({marcadores}) AND posicion_ms >= ?
                ORDER BY actualizado DESC LIMIT 1""",
            (*rutas, RETOMAR_DESDE_MS),
        ).fetchone()
        if fila:
            return fila[0]
        vistos = {r for r, in self.con.execute(
            f"SELECT ruta FROM progreso WHERE visto AND ruta IN ({marcadores})", rutas)}
        return next((r for r in rutas if r not in vistos), None)

    def seguir_viendo(self, limite: int = 15) -> list[tuple[int, str, str, int, int]]:
        """Los videos que quedaron a medias, el último que se tocó primero:
        (id, ruta, nombre, posición ms, duración ms)."""
        return self.con.execute(
            """
            SELECT a.id, a.ruta, a.nombre, p.posicion_ms, p.duracion_ms FROM progreso p
            JOIN archivos a ON a.ruta = p.ruta
            WHERE a.tipo = 'video' AND p.posicion_ms >= ? AND p.duracion_ms > 0
                AND p.posicion_ms < p.duracion_ms * ?
            ORDER BY p.actualizado DESC LIMIT ?
            """,
            (RETOMAR_DESDE_MS, VISTO_DESDE, limite),
        ).fetchall()

    def vistos_por_categoria(self) -> dict[int, int]:
        """{id de categoría: cantidad de videos vistos}."""
        return dict(self.con.execute(
            """
            SELECT ac.categoria_id, COUNT(*) FROM archivo_categoria ac
            JOIN archivos a ON a.id = ac.archivo_id
            JOIN progreso p ON p.ruta = a.ruta AND p.visto
            GROUP BY ac.categoria_id
            """
        ).fetchall())

    def videos_por_categoria(self) -> dict[int, int]:
        """{id de categoría: cantidad de videos}."""
        return dict(self.con.execute(
            """
            SELECT ac.categoria_id, COUNT(*) FROM archivo_categoria ac
            JOIN archivos a ON a.id = ac.archivo_id
            WHERE a.tipo = 'video'
            GROUP BY ac.categoria_id
            """
        ).fetchall())

    # --- Subtítulos ----------------------------------------------------------

    def subtitulos_de(self, ruta_video: str) -> tuple[str | None, int] | None:
        """(ruta del subtítulo o None, retraso ms), o None si nunca se configuró."""
        return self.con.execute(
            "SELECT ruta_sub, retraso_ms FROM subtitulos WHERE ruta_video = ?", (ruta_video,)
        ).fetchone()

    def guardar_subtitulos(self, ruta_video: str, ruta_sub: str | None, retraso_ms: int) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO subtitulos VALUES (?, ?, ?)", (ruta_video, ruta_sub, retraso_ms)
        )
        self.con.commit()

    def quitar_archivos(self, archivo_ids: list[int]) -> None:
        """Quita varios archivos de la biblioteca (no los borra del disco)."""
        self.con.executemany("DELETE FROM archivos WHERE id = ?", [(a,) for a in archivo_ids])
        self.con.commit()
