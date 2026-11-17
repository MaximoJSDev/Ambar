"""Excepciones compartidas por los servicios de dominio."""

from datetime import time, timedelta


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


class NoEncontrado(Exception):
    pass


class CupoLleno(Exception):
    """No hay lugar en ningún grupo de primer semestre."""


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
