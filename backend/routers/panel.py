"""Datos del panel de Secretaría."""
from fastapi import APIRouter, Depends
from sqlalchemy import bindparam, text

from ..config import settings
from ..constantes import ROL_SECRETARIA, SEMESTRE_INGRESO, TIPOS_REQUERIDOS
from ..config import engine
from ..deps import requiere_roles

router = APIRouter(prefix="/panel", tags=["Panel"])


@router.get("/resumen")
def resumen(_: dict = Depends(requiere_roles(ROL_SECRETARIA))):
    en_tipos = bindparam("tipos", expanding=True)
    with engine.connect() as conn:
        nuevos = conn.execute(
            text("""SELECT COUNT(*) FROM alumnos
                    WHERE semestre_actual = :s AND estatus = 'Activo' AND eliminado = FALSE"""),
            {"s": SEMESTRE_INGRESO},
        ).scalar_one()

        grupos = conn.execute(
            text("SELECT COUNT(DISTINCT id_paquete) FROM grupos WHERE periodo_escolar = :p"),
            {"p": settings.periodo},
        ).scalar_one()

        recientes = conn.execute(
            text("""SELECT a.numero_control,
                           CONCAT_WS(
                               ' ', a.apellido_paterno, a.apellido_materno, a.nombres
                           ) AS alumno,
                           a.apellido_paterno, a.apellido_materno, a.nombres,
                           (SELECT COUNT(*) FROM expedientes_digitales e
                            WHERE e.numero_control = a.numero_control
                              AND e.tipo_documento IN :tipos) AS docs
                    FROM alumnos a
                    WHERE a.eliminado = FALSE
                    ORDER BY a.apellido_paterno, a.apellido_materno, a.nombres,
                             a.numero_control""").bindparams(
                en_tipos
            ),
            {"tipos": TIPOS_REQUERIDOS},
        ).mappings().all()

    completo = len(TIPOS_REQUERIDOS)
    return {
        "alumnos_nuevo_ingreso": nuevos,
        "grupos": grupos,
        "reinscripciones_hoy": 0,       # aún no existe tabla/módulo de reinscripciones
        "actividad": [
            {"numero_control": f["numero_control"],
             "alumno": f["alumno"],
             "tramite": "Alta" if f["docs"] >= completo else "Documentos",
             "estado": "Completada" if f["docs"] >= completo else "Pendiente"}
            for f in recientes
        ],
    }
