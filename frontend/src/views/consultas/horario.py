"""Panel del horario y asignación del paquete del expediente."""

import flet as ft
from api_client import ApiError

from app_state import api
from ui.components import crear_tarjeta, estilo_boton_primario, estilo_boton_secundario, snackbar
from ui.errors import manejar_error_api
from ui.files import descargar_pdf_y_abrir
from ui.theme import BORDER, MUTED, NAVY, TEXT, WARN_FG
from .historial import ordinal_semestre


class HorarioMixin:
    def _descargar_horario(self):
        if not self.horario or not self.horario.get("asignado"):
            return
        numero = self.horario["numero_control"]
        try:
            descargar_pdf_y_abrir(
                f"horario_{numero}.pdf", lambda _: api.descargar_horario_alumno(numero),
            )
        except ApiError as ex:
            manejar_error_api(ex, self.navegar, "/consultas", self.page)
        except OSError as ex:
            snackbar(self.page, f"No se pudo guardar el horario PDF: {ex}")

    def _confirmar_asignacion_paquete(self, selector: ft.Dropdown):
        try:
            id_paquete = int(selector.value)
        except (TypeError, ValueError):
            snackbar(self.page, "Selecciona un paquete de horario.")
            return
        paquete = next(
            (item for item in self.paquetes_horario if item["id_paquete"] == id_paquete),
            None,
        )
        if paquete is None:
            snackbar(self.page, "El paquete seleccionado ya no está disponible.")
            return
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Asignar paquete de horario"),
            content=ft.Text(
                f"Se inscribirá al alumno en todas las materias de {paquete['nombre']}. "
                "Al confirmar, el alumno quedará en un solo paquete para "
                f"{paquete['periodo']}."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Confirmar asignación",
                    style=estilo_boton_primario(),
                    on_click=lambda _: self._asignar_paquete(id_paquete),
                ),
            ],
        ))

    def _asignar_paquete(self, id_paquete: int):
        self.page.pop_dialog()
        try:
            self.horario = api.asignar_paquete(self.datos["numero_control"], id_paquete)
            self.datos = api.expediente(self.datos["numero_control"])
            self.error_horario = None
            self._pintar()
            self.page.update()
            snackbar(self.page, f"Horario {self.horario['paquete']['nombre']} asignado.")
        except ApiError as ex:
            if manejar_error_api(
                ex, self.navegar, "/consultas", self.page,
                mostrar=lambda mensaje: setattr(self, "error_horario", mensaje),
            ):
                return
            self._pintar()
            self.page.update()

    def _panel_horario(self) -> ft.Control:
        if self.error_horario:
            return crear_tarjeta(ft.Column(spacing=8, controls=[
                ft.Text("Horario y grupo", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(self.error_horario, color=ft.Colors.RED_700),
            ]), padding=20)
        if self.horario is None:
            return crear_tarjeta(ft.Text(
                "No se pudo cargar el estado del horario.",
                color=ft.Colors.RED_700,
            ), padding=20)

        if not self.horario["asignado"]:
            if self.usuario["rol"] != "Secretaría":
                return crear_tarjeta(ft.Column(spacing=8, controls=[
                    ft.Text(
                        f"Horario y grupo · {ordinal_semestre(self.horario['semestre'])}",
                        size=19,
                        weight=ft.FontWeight.BOLD,
                        color=NAVY,
                    ),
                    ft.Text(
                        "El alumno no tiene un paquete asignado en este periodo.",
                        size=14,
                        color=TEXT,
                    ),
                ]), padding=20)
            selector = ft.Dropdown(
                label=f"Grupo destino para semestre {self.horario['semestre']}",
                options=[
                    ft.DropdownOption(
                        key=str(paquete["id_paquete"]),
                        text=(
                            f"{paquete['nombre']} · {paquete['turno']} · "
                            f"{paquete['lugares']} lugares disponibles"
                        ),
                    )
                    for paquete in self.paquetes_horario
                ],
                width=380,
                disabled=not self.paquetes_horario,
            )
            if self.paquetes_horario:
                mensaje = f"El alumno aún no tiene paquete para {self.horario['periodo']}."
            else:
                mensaje = (
                    f"No hay paquetes disponibles para el semestre "
                    f"{self.horario['semestre']} en {self.horario['periodo']}."
                )
            return crear_tarjeta(ft.Column(spacing=12, controls=[
                ft.Text("Horario y grupo", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(mensaje, size=14, color=TEXT),
                ft.Row(spacing=12, controls=[
                    selector,
                    ft.FilledButton(
                        "Asignar paquete",
                        style=estilo_boton_primario(),
                        disabled=not self.paquetes_horario,
                        on_click=lambda _: self._confirmar_asignacion_paquete(selector),
                    ),
                ]),
                ft.Text(
                    "La asignación inscribe al alumno en todas las materias del paquete "
                    "y respeta el cupo de cada grupo.",
                    size=12,
                    color=MUTED,
                ),
            ]), padding=20)

        paquete = self.horario["paquete"]
        materias = self.horario["materias"]
        if not any(materia["horarios"] for materia in materias):
            horario_tabla: list[ft.Control] = [ft.Text(
                "El grupo existe, pero no tiene un horario cargado en el sistema.",
                size=13,
                color=WARN_FG,
            )]
        else:
            horario_tabla = [
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=8),
                    border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.ResponsiveRow(spacing=10, run_spacing=5, controls=[
                        ft.Container(col={"xs": 12, "md": 3}, content=ft.Text(
                            materia["nombre_materia"], size=13,
                            weight=ft.FontWeight.BOLD, color=TEXT,
                        )),
                        ft.Container(col={"xs": 12, "md": 6}, content=ft.Text(
                            ", ".join(
                                f"{fila['dia'][:3]} {fila['inicio']}-{fila['fin']}"
                                for fila in materia["horarios"]
                            ) or "Sin horario",
                            size=12,
                            color=MUTED,
                        )),
                        ft.Container(col={"xs": 6, "md": 1}, content=ft.Text(
                            materia["aula"], size=12, color=TEXT,
                        )),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Text(
                            materia["docente"], size=12, color=TEXT,
                        )),
                    ]),
                )
                for materia in materias
            ]
        return crear_tarjeta(ft.Column(spacing=12, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                ft.Column(spacing=4, controls=[
                    ft.Text(
                        f"Horario y grupo · {ordinal_semestre(self.horario['semestre'])}",
                        size=19,
                        weight=ft.FontWeight.BOLD,
                        color=NAVY,
                    ),
                    ft.Text(
                        f"{paquete['nombre']} · {paquete['periodo']} · "
                        f"{len(materias)} materias",
                        size=13,
                        color=MUTED,
                    ),
                ]),
                ft.OutlinedButton(
                    "Descargar horario PDF",
                    icon=ft.Icons.DOWNLOAD_OUTLINED,
                    style=estilo_boton_secundario(),
                    disabled=not any(materia["horarios"] for materia in materias),
                    on_click=lambda _: self._descargar_horario(),
                ),
            ]),
            ft.Column(spacing=0, controls=horario_tabla),
        ]), padding=20)
