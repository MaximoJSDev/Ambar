"""Postal-address controls backed by the local postal-code catalog."""

import re

import flet as ft
from api_client import ApiError
from ambar_common import validators as v

from app_state import api
from ui.components import crear_campo_etiquetado, crear_campo_texto
from ui.theme import BORDER, WARN_FG


def formatear_ficha(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor)[:10]
    return f"{digitos[:4]}-{digitos[4:]}" if len(digitos) > 4 else digitos


class DomicilioCampos:
    """Campos dependientes de un catálogo postal local."""

    def __init__(
        self,
        page: ft.Page,
        valores: dict | None = None,
        permitir_cp_sin_catalogo: bool = False,
    ):
        valores = valores or {}
        self.page = page
        self.permitir_cp_sin_catalogo = permitir_cp_sin_catalogo
        self.campos_ubicacion_manuales = False
        self.catalogo: dict[str, dict[str, list[str]]] = {}
        self.aviso = ft.Text("", size=12, color=WARN_FG, visible=False)
        self.codigo_postal = crear_campo_texto(
            "5 dígitos",
            value=valores.get("codigo_postal") or "",
            max_length=5,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.codigo_postal.on_change = self._codigo_postal_cambiado
        self.estado = self._crear_dropdown("Estado", self._estado_cambiado)
        self.municipio = self._crear_dropdown("Municipio", self._municipio_cambiado)
        self.colonia = self._crear_dropdown("Colonia")
        self.calle = crear_campo_texto(
            "Calle y/o avenida",
            value=valores.get("calle") or "",
            max_length=150,
        )
        self.numero_exterior = crear_campo_texto(
            "Número exterior",
            value=valores.get("numero_exterior") or "",
            max_length=20,
        )
        self.fila_codigo_estado = ft.Row(spacing=16, controls=[
            crear_campo_etiquetado("Código postal", self.codigo_postal),
            crear_campo_etiquetado("Estado", self.estado),
        ])
        self.fila_municipio_colonia = ft.Row(spacing=16, controls=[
            crear_campo_etiquetado("Municipio", self.municipio),
            crear_campo_etiquetado("Colonia", self.colonia),
        ])
        self.controles = [
            self.fila_codigo_estado,
            self.fila_municipio_colonia,
            ft.Row(spacing=16, controls=[
                crear_campo_etiquetado("Calle", self.calle),
                crear_campo_etiquetado("Número exterior", self.numero_exterior),
            ]),
            self.aviso,
        ]
        codigo_postal = self.codigo_postal.value or ""
        if len(codigo_postal) == 5:
            self._cargar_catalogo(valores)

    @staticmethod
    def _crear_dropdown(etiqueta: str, on_select=None) -> ft.Dropdown:
        return ft.Dropdown(
            label=etiqueta,
            hint_text="Selecciona",
            text_size=13,
            border_radius=6,
            border_color=BORDER,
            expand=True,
            disabled=True,
            options=[],
            on_select=on_select,
        )

    @staticmethod
    def _opciones(valores: list[str]) -> list[ft.DropdownOption]:
        return [ft.DropdownOption(key=valor, text=valor) for valor in valores]

    def _limpiar_selecciones(self):
        self.catalogo = {}
        if self.campos_ubicacion_manuales:
            self._restaurar_selectores()
        for control in (self.estado, self.municipio, self.colonia):
            control.value = None
            control.options = []
            control.disabled = True
            control.error_text = None

    def _codigo_postal_cambiado(self, e):
        self.codigo_postal.error = None
        codigo_postal = (self.codigo_postal.value or "").strip()
        if len(codigo_postal) == 5:
            self._cargar_catalogo()
        else:
            self._limpiar_selecciones()
            self.aviso.value = ""
            self.aviso.visible = False
        self.page.update()

    def _cargar_catalogo(self, valores: dict | None = None):
        codigo_postal = (self.codigo_postal.value or "").strip()
        try:
            resultado = api.opciones_domicilio(codigo_postal)
        except ApiError as ex:
            self._limpiar_selecciones()
            self.aviso.value = ex.mensaje
            self.aviso.visible = True
            return

        self.catalogo = {
            item["estado"]: {
                municipio["municipio"]: municipio["colonias"]
                for municipio in item["municipios"]
            }
            for item in resultado["estados"]
        }
        if not self.catalogo and self.permitir_cp_sin_catalogo:
            self._usar_campos_manuales(valores or {})
            self.aviso.value = (
                "Este código postal no está en el catálogo local. "
                "Puedes capturar Estado, Municipio y Colonia manualmente."
            )
            self.aviso.visible = True
            return
        if self.campos_ubicacion_manuales:
            self._restaurar_selectores()
        self.aviso.value = (
            "" if self.catalogo else "Código postal no encontrado en el catálogo local."
        )
        self.aviso.visible = not bool(self.catalogo)
        estados = list(self.catalogo)
        self.estado.options = self._opciones(estados)
        self.estado.disabled = not estados
        preferido = (valores or {}).get("estado")
        self.estado.value = preferido if preferido in self.catalogo else (
            estados[0] if len(estados) == 1 else None
        )
        self._actualizar_municipios(
            (valores or {}).get("municipio"),
            (valores or {}).get("colonia"),
        )

    def _usar_campos_manuales(self, valores: dict):
        self.campos_ubicacion_manuales = True
        self.estado = crear_campo_texto(
            value=valores.get("estado") or "",
            label="Estado",
            max_length=100,
        )
        self.municipio = crear_campo_texto(
            value=valores.get("municipio") or "",
            label="Municipio",
            max_length=100,
        )
        self.colonia = crear_campo_texto(
            value=valores.get("colonia") or "",
            label="Colonia",
            max_length=150,
        )
        self.fila_codigo_estado.controls[1] = crear_campo_etiquetado("Estado", self.estado)
        self.fila_municipio_colonia.controls = [
            crear_campo_etiquetado("Municipio", self.municipio),
            crear_campo_etiquetado("Colonia", self.colonia),
        ]

    def _restaurar_selectores(self):
        self.campos_ubicacion_manuales = False
        self.estado = self._crear_dropdown("Estado", self._estado_cambiado)
        self.municipio = self._crear_dropdown("Municipio", self._municipio_cambiado)
        self.colonia = self._crear_dropdown("Colonia")
        self.fila_codigo_estado.controls[1] = crear_campo_etiquetado("Estado", self.estado)
        self.fila_municipio_colonia.controls = [
            crear_campo_etiquetado("Municipio", self.municipio),
            crear_campo_etiquetado("Colonia", self.colonia),
        ]

    def _actualizar_municipios(self, preferido: str | None = None, colonia: str | None = None):
        municipios = self.catalogo.get(self.estado.value, {})
        opciones = list(municipios)
        self.municipio.options = self._opciones(opciones)
        self.municipio.disabled = not opciones
        self.municipio.value = preferido if preferido in municipios else (
            opciones[0] if len(opciones) == 1 else None
        )
        self._actualizar_colonias(colonia)

    def _actualizar_colonias(self, preferida: str | None = None):
        colonias = self.catalogo.get(self.estado.value, {}).get(self.municipio.value, [])
        self.colonia.options = self._opciones(colonias)
        self.colonia.disabled = not colonias
        self.colonia.value = preferida if preferida in colonias else (
            colonias[0] if len(colonias) == 1 else None
        )

    def _estado_cambiado(self, e):
        self.estado.error_text = None
        self._actualizar_municipios()
        self.page.update()

    def _municipio_cambiado(self, e):
        self.municipio.error_text = None
        self._actualizar_colonias()
        self.page.update()

    def validar(self) -> bool:
        self.codigo_postal.error = (
            None if re.fullmatch(r"\d{5}", self.codigo_postal.value or "")
            else "El código postal debe contener 5 dígitos"
        )
        valido = self.codigo_postal.error is None
        if self.campos_ubicacion_manuales:
            for control in (self.estado, self.municipio, self.colonia):
                control.error = None if (control.value or "").strip() else "Campo obligatorio"
                valido &= control.error is None
        else:
            for control in (self.estado, self.municipio, self.colonia):
                control.error_text = None if control.value else "Selecciona una opción"
                valido &= control.error_text is None
        self.calle.error = v.validar_calle(self.calle.value or "")
        self.numero_exterior.error = v.validar_numero_exterior(
            self.numero_exterior.value or "",
        )
        return bool(valido and not self.calle.error and not self.numero_exterior.error)

    def datos(self) -> dict[str, str]:
        return {
            "codigo_postal": (self.codigo_postal.value or "").strip(),
            "estado": self.estado.value or "",
            "municipio": self.municipio.value or "",
            "colonia": self.colonia.value or "",
            "calle": (self.calle.value or "").strip(),
            "numero_exterior": (self.numero_exterior.value or "").strip(),
        }

    def texto(self) -> str:
        datos = self.datos()
        if not any(datos.values()):
            return ""
        return (
            f"{datos['calle']} {datos['numero_exterior']}, {datos['colonia']}, "
            f"{datos['municipio']}, {datos['estado']}, C.P. {datos['codigo_postal']}"
        )

    def marcar_errores(self, errores: dict[str, str]):
        controles = {
            "codigo_postal": self.codigo_postal,
            "estado": self.estado,
            "municipio": self.municipio,
            "colonia": self.colonia,
            "calle": self.calle,
            "numero_exterior": self.numero_exterior,
        }
        for campo, control in controles.items():
            if campo not in errores:
                continue
            if isinstance(control, ft.Dropdown):
                control.error_text = errores[campo]
            else:
                control.error = errores[campo]
