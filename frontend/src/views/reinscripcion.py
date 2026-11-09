"""Registration and maintenance flow for reinscribed students."""

import re

import flet as ft
from ambar_common import validators as v
from api_client import ApiClient, ApiError

from ui.components import (
    crear_campo_etiquetado,
    crear_campo_texto,
    crear_tarjeta,
    estilo_boton_primario,
    snackbar,
    titulo_pagina,
)
from ui.theme import WARN_FG

def build_reinscripcion(page: ft.Page, navegar, api_client: ApiClient) -> ft.Control:
    numero = crear_campo_texto(
        "8 dígitos",
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.NumbersOnlyInputFilter(),
        max_length=8,
    )
    nombre = crear_campo_texto("Nombre(s)", max_length=50)
    apellido_paterno = crear_campo_texto("Apellido paterno", max_length=50)
    apellido_materno = crear_campo_texto("Apellido materno", max_length=50)
    semestre = ft.Dropdown(
        label="Semestre",
        options=[
            ft.DropdownOption(key="2", text="Segundo semestre"),
            ft.DropdownOption(key="3", text="Tercer semestre"),
        ],
        expand=True,
    )
    paquete = ft.Dropdown(
        label="Paquete asignado",
        options=[],
        expand=True,
        visible=False,
    )
    aviso_paquete = ft.Text(
        "No hay paquetes con lugares disponibles para este semestre.",
        size=12,
        color=WARN_FG,
        visible=False,
    )
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    boton_registrar = ft.FilledButton(
        "Registrar reinscripción",
        icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
        style=estilo_boton_primario(),
    )
    boton_buscar = ft.OutlinedButton(
        "Buscar para modificar",
        icon=ft.Icons.SEARCH,
    )
    boton_cancelar = ft.TextButton("Cancelar modificación", visible=False)
    numero_original: str | None = None

    def limpiar_errores():
        for campo in (numero, nombre, apellido_paterno, apellido_materno):
            campo.error = None
        semestre.error_text = None
        paquete.error_text = None
        aviso.visible = False

    def actualizar_paquetes(valor_semestre, id_actual=None):
        if not valor_semestre:
            paquete.options = []
            paquete.value = None
            paquete.visible = False
            aviso_paquete.visible = False
            return True
        try:
            paquetes = api_client.paquetes_horario(int(valor_semestre))
        except ApiError as ex:
            if ex.status == 401:
                navegar("/secretaria")
                return False
            paquete.options = []
            paquete.value = None
            paquete.visible = True
            aviso_paquete.value = ex.mensaje
            aviso_paquete.visible = True
            return False

        disponibles = [
            item for item in paquetes
            if item["lugares"] > 0 or item["id_paquete"] == id_actual
        ]
        if id_actual is not None and not any(
            item["id_paquete"] == id_actual for item in disponibles
        ):
            disponibles.append({
                "id_paquete": id_actual,
                "nombre": "Paquete actual",
                "turno": "",
                "lugares": 0,
            })
        paquete.options = [
            ft.DropdownOption(
                key=str(item["id_paquete"]),
                text=(
                    f"{item['nombre']} · {item['turno']} · {item['lugares']} lugares"
                    if item["id_paquete"] != id_actual
                    else f"{item['nombre']} · paquete actual"
                ),
            )
            for item in disponibles
        ]
        paquete.value = str(id_actual) if id_actual is not None else None
        paquete.visible = True
        aviso_paquete.visible = not disponibles
        return True

    def semestre_seleccionado(_):
        semestre.error_text = None
        paquete.error_text = None
        aviso_paquete.visible = False
        actualizar_paquetes(semestre.value)
        page.update()

    def reiniciar_formulario():
        nonlocal numero_original
        numero_original = None
        numero.value = ""
        nombre.value = ""
        apellido_paterno.value = ""
        apellido_materno.value = ""
        semestre.value = None
        numero.read_only = False
        paquete.options = []
        paquete.value = None
        paquete.visible = False
        aviso_paquete.visible = False
        boton_registrar.content = "Registrar reinscripción"
        boton_buscar.visible = True
        boton_cancelar.visible = False
        limpiar_errores()
        page.update()

    def buscar_reinscripcion(_=None):
        nonlocal numero_original
        limpiar_errores()
        consulta = (numero.value or "").strip()
        if not re.fullmatch(r"\d{8}", consulta):
            numero.error = "Escribe un número de control de 8 dígitos"
            page.update()
            return
        try:
            registro = api_client.reinscripcion(consulta)
        except ApiError as ex:
            if ex.status == 401:
                navegar("/secretaria")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
        else:
            numero_original = registro["numero_control"]
            numero.value = registro["numero_control"]
            numero.read_only = True
            nombre.value = registro["nombre"]
            apellido_paterno.value = registro["apellido_paterno"]
            apellido_materno.value = registro["apellido_materno"]
            semestre.value = str(registro["semestre"])
            if not actualizar_paquetes(registro["semestre"], registro.get("id_paquete")):
                aviso.value = "No se pudieron cargar las opciones de paquete."
                aviso.visible = True
            boton_registrar.content = "Actualizar reinscripción"
            boton_buscar.visible = False
            boton_cancelar.visible = True
        page.update()

    def validar():
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
                    f"Para {datos['semestre']}° semestre, el número de control debe corresponder al año {anio}"
                )
            elif error := v.validar_periodo_numero_control(
                datos["numero_control"], datos["semestre"],
            ):
                errores["numero_control"] = error
        if datos["id_paquete"] is None:
            errores["id_paquete"] = "Selecciona un paquete con lugares disponibles"
        return datos, errores

    def registrar(_=None):
        limpiar_errores()
        datos, errores = validar()
        if errores:
            numero.error = errores.get("numero_control")
            nombre.error = errores.get("nombre")
            apellido_paterno.error = errores.get("apellido_paterno")
            apellido_materno.error = errores.get("apellido_materno")
            semestre.error_text = errores.get("semestre")
            paquete.error_text = errores.get("id_paquete")
            page.update()
            return

        boton_registrar.disabled = True
        page.update()
        try:
            if numero_original:
                api_client.modificar_reinscripcion(numero_original, datos)
                resultado = None
            else:
                resultado = api_client.registrar_reinscripcion(datos)
        except ApiError as ex:
            if ex.status == 401:
                navegar("/secretaria")
                return
            for campo, mensaje in ex.errores.items():
                control = {
                    "numero_control": numero,
                    "nombre": nombre,
                    "apellido_paterno": apellido_paterno,
                    "apellido_materno": apellido_materno,
                    "semestre": semestre,
                    "id_paquete": paquete,
                }.get(campo)
                if isinstance(control, ft.Dropdown):
                    control.error_text = mensaje
                elif control is not None:
                    control.error = mensaje
            aviso.value = ex.mensaje
            aviso.visible = True
        else:
            actualizando = numero_original is not None
            reiniciar_formulario()
            snackbar(
                page,
                "Reinscripción actualizada correctamente." if actualizando
                else f"Reinscripción registrada. Horario asignado al grupo {resultado['paquete']}.",
            )
        finally:
            boton_registrar.disabled = False
            page.update()

    boton_registrar.on_click = registrar
    boton_buscar.on_click = buscar_reinscripcion
    boton_cancelar.on_click = lambda _: reiniciar_formulario()
    semestre.on_select = semestre_seleccionado
    vista = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=20, controls=[
        titulo_pagina(
            "Reinscripción",
            "Registra reinscritos con el paquete de horario elegido o busca su número de control para modificar sus datos.",
        ),
        crear_tarjeta(ft.Column(spacing=16, controls=[
            ft.ResponsiveRow(spacing=12, run_spacing=12, controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Número de control", numero)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Semestre", semestre)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Nombre", nombre)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Apellido paterno", apellido_paterno)),
                ft.Container(col={"xs": 12, "md": 6}, content=crear_campo_etiquetado("Apellido materno", apellido_materno)),
            ]),
            ft.Column(spacing=4, controls=[paquete, aviso_paquete]),
            aviso,
            ft.Row(controls=[boton_buscar, boton_cancelar, boton_registrar]),
        ]), padding=ft.Padding.symmetric(horizontal=20, vertical=16)),
    ])
    return vista
