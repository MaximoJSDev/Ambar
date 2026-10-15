"""Datos del panel de Secretaría."""
from fastapi import APIRouter, Depends
from sqlalchemy import bindparam, text

from ..config import settings
from ..constantes import DOCUMENTOS, ROL_SECRETARIA, SEMESTRE_INGRESO, TIPOS_REQUERIDOS
from ..config import engine
from ..deps import requiere_roles

router = APIRouter(prefix="/panel", tags=["Panel"])


@router.get("/resumen")
def resumen(_: dict = Depends(requiere_roles(ROL_SECRETARIA))):
    en_tipos = bindparam("tipos", expanding=True)
    with engine.connect() as conn:
        nuevos = conn.execute(
            text("SELECT COUNT(*) FROM alumnos WHERE semestre_actual = :s AND estatus = 'Activo'"),
            {"s": SEMESTRE_INGRESO},
        ).scalar_one()

        grupos = conn.execute(
            text("SELECT COUNT(DISTINCT id_paquete) FROM grupos WHERE periodo_escolar = :p"),
            {"p": settings.periodo},
        ).scalar_one()

        # Expediente pendiente = alumno activo sin alguno de los documentos requeridos
        pendientes = conn.execute(
            text("""SELECT COUNT(*) FROM alumnos a
                    WHERE a.estatus = 'Activo' AND (
                        SELECT COUNT(*) FROM expedientes_digitales e
                        WHERE e.numero_control = a.numero_control
                          AND e.tipo_documento IN :tipos) < :n""").bindparams(en_tipos),
            {"tipos": TIPOS_REQUERIDOS, "n": len(TIPOS_REQUERIDOS)},
        ).scalar_one()

        faltantes = []
        for visible, tipo_bd in DOCUMENTOS.values():
            cantidad = conn.execute(
                text("""SELECT COUNT(*) FROM alumnos a
                        WHERE a.estatus = 'Activo' AND NOT EXISTS (
                            SELECT 1 FROM expedientes_digitales e
                            WHERE e.numero_control = a.numero_control AND e.tipo_documento = :t)"""),
                {"t": tipo_bd},
            ).scalar_one()
            if cantidad:
                faltantes.append({"documento": visible, "cantidad": cantidad})
        faltantes.sort(key=lambda f: -f["cantidad"])

        recientes = conn.execute(
            text("""SELECT CONCAT_WS(' ', a.nombres, a.apellido_paterno, a.apellido_materno) AS alumno,
                           (SELECT COUNT(*) FROM expedientes_digitales e
                            WHERE e.numero_control = a.numero_control
                              AND e.tipo_documento IN :tipos) AS docs
                    FROM alumnos a
                    ORDER BY (SELECT MAX(i.id_inscripcion) FROM inscripciones_grupos i
                              WHERE i.numero_control = a.numero_control) DESC,
                             a.numero_control DESC
                    LIMIT 6""").bindparams(en_tipos),
            {"tipos": TIPOS_REQUERIDOS},
        ).mappings().all()

    completo = len(TIPOS_REQUERIDOS)
    return {
        "alumnos_nuevo_ingreso": nuevos,
        "grupos": grupos,
        "expedientes_pendientes": pendientes,
        "reinscripciones_hoy": 0,       # aún no existe tabla/módulo de reinscripciones
        "pendientes": faltantes,
        "actividad": [
            {"alumno": f["alumno"],
             "tramite": "Alta" if f["docs"] >= completo else "Documentos",
             "estado": "Completada" if f["docs"] >= completo else "Pendiente"}
            for f in recientes
        ],
    }
