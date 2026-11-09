"""Authentication screen and login interaction."""

import asyncio
import time

import flet as ft
from api_client import ApiError
from ambar_common import validators as v

from app_state import api
from ui.components import crear_campo_texto, estilo_boton_primario
from ui.theme import BG, BORDER, GOLD, MUTED, NAVY, TEXT, WHITE



def build_login(page: ft.Page, al_entrar) -> ft.View:
    correo = crear_campo_texto("usuario@acapulco.tecnm.mx", autofocus=True, keyboard_type=ft.KeyboardType.EMAIL)
    password = crear_campo_texto("Contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", color=ft.Colors.RED_700, size=13, weight=ft.FontWeight.W_600, visible=False)
    boton = ft.FilledButton(
        "Iniciar sesión",
        style=estilo_boton_primario(),
        height=46,
    )

    def bloquear_ui(bloqueado: bool):
        password.disabled = bloqueado
        boton.disabled = bloqueado

    async def cuenta_regresiva(segundos: int):
        fin = time.monotonic() + segundos
        try:
            while True:
                segundos_restantes = int(fin - time.monotonic() + 0.999)
                if segundos_restantes <= 0:
                    break
                aviso.value = (f"Cuenta bloqueada por demasiados intentos. "
                               f"Intenta de nuevo en {segundos_restantes // 60}:{segundos_restantes % 60:02d}.")
                aviso.visible = True
                page.update()
                await asyncio.sleep(1)
            aviso.visible = False
            bloquear_ui(False)
            password.value = ""
            page.update()
        except Exception:
            # Al cambiar de vista, Flet puede invalidar los controles que actualiza esta tarea.
            pass

    def autenticar(e=None):
        correo_normalizado = (correo.value or "").strip().lower()
        contrasena = password.value or ""
        correo.error = None
        password.error = None
        aviso.visible = False

        error_correo = v.validar_correo_login(correo_normalizado)
        if error_correo:
            correo.error = error_correo
            page.update()
            return
        if not contrasena:
            password.error = "Contraseña obligatoria"
            page.update()
            return

        # La llamada al API es síncrona; deshabilitar el botón evita solicitudes duplicadas.
        boton.disabled = True
        page.update()
        try:
            usuario = api.login(correo_normalizado, contrasena)
        except ApiError as ex:
            boton.disabled = False
            if ex.status == 423:        # El servidor centraliza el bloqueo y comunica el tiempo restante.
                bloquear_ui(True)
                page.update()
                page.run_task(cuenta_regresiva, int(ex.extra.get("segundos", 300)))
                return
            if ex.status == 401:        # El mensaje no distingue entre correo inexistente y contraseña incorrecta.
                restantes = ex.extra.get("intentos_restantes", 0)
                password.error = (f"Contraseña incorrecta. Te quedan {restantes} "
                                  f"intento{'s' if restantes != 1 else ''}.")
            else:
                aviso.value = ex.mensaje
                aviso.visible = True
            page.update()
            return
        boton.disabled = False
        password.value = ""
        al_entrar(usuario)

    boton.on_click = autenticar
    correo.on_submit = autenticar
    password.on_submit = autenticar

    def ayuda(e=None):
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Necesitas ayuda para acceder?"),
            content=ft.Text("Si olvidaste tu contraseña o tu cuenta fue bloqueada, "
                            "contacta al área de sistemas de tu campus."),
            actions=[ft.TextButton("Entendido", on_click=lambda _: page.pop_dialog())],
        ))

    panel_izq = ft.Container(
        expand=5,
        bgcolor=NAVY,
        padding=ft.Padding.only(left=76, right=40, top=140, bottom=100),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(spacing=8, controls=[
                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED, color=GOLD, size=60),
                    ft.Text("SIGE", size=68, weight=ft.FontWeight.BOLD, color=WHITE),
                    ft.Text("Sistema Integral de\nGestión Escolar", size=26, color=WHITE),
                    ft.Container(width=136, height=5, bgcolor=GOLD, margin=ft.Margin.only(top=18, bottom=14)),
                    ft.Text("TecNM • Campus Acapulco", size=20, color="#D5DDEA"),
                ]),
                ft.Column(spacing=4, controls=[
                    ft.Text("Servicios escolares y docentes", size=19, color=WHITE),
                    ft.Text("en una sola plataforma.", size=19, color="#D5DDEA"),
                ]),
            ],
        ),
    )

    tarjeta_login = ft.Container(
        width=620,
        bgcolor=WHITE,
        border=ft.Border.all(1, BORDER),
        border_radius=14,
        padding=52,
        content=ft.Column(
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Text("Bienvenido", size=36, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text("Ingresa con tu cuenta institucional.", size=16, color=MUTED),
                ft.Container(height=30),
                ft.Text("Correo institucional", size=13, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(height=6),
                correo,
                ft.Container(height=20),
                ft.Text("Contraseña", size=13, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(height=6),
                password,
                ft.Container(height=10),
                aviso,
                ft.Container(height=14),
                ft.Row(controls=[ft.Container(content=boton, expand=True)]),
                ft.Container(height=22),
                ft.Text("El sistema identifica tu perfil al iniciar sesión.", size=13, color=MUTED),
                ft.Container(height=14),
                ft.Row(controls=[ft.Container(
                    content=ft.Text("¿Necesitas ayuda para acceder?", size=14,
                                    weight=ft.FontWeight.BOLD, color=NAVY),
                    on_click=ayuda,
                )]),
            ],
        ),
    )

    panel_der = ft.Container(expand=7, bgcolor=BG, alignment=ft.Alignment.CENTER, content=tarjeta_login)

    return ft.View(
        route="/",
        padding=0,
        spacing=0,
        bgcolor=BG,
        controls=[ft.Row(expand=True, spacing=0, controls=[panel_izq, panel_der])],
    )
