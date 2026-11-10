"""Student record lookup, editing, and lifecycle actions."""

import asyncio
import datetime
import re
from pathlib import Path

import flet as ft
from api_client import ApiError
from ambar_common import validators as v

from app_state import api
from forms.domicilio import DomicilioCampos
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
from ui.files import abrir_archivo, carpeta_pdf_temporal as _carpeta_pdf_temporal
from ui.theme import (
    BORDER,
    DOCUMENTOS_MODIFICABLES,
    MUTED,
    NAVY,
    OK_FG,
    TEXT,
    WARN_FG,
    WHITE,
)

_CAMPOS_HISTORIAL = {
    "numero_ficha": ("Identificación", "Número de ficha"),
    "nombres": ("Identificación", "Nombre(s)"),
    "apellido_paterno": ("Identificación", "Apellido paterno"),
    "apellido_materno": ("Identificación", "Apellido materno"),
    "fecha_nacimiento": ("Datos personales", "Fecha de nacimiento"),
    "genero": ("Datos personales", "Género"),
    "curp": ("Datos personales", "CURP"),
    "rfc": ("Datos personales", "RFC"),
    "ine": ("Datos personales", "IDMEX"),
    "nss": ("Datos personales", "Número de seguro social"),
    "domicilio": ("Contacto", "Domicilio"),
    "celular": ("Contacto", "Celular"),
    "celular_emergencia": ("Contacto", "Celular de emergencia"),
    "correo_personal": ("Contacto", "Correo personal"),
    "correo_emergencia": ("Contacto", "Correo de emergencia"),
    "correo_institucional": ("Contacto", "Correo institucional"),
    "tipo_sangre": ("Contacto y salud", "Tipo de sangre"),
    "alergias": ("Contacto y salud", "Alergias"),
    "preparatoria_procedencia": ("Trayectoria académica", "Preparatoria de procedencia"),
    "promedio_preparatoria": ("Trayectoria académica", "Promedio de preparatoria"),
    "turno": ("Trayectoria académica", "Turno"),
    "semestre_actual": ("Trayectoria académica", "Semestre actual"),
    "estatus": ("Trayectoria académica", "Situación escolar"),
    "motivo_baja": ("Trayectoria académica", "Motivo de baja"),
}


def ordinal_semestre(n: int) -> str:
    return f"{n}.{'er' if n in (1, 3) else 'º'} semestre"


def _valor_historial(campo: str, valor) -> str:
    if valor is None or str(valor).strip() == "":
        return "Sin dato"
    if campo == "genero":
        return v.GENEROS.get(str(valor), str(valor).capitalize())
    if campo == "promedio_preparatoria":
        try:
            return f"{float(valor):.2f}"
        except (TypeError, ValueError):
            return str(valor)
    if campo == "fecha_nacimiento":
        try:
            return datetime.date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return str(valor)
    return str(valor)


def _cambios_historial(evento: dict) -> dict[str, list[dict[str, str]]]:
    if evento.get("accion") == "BAJA":
        return {"Situación del expediente": [{
            "campo": "Estado",
            "antes": "Activo",
            "despues": "Dado de baja",
        }]}

    anterior = evento.get("datos_anteriores") or {}
    nuevo = evento.get("datos_nuevos") or {}
    secciones: dict[str, list[dict[str, str]]] = {}
    for campo, (seccion, etiqueta_campo) in _CAMPOS_HISTORIAL.items():
        antes = anterior.get(campo)
        despues = nuevo.get(campo)
        if antes == despues:
            continue
        secciones.setdefault(seccion, []).append({
            "campo": etiqueta_campo,
            "antes": _valor_historial(campo, antes),
            "despues": _valor_historial(campo, despues),
        })
    return secciones


class ConsultaExpediente:
    SECCIONES = [("personales", "Datos personales"), ("contacto", "Contacto"),
                 ("academicos", "Datos académicos"), ("documentos", "Documentos")]
    CAMPOS = {
        "personales": [
            ("nombres", "Nombre(s)"), ("apellido_paterno", "Apellido paterno"),
            ("apellido_materno", "Apellido materno"), ("fecha_nacimiento", "Fecha de nacimiento"),
            ("genero", "Género"), ("curp", "CURP"), ("rfc", "RFC"),
            ("ine", "IDMEX"), ("nss", "Número de seguro social"),
        ],
        "contacto": [
            ("domicilio", "Domicilio"), ("celular", "Celular"),
            ("correo_personal", "Correo personal"), ("correo_institucional", "Correo institucional"),
            ("celular_emergencia", "Celular de emergencia"), ("correo_emergencia", "Correo de emergencia"),
            ("tipo_sangre", "Tipo de sangre"),
            ("alergias", "Alergias"),
        ],
        "academicos": [
            ("numero_ficha", "Número de ficha"), ("preparatoria", "Preparatoria de procedencia"),
            ("promedio", "Promedio de preparatoria"), ("turno", "Turno"),
            ("semestre", "Semestre actual"), ("grupo", "Grupo"),
            ("periodo", "Periodo escolar"), ("estatus", "Estatus"),
            ("motivo_baja", "Motivo de baja"),
        ],
    }

    def __init__(
        self,
        page: ft.Page,
        picker: ft.FilePicker,
        usuario: dict,
        navegar,
        modo_modificacion: bool = False,
        modo_bajas: bool = False,
        numero_control_inicial: str | None = None,
    ):
        self.page = page
        self.picker = picker
        self.usuario = usuario
        self.es_admin = usuario["rol"] == "Administrador"
        self.modo_modificacion = modo_modificacion
        self.modo_bajas = modo_bajas
        self.navegar = navegar
        self.datos: dict | None = None
        self.reinscripcion_data: dict | None = None
        self.incluir_bajas = False
        self.historial: list[dict] = []
        self.error_historial: str | None = None
        self.horario: dict | None = None
        self.paquetes_horario: list[dict] = []
        self.error_horario: str | None = None
        self.seccion = "personales"
        self.boton_descargar = ft.OutlinedButton(
            "Descargar expediente PDF",
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            style=estilo_boton_secundario(),
            on_click=lambda e: self.page.run_task(self.descargar_pdf),
        )

        self.entrada = crear_campo_texto("Número de control o CURP", on_submit=self.buscar,
                          capitalization=ft.TextCapitalization.CHARACTERS)
        self.boton = ft.FilledButton("Buscar", style=estilo_boton_primario(), height=46, on_click=self.buscar)
        self.filtro_bajas = ft.Checkbox(
            label="Incluir alumnos dados de baja",
            value=False,
            on_change=self._cambiar_filtro_bajas,
        )
        self.aviso = ft.Text("", color=ft.Colors.RED_700, size=13, weight=ft.FontWeight.W_600, visible=False)
        self.resultado = ft.Column(spacing=20)
        self._pintar()

        buscador = crear_tarjeta(ft.Column(spacing=8, controls=[
            ft.Row(vertical_alignment=ft.CrossAxisAlignment.END, spacing=16, controls=[
                crear_campo_etiquetado("Número de control o CURP", self.entrada),
                self.boton,
            ]),
            *([self.filtro_bajas] if self.es_admin else []),
            self.aviso,
        ]), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

        if self.modo_modificacion:
            titulo = "Modificación de alumnos"
            subtitulo = "Busca un alumno para modificar sus datos y documentos."
        elif self.modo_bajas:
            titulo = "Bajas de alumnos"
            subtitulo = "Busca un alumno para dar de baja su expediente."
        elif self.es_admin:
            titulo = "Historial administrativo"
            subtitulo = "Consulta expedientes, bajas y versiones anteriores."
        else:
            titulo = "Expediente del alumno"
            subtitulo = "Consulta la información académica y los documentos del estudiante."

        self.vista = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
            titulo_pagina(titulo, subtitulo),
            buscador,
            self.resultado,
        ])
        if numero_control_inicial:
            self.entrada.value = numero_control_inicial
            self.page.run_task(self._buscar_inicial)

    async def _buscar_inicial(self):
        self.buscar()

    def buscar(self, e=None):
        q = (self.entrada.value or "").strip()
        self.entrada.error = None
        self.aviso.visible = False
        if not q:
            self.entrada.error = "Escribe un número de control o una CURP"
            self.page.update()
            return
        self.boton.disabled = True
        self.page.update()
        try:
            self.reinscripcion_data = None
            if (
                self.usuario["rol"] in {"Secretaría", "Administrador"}
                and re.fullmatch(r"\d{8}", q)
            ):
                try:
                    self.reinscripcion_data = api.reinscripcion(q)
                except ApiError as ex:
                    if ex.status != 404:
                        raise
            if self.reinscripcion_data is None:
                self.datos = api.expediente(q, self.es_admin and self.incluir_bajas)
            else:
                self.datos = None
            self.seccion = "personales"
            self.historial = []
            self.error_historial = None
            self.horario = None
            self.paquetes_horario = []
            self.error_horario = None
            if (
                self.reinscripcion_data is not None
                and not self.reinscripcion_data.get("eliminado", False)
                and not self.modo_modificacion
                and not self.modo_bajas
            ):
                try:
                    self.horario = api.estado_horario(
                        self.reinscripcion_data["numero_control"],
                    )
                except ApiError as ex:
                    if ex.status == 401:
                        self.navegar("/consultas")
                        return
                    self.error_horario = ex.mensaje
            if (
                self.datos is not None
                and
                self.usuario["rol"] == "Secretaría"
                and not self.modo_modificacion
                and not self.modo_bajas
            ):
                try:
                    self.horario = api.estado_horario(self.datos["numero_control"])
                    if not self.horario["asignado"]:
                        self.paquetes_horario = api.paquetes_horario(self.horario["semestre"])
                except ApiError as ex:
                    if ex.status == 401:
                        self.navegar("/consultas")
                        return
                    self.error_horario = ex.mensaje
            if self.es_admin and self.reinscripcion_data is None:
                try:
                    self.historial = api.historial_alumno(self.datos["numero_control"])
                except ApiError as ex:
                    if ex.status == 401:
                        self.navegar("/consultas")
                        return
                    self.error_historial = ex.mensaje
        except ApiError as ex:
            self.datos = None
            self.reinscripcion_data = None
            self.horario = None
            if ex.status == 401:            # El manejador de rutas redirige al login cuando la sesión vence.
                self.navegar("/consultas")
                return
            self.aviso.value = ex.mensaje
            self.aviso.visible = True
        finally:
            self.boton.disabled = False
        self._pintar()
        self.page.update()

    def _cambiar_filtro_bajas(self, e):
        self.incluir_bajas = bool(e.control.value)
        if (self.entrada.value or "").strip():
            self.buscar()

    def _cambiar_seccion(self, clave: str):
        self.seccion = clave
        self._pintar()
        self.page.update()

    def ver_pdf(self, doc: dict):
        snackbar(self.page, f"Abriendo «{doc['documento']}»…")
        try:
            destino = _carpeta_pdf_temporal() / f"{self.datos['numero_control']}_{doc['id_documento']}.pdf"
            api.descargar_documento(
                doc["id_documento"], destino, self.es_admin and self.incluir_bajas,
            )
            abrir_archivo(destino)
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
        except OSError as ex:
            snackbar(self.page, f"No se pudo abrir el PDF: {ex}")

    async def _elegir_documento(self, documento: str):
        try:
            seleccionados = await self.picker.pick_files(
                dialog_title=f"Selecciona: {documento}",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                allow_multiple=False,
            )
        except Exception as ex:
            snackbar(self.page, f"No se pudo abrir el selector de archivos: {ex}")
            return
        if not seleccionados:
            return

        archivo = seleccionados[0]
        error_pdf = v.validar_pdf(archivo.name or "", archivo.size, archivo.path)
        if error_pdf:
            snackbar(self.page, f"{documento}: {error_pdf}")
            return

        numero_control = self.datos["numero_control"]
        try:
            await asyncio.to_thread(
                api.actualizar_documentos,
                numero_control,
                {documento: archivo.path},
            )
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
            return

        try:
            self.datos = await asyncio.to_thread(
                api.expediente, numero_control, self.es_admin and self.incluir_bajas,
            )
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, f"El documento se guardó, pero no se pudo actualizar la vista: {ex.mensaje}")
            return

        self.seccion = "documentos"
        self._pintar()
        self.page.update()
        snackbar(self.page, f"«{documento}» se guardó correctamente.")

    async def descargar_pdf(self):
        if self.datos is None:
            return
        self.boton_descargar.disabled = True
        self.page.update()
        try:
            contenido = await asyncio.to_thread(
                api.descargar_expediente,
                self.datos["numero_control"],
                self.es_admin and self.incluir_bajas,
            )
            nombre = f"expediente_{self.datos['numero_control']}.pdf"
            carpeta_descargas = Path.home() / "Downloads"
            destino = await self.picker.save_file(
                dialog_title="Guardar expediente PDF",
                file_name=nombre,
                initial_directory=str(
                    carpeta_descargas if carpeta_descargas.is_dir() else Path.home()
                ),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                src_bytes=contenido,
            )
            if destino:
                snackbar(self.page, f"Expediente guardado en «{destino}».")
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
        except OSError as ex:
            snackbar(self.page, f"No se pudo guardar el PDF: {ex}")
        except (OSError, RuntimeError, TimeoutError, ValueError) as ex:
            snackbar(self.page, f"No se pudo guardar el expediente PDF: {ex}")
        finally:
            self.boton_descargar.disabled = False
            self.page.update()

    def _descargar_horario(self):
        if not self.horario or not self.horario.get("asignado"):
            return
        numero = self.horario["numero_control"]
        try:
            contenido = api.descargar_horario_alumno(numero)
            destino = _carpeta_pdf_temporal() / f"horario_{numero}.pdf"
            destino.write_bytes(contenido)
            abrir_archivo(destino)
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
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
            if ex.status == 401:
                self.navegar("/consultas")
                return
            self.error_horario = ex.mensaje
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

    def _pintar(self):
        if self.reinscripcion_data is not None:
            self.resultado.controls = [self._encabezado_reinscripcion()]
            if (
                not self.modo_modificacion
                and not self.modo_bajas
                and (
                    self.horario is not None
                    or self.error_horario is not None
                )
            ):
                self.resultado.controls.append(self._panel_horario())
            return
        if self.datos is None:
            self.resultado.controls = [crear_tarjeta(
                ft.Text("Busca un alumno por número de control o CURP para ver su expediente.",
                        size=14, color=MUTED))]
            return
        self.resultado.controls = [
            self._encabezado(),
            *([
                self._panel_horario()
            ] if (
                self.usuario["rol"] == "Secretaría"
                and not self.modo_modificacion
                and not self.modo_bajas
            ) else []),
            self._pestanas(),
            *([self._panel_historial()] if self.es_admin else []),
        ]

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
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
            return

        self.page.pop_dialog()
        self.reinscripcion_data["eliminado"] = True
        self.reinscripcion_data["baja_en"] = None
        self.horario = None
        self._pintar()
        self.page.update()
        snackbar(self.page, f"Reinscripción {numero_control} dada de baja.")

    def _editar_reinscripcion(self, e=None):
        registro = self.reinscripcion_data
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
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
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
                if ex.status == 401:
                    self.navegar("/consultas")
                    return
                aviso.value = ex.mensaje
                aviso.visible = True
                paquete.options = []
                paquete.value = None
                self.page.update()
                return
            paquete.options = opciones_paquete(nuevos_paquetes)
            paquete.value = None
            paquete.error_text = None
            aviso.visible = False
            self.page.update()

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
                self.page.update()
                return

            try:
                api.modificar_reinscripcion(registro["numero_control"], datos)
                actualizada = api.reinscripcion(datos["numero_control"])
            except ApiError as ex:
                if ex.status == 401:
                    self.navegar("/consultas")
                    return
                for campo, mensaje in ex.errores.items():
                    if campo in campos:
                        control = campos[campo]
                        if isinstance(control, ft.Dropdown):
                            control.error_text = mensaje
                        else:
                            control.error = mensaje
                aviso.value = ex.mensaje
                aviso.visible = True
                self.page.update()
                return
            self.page.pop_dialog()
            self.reinscripcion_data = actualizada
            self.entrada.value = actualizada["numero_control"]
            self._pintar()
            self.page.update()
            snackbar(self.page, "Los datos de reinscripción se actualizaron.")

        self.page.show_dialog(ft.AlertDialog(
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
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Actualizar reinscripción",
                    style=estilo_boton_primario(),
                    on_click=guardar,
                ),
            ],
        ))

    def _encabezado(self) -> ft.Control:
        d = self.datos
        p = d["personales"]
        iniciales = (p["nombres"][:1] + p["apellido_paterno"][:1]).upper()
        activo = d["estatus"] == "Activo"
        return crear_tarjeta(ft.Row(spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
            ft.Container(width=62, height=62, border_radius=31, bgcolor="#D6E3F7",
                         alignment=ft.Alignment.CENTER,
                         content=ft.Text(iniciales, size=20, weight=ft.FontWeight.BOLD, color=NAVY)),
            ft.Column(expand=True, spacing=6, controls=[
                ft.Text(d["nombre_completo"], size=22, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(f"{d['numero_control']} • Turno {d['academicos']['turno']}", size=14, color=MUTED),
            ]),
            ft.Column(horizontal_alignment=ft.CrossAxisAlignment.END, spacing=10, controls=[
                ft.Row(spacing=12, controls=[
                    chip(ordinal_semestre(d["semestre_actual"]), True),
                    chip("Inscripción activa" if activo else "Inscripción inactiva", activo),
                    *([chip("Dado de baja", False)] if d["eliminado"] else []),
                ]),
                self.boton_descargar,
                *([] if d["eliminado"] or not (self.modo_modificacion or self.modo_bajas) else [
                    ft.Row(spacing=8, controls=[
                        *([
                            ft.OutlinedButton(
                                "Modificar datos", style=estilo_boton_secundario(),
                                on_click=self._editar_alumno,
                            ),
                        ] if self.modo_modificacion else []),
                        *([
                            ft.OutlinedButton(
                                "Dar de baja", style=estilo_boton_secundario(),
                                on_click=self._confirmar_baja,
                            ),
                        ] if self.modo_bajas else []),
                    ]),
                ]),
            ]),
        ]), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

    def _editar_alumno(self, e=None):
        d = self.datos
        p, c, a = d["personales"], d["contacto"], d["academicos"]
        genero = next((key for key, valor in v.GENEROS.items() if valor == p["genero"]), None)
        campos = {
            "ficha": crear_campo_texto(value=a["numero_ficha"], label="Número de ficha"),
            "nombre": crear_campo_texto(value=p["nombres"], label="Nombre(s)", max_length=50),
            "ap_paterno": crear_campo_texto(
                value=p["apellido_paterno"], label="Apellido paterno", max_length=50,
            ),
            "ap_materno": crear_campo_texto(
                value=p["apellido_materno"], label="Apellido materno", max_length=50,
            ),
            "fecha_nacimiento": crear_campo_texto(
                value=datetime.datetime.strptime(p["fecha_nacimiento"], "%d/%m/%Y").date().isoformat(),
                label="Fecha de nacimiento (AAAA-MM-DD)",
            ),
            "curp": crear_campo_texto(value=p["curp"], label="CURP"),
            "rfc": crear_campo_texto(value="" if p["rfc"] == "—" else p["rfc"], label="RFC (opcional)"),
            "nss": crear_campo_texto(value=p["nss"], label="Número de seguro social"),
            "ine": crear_campo_texto(
                value="" if p["ine"] == "—" else p["ine"],
                label="IDMEX (OCR, 13 dígitos)",
                keyboard_type=ft.KeyboardType.NUMBER,
                input_filter=ft.NumbersOnlyInputFilter(),
                max_length=13,
            ),
            "genero": ft.Dropdown(
                label="Género",
                value=genero,
                options=[ft.DropdownOption(key=k, text=nombre) for k, nombre in v.GENEROS.items()],
            ),
            "celular": crear_campo_texto(value=c["celular"], label="Celular"),
            "correo": crear_campo_texto(value=c["correo_personal"], label="Correo personal"),
            "preparatoria": crear_campo_texto(value=a["preparatoria"], label="Preparatoria"),
            "promedio": crear_campo_texto(value=a["promedio"], label="Promedio"),
            "celular_emergencia": crear_campo_texto(value=c["celular_emergencia"], label="Celular de emergencia"),
            "correo_emergencia": crear_campo_texto(value=c["correo_emergencia"], label="Correo de emergencia"),
            "tipo_sangre": ft.Dropdown(
                label="Tipo de sangre",
                value=None if c["tipo_sangre"] == "—" else c["tipo_sangre"],
                options=[ft.DropdownOption(key=tipo, text=tipo) for tipo in v.TIPOS_SANGRE],
            ),
            "alergias": crear_campo_texto(value=c["alergias"], label="Alergias"),
        }
        domicilio = DomicilioCampos(self.page, c, permitir_cp_sin_catalogo=True)
        contenido = ft.ResponsiveRow(
            spacing=12,
            run_spacing=8,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=campo)
                for campo in campos.values()
            ] + [
                ft.Container(col={"xs": 12, "md": 12}, content=control)
                for control in domicilio.controles
            ],
        )
        aviso = ft.Text(
            "",
            size=13,
            color=ft.Colors.RED_700,
            weight=ft.FontWeight.W_600,
            visible=False,
        )
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            bgcolor=WHITE,
            title=ft.Text("Modificar datos del alumno"),
            content=ft.Container(
                width=680,
                height=640,
                content=ft.Column(spacing=8, controls=[
                    aviso,
                    ft.Container(
                        expand=True,
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO,
                            controls=[contenido],
                        ),
                    ),
                ]),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Guardar cambios", style=estilo_boton_primario(),
                    on_click=lambda _: self._guardar_edicion(campos, domicilio, aviso),
                ),
            ],
        ))

    def _guardar_edicion(self, campos: dict, domicilio: DomicilioCampos, aviso: ft.Text):
        datos = {clave: (campo.value or "").strip() for clave, campo in campos.items()}
        if not domicilio.validar():
            aviso.value = "Completa los campos del domicilio."
            aviso.visible = True
            self.page.update()
            return
        datos.update(domicilio.datos())
        datos["ine"] = v.normalizar_ine(datos["ine"])
        try:
            fecha_nacimiento = datetime.date.fromisoformat(datos["fecha_nacimiento"])
            datos["fecha_nacimiento"] = fecha_nacimiento.isoformat()
            datos["promedio"] = float(datos["promedio"].replace(",", "."))
        except ValueError:
            aviso.value = "Revisa la fecha (AAAA-MM-DD) y el promedio."
            aviso.visible = True
            self.page.update()
            return
        datos["rfc"] = datos["rfc"] or None

        campos["curp"].error = v.validar_curp(
            datos["curp"],
            fecha_nacimiento,
            datos["ap_paterno"],
            datos["ap_materno"],
            datos["genero"],
        )
        campos["rfc"].error = v.validar_rfc(
            datos["rfc"],
            fecha_nacimiento,
        )
        if campos["curp"].error or campos["rfc"].error:
            aviso.value = "Revisa la CURP y el RFC antes de guardar."
            aviso.visible = True
            self.page.update()
            return

        try:
            api.actualizar_alumno(self.datos["numero_control"], datos)
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            for campo, mensaje in ex.errores.items():
                if campo in campos:
                    campos[campo].error = mensaje
            domicilio.marcar_errores(ex.errores)
            detalles = "; ".join(f"{campo}: {mensaje}" for campo, mensaje in ex.errores.items())
            aviso.value = f"{ex.mensaje}{': ' + detalles if detalles else ''}"
            aviso.visible = True
            self.page.update()
            return

        numero_control = self.datos["numero_control"]
        self.page.pop_dialog()
        self.entrada.value = numero_control
        self.buscar()
        snackbar(self.page, "Los datos del alumno se actualizaron.")

    def _confirmar_baja(self, e=None):
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Dar de baja el expediente"),
            content=ft.Text(
                "El expediente dejará de aparecer para Secretaría. "
                "El registro, sus documentos y sus versiones anteriores se conservarán "
                "y solo Administración podrá consultarlos."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Confirmar baja", style=estilo_boton_primario(),
                    on_click=self._dar_baja,
                ),
            ],
        ))

    def _dar_baja(self, e=None):
        try:
            api.eliminar_alumno(self.datos["numero_control"])
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            snackbar(self.page, ex.mensaje)
            return

        numero_control = self.datos["numero_control"]
        self.page.pop_dialog()
        self.datos = None
        self.historial = []
        self._pintar()
        self.page.update()
        snackbar(self.page, f"Expediente {numero_control} dado de baja; el historial se conservó.")

    def _panel_historial(self) -> ft.Control:
        if self.error_historial:
            return crear_tarjeta(ft.Text(
                f"No se pudo cargar el historial: {self.error_historial}",
                color=ft.Colors.RED_700,
            ))
        if not self.historial:
            cuerpo = ft.Text("Este expediente no tiene modificaciones ni bajas registradas.", color=MUTED)
        else:
            cuerpo = ft.Column(spacing=8, controls=[
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.Row(controls=[
                        ft.Text(f"{evento['accion']} · {evento['fecha']}", expand=True,
                                size=14, weight=ft.FontWeight.BOLD, color=NAVY),
                        ft.Text(f"Usuario: {evento['usuario']}", size=12, color=MUTED),
                        ft.TextButton(
                            "Ver cambios",
                            on_click=lambda e, item=evento: self._ver_detalle_historial(item),
                        ),
                    ]),
                )
                for evento in self.historial
            ])
        return crear_tarjeta(ft.Column(spacing=12, controls=[
            ft.Text("Historial de cambios", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            cuerpo,
        ]), padding=20)

    def _ver_detalle_historial(self, evento: dict):
        cambios = _cambios_historial(evento)
        secciones = []
        for titulo, campos in cambios.items():
            filas = []
            for cambio in campos:
                filas.append(ft.Container(
                    padding=ft.Padding.symmetric(vertical=9),
                    border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.Column(spacing=8, controls=[
                        ft.Text(cambio["campo"], size=13, weight=ft.FontWeight.BOLD, color=TEXT),
                        ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                                ft.Text("ANTES", size=10, weight=ft.FontWeight.BOLD, color=MUTED),
                                ft.Text(cambio["antes"], size=13, color=TEXT, selectable=True),
                            ])),
                            ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                                ft.Text("AHORA", size=10, weight=ft.FontWeight.BOLD, color=OK_FG),
                                ft.Text(cambio["despues"], size=13, color=TEXT, selectable=True),
                            ])),
                        ]),
                    ]),
                ))
            secciones.append(ft.Column(spacing=2, controls=[
                ft.Text(titulo, size=15, weight=ft.FontWeight.BOLD, color=NAVY),
                *filas,
            ]))

        if not secciones:
            secciones = [ft.Text("No se detectaron diferencias en los datos guardados.", color=MUTED)]
        accion = "Baja de expediente" if evento["accion"] == "BAJA" else "Cambios en el expediente"
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            bgcolor=WHITE,
            title=ft.Text(accion),
            content=ft.Container(
                width=760,
                height=560,
                content=ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, controls=[
                    ft.Container(
                        padding=ft.Padding.only(bottom=10),
                        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                        content=ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                                ft.Text("FECHA Y HORA", size=10, weight=ft.FontWeight.BOLD, color=MUTED),
                                ft.Text(evento["fecha"], size=13, color=TEXT),
                            ])),
                            ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=3, controls=[
                                ft.Text("REALIZADO POR", size=10, weight=ft.FontWeight.BOLD, color=MUTED),
                                ft.Text(evento["usuario"], size=13, color=TEXT),
                            ])),
                        ]),
                    ),
                    *secciones,
                ]),
            ),
            actions=[ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())],
        ))

    def _pestanas(self) -> ft.Control:
        def pestana(clave, texto):
            activa = clave == self.seccion
            return ft.Container(
                ink=True, on_click=lambda e, c=clave: self._cambiar_seccion(c),
                padding=ft.Padding.symmetric(horizontal=22, vertical=14),
                border=ft.Border.only(bottom=ft.BorderSide(3, NAVY if activa else ft.Colors.TRANSPARENT)),
                content=ft.Text(texto, size=14, color=NAVY if activa else MUTED,
                                weight=ft.FontWeight.BOLD if activa else ft.FontWeight.NORMAL),
            )

        barra = ft.Container(
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
            content=ft.Row(spacing=0, scroll=ft.ScrollMode.AUTO,
                           controls=[pestana(c, t) for c, t in self.SECCIONES]),
        )
        cuerpo = self._documentos() if self.seccion == "documentos" else self._campos(self.seccion)
        return ft.Container(
            bgcolor=WHITE, border=ft.Border.all(1, BORDER), border_radius=10,
            content=ft.Column(spacing=0, controls=[
                barra,
                ft.Container(padding=ft.Padding.all(20), content=cuerpo),
            ]),
        )

    def _campos(self, seccion: str) -> ft.Control:
        valores = self.datos[seccion]
        titulo = dict(self.SECCIONES)[seccion]
        celdas = [
            ft.Container(col={"xs": 12, "md": 6}, content=ft.Column(spacing=2, controls=[
                ft.Text(etiqueta_campo, size=12, color=MUTED),
                ft.Text(str(valores[clave]), size=15, weight=ft.FontWeight.W_600, color=TEXT, selectable=True),
            ]))
            for clave, etiqueta_campo in self.CAMPOS[seccion] if clave in valores
        ]
        return ft.Column(spacing=16, controls=[
            ft.Text(titulo, size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.ResponsiveRow(spacing=20, run_spacing=16, controls=celdas),
        ])

    def _documentos(self) -> ft.Control:
        def celda(contenido, expand):
            if isinstance(contenido, str):
                contenido = ft.Text(contenido, size=14, color=TEXT)
            return ft.Container(expand=expand, content=contenido)

        def encabezado(texto):
            return ft.Text(texto, size=13, weight=ft.FontWeight.BOLD, color=TEXT)

        filas = [ft.Container(
            bgcolor="#EEF2F8", border_radius=6,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            content=ft.Row(controls=[celda(encabezado("Documento"), 5), celda(encabezado("Estado"), 3),
                                     celda(encabezado("Acciones"), 3)]),
        )]
        for doc in self.datos["documentos"]:
            recibido = doc["estado"] == "Recibido"
            acciones = []
            if recibido:
                acciones.append(ft.TextButton(
                    "Ver PDF", style=ft.ButtonStyle(color=NAVY),
                    on_click=lambda e, d=doc: self.ver_pdf(d),
                ))
            if (
                self.modo_modificacion
                and not self.datos["eliminado"]
                and doc["documento"] in DOCUMENTOS_MODIFICABLES
            ):
                acciones.append(ft.TextButton(
                    "Cambiar PDF" if recibido else "Agregar PDF",
                    style=ft.ButtonStyle(color=NAVY),
                    on_click=lambda e, d=doc: self.page.run_task(
                        self._elegir_documento, d["documento"],
                    ),
                ))
            accion = ft.Row(spacing=0, controls=acciones) if acciones else ft.Text(
                "—", size=16, weight=ft.FontWeight.BOLD, color=TEXT,
            )
            filas.append(ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                    celda(doc["documento"], 5),
                    celda(ft.Row([chip(doc["estado"], recibido)]), 3),
                    celda(accion, 3),
                ]),
            ))
        return ft.Column(spacing=14, controls=[
            ft.Text("Documentos del expediente", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Column(spacing=0, controls=filas),
        ])


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
