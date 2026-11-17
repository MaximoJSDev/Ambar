"""Servicios de docentes y calificaciones."""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import bindparam, text

from ..config import engine, settings
from .common import Conflicto, NoEncontrado, _formatear_hora, _obtener_fecha_inicio_periodo, _semana_del_periodo
from .periodos import _SQL_FECHA_INICIO

SEMANAS_EVALUACION = {
    "Semana 5": 5,
    "Semana 9": 9,
    "Semana 13": 13,
    "Final": 17,
}


def listar_grupos_docente(id_usuario: int) -> list[dict]:
    """Devuelve solo los grupos asignados al docente, con su horario y calificaciones."""
    dias = ("", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes")
    with engine.connect() as conn:
        fecha_inicio = _obtener_fecha_inicio_periodo(conn, settings.periodo, _SQL_FECHA_INICIO)
        filas = conn.execute(
            text("""SELECT g.id_grupo, p.id_paquete, p.nombre_paquete AS grupo,
                           m.nombre_materia, g.aula, g.creditos, g.turno,
                           g.periodo_escolar, d.nombres AS docente_nombres,
                           d.apellidos AS docente_apellidos,
                           h.dia_semana, h.hora_inicio, h.hora_fin
                    FROM empleados_docentes d
                    JOIN grupos g ON g.id_docente = d.id_docente
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    JOIN materias m ON m.id_materia = g.id_materia
                    LEFT JOIN horarios_grupo h ON h.id_grupo = g.id_grupo
                    WHERE d.id_usuario = :usuario AND g.periodo_escolar = :periodo
                    ORDER BY p.nombre_paquete, m.nombre_materia, h.dia_semana"""),
            {"usuario": id_usuario, "periodo": settings.periodo},
        ).mappings().all()

        grupos: dict[int, dict] = {}
        for fila in filas:
            grupo = grupos.setdefault(fila["id_grupo"], {
                "id_grupo": fila["id_grupo"],
                "id_paquete": fila["id_paquete"],
                "grupo": fila["grupo"],
                "nombre_materia": fila["nombre_materia"],
                "aula": fila["aula"],
                "creditos": fila["creditos"],
                "turno": fila["turno"],
                "periodo": fila["periodo_escolar"],
                "docente": " ".join(filter(None, (
                    fila["docente_nombres"], fila["docente_apellidos"],
                ))),
                "horarios": [],
                "alumnos": [],
            })
            if fila["dia_semana"] is not None:
                inicio = fila["hora_inicio"]
                fin = fila["hora_fin"]
                grupo["horarios"].append({
                    "dia": dias[fila["dia_semana"]],
                    "inicio": inicio[:5] if isinstance(inicio, str) else _formatear_hora(inicio)[:5],
                    "fin": fin[:5] if isinstance(fin, str) else _formatear_hora(fin)[:5],
                })

        if not grupos:
            return []

        semana_actual = _semana_del_periodo(fecha_inicio) if fecha_inicio else None
        evaluaciones_disponibles = [
            periodo for periodo, semana in SEMANAS_EVALUACION.items()
            if semana_actual is not None and semana_actual >= semana
        ]
        inscripciones = conn.execute(
            text("""SELECT i.id_grupo, i.numero_control,
                           COALESCE(a.nombres, r.nombre) AS nombres,
                           COALESCE(a.apellido_paterno, r.apellido_paterno) AS apellido_paterno,
                           COALESCE(a.apellido_materno, r.apellido_materno) AS apellido_materno,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Semana 5' THEN c.valor END) AS semana_5,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Semana 9' THEN c.valor END) AS semana_9,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Semana 13' THEN c.valor END) AS semana_13,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Final' THEN c.valor END) AS final,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Final'
                                    THEN c.confirmada ELSE FALSE END) AS final_confirmada
                    FROM inscripciones_grupos i
                    LEFT JOIN alumnos a ON a.numero_control = i.numero_control
                    LEFT JOIN reinscripciones r ON r.numero_control = i.numero_control
                    LEFT JOIN calificaciones c ON c.id_inscripcion = i.id_inscripcion
                    WHERE i.id_grupo IN :grupos
                      AND ((a.numero_control IS NOT NULL AND a.estatus = 'Activo'
                            AND a.eliminado = FALSE)
                           OR (r.numero_control IS NOT NULL AND r.eliminado = FALSE))
                    GROUP BY i.id_grupo, i.numero_control, a.numero_control, r.nombre,
                             a.nombres, r.nombre, r.apellido_paterno, r.apellido_materno,
                             a.apellido_paterno, a.apellido_materno
                    ORDER BY i.id_grupo,
                             COALESCE(a.apellido_paterno, r.apellido_paterno),
                             COALESCE(a.apellido_materno, r.apellido_materno),
                             COALESCE(a.nombres, r.nombre),
                             i.numero_control""").bindparams(
                bindparam("grupos", expanding=True)
            ),
            {"grupos": list(grupos)},
        ).mappings().all()

    for fila in inscripciones:
        grupos[fila["id_grupo"]]["alumnos"].append({
            "numero_control": fila["numero_control"],
            "nombres": fila["nombres"],
            "apellido_paterno": fila["apellido_paterno"],
            "apellido_materno": fila["apellido_materno"],
            "nombre_completo": " ".join(filter(None, (
                fila["apellido_paterno"], fila["apellido_materno"], fila["nombres"],
            ))),
            "semana_5": fila["semana_5"],
            "semana_9": fila["semana_9"],
            "semana_13": fila["semana_13"],
            "final": fila["final"],
            "final_confirmada": bool(fila["final_confirmada"]),
        })
    for grupo in grupos.values():
        grupo["semana_actual"] = semana_actual
        grupo["evaluaciones_disponibles"] = evaluaciones_disponibles
        grupo["fecha_inicio_periodo"] = fecha_inicio
    return list(grupos.values())


def _inscripcion_docente_bloqueada(conn, id_usuario: int, id_grupo: int, numero_control: str):
    fila = conn.execute(
        text("""SELECT i.id_inscripcion
                FROM inscripciones_grupos i
                JOIN grupos g ON g.id_grupo = i.id_grupo
                JOIN empleados_docentes d ON d.id_docente = g.id_docente
                LEFT JOIN alumnos a ON a.numero_control = i.numero_control
                LEFT JOIN reinscripciones r ON r.numero_control = i.numero_control
                WHERE d.id_usuario = :usuario AND g.id_grupo = :grupo
                  AND g.periodo_escolar = :periodo
                  AND i.numero_control = :numero
                  AND ((a.numero_control IS NOT NULL AND a.estatus = 'Activo'
                        AND a.eliminado = FALSE)
                       OR (r.numero_control IS NOT NULL AND r.eliminado = FALSE))
                FOR UPDATE"""),
        {
            "usuario": id_usuario,
            "grupo": id_grupo,
            "periodo": settings.periodo,
            "numero": numero_control,
        },
    ).mappings().first()
    if fila is None:
        raise NoEncontrado
    return fila["id_inscripcion"]


def guardar_calificacion_docente(
    id_usuario: int,
    id_grupo: int,
    numero_control: str,
    periodo_evaluacion: str,
    valor: int,
) -> dict:
    if periodo_evaluacion not in ("Semana 5", "Semana 9", "Semana 13"):
        raise Conflicto("Selecciona un periodo de evaluación válido.")
    with engine.begin() as conn:
        inscripcion = _inscripcion_docente_bloqueada(
            conn, id_usuario, id_grupo, numero_control,
        )
        fecha_inicio = _obtener_fecha_inicio_periodo(conn, settings.periodo, _SQL_FECHA_INICIO)
        if fecha_inicio is None:
            raise Conflicto("El administrador aún no configuró la fecha de inicio de este periodo.")
        if _semana_del_periodo(fecha_inicio) < SEMANAS_EVALUACION[periodo_evaluacion]:
            raise Conflicto(f"La captura de {periodo_evaluacion} aún no está habilitada.")
        final_confirmada = conn.execute(
            text("""SELECT confirmada FROM calificaciones
                    WHERE id_inscripcion = :inscripcion AND periodo_evaluacion = 'Final'
                    FOR UPDATE"""),
            {"inscripcion": inscripcion},
        ).scalar_one_or_none()
        if final_confirmada:
            raise Conflicto(
                "No se pueden modificar los periodos después de confirmar la calificación final."
            )

        periodo_previo = {
            "Semana 9": "Semana 5",
            "Semana 13": "Semana 9",
        }.get(periodo_evaluacion)
        if periodo_previo is not None:
            calificacion_previa = conn.execute(
                text("""SELECT valor FROM calificaciones
                        WHERE id_inscripcion = :inscripcion
                          AND periodo_evaluacion = :periodo
                        FOR UPDATE"""),
                {"inscripcion": inscripcion, "periodo": periodo_previo},
            ).scalar_one_or_none()
            if calificacion_previa is None:
                raise Conflicto(
                    f"No se puede capturar {periodo_evaluacion} sin registrar "
                    f"primero {periodo_previo}."
                )

        conn.execute(
            text("""INSERT INTO calificaciones (id_inscripcion, periodo_evaluacion, valor)
                    VALUES (:inscripcion, :periodo, :valor)
                    ON DUPLICATE KEY UPDATE valor = VALUES(valor)"""),
            {"inscripcion": inscripcion, "periodo": periodo_evaluacion, "valor": valor},
        )
    return {"numero_control": numero_control, "periodo_evaluacion": periodo_evaluacion, "valor": valor}


def confirmar_calificacion_final_docente(
    id_usuario: int,
    id_grupo: int,
    numero_control: str,
) -> dict:
    with engine.begin() as conn:
        inscripcion = _inscripcion_docente_bloqueada(
            conn, id_usuario, id_grupo, numero_control,
        )
        fecha_inicio = _obtener_fecha_inicio_periodo(conn, settings.periodo, _SQL_FECHA_INICIO)
        if fecha_inicio is None:
            raise Conflicto("El administrador aún no configuró la fecha de inicio de este periodo.")
        if _semana_del_periodo(fecha_inicio) < SEMANAS_EVALUACION["Final"]:
            raise Conflicto("La calificación final solo se puede confirmar a partir de la semana 17.")

        final_existente = conn.execute(
            text("""SELECT confirmada FROM calificaciones
                    WHERE id_inscripcion = :inscripcion AND periodo_evaluacion = 'Final'
                    FOR UPDATE"""),
            {"inscripcion": inscripcion},
        ).scalar_one_or_none()
        if final_existente:
            raise Conflicto("La calificación final ya fue confirmada y no se puede modificar.")

        periodos = conn.execute(
            text("""SELECT periodo_evaluacion, valor FROM calificaciones
                    WHERE id_inscripcion = :inscripcion
                      AND periodo_evaluacion IN ('Semana 5', 'Semana 9', 'Semana 13')
                    FOR UPDATE"""),
            {"inscripcion": inscripcion},
        ).mappings().all()
        valores = {fila["periodo_evaluacion"]: Decimal(str(fila["valor"])) for fila in periodos}
        requeridos = ("Semana 5", "Semana 9", "Semana 13")
        faltantes = [periodo for periodo in requeridos if periodo not in valores]
        if faltantes:
            raise Conflicto(
                f"No se puede confirmar la final; faltan calificaciones: {', '.join(faltantes)}."
            )

        promedio_exacto = sum(valores.values()) / Decimal(3)
        promedio = promedio_exacto.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        final = promedio if promedio_exacto >= 70 else Decimal("0")
        if final_existente is None:
            conn.execute(
                text("""INSERT INTO calificaciones
                            (id_inscripcion, periodo_evaluacion, valor, confirmada)
                        VALUES (:inscripcion, 'Final', :valor, TRUE)"""),
                {"inscripcion": inscripcion, "valor": final},
            )
        else:
            conn.execute(
                text("""UPDATE calificaciones
                        SET valor = :valor, confirmada = TRUE
                        WHERE id_inscripcion = :inscripcion
                          AND periodo_evaluacion = 'Final' AND confirmada = FALSE"""),
                {"inscripcion": inscripcion, "valor": final},
            )
    return {
        "numero_control": numero_control,
        "periodo_evaluacion": "Final",
        "valor": final,
        "confirmada": True,
    }
