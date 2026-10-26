"""Persistencia en SQLite: archivos, categorías y su relación."""
import sqlite3
from pathlib import Path

EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".flv", ".mpg", ".mpeg"}
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def tipo_de(ruta: Path) -> str | None:
    ext = ruta.suffix.lower()
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_IMAGEN:
        return "imagen"
    return None


class Biblioteca:
    def __init__(self, ruta_db: Path):
        self.con = sqlite3.connect(ruta_db)
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
            """
        )
        self.con.commit()

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
        sql += " ORDER BY a.nombre COLLATE NOCASE"
        return self.con.execute(sql, params).fetchall()

    # --- Categorías -------------------------------------------------------

    def listar_categorias(self) -> list[tuple[int, str, int]]:
        """Devuelve (id, nombre, cantidad de archivos)."""
        return self.con.execute(
            """
            SELECT c.id, c.nombre, COUNT(ac.archivo_id)
            FROM categorias c LEFT JOIN archivo_categoria ac ON ac.categoria_id = c.id
            GROUP BY c.id ORDER BY c.nombre COLLATE NOCASE
            """
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
