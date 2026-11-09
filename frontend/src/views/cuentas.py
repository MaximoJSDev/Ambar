"""Administrative account creation and directory screens."""

import flet as ft
from api_client import ApiError
from ambar_common import validators as v

from app_state import api
from ui.components import (
    chip,
    crear_campo_etiquetado,
    crear_campo_texto,
    crear_tarjeta,
    estilo_boton_primario,
    estilo_boton_secundario,
    snackbar,
    titulo_pagina,
)
from ui.theme import MUTED, NAVY, WARN_FG



def build_alta_secretaria(page: ft.Page, navegar) -> ft.Control:
    nombres = crear_campo_texto("Nombre(s)", max_length=50)
    apellidos = crear_campo_texto("Apellidos", max_length=50)
    correo = crear_campo_texto("usuario@acapulco.tecnm.mx", keyboard_type=ft.KeyboardType.EMAIL)
    password = crear_campo_texto("Contraseña (mínimo 10 caracteres)", password=True, can_reveal_password=True)
    confirmar = crear_campo_texto("Confirma la contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    boton = ft.FilledButton("Crear cuenta de secretaria", style=estilo_boton_primario())

    def crear(_):
        for campo in (nombres, apellidos, correo, password, confirmar):
            campo.error = None
        aviso.visible = False
        errores = []
        error_nombre = v.validar_nombre_personal(nombres.value or "", "Nombre", 50)
        if error_nombre:
            nombres.error = error_nombre
            errores.append(True)
        error_apellidos = v.validar_nombre_personal(apellidos.value or "", "Apellidos", 50)
        if error_apellidos:
            apellidos.error = error_apellidos
            errores.append(True)
        error_correo = v.validar_correo_institucional(correo.value or "")
        if error_correo:
            correo.error = error_correo
            errores.append(True)
        if len(password.value or "") < 10:
            password.error = "Usa al menos 10 caracteres"
            errores.append(True)
        if password.value != confirmar.value:
            confirmar.error = "Las contraseñas no coinciden"
            errores.append(True)
        if errores:
            page.update()
            return

        boton.disabled = True
        page.update()
        try:
            creada = api.crear_secretaria({
                "nombres": nombres.value,
                "apellidos": apellidos.value,
                "correo": correo.value,
                "password": password.value,
            })
            for campo in (nombres, apellidos, correo, password, confirmar):
                campo.value = ""
            snackbar(page, f"Cuenta creada para {creada['nombres']} {creada['apellidos']}.")
        except ApiError as ex:
            if ex.status == 401:
                navegar("/consultas")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
        finally:
            boton.disabled = False
            page.update()

    boton.on_click = crear
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina(
            "Alta de secretaria",
            "Crea una cuenta de acceso para personal de Secretaría.",
        ),
        crear_tarjeta(ft.Column(spacing=18, controls=[
            ft.ResponsiveRow(spacing=16, run_spacing=14, controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Nombre(s)", nombres)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Apellidos", apellidos)),
                ft.Container(col={"xs": 12}, content=crear_campo_etiquetado("Correo de acceso", correo)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Contraseña", password)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Confirmar contraseña", confirmar)),
            ]),
            ft.Text("La contraseña debe tener al menos 10 caracteres.", size=12, color=MUTED),
            aviso,
            ft.Row(alignment=ft.MainAxisAlignment.END, controls=[boton]),
        ])),
    ])


def build_alta_maestro(page: ft.Page, navegar) -> ft.Control:
    nombres = crear_campo_texto("Nombre(s)", max_length=50)
    apellidos = crear_campo_texto("Apellidos", max_length=50)
    correo = crear_campo_texto("usuario@acapulco.tecnm.mx", keyboard_type=ft.KeyboardType.EMAIL)
    password = crear_campo_texto("Contraseña (mínimo 10 caracteres)", password=True, can_reveal_password=True)
    confirmar = crear_campo_texto("Confirma la contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    boton = ft.FilledButton("Crear cuenta de maestro", style=estilo_boton_primario())

    def crear(_):
        for campo in (nombres, apellidos, correo, password, confirmar):
            campo.error = None
        aviso.visible = False
        errores = []
        error_nombre = v.validar_nombre_personal(nombres.value or "", "Nombre", 50)
        if error_nombre:
            nombres.error = error_nombre
            errores.append(True)
        error_apellidos = v.validar_nombre_personal(apellidos.value or "", "Apellidos", 50)
        if error_apellidos:
            apellidos.error = error_apellidos
            errores.append(True)
        error_correo = v.validar_correo_institucional(correo.value or "")
        if error_correo:
            correo.error = error_correo
            errores.append(True)
        if len(password.value or "") < 10:
            password.error = "Usa al menos 10 caracteres"
            errores.append(True)
        if password.value != confirmar.value:
            confirmar.error = "Las contraseñas no coinciden"
            errores.append(True)
        if errores:
            page.update()
            return

        boton.disabled = True
        page.update()
        try:
            creado = api.crear_docente({
                "nombres": nombres.value,
                "apellidos": apellidos.value,
                "correo": correo.value,
                "password": password.value,
            })
            for campo in (nombres, apellidos, correo, password, confirmar):
                campo.value = ""
            snackbar(page, f"Cuenta docente creada para {creado['nombres']} {creado['apellidos']}.")
        except ApiError as ex:
            if ex.status == 401:
                navegar("/secretaria")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
        finally:
            boton.disabled = False
            page.update()

    boton.on_click = crear
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina(
            "Alta de maestros",
            "Crea una cuenta de acceso para un maestro.",
        ),
        crear_tarjeta(ft.Column(spacing=18, controls=[
            ft.ResponsiveRow(spacing=16, run_spacing=14, controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Nombre(s)", nombres)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Apellidos", apellidos)),
                ft.Container(col={"xs": 12}, content=crear_campo_etiquetado("Correo de acceso", correo)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Contraseña", password)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Confirmar contraseña", confirmar)),
            ]),
            ft.Text("La contraseña debe tener al menos 10 caracteres.", size=12, color=MUTED),
            aviso,
            ft.Row(alignment=ft.MainAxisAlignment.END, controls=[boton]),
        ])),
    ])


def build_consulta_secretarias(page: ft.Page, navegar) -> ft.Control:
    filas = ft.Column(spacing=12)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)

    def cargar(_=None):
        aviso.visible = False
        try:
            registros = api.secretarias()
        except ApiError as ex:
            if ex.status == 401:
                navegar("/consultas")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
            filas.controls = []
        else:
            if not registros:
                filas.controls = [ft.Text("Aún no hay cuentas de secretarias.", size=14, color=MUTED)]
            else:
                filas.controls = [_tarjeta_secretaria(registro) for registro in registros]
        page.update()

    def dar_baja(registro: dict):
        def confirmar(_):
            page.pop_dialog()
            try:
                api.dar_baja_secretaria(registro["id_usuario"])
            except ApiError as ex:
                if ex.status == 401:
                    navegar("/consultas")
                    return
                snackbar(page, ex.mensaje)
            else:
                snackbar(page, f"Se dio de baja la cuenta de {registro['nombres']} {registro['apellidos']}.")
                cargar()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Dar de baja esta cuenta?"),
            content=ft.Text(
                f"{registro['nombres']} {registro['apellidos']} ya no podrá iniciar sesión. "
                "Sus datos se conservarán."
            ),
            actions=[
                ft.TextButton("Dar de baja", on_click=confirmar),
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _tarjeta_secretaria(registro: dict) -> ft.Control:
        activa = registro["estatus"] == "Activo"
        nombre = f"{registro['nombres']} {registro['apellidos']}"
        controles = [
            ft.Column(expand=True, spacing=5, controls=[
                ft.Text(nombre, size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(registro["correo"], size=13, color=MUTED),
            ]),
            chip("Activa" if activa else "Inactiva", activa),
        ]
        if activa:
            controles.append(ft.OutlinedButton(
                "Dar de baja",
                style=estilo_boton_secundario(),
                on_click=lambda _, r=registro: dar_baja(r),
            ))
        return crear_tarjeta(ft.Row(
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controles,
        ), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina(
            "Consulta de secretarias",
            "Revisa los datos de acceso y da de baja cuentas cuando sea necesario.",
        ),
        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[
            ft.OutlinedButton("Actualizar lista", icon=ft.Icons.REFRESH, on_click=cargar),
        ]),
        aviso,
        filas,
    ])


def build_consulta_maestros(page: ft.Page, navegar) -> ft.Control:
    filas = ft.Column(spacing=12)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)

    def cargar(_=None):
        aviso.visible = False
        try:
            registros = api.docentes()
        except ApiError as ex:
            if ex.status == 401:
                navegar("/secretaria")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
            filas.controls = []
        else:
            if not registros:
                filas.controls = [ft.Text("Aún no hay cuentas de maestros.", size=14, color=MUTED)]
            else:
                filas.controls = [_tarjeta_docente(registro) for registro in registros]
        page.update()

    def dar_baja(registro: dict):
        def confirmar(_):
            page.pop_dialog()
            try:
                api.dar_baja_docente(registro["id_usuario"])
            except ApiError as ex:
                if ex.status == 401:
                    navegar("/secretaria")
                    return
                snackbar(page, ex.mensaje)
            else:
                snackbar(page, f"Se dio de baja la cuenta de {registro['nombres']} {registro['apellidos']}.")
                cargar()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Dar de baja esta cuenta?"),
            content=ft.Text(
                f"{registro['nombres']} {registro['apellidos']} ya no podrá iniciar sesión. "
                "Sus datos se conservarán."
            ),
            actions=[
                ft.TextButton("Dar de baja", on_click=confirmar),
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _tarjeta_docente(registro: dict) -> ft.Control:
        activa = registro["estatus"] == "Activo"
        nombre = f"{registro['nombres']} {registro['apellidos']}"
        controles = [
            ft.Column(expand=True, spacing=5, controls=[
                ft.Text(nombre, size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(registro["correo"], size=13, color=MUTED),
            ]),
            chip("Activo" if activa else "Inactivo", activa),
        ]
        if activa:
            controles.append(ft.OutlinedButton(
                "Dar de baja",
                style=estilo_boton_secundario(),
                on_click=lambda _, r=registro: dar_baja(r),
            ))
        return crear_tarjeta(ft.Row(
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controles,
        ), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina(
            "Consulta de maestros",
            "Revisa los datos de acceso y da de baja cuentas cuando sea necesario.",
        ),
        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[
            ft.OutlinedButton("Actualizar lista", icon=ft.Icons.REFRESH, on_click=cargar),
        ]),
        aviso,
        filas,
    ])
