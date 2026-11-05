"""Migraciones incrementales para bases de datos existentes."""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

log = logging.getLogger("sige")

_MIGRACION_DOMICILIO_ESTRUCTURADO = "2026_11_04_domicilio_estructurado"


def _migrar_domicilio_estructurado(conn: Connection) -> None:
    columnas = {columna["name"] for columna in inspect(conn).get_columns("alumnos")}
    if "domicilio" not in columnas:
        return

    conn.execute(text("""CREATE TABLE IF NOT EXISTS domicilios (
        id_domicilio INT AUTO_INCREMENT PRIMARY KEY,
        numero_control VARCHAR(20) NOT NULL UNIQUE,
        codigo_postal CHAR(5),
        estado VARCHAR(100),
        municipio VARCHAR(100),
        colonia VARCHAR(150),
        calle VARCHAR(255) NOT NULL,
        numero_exterior VARCHAR(20),
        FOREIGN KEY (numero_control) REFERENCES alumnos(numero_control)
            ON UPDATE CASCADE ON DELETE CASCADE
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"""))
    conn.execute(text("""INSERT INTO domicilios (numero_control, calle)
                         SELECT a.numero_control, COALESCE(a.domicilio, '')
                         FROM alumnos a
                         LEFT JOIN domicilios d ON d.numero_control = a.numero_control
                         WHERE d.numero_control IS NULL"""))
    conn.execute(text("ALTER TABLE alumnos DROP COLUMN domicilio"))
    log.info("Migrado domicilio antiguo de alumnos a domicilios.")


def aplicar_migraciones(conn: Connection) -> None:
    """Aplica una sola vez cada migración compatible con el esquema actual."""
    inspector = inspect(conn)
    if not inspector.has_table("alumnos"):
        raise RuntimeError(
            "No existe la tabla alumnos. Inicializa la base de datos con ambar-db.sql."
        )

    conn.execute(text("""CREATE TABLE IF NOT EXISTS ambar_schema_migrations (
        version VARCHAR(100) PRIMARY KEY,
        applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))
    aplicada = conn.execute(
        text("""SELECT version FROM ambar_schema_migrations
                WHERE version = :version"""),
        {"version": _MIGRACION_DOMICILIO_ESTRUCTURADO},
    ).scalar_one_or_none()
    if aplicada is not None:
        return

    _migrar_domicilio_estructurado(conn)
    conn.execute(
        text("INSERT INTO ambar_schema_migrations (version) VALUES (:version)"),
        {"version": _MIGRACION_DOMICILIO_ESTRUCTURADO},
    )
    log.info("Migración de base de datos aplicada: %s", _MIGRACION_DOMICILIO_ESTRUCTURADO)
