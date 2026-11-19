"""Vista de estadísticas académicas por grupo."""

import flet as ft

from api_client import ApiError
from app_state import api
from ui.components import crear_tarjeta, snackbar, titulo_pagina
from ui.errors import manejar_error_api
from ui.files import descargar_pdf_y_abrir
from ui.theme import BORDER, GOLD, MUTED, NAVY, TEXT, WARN_BG, WARN_FG


def build_estadisticas(page: ft.Page, navegar) -> ft.Control:
    aviso_error = ft.Container(
        bgcolor=WARN_BG,
        border_radius=8,
        padding=12,
        visible=False,
        content=ft.Text("", size=13, color=WARN_FG),
    )
    periodo = ft.Text("", size=13, color=MUTED)
    resumen = ft.ResponsiveRow(spacing=16, run_spacing=16)
    listado = ft.Column(spacing=8)

    def estadistica(valor, etiqueta, detalle=None, color=NAVY):
        return ft.Container(
            col={"xs": 12, "sm": 6, "lg": 3},
            content=crear_tarjeta(ft.Column(spacing=4, controls=[
                ft.Text(str(valor), size=30, weight=ft.FontWeight.BOLD, color=color),
                ft.Text(etiqueta, size=12, color=MUTED),
                *([ft.Text(detalle, size=11, color=MUTED)] if detalle else []),
            ]), padding=16),
        )

    def descargar(_):
        try:
            descargar_pdf_y_abrir(
                "estadisticas_grupos.pdf",
                lambda _: api.descargar_estadisticas_grupos(),
            )
        except ApiError as ex:
            manejar_error_api(ex, navegar, "/", page)
        except OSError as ex:
            snackbar(page, f"No se pudo guardar el PDF: {ex}")

    def cargar():
        aviso_error.visible = False
        try:
            datos = api.estadisticas_grupos()
        except ApiError as ex:
            manejar_error_api(ex, navegar, "/", page)
            aviso_error.content = ft.Text(ex.mensaje, size=13, color=WARN_FG)
            aviso_error.visible = True
            page.update()
            return

        grupos = datos["grupos"]
        periodo.value = f"Periodo escolar: {datos['periodo']}"
        totales = datos["totales"]
        porcentajes = totales["porcentajes"]
        resumen.controls = [
            estadistica(len(grupos), "Grupos registrados"),
            estadistica(totales["total"], "Alumnos inscritos"),
            estadistica(
                totales["hombres"], "Hombres (general)",
                f'{porcentajes["hombres"]:.1f}% del total',
            ),
            estadistica(
                totales["mujeres"], "Mujeres (general)",
                f'{porcentajes["mujeres"]:.1f}% del total',
            ),
        ]

        listado.controls = []
        if not grupos:
            listado.controls.append(ft.Text("No hay grupos registrados en el periodo actual.", color=MUTED))
        else:
            encabezado = ft.Container(
                bgcolor="#EEF1F6",
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border_radius=6,
                content=ft.Row(spacing=8, controls=[
                    ft.Text("Grupo", weight=ft.FontWeight.BOLD, color=NAVY, expand=3),
                    ft.Text("Total", weight=ft.FontWeight.BOLD, color=NAVY, expand=1),
                    ft.Text("Hombres (n / %)", size=11, weight=ft.FontWeight.BOLD, color=NAVY, expand=1),
                    ft.Text("Mujeres (n / %)", size=11, weight=ft.FontWeight.BOLD, color=NAVY, expand=1),
                    ft.Text("No binario (n / %)", size=11, weight=ft.FontWeight.BOLD, color=NAVY, expand=1),
                    ft.Text("Sin especificar (n / %)", size=11, weight=ft.FontWeight.BOLD, color=NAVY, expand=1),
                    ft.Text("Cupo", weight=ft.FontWeight.BOLD, color=NAVY, expand=1),
                ]),
            )
            listado.controls.append(encabezado)
            for grupo in grupos:
                listado.controls.append(ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=12),
                    border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.Row(spacing=8, controls=[
                        ft.Column(expand=3, spacing=2, controls=[
                            ft.Text(grupo["grupo"], size=13, weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Text(
                                f"Semestre {grupo['semestre']} · {grupo['turno']}",
                                size=11,
                                color=MUTED,
                            ),
                        ]),
                        ft.Text(str(grupo["total"]), size=13, color=TEXT, expand=1),
                        *[
                            ft.Text(
                                f'{grupo[categoria]} / {grupo["porcentajes"][categoria]:.1f}%',
                                size=12,
                                color=TEXT,
                                expand=1,
                            )
                            for categoria in (
                                "hombres", "mujeres", "no_binarios", "sin_especificar",
                            )
                        ],
                        ft.Column(expand=1, spacing=2, controls=[
                            ft.Text(f"{grupo['lugares_disponibles']} disponibles", size=12, color=TEXT),
                            ft.Text(f"de {grupo['cupo']}", size=11, color=MUTED),
                        ]),
                    ]),
                ))

        page.update()

    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=18, controls=[
        ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                titulo_pagina(
                    "Estadísticas por grupo",
                    "Consulta la matrícula y distribución de género de cada grupo.",
                ),
                ft.FilledButton(
                    "Descargar PDF",
                    icon=ft.Icons.PICTURE_AS_PDF_OUTLINED,
                    on_click=descargar,
                ),
            ],
        ),
        periodo,
        aviso_error,
        resumen,
        crear_tarjeta(ft.Column(spacing=10, controls=[
            ft.Text("Detalle por grupo", size=18, weight=ft.FontWeight.BOLD, color=NAVY),
            listado,
        ]), padding=18),
    ])
