"""Consultas y mantenimiento de periodos escolares."""

import logging
from datetime import date

from sqlalchemy import text

from ..config import engine, settings
from .common import Conflicto, _obtener_fecha_inicio_periodo, _semana_del_periodo

log = logging.getLogger("sige")
_SQL_FECHA_INICIO = text("SELECT fecha_inicio FROM periodos_escolares WHERE periodo = :periodo")
_SQL_FECHA_INICIO_BLOQUEADA = text(
    "SELECT fecha_inicio FROM periodos_escolares WHERE periodo = :periodo FOR UPDATE"
)
_SQL_FECHA_INICIO_BLOQUEADA_AVANCE = text(
    "SELECT fecha_inicio FROM periodos_escolares\n"
    "                    WHERE periodo = :periodo FOR UPDATE"
)


def listar_periodos_escolares() -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT periodo, fecha_inicio, actualizado_en
                    FROM periodos_escolares
                    ORDER BY fecha_inicio DESC, periodo DESC""")
        ).mappings().all()
    return [dict(fila) for fila in filas]


def preparar_avances_semestre(conn) -> None:
    conn.execute(
        text("""CREATE TABLE IF NOT EXISTS avances_semestre (
                    periodo VARCHAR(20) PRIMARY KEY,
                    alumnos_avanzados INT UNSIGNED NOT NULL,
                    fecha_avance TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB""")
    )


def avanzar_semestre_si_corresponde() -> dict | None:
    periodo = settings.periodo
    with engine.begin() as conn:
        fecha_inicio = _obtener_fecha_inicio_periodo(
            conn, periodo, _SQL_FECHA_INICIO_BLOQUEADA_AVANCE,
        )
        if fecha_inicio is None:
            return None

        semana = _semana_del_periodo(fecha_inicio)
        if semana < 18:
            return None

        avance_existente = conn.execute(
            text("SELECT periodo FROM avances_semestre WHERE periodo = :periodo"),
            {"periodo": periodo},
        ).scalar_one_or_none()
        if avance_existente is not None:
            return None

        conn.execute(
            text("""INSERT INTO avances_semestre (periodo, alumnos_avanzados)
                    VALUES (:periodo, 0)"""),
            {"periodo": periodo},
        )
        resultado = conn.execute(
            text("""UPDATE alumnos
                    SET semestre_actual = LEAST(semestre_actual + 1, 10)
                    WHERE estatus = 'Activo' AND eliminado = FALSE
                      AND semestre_actual < 10""")
        )
        alumnos_avanzados = resultado.rowcount
        conn.execute(
            text("""UPDATE avances_semestre
                    SET alumnos_avanzados = :cantidad
                    WHERE periodo = :periodo"""),
            {"cantidad": alumnos_avanzados, "periodo": periodo},
        )

    log.info(
        "Avance de semestre aplicado periodo=%s semana=%s alumnos=%s",
        periodo, semana, alumnos_avanzados,
    )
    return {
        "periodo": periodo,
        "semana": semana,
        "alumnos_avanzados": alumnos_avanzados,
    }


def guardar_periodo_escolar(
    periodo: str,
    fecha_inicio: date,
    id_usuario: int,
    periodo_anterior: str | None = None,
) -> dict:
    origen = periodo_anterior or periodo
    with engine.begin() as conn:
        existente = _obtener_fecha_inicio_periodo(
            conn, origen, _SQL_FECHA_INICIO_BLOQUEADA,
        )
        if periodo_anterior and existente is None:
            raise Conflicto("El periodo seleccionado ya no existe. Actualiza la lista e inténtalo de nuevo.")

        if origen != periodo:
            duplicado = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM periodos_escolares WHERE periodo = :periodo)"),
                {"periodo": periodo},
            ).scalar_one()
            if duplicado:
                raise Conflicto("Ya existe un periodo con ese nombre.")
            grupos_destino = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM grupos WHERE periodo_escolar = :periodo)"),
                {"periodo": periodo},
            ).scalar_one()
            if grupos_destino:
                raise Conflicto(
                    "Ya hay grupos asociados al periodo de destino; no se pueden combinar automáticamente."
                )
            conn.execute(
                text("UPDATE grupos SET periodo_escolar = :nuevo WHERE periodo_escolar = :anterior"),
                {"nuevo": periodo, "anterior": origen},
            )
            conn.execute(
                text("""UPDATE periodos_escolares
                        SET periodo = :nuevo, fecha_inicio = :fecha_inicio, actualizado_por = :usuario
                        WHERE periodo = :anterior"""),
                {
                    "nuevo": periodo,
                    "anterior": origen,
                    "fecha_inicio": fecha_inicio,
                    "usuario": id_usuario,
                },
            )
            conn.execute(
                text("UPDATE avances_semestre SET periodo = :nuevo WHERE periodo = :anterior"),
                {"nuevo": periodo, "anterior": origen},
            )
        elif existente is not None:
            conn.execute(
                text("""UPDATE periodos_escolares
                        SET fecha_inicio = :fecha_inicio, actualizado_por = :usuario
                        WHERE periodo = :periodo"""),
                {"periodo": periodo, "fecha_inicio": fecha_inicio, "usuario": id_usuario},
            )
        else:
            conn.execute(
                text("""INSERT INTO periodos_escolares (periodo, fecha_inicio, actualizado_por)
                        VALUES (:periodo, :fecha_inicio, :usuario)"""),
                {"periodo": periodo, "fecha_inicio": fecha_inicio, "usuario": id_usuario},
            )
        fila = conn.execute(
            text("""SELECT periodo, fecha_inicio, actualizado_en
                    FROM periodos_escolares WHERE periodo = :periodo"""),
            {"periodo": periodo},
        ).mappings().one()
    if origen != periodo and settings.periodo == origen:
        settings.periodo_escolar = periodo
    return dict(fila)
