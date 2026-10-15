"""Dependencias de FastAPI: usuario autenticado y control por rol."""
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from . import seguridad
from .config import engine
from .constantes import ROL_DOCENTE, ROL_SECRETARIA

SELECT_USUARIO = f"""
    SELECT u.id_usuario, u.correo, u.password, u.estatus, r.nombre_rol AS rol,
           CASE r.nombre_rol
               WHEN '{ROL_SECRETARIA}' THEN CONCAT_WS(' ', ps.nombres, ps.apellidos)
               WHEN '{ROL_DOCENTE}' THEN CONCAT_WS(' ', d.nombres, d.apellidos)
           END AS nombre
    FROM usuarios u
    JOIN roles r ON r.id_rol = u.id_rol
    LEFT JOIN personal_secretaria ps ON ps.id_usuario = u.id_usuario
    LEFT JOIN empleados_docentes d ON d.id_usuario = u.id_usuario
"""

_bearer = HTTPBearer(auto_error=False)


def _no_autenticado(mensaje: str) -> HTTPException:
    return HTTPException(401, {"mensaje": mensaje}, headers={"WWW-Authenticate": "Bearer"})


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise _no_autenticado("No has iniciado sesión")
    try:
        payload = seguridad.decodificar(cred.credentials)
        id_usuario = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _no_autenticado("Tu sesión expiró. Inicia sesión de nuevo.")

    with engine.connect() as conn:
        fila = conn.execute(
            text(SELECT_USUARIO + " WHERE u.id_usuario = :id"),
            {"id": id_usuario},
        ).mappings().first()
    # Se consulta en cada petición: una cuenta dada de baja pierde acceso de inmediato
    if fila is None or fila["estatus"] != "Activo":
        raise _no_autenticado("La cuenta no está activa")
    return {
        "id_usuario": fila["id_usuario"],
        "correo": fila["correo"],
        "nombre": fila["nombre"] or fila["correo"],
        "rol": fila["rol"],
        "bid": payload.get("bid"),
    }


def requiere_roles(*roles: str):
    def dependencia(usuario: dict = Depends(usuario_actual)) -> dict:
        if usuario["rol"] not in roles:
            raise HTTPException(403, {"mensaje": "No tienes permiso para esta acción"})
        return usuario
    return dependencia
