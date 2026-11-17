"""Edición y presentación de reinscripciones en la consulta del expediente."""

import re

import flet as ft
from ambar_common import validators as v
from api_client import ApiError

from app_state import api
from ui.components import (
    crear_campo_texto,
    crear_tarjeta,
    estilo_boton_primario,
    estilo_boton_secundario,
    snackbar,
)
from ui.errors import manejar_error_api
from ui.theme import MUTED, NAVY, TEXT, WHITE
from .historial import ordinal_semestre


class EdicionReinscripcion:
    def __init__(self, expediente):
        self.expediente = expediente

    def mostrar(self):
        expediente = self.expediente
        registro = expediente.reinscripcion_data
        numero = crear_campo_texto(
            value=registro["numero_control"],
            label="Número de control",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=8,
            read_only=True,
        )
        nombre = crear_campo_texto(value=registro["nombre"], label="Nombre", max_length=50)
        apellido_paterno = crear_campo_texto(
            value=registro["apellido_paterno"], label="Apellido paterno", max_length=50,
        )
        apellido_materno = crear_campo_texto(
            value=registro["apellido_materno"], label="Apellido materno", max_length=50,
        )
        semestre = ft.Dropdown(
            label="Semestre",
            value=str(registro["semestre"]),
            options=[
                ft.DropdownOption(key="2", text="Segundo semestre"),
                ft.DropdownOption(key="3", text="Tercer semestre"),
            ],
            expand=True,
        )
        try:
            paquetes_horario = api.paquetes_horario(registro["semestre"])
        except ApiError as ex:
            manejar_error_api(ex, expediente.navegar, "/consultas", expediente.page)
            return

        def opciones_paquete(paquetes, id_actual=None):
            disponibles = [
                item for item in paquetes
                if item["lugares"] > 0 or item["id_paquete"] == id_actual
            ]
            if id_actual is not None and not any(
                item["id_paquete"] == id_actual for item in disponibles
            ):
                disponibles.append({
                    "id_paquete": id_actual,
                    "nombre": registro["paquete"] or "Paquete actual",
                    "turno": "",
                    "lugares": 0,
                })
            return [
                ft.DropdownOption(
                    key=str(item["id_paquete"]),
                    text=(
                        f"{item['nombre']} · {item['turno']} · "
                        f"{item['lugares']} lugares"
                        if item["id_paquete"] != id_actual
                        else f"{item['nombre']} · paquete actual"
                    ),
                )
                for item in disponibles
            ]

        paquete = ft.Dropdown(
            label="Paquete asignado",
            value=str(registro["id_paquete"]) if registro.get("id_paquete") is not None else None,
            options=opciones_paquete(paquetes_horario, registro.get("id_paquete")),
            expand=True,
        )
        aviso = ft.Text("", size=13, color=ft.Colors.RED_700, visible=False)

        def cambiar_semestre(_):
            try:
                nuevos_paquetes = api.paquetes_horario(int(semestre.value))
            except ApiError as ex:
                if manejar_error_api(ex, expediente.navegar, "/consultas", expediente.page, aviso):
                    return
                paquete.options = []
                paquete.value = None
                expediente.page.update()
                return
            paquete.options = opciones_paquete(nuevos_paquetes)
            paquete.value = None
            paquete.error_text = None
            aviso.visible = False
            expediente.page.update()

        semestre.on_change = cambiar_semestre
        campos = {
            "numero_control": numero,
            "nombre": nombre,
            "apellido_paterno": apellido_paterno,
            "apellido_materno": apellido_materno,
            "semestre": semestre,
            "id_paquete": paquete,
        }

        def guardar(_):
            datos = {
                "numero_control": (numero.value or "").strip(),
                "nombre": (nombre.value or "").strip(),
                "apellido_paterno": (apellido_paterno.value or "").strip(),
                "apellido_materno": (apellido_materno.value or "").strip(),
                "semestre": int(semestre.value) if semestre.value else None,
                "id_paquete": int(paquete.value) if paquete.value else None,
            }
            errores = {}
            if not re.fullmatch(r"\d{8}", datos["numero_control"]):
                errores["numero_control"] = "Debe contener exactamente 8 dígitos"
            if error := v.validar_nombre_personal(datos["nombre"], "Nombre", maximo=50):
                errores["nombre"] = error
            if error := v.validar_nombre_personal(
                datos["apellido_paterno"], "Apellido paterno", maximo=50,
            ):
                errores["apellido_paterno"] = error
            if error := v.validar_nombre_personal(
                datos["apellido_materno"], "Apellido materno", maximo=50,
            ):
                errores["apellido_materno"] = error
            if datos["semestre"] not in (2, 3):
                errores["semestre"] = "Selecciona segundo o tercer semestre"
            elif (
                "numero_control" not in errores
                and re.fullmatch(r"\d{8}", datos["numero_control"])
            ):
                prefijo = "26" if datos["semestre"] == 2 else "25"
                if not datos["numero_control"].startswith(prefijo):
                    anio = "2026" if datos["semestre"] == 2 else "2025"
                    errores["numero_control"] = (
                        f"Para {datos['semestre']}° semestre, el número de control "
                        f"debe corresponder al año {anio}"
                    )
                elif error := v.validar_periodo_numero_control(
                    datos["numero_control"], datos["semestre"],
                ):
                    errores["numero_control"] = error
            if datos["id_paquete"] is None:
                errores["id_paquete"] = "Selecciona un paquete con lugares disponibles"
            for campo, mensaje in errores.items():
                control = campos[campo]
                if isinstance(control, ft.Dropdown):
                    control.error_text = mensaje
                else:
                    control.error = mensaje
            if errores:
                expediente.page.update()
                return

            try:
                api.modificar_reinscripcion(registro["numero_control"], datos)
                actualizada = api.reinscripcion(datos["numero_control"])
            except ApiError as ex:
                if manejar_error_api(ex, expediente.navegar, "/consultas", expediente.page, aviso):
                    return
                for campo, mensaje in ex.errores.items():
                    if campo in campos:
                        control = campos[campo]
                        if isinstance(control, ft.Dropdown):
                            control.error_text = mensaje
                        else:
                            control.error = mensaje
                expediente.page.update()
                return
            expediente.page.pop_dialog()
            expediente.reinscripcion_data = actualizada
            expediente.entrada.value = actualizada["numero_control"]
            expediente._pintar()
            expediente.page.update()
            snackbar(expediente.page, "Los datos de reinscripción se actualizaron.")

        expediente.page.show_dialog(ft.AlertDialog(
            modal=True,
            bgcolor=WHITE,
            title=ft.Text("Modificar reinscripción"),
            content=ft.Container(
                width=560,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        aviso, numero, nombre, apellido_paterno, apellido_materno,
                        semestre, paquete,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: expediente.page.pop_dialog()),
                ft.FilledButton(
                    "Actualizar reinscripción",
                    style=estilo_boton_primario(),
                    on_click=guardar,
                ),
            ],
        ))


class ReinscripcionMixin:
    def _encabezado_reinscripcion(self) -> ft.Control:
        registro = self.reinscripcion_data
        return crear_tarjeta(ft.Column(spacing=16, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                ft.Column(spacing=4, controls=[
                    ft.Text("Datos de reinscripción", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Text(registro["numero_control"], size=13, color=MUTED),
                ]),
                ft.Row(spacing=8, controls=[
                    *([
                        ft.OutlinedButton(
                            "Modificar reinscripción",
                            style=estilo_boton_secundario(),
                            on_click=self._editar_reinscripcion,
                        ),
                    ] if self.modo_modificacion and not registro.get("eliminado") else []),
                    *([
                        ft.OutlinedButton(
                            "Dar de baja",
                            style=estilo_boton_secundario(),
                            on_click=self._confirmar_baja_reinscripcion,
                        ),
                    ] if self.modo_bajas and not registro.get("eliminado") else []),
                ]),
            ]),
            ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Nombre", size=12, color=MUTED),
                    ft.Text(registro["nombre"], size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Apellido paterno", size=12, color=MUTED),
                    ft.Text(registro["apellido_paterno"], size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Apellido materno", size=12, color=MUTED),
                    ft.Text(registro["apellido_materno"], size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Semestre", size=12, color=MUTED),
                    ft.Text(ordinal_semestre(registro["semestre"]), size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Paquete asignado", size=12, color=MUTED),
                    ft.Text(registro["paquete"] or "Sin paquete", size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Estado", size=12, color=MUTED),
                    ft.Text(
                        "Dado de baja" if registro.get("eliminado") else "Activo",
                        size=14,
                        color=TEXT,
                    ),
                ])),
            ]),
        ]), padding=20)

    def _confirmar_baja_reinscripcion(self, e=None):
        registro = self.reinscripcion_data
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Dar de baja la reinscripción"),
            content=ft.Text(
                "La reinscripción dejará de aparecer en las listas activas. "
                "Se conservarán sus inscripciones y calificaciones históricas."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Confirmar baja",
                    style=estilo_boton_primario(),
                    on_click=self._dar_baja_reinscripcion,
                ),
            ],
        ))

    def _dar_baja_reinscripcion(self, e=None):
        numero_control = self.reinscripcion_data["numero_control"]
        try:
            api.eliminar_reinscripcion(numero_control)
        except ApiError as ex:
            manejar_error_api(ex, self.navegar, "/consultas", self.page)
            return

        self.page.pop_dialog()
        self.reinscripcion_data["eliminado"] = True
        self.reinscripcion_data["baja_en"] = None
        self.horario = None
        self._pintar()
        self.page.update()
        snackbar(self.page, f"Reinscripción {numero_control} dada de baja.")

    def _editar_reinscripcion(self, e=None):
        EdicionReinscripcion(self).mostrar()
