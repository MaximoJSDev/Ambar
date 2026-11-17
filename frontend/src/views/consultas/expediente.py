"""Vista principal de consulta y mantenimiento del expediente."""

import datetime
import re

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
from ui.errors import manejar_error_api
from ui.theme import BORDER, MUTED, NAVY, TEXT, WHITE
from .documentos import DocumentosMixin
from .historial import HistorialMixin, ordinal_semestre
from .horario import HorarioMixin
from .reinscripcion import ReinscripcionMixin


class ConsultaExpediente(HorarioMixin, HistorialMixin, DocumentosMixin, ReinscripcionMixin):
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
                    if manejar_error_api(
                        ex, self.navegar, "/consultas", self.page,
                        mostrar=lambda mensaje: setattr(self, "error_horario", mensaje),
                    ):
                        return
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
                    if manejar_error_api(
                        ex, self.navegar, "/consultas", self.page,
                        mostrar=lambda mensaje: setattr(self, "error_horario", mensaje),
                    ):
                        return
            if self.es_admin and self.reinscripcion_data is None:
                try:
                    self.historial = api.historial_alumno(self.datos["numero_control"])
                except ApiError as ex:
                    if manejar_error_api(
                        ex, self.navegar, "/consultas", self.page,
                        mostrar=lambda mensaje: setattr(self, "error_historial", mensaje),
                    ):
                        return
        except ApiError as ex:
            self.datos = None
            self.reinscripcion_data = None
            self.horario = None
            if manejar_error_api(ex, self.navegar, "/consultas", self.page, self.aviso):
                return
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
            if manejar_error_api(ex, self.navegar, "/consultas", self.page, self.aviso):
                return
            for campo, mensaje in ex.errores.items():
                if campo in campos:
                    campos[campo].error = mensaje
            domicilio.marcar_errores(ex.errores)
            detalles = "; ".join(f"{campo}: {mensaje}" for campo, mensaje in ex.errores.items())
            self.aviso.value = f"{ex.mensaje}{': ' + detalles if detalles else ''}"
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
            manejar_error_api(ex, self.navegar, "/consultas", self.page)
            return

        numero_control = self.datos["numero_control"]
        self.page.pop_dialog()
        self.datos = None
        self.historial = []
        self._pintar()
        self.page.update()
        snackbar(self.page, f"Expediente {numero_control} dado de baja; el historial se conservó.")

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
