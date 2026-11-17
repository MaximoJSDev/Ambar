"""Excepciones compartidas por los servicios de dominio."""


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
