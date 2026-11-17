"""Pantallas de creación de cuentas administrativas y consulta de directorios."""

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
from ui.errors import manejar_error_api
from ui.theme import MUTED, NAVY, WARN_FG


def alta_cuenta(page: ft.Page, navegar, rol: str) -> ft.Control:
    configuraciones = {
        "secretaria": {
            "crear": api.crear_secretaria,
            "destino_error": "/consultas",
            "texto_boton": "Crear cuenta de secretaria",
            "titulo": "Alta de secretaria",
            "descripcion": "Crea una cuenta de acceso para personal de Secretaría.",
            "mensaje_exito": "Cuenta creada para",
        },
        "maestro": {
            "crear": api.crear_docente,
            "destino_error": "/secretaria",
            "texto_boton": "Crear cuenta de maestro",
            "titulo": "Alta de maestros",
            "descripcion": "Crea una cuenta de acceso para un maestro.",
            "mensaje_exito": "Cuenta docente creada para",
        },
    }
    config = configuraciones[rol]
    nombres = crear_campo_texto("Nombre(s)", max_length=50)
    apellidos = crear_campo_texto("Apellidos", max_length=50)
    correo = crear_campo_texto("usuario@acapulco.tecnm.mx", keyboard_type=ft.KeyboardType.EMAIL)
    password = crear_campo_texto("Contraseña (mínimo 10 caracteres)", password=True, can_reveal_password=True)
    confirmar = crear_campo_texto("Confirma la contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    boton = ft.FilledButton(config["texto_boton"], style=estilo_boton_primario())

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
            creada = config["crear"]({
                "nombres": nombres.value,
                "apellidos": apellidos.value,
                "correo": correo.value,
                "password": password.value,
            })
            for campo in (nombres, apellidos, correo, password, confirmar):
                campo.value = ""
            snackbar(
                page,
                f"{config['mensaje_exito']} {creada['nombres']} {creada['apellidos']}.",
            )
        except ApiError as ex:
            if manejar_error_api(ex, navegar, config["destino_error"], page, aviso):
                return
        finally:
            boton.disabled = False
            page.update()

    boton.on_click = crear
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina(config["titulo"], config["descripcion"]),
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


def consulta_cuentas(page: ft.Page, navegar, rol: str) -> ft.Control:
    configuraciones = {
        "secretaria": {
            "listar": api.secretarias,
            "dar_baja": api.dar_baja_secretaria,
            "destino_error": "/consultas",
            "vacio": "Aún no hay cuentas de secretarias.",
            "titulo": "Consulta de secretarias",
            "estatus_activa": "Activa",
            "estatus_inactiva": "Inactiva",
        },
        "maestro": {
            "listar": api.docentes,
            "dar_baja": api.dar_baja_docente,
            "destino_error": "/secretaria",
            "vacio": "Aún no hay cuentas de maestros.",
            "titulo": "Consulta de maestros",
            "estatus_activa": "Activo",
            "estatus_inactiva": "Inactivo",
        },
    }
    config = configuraciones[rol]
    filas = ft.Column(spacing=12)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)

    def cargar(_=None):
        aviso.visible = False
        try:
            registros = config["listar"]()
        except ApiError as ex:
            if manejar_error_api(ex, navegar, config["destino_error"], page, aviso):
                return
            filas.controls = []
        else:
            if not registros:
                filas.controls = [ft.Text(config["vacio"], size=14, color=MUTED)]
            else:
                filas.controls = [_tarjeta(registro) for registro in registros]
        page.update()

    def dar_baja(registro: dict):
        def confirmar(_):
            page.pop_dialog()
            try:
                config["dar_baja"](registro["id_usuario"])
            except ApiError as ex:
                manejar_error_api(ex, navegar, config["destino_error"], page)
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

    def _tarjeta(registro: dict) -> ft.Control:
        activa = registro["estatus"] == "Activo"
        nombre = f"{registro['nombres']} {registro['apellidos']}"
        controles = [
            ft.Column(expand=True, spacing=5, controls=[
                ft.Text(nombre, size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(registro["correo"], size=13, color=MUTED),
            ]),
            chip(config["estatus_activa"] if activa else config["estatus_inactiva"], activa),
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
            config["titulo"],
            "Revisa los datos de acceso y da de baja cuentas cuando sea necesario.",
        ),
        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[
            ft.OutlinedButton("Actualizar lista", icon=ft.Icons.REFRESH, on_click=cargar),
        ]),
        aviso,
        filas,
    ])
