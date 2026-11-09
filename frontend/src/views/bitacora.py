"""Administrative login and activity audit screen."""

import flet as ft
from api_client import ApiError

from app_state import api
from ui.components import crear_tarjeta, titulo_pagina
from ui.theme import MUTED, NAVY, TEXT, WARN_FG



def build_bitacora_admin(page: ft.Page, navegar) -> ft.Control:
    filas = ft.Column(spacing=0)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)

    def cargar(_=None):
        aviso.visible = False
        try:
            registros = api.bitacora()
        except ApiError as ex:
            if ex.status == 401:
                navegar("/consultas")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
            filas.controls = []
        else:
            if not registros:
                filas.controls = [ft.Text("Aún no hay accesos registrados.", size=14, color=MUTED)]
            else:
                filas.controls = [
                    crear_tarjeta(ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
                        ft.Container(col={"xs": 12, "md": 3}, content=ft.Column(spacing=3, controls=[
                            ft.Text(registro["nombre"], size=14, weight=ft.FontWeight.BOLD, color=NAVY),
                            ft.Text(registro["correo"], size=12, color=MUTED),
                        ])),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Perfil", size=11, color=MUTED),
                            ft.Text(registro["rol"], size=13, color=TEXT),
                        ])),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Fecha", size=11, color=MUTED),
                            ft.Text(registro["fecha"], size=13, color=TEXT),
                        ])),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Entrada", size=11, color=MUTED),
                            ft.Text(registro["hora_entrada"], size=13, color=TEXT),
                        ])),
                        ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Salida", size=11, color=MUTED),
                            ft.Text(registro["hora_salida"] or "Sesión en curso", size=13, color=TEXT),
                        ])),
                    ]), padding=ft.Padding.symmetric(horizontal=18, vertical=14))
                    for registro in registros
                ]
        page.update()

    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=20, controls=[
        titulo_pagina(
            "Bitácora de accesos",
            "Consulta los inicios y cierres de sesión registrados en el sistema.",
        ),
        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[
            ft.OutlinedButton("Actualizar", icon=ft.Icons.REFRESH, on_click=cargar),
        ]),
        aviso,
        filas,
    ])
