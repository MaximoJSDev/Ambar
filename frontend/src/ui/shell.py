"""Persistent navigation frame reused while switching route content."""

import flet as ft

from ui.components import snackbar
from ui.navigation import ADMIN_NAV, DOCENTE_NAV, IMPLEMENTADAS, NAV
from ui.theme import BG, GOLD, MUTED, NAVY, TEXT, WHITE

class Shell:
    """Marco fijo de la aplicación: barra lateral + encabezado + pie.

    Se construye UNA sola vez por sesión y vive en una única `ft.View`. Al navegar
    solo se cambia `self.host.content` y el resaltado del menú; así la barra azul no
    se vuelve a crear ni hay transición de pantalla (el "zoom" de Flutter aparece
    cuando se reemplazan Views).
    """

    def __init__(self, page: ft.Page, usuario: dict, navegar, cerrar_sesion):
        self.page = page
        self.navegar = navegar
        self.activo: str | None = None
        self._items: dict[str, tuple[ft.Container, ft.Icon, ft.Text]] = {}
        self._controles_navegacion: list[ft.Container] = []

        items = []
        if usuario["rol"] == "Administrador":
            nav = ADMIN_NAV
        elif usuario["rol"] == "Secretaría":
            nav = NAV
        else:
            nav = DOCENTE_NAV
        for destino, nombre, icono in nav:
            ico = ft.Icon(icono, size=18, color="#C9D3E3")
            txt = ft.Text(nombre, size=14, color="#E1E8F3")
            cont = ft.Container(
                margin=ft.Margin.symmetric(horizontal=12, vertical=2),
                padding=ft.Padding.symmetric(horizontal=14, vertical=13),
                border_radius=6,
                ink=True,
                on_click=lambda e, d=destino, n=nombre: self._ir(d, n),
                content=ft.Row(spacing=14, controls=[ico, txt]),
            )
            self._items[destino] = (cont, ico, txt)
            self._controles_navegacion.append(cont)
            items.append(cont)

        def pie(icono, texto, on_click):
            control = ft.Container(
                padding=ft.Padding.symmetric(horizontal=26, vertical=10),
                ink=True,
                on_click=on_click,
                content=ft.Row(spacing=10, controls=[
                    ft.Icon(icono, size=16, color="#E1E8F3"),
                    ft.Text(texto, size=14, color="#E1E8F3"),
                ]),
            )
            self._controles_navegacion.append(control)
            return control

        barra_lateral = ft.Container(
            width=230,
            bgcolor=NAVY,
            content=ft.Column(
                spacing=0,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Column(spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=20, top=24, bottom=18),
                            content=ft.Column(spacing=4, controls=[
                                ft.Row(spacing=10, controls=[
                                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED, color=GOLD, size=40),
                                    ft.Text("SIGE", size=30, weight=ft.FontWeight.BOLD, color=WHITE),
                                ]),
                                ft.Text("Campus Acapulco", size=12, color="#D5DDEA"),
                            ]),
                        ),
                        ft.Divider(height=1, color="#2B4A78"),
                        ft.Container(height=4),
                        *items,
                    ]),
                    ft.Column(spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
                        pie(ft.Icons.HELP_OUTLINE, "Ayuda", lambda e: snackbar(
                            page, "Ayuda: contacta al área de sistemas del campus.")),
                        pie(ft.Icons.LOGOUT, "Cerrar sesión", lambda e: cerrar_sesion()),
                        ft.Container(height=14),
                    ]),
                ],
            ),
        )

        encabezado = ft.Container(
            height=72,
            bgcolor=WHITE,
            padding=ft.Padding.symmetric(horizontal=32),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Sistema Integral de Gestión Escolar", size=22,
                            weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Column(spacing=2, alignment=ft.MainAxisAlignment.CENTER, controls=[
                        ft.Text(usuario["nombre"], size=14, weight=ft.FontWeight.BOLD, color=TEXT),
                        ft.Text(usuario["rol"], size=12, color=MUTED),
                    ]),
                ],
            ),
        )

        # Mantener el marco fuera del scroll conserva fija la navegación; cada pantalla controla su propio desplazamiento.
        self.host = ft.Container(expand=True, bgcolor=BG, padding=32)

        self.view = ft.View(
            route="/secretaria",
            padding=0,
            spacing=0,
            bgcolor=BG,
            controls=[ft.Row(expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
                barra_lateral,
                ft.Column(expand=True, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                          controls=[encabezado, self.host]),
            ])],
        )

    def _ir(self, destino: str, nombre: str):
        if destino in IMPLEMENTADAS:
            self.navegar(destino)
        else:
            snackbar(self.page, f"El módulo «{nombre}» estará disponible próximamente.")

    def mostrar(self, ruta: str, contenido: ft.Control):
        """Cambia el contenido y el elemento activo del menú sin recrear el marco."""
        self.activo = ruta
        # Evita que los accesos laterales interrumpan la tabulación del formulario de altas.
        permitir_tab_navegacion = ruta != "/altas"
        for control in self._controles_navegacion:
            control.ink = permitir_tab_navegacion
        for r, (cont, ico, txt) in self._items.items():
            act = r == ruta
            cont.bgcolor = GOLD if act else None
            ico.color = WHITE if act else "#C9D3E3"
            txt.color = WHITE if act else "#E1E8F3"
            txt.weight = ft.FontWeight.BOLD if act else ft.FontWeight.NORMAL
        self.host.content = contenido
