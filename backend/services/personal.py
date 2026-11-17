"""Operaciones de cuentas de Secretaría y Docencia."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..config import engine
from ..constantes import ROL_DOCENTE, ROL_SECRETARIA
from ..esquemas import DocenteCreate, SecretariaCreate
from ..seguridad import hashear
from .common import Conflicto, NoEncontrado


def _listar_personal(rol: str, tabla_perfil: str, alias_perfil: str) -> list[dict]:
    """Devuelve las cuentas activas o inactivas de un perfil de personal."""
    with engine.connect() as conn:
        filas = conn.execute(
            text(f"""SELECT u.id_usuario, u.correo, u.estatus, {alias_perfil}.nombres, {alias_perfil}.apellidos
                    FROM usuarios u
                    JOIN roles r ON r.id_rol = u.id_rol
                    JOIN {tabla_perfil} {alias_perfil} ON {alias_perfil}.id_usuario = u.id_usuario
                    WHERE r.nombre_rol = :rol
                    ORDER BY {alias_perfil}.apellidos, {alias_perfil}.nombres, u.correo"""),
            {"rol": rol},
        ).mappings().all()
    return [dict(fila) for fila in filas]


def listar_secretarias() -> list[dict]:
    return _listar_personal(ROL_SECRETARIA, "personal_secretaria", "ps")


def listar_docentes() -> list[dict]:
    return _listar_personal(ROL_DOCENTE, "empleados_docentes", "d")


def _crear_cuenta_personal(
    datos: SecretariaCreate, rol: str, tabla_perfil: str,
) -> dict:
    """Crea una cuenta y su perfil para el rol indicado."""
    try:
        with engine.begin() as conn:
            id_rol = conn.execute(
                text("SELECT id_rol FROM roles WHERE nombre_rol = :rol"),
                {"rol": rol},
            ).scalar_one_or_none()
            if id_rol is None:
                raise Conflicto(f"No está configurado el rol {rol} en la base de datos.")
            id_usuario = conn.execute(
                text("""INSERT INTO usuarios (correo, password, id_rol, estatus)
                        VALUES (:correo, :password, :rol, 'Activo')"""),
                {
                    "correo": datos.correo,
                    "password": hashear(datos.password),
                    "rol": id_rol,
                },
            ).lastrowid
            conn.execute(
                text(f"""INSERT INTO {tabla_perfil} (id_usuario, nombres, apellidos)
                        VALUES (:usuario, :nombres, :apellidos)"""),
                {
                    "usuario": id_usuario,
                    "nombres": datos.nombres,
                    "apellidos": datos.apellidos,
                },
            )
    except IntegrityError as exc:
        raise Conflicto("Ya existe una cuenta con ese correo.") from exc
    return {
        "id_usuario": id_usuario,
        "correo": datos.correo,
        "estatus": "Activo",
        "nombres": datos.nombres,
        "apellidos": datos.apellidos,
    }


def crear_secretaria(datos: SecretariaCreate) -> dict:
    return _crear_cuenta_personal(datos, ROL_SECRETARIA, "personal_secretaria")


def crear_docente(datos: DocenteCreate) -> dict:
    return _crear_cuenta_personal(datos, ROL_DOCENTE, "empleados_docentes")


def _dar_baja_personal(
    id_usuario: int, rol: str, tabla_perfil: str, alias_perfil: str,
) -> dict:
    """Desactiva una cuenta del perfil indicado y devuelve sus datos."""
    with engine.begin() as conn:
        fila = conn.execute(
            text(f"""SELECT u.id_usuario, u.correo, u.estatus, {alias_perfil}.nombres, {alias_perfil}.apellidos
                    FROM usuarios u
                    JOIN roles r ON r.id_rol = u.id_rol
                    JOIN {tabla_perfil} {alias_perfil} ON {alias_perfil}.id_usuario = u.id_usuario
                    WHERE u.id_usuario = :usuario AND r.nombre_rol = :rol
                    FOR UPDATE"""),
            {"usuario": id_usuario, "rol": rol},
        ).mappings().first()
        if fila is None:
            raise NoEncontrado()
        if fila["estatus"] == "Activo":
            conn.execute(
                text("UPDATE usuarios SET estatus = 'Inactivo' WHERE id_usuario = :usuario"),
                {"usuario": id_usuario},
            )
    return dict(fila) | {"estatus": "Inactivo"}


def dar_baja_docente(id_usuario: int) -> dict:
    return _dar_baja_personal(id_usuario, ROL_DOCENTE, "empleados_docentes", "d")


def dar_baja_secretaria(id_usuario: int) -> dict:
    return _dar_baja_personal(id_usuario, ROL_SECRETARIA, "personal_secretaria", "ps")
