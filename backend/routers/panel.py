"""Datos del panel de Secretaría."""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import bindparam, text

from .. import reportes
from ..config import settings
from ..constantes import ROL_SECRETARIA, SEMESTRE_INGRESO, TIPOS_REQUERIDOS
from ..config import engine
from ..deps import requiere_roles

router = APIRouter(prefix="/panel", tags=["Panel"])


@router.get("/estadisticas")
def estadisticas(_: dict = Depends(requiere_roles(ROL_SECRETARIA))):
    """Estadísticas de alumnos por grupo y género para el periodo actual."""
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT p.id_paquete,
                           p.nombre_paquete AS grupo,
                           p.semestre,
                           MIN(g.turno) AS turno,
                           MIN(g.cupo_maximo) AS cupo_por_grupo,
                           COUNT(DISTINCT CASE
                               WHEN (a.numero_control IS NOT NULL
                                     AND a.eliminado = FALSE
                                     AND a.estatus = 'Activo')
                                 OR (r.numero_control IS NOT NULL
                                     AND r.eliminado = FALSE)
                               THEN i.numero_control END) AS total,
                           COUNT(DISTINCT CASE
                               WHEN a.genero = 'hombre'
                                AND ((a.numero_control IS NOT NULL
                                      AND a.eliminado = FALSE
                                      AND a.estatus = 'Activo')
                                     OR (r.numero_control IS NOT NULL
                                         AND r.eliminado = FALSE))
                               THEN i.numero_control END) AS hombres,
                           COUNT(DISTINCT CASE
                               WHEN a.genero = 'mujer'
                                AND ((a.numero_control IS NOT NULL
                                      AND a.eliminado = FALSE
                                      AND a.estatus = 'Activo')
                                     OR (r.numero_control IS NOT NULL
                                         AND r.eliminado = FALSE))
                               THEN i.numero_control END) AS mujeres,
                           COUNT(DISTINCT CASE
                               WHEN a.genero = 'no_binario'
                                AND ((a.numero_control IS NOT NULL
                                      AND a.eliminado = FALSE
                                      AND a.estatus = 'Activo')
                                     OR (r.numero_control IS NOT NULL
                                         AND r.eliminado = FALSE))
                               THEN i.numero_control END) AS no_binarios,
                           COUNT(DISTINCT CASE
                               WHEN (a.genero IS NULL OR a.genero NOT IN ('hombre', 'mujer', 'no_binario'))
                                AND (
                                    (a.numero_control IS NOT NULL
                                     AND a.eliminado = FALSE
                                     AND a.estatus = 'Activo')
                                    OR (r.numero_control IS NOT NULL
                                        AND r.eliminado = FALSE)
                                )
                               THEN i.numero_control END) AS sin_especificar
                    FROM paquetes_horario p
                    JOIN grupos g ON g.id_paquete = p.id_paquete
                    LEFT JOIN inscripciones_grupos i ON i.id_grupo = g.id_grupo
                    LEFT JOIN alumnos a ON a.numero_control = i.numero_control
                    LEFT JOIN reinscripciones r ON r.numero_control = i.numero_control
                    WHERE g.periodo_escolar = :periodo
                      AND p.semestre BETWEEN 1 AND 3
                    GROUP BY p.id_paquete, p.nombre_paquete, p.semestre
                    ORDER BY p.nombre_paquete"""),
            {"periodo": settings.periodo},
        ).mappings().all()

    grupos = []
    for fila in filas:
        cupo = int(fila["cupo_por_grupo"] or 25)
        total = int(fila["total"] or 0)
        grupos.append({
            "id_paquete": int(fila["id_paquete"]),
            "grupo": fila["grupo"],
            "semestre": int(fila["semestre"]),
            "turno": fila["turno"],
            "cupo": cupo,
            "total": total,
            "hombres": int(fila["hombres"] or 0),
            "mujeres": int(fila["mujeres"] or 0),
            "no_binarios": int(fila["no_binarios"] or 0),
            "sin_especificar": int(fila["sin_especificar"] or 0),
            "lugares_disponibles": max(cupo - total, 0),
        })
    return {"periodo": settings.periodo, "grupos": grupos}


@router.get("/estadisticas/pdf")
def descargar_estadisticas(
    _: dict = Depends(requiere_roles(ROL_SECRETARIA)),
):
    datos = estadisticas({})
    contenido = reportes.generar_estadisticas_grupos_pdf(datos)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="estadisticas_grupos.pdf"'},
    )


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

        reinscripciones = conn.execute(
            text("""SELECT COUNT(*) FROM reinscripciones
                    WHERE creado_en >= CURRENT_DATE
                      AND creado_en < CURRENT_DATE + INTERVAL 1 DAY"""),
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
        "reinscripciones_hoy": reinscripciones,
        "actividad": [
            {"numero_control": f["numero_control"],
             "alumno": f["alumno"],
             "tramite": "Alta" if f["docs"] >= completo else "Documentos",
             "estado": "Completada" if f["docs"] >= completo else "Pendiente"}
            for f in recientes
        ],
    }
