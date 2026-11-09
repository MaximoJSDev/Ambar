import flet as ft

from api_client import ApiError
from app_state import api, log
from forms.alta import FormAltas, build_formulario_inscripcion
from forms.domicilio import DomicilioCampos, formatear_ficha
from ui.components import snackbar
from ui.navigation import IMPLEMENTADAS, RUTAS_ADMIN
from ui.shell import Shell
from ui.theme import BG
from views.bitacora import build_bitacora_admin
from views.cuentas import (
    build_alta_maestro,
    build_alta_secretaria,
    build_consulta_maestros,
    build_consulta_secretarias,
)
from views.consultas import (
    ConsultaExpediente,
    _cambios_historial,
    build_bajas,
    build_consultas,
    build_modificacion,
    ordinal_semestre,
)
from views.docente import build_grupos_horarios, build_inicio_docente
from views.login import build_login
from views.reinscripcion import build_reinscripcion as _build_reinscripcion
from views.secretaria import build_panel, build_periodos_escolares

def build_reinscripcion(page: ft.Page, navegar) -> ft.Control:
    # Keep the application-wide client so authentication state is shared between views.
    return _build_reinscripcion(page, navegar, api)


# Application composition and route-level session state stay here; screen details live in views.
def main(page: ft.Page):
    page.title = "SIGE - Sistema Integral de Gestión Escolar"
    page.padding = 0
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed="#000000")

    sesion: dict = {
        "usuario": None,
        "shell": None,
        "consulta_numero_control": None,
    }

    # Flet services belong to the page, so one picker is reused across document workflows.
    selector_archivos = ft.FilePicker()

    def navegar(ruta: str):
        page.route = ruta
        route_change()

    def entrar(usuario: dict):
        sesion["usuario"] = usuario
        ruta_inicial = {
            "Administrador": "/consultas",
            "Docente": "/docente",
        }.get(usuario["rol"], "/secretaria")
        navegar(ruta_inicial)

    def consultar_alumno(numero_control: str):
        sesion["consulta_numero_control"] = numero_control
        navegar("/consultas")

    def cerrar_sesion():
        try:
            api.logout()
        except ApiError as ex:
            log.warning("No se pudo registrar el cierre de sesión: %s", ex.mensaje)
        sesion["usuario"] = None
        sesion["shell"] = None
        navegar("/")

    def cerrar_sesion_al_cerrar_app(e=None):
        try:
            api.logout()
        except ApiError as ex:
            log.warning(
                "No se pudo registrar la salida de sesión al cerrar la aplicación: %s",
                ex.mensaje,
            )

    def contenido_para(ruta: str, usuario: dict) -> ft.Control:
        if ruta == "/docente" and usuario["rol"] == "Docente":
            return build_inicio_docente(page, usuario, navegar)
        if ruta == "/altas":
            return build_formulario_inscripcion(page, selector_archivos, navegar)
        if ruta == "/altas-maestros":
            return build_alta_maestro(page, navegar)
        if ruta == "/consulta-maestros":
            return build_consulta_maestros(page, navegar)
        if ruta == "/grupos-horarios":
            return build_grupos_horarios(page, navegar)
        if ruta == "/reinscripcion":
            return build_reinscripcion(page, navegar)
        if ruta == "/consultas":
            numero_control = sesion.pop("consulta_numero_control", None)
            return build_consultas(
                page, selector_archivos, usuario, navegar, numero_control,
            )
        if ruta == "/modificacion":
            return build_modificacion(page, selector_archivos, usuario, navegar)
        if ruta == "/bajas":
            return build_bajas(page, selector_archivos, usuario, navegar)
        if ruta == "/administracion/secretarias/alta":
            return build_alta_secretaria(page, navegar)
        if ruta == "/administracion/periodos":
            return build_periodos_escolares(page)
        if ruta == "/administracion/secretarias":
            return build_consulta_secretarias(page, navegar)
        if ruta == "/bitacora":
            return build_bitacora_admin(page, navegar)
        return build_panel(page, navegar, consultar_alumno)

    def route_change(e=None):
        # A rejected token closes protected access before building another private screen.
        sesion_expirada = False
        if api.sesion_vencida:
            api.sesion_vencida = False
            if sesion["usuario"] is not None:
                sesion["usuario"] = None
                sesion["shell"] = None
                sesion_expirada = True

        ruta = page.route or "/"
        usuario = sesion["usuario"]
        if usuario is None:
            ruta = "/"
        elif usuario["rol"] == "Docente":
            if ruta != "/docente":
                ruta = "/docente"
        elif usuario["rol"] not in {"Administrador", "Secretaría"}:
            ruta = "/secretaria"
        elif usuario["rol"] == "Administrador" and ruta not in RUTAS_ADMIN:
            ruta = "/consultas"
        elif usuario["rol"] != "Administrador" and ruta in RUTAS_ADMIN - {
            "/consultas", "/modificacion",
        }:
            ruta = "/secretaria"
        elif ruta in {"/altas-maestros", "/consulta-maestros"} and usuario["rol"] != "Secretaría":
            ruta = "/secretaria"
        elif ruta not in IMPLEMENTADAS:
            ruta = "/secretaria"
        page.route = ruta

        if ruta == "/":
            sesion["shell"] = None
            page.views.clear()
            page.views.append(build_login(page, entrar))
            page.update()
            if sesion_expirada:
                snackbar(page, "Tu sesión expiró. Inicia sesión de nuevo.")
            return

        shell: Shell | None = sesion["shell"]
        if shell is None:
            shell = sesion["shell"] = Shell(page, usuario, navegar, cerrar_sesion)
        if not page.views or page.views[0] is not shell.view:
            page.views.clear()
            page.views.append(shell.view)
        if shell.activo != ruta:
            contenido = contenido_para(ruta, usuario)
            if api.sesion_vencida:
                route_change()
                return
            shell.mostrar(ruta, contenido)
        page.update()

    page.on_route_change = route_change
    page.on_close = cerrar_sesion_al_cerrar_app
    navegar("/")


if __name__ == "__main__":
    ft.run(main)
