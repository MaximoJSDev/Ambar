"""Vistas de consulta del expediente y sus responsabilidades específicas."""

import flet as ft

from app_state import api
from .expediente import ConsultaExpediente
from .historial import _cambios_historial, _valor_historial, ordinal_semestre


def build_consultas(
    page: ft.Page,
    picker: ft.FilePicker,
    usuario: dict,
    navegar,
    numero_control: str | None = None,
) -> ft.Control:
    return ConsultaExpediente(
        page, picker, usuario, navegar, numero_control_inicial=numero_control,
    ).vista


def build_modificacion(page: ft.Page, picker: ft.FilePicker, usuario: dict, navegar) -> ft.Control:
    return ConsultaExpediente(
        page, picker, usuario, navegar, modo_modificacion=True,
    ).vista


def build_bajas(page: ft.Page, picker: ft.FilePicker, usuario: dict, navegar) -> ft.Control:
    return ConsultaExpediente(
        page, picker, usuario, navegar, modo_bajas=True,
    ).vista
