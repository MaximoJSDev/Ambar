"""Consulta de usuario con su nombre según el rol.

usuarios no guarda el nombre: Secretaría lo toma de personal_secretaria y Docente de
empleados_docentes. Para otros roles (o si no hay ficha de personal) se usa el correo.
"""
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
