"""Constantes de negocio compartidas por routers y servicios."""

from ambar_common.documents import DOCUMENTOS, DOCUMENTOS_MODIFICABLES

ROL_SECRETARIA = "Secretaría"
ROL_DOCENTE = "Docente"
ROL_ADMINISTRADOR = "Administrador"
TURNOS = ("Matutino", "Vespertino")
SEMESTRE_INGRESO = 1

TIPOS_REQUERIDOS = [tipo_bd for _, tipo_bd in DOCUMENTOS.values()]
