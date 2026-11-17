"""Manejo común de errores de la API en la interfaz."""

from collections.abc import Callable

import flet as ft
from api_client import ApiError

from ui.components import snackbar


def manejar_error_api(
    error: ApiError, navegar: Callable[[str], None], ruta_login: str, page: ft.Page,
    aviso: ft.Text | None = None, mostrar: Callable[[str], None] | None = None,
) -> bool:
    if error.status == 401:
        navegar(ruta_login)
        return True
    if aviso is not None:
        aviso.value = error.mensaje
        aviso.visible = True
    elif mostrar is not None:
        mostrar(error.mensaje)
    else:
        snackbar(page, error.mensaje)
    return False
