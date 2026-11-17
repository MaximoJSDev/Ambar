"""Consultas del registro de accesos."""

from sqlalchemy import text

from ..config import engine
from .common import _formatear_hora


def listar_bitacora_accesos(limite: int = 200) -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT b.id_bitacora, b.fecha, b.hora_entrada, b.hora_salida,
                           u.correo, r.nombre_rol AS rol,
                           COALESCE(
                               NULLIF(TRIM(CONCAT_WS(' ', ps.nombres, ps.apellidos)), ''),
                               NULLIF(TRIM(CONCAT_WS(' ', d.nombres, d.apellidos)), ''),
                               u.correo
                           ) AS nombre
                    FROM bitacora_accesos b
                    JOIN usuarios u ON u.id_usuario = b.id_usuario
                    JOIN roles r ON r.id_rol = u.id_rol
                    LEFT JOIN personal_secretaria ps ON ps.id_usuario = u.id_usuario
                    LEFT JOIN empleados_docentes d ON d.id_usuario = u.id_usuario
                    ORDER BY b.fecha DESC, b.hora_entrada DESC, b.id_bitacora DESC
                    LIMIT :limite"""),
            {"limite": limite},
        ).mappings().all()
    return [
        {
            "id_bitacora": fila["id_bitacora"],
            "fecha": fila["fecha"].strftime("%d/%m/%Y"),
            "hora_entrada": _formatear_hora(fila["hora_entrada"]),
            "hora_salida": _formatear_hora(fila["hora_salida"]),
            "correo": fila["correo"],
            "rol": fila["rol"],
            "nombre": fila["nombre"],
        }
        for fila in filas
    ]
