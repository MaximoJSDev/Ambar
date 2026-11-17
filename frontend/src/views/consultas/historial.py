"""Presentación y formato del historial del expediente."""

import datetime

import flet as ft
from ambar_common import validators as v

from ui.components import crear_tarjeta
from ui.theme import BORDER, MUTED, NAVY, OK_FG, TEXT, WHITE

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


class HistorialMixin:
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
