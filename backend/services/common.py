"""Utilidades y excepciones comunes de los servicios."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date, time, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import TextClause

from ..config import engine, settings

NOMBRE_CANDADO = "sige_altas"


@contextmanager
def _administrar_candado_mysql_altas() -> Iterator[None]:
    """Adquiere y libera el candado MySQL de altas."""
    with engine.connect() as candado:
        if candado.execute(
            text("SELECT GET_LOCK(:n, 20)"), {"n": NOMBRE_CANDADO},
        ).scalar() != 1:
            raise Ocupado()
        try:
            yield
        finally:
            candado.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": NOMBRE_CANDADO})


def _formatear_hora(valor: time | timedelta | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, timedelta):
        segundos_totales = int(valor.total_seconds())
        signo = "-" if segundos_totales < 0 else ""
        horas, resto = divmod(abs(segundos_totales), 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{signo}{horas:02d}:{minutos:02d}:{segundos:02d}"
    return valor.strftime("%H:%M:%S")


def _obtener_fecha_inicio_periodo(
    conn: Connection, periodo: str, consulta: TextClause,
) -> date | None:
    """Devuelve la fecha de inicio guardada para un periodo."""
    fila = conn.execute(consulta, {"periodo": periodo}).mappings().first()
    return fila["fecha_inicio"] if fila else None


def _semana_del_periodo(fecha_inicio: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return max(0, (hoy - fecha_inicio).days // 7 + 1)


class NoEncontrado(Exception):
    pass


class CupoLleno(Exception):
    """No hay lugar en ningún grupo de primer semestre."""


def _inscribir_en_grupos(
    conn: Connection, numero_control: str, ids_grupo: Iterable[int],
) -> None:
    ids = sorted(ids_grupo)
    if settings.db_tidb:
        descontar = text("""UPDATE grupos
                            SET cupo_disponible = cupo_disponible - 1
                            WHERE id_grupo = :grupo AND cupo_disponible > 0""")
        for id_grupo in ids:
            if conn.execute(descontar, {"grupo": id_grupo}).rowcount != 1:
                raise CupoLleno("El paquete seleccionado ya no tiene cupo disponible.")
    conn.execute(
        text("""INSERT INTO inscripciones_grupos (numero_control, id_grupo)
                VALUES (:numero, :grupo)"""),
        [{"numero": numero_control, "grupo": id_grupo} for id_grupo in ids],
    )


class SinGrupos(Exception):
    """El periodo no tiene grupos de primer semestre configurados."""


class Ocupado(Exception):
    """No se obtuvo el candado de altas a tiempo."""


class Conflicto(Exception):
    def __init__(self, mensaje: str, errores: dict[str, str] | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.errores = errores or {}


class NumeroControlDuplicado(Conflicto):
    pass
