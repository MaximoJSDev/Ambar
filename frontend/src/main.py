import asyncio
import atexit
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import flet as ft

from ambar_common import validators as v
from api_client import ApiClient, ApiError

# =====================================================================
# CONSTANTES DE DISEÑO
# =====================================================================
NAVY = "#17345C"
GOLD = "#D99A2B"
BG = "#F3F5F9"
WHITE = "#FFFFFF"
TEXT = "#1B2A41"
MUTED = "#6B7A90"
BORDER = "#E3E7EF"
SOFT_BLUE = "#E8F0FB"
OK_BG, OK_FG = "#DFF1E8", "#13734A"
WARN_BG, WARN_FG = "#FFEFD2", "#9A5B00"

# El servidor es la fuente de verdad para autenticación, cupos y almacenamiento de PDF.
# SIGE_API_URL permite apuntar el cliente a la instancia del backend correspondiente.
api = ApiClient()
log = logging.getLogger("sige.frontend")


# --- Reglas de Altas (documento de contexto, Algoritmo 3) -------------------
DOCUMENTOS = [                               # La API usa estos nombres para asociar cada PDF con su tipo documental.
    "Acta de nacimiento",
    "CURP",
    "Comprobante de domicilio",
    "INE",
    "Certificado de preparatoria",
    "Certificado médico",
]
# La constancia fiscal se puede agregar al expediente, aunque no se solicita en Altas.
DOCUMENTOS_MODIFICABLES = (*DOCUMENTOS, "Constancia de situación fiscal")
# Este indicador controla la validación inmediata de la interfaz; el servidor aplica su propia política.
REQUIERE_TODOS_LOS_DOCUMENTOS = True


NAV = [
    ("/secretaria", "Inicio", ft.Icons.HOME_OUTLINED),
    ("/altas", "Altas", ft.Icons.ADD),
    ("/altas-maestros", "Alta de maestros", ft.Icons.PERSON_ADD_ALT_1),
    ("/consulta-maestros", "Consulta de maestros", ft.Icons.GROUP_OUTLINED),
    ("/consultas", "Consultas", ft.Icons.LIST_ALT),
    ("/grupos-horarios", "Grupos y horarios", ft.Icons.GROUP_OUTLINED),
    ("/modificacion", "Modificación", ft.Icons.EDIT_OUTLINED),
    ("/bajas", "Bajas", ft.Icons.REMOVE),
    ("/reinscripcion", "Reinscripción", ft.Icons.REPLAY),
    ("/estadisticas", "Estadísticas", ft.Icons.BAR_CHART),
]
ADMIN_NAV = [
    ("/consultas", "Historial de alumnos", ft.Icons.HISTORY),
    ("/modificacion", "Modificación", ft.Icons.EDIT_OUTLINED),
    ("/administracion/periodos", "Periodos escolares", ft.Icons.CALENDAR_MONTH),
    ("/administracion/secretarias/alta", "Alta de secretaria", ft.Icons.PERSON_ADD_ALT_1),
    ("/administracion/secretarias", "Consulta de secretarias", ft.Icons.LIST_ALT),
    ("/bitacora", "Bitácora", ft.Icons.FORMAT_LIST_BULLETED),
]
DOCENTE_NAV = [
    ("/docente", "Mis grupos", ft.Icons.GROUP_OUTLINED),
]
RUTAS_ADMIN = {
    "/consultas",
    "/modificacion",
    "/administracion/periodos",
    "/administracion/secretarias/alta",
    "/administracion/secretarias",
    "/bitacora",
}
IMPLEMENTADAS = {
    "/secretaria", "/altas", "/altas-maestros", "/consulta-maestros",
    "/grupos-horarios", "/modificacion", "/bajas", "/docente",
    *RUTAS_ADMIN,
}

_CAMPOS_HISTORIAL = {
    "numero_ficha": ("Identificación", "Número de ficha"),
    "nombres": ("Identificación", "Nombre(s)"),
    "apellido_paterno": ("Identificación", "Apellido paterno"),
    "apellido_materno": ("Identificación", "Apellido materno"),
    "fecha_nacimiento": ("Datos personales", "Fecha de nacimiento"),
    "genero": ("Datos personales", "Género"),
    "curp": ("Datos personales", "CURP"),
    "rfc": ("Datos personales", "RFC"),
    "ine": ("Datos personales", "Clave de elector (INE)"),
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


# =====================================================================
# AYUDAS DE UI
# =====================================================================
def _limpiar_error(e):
    if getattr(e.control, "error", None) or getattr(e.control, "error_text", None):
        if hasattr(e.control, "error"):
            e.control.error = None
        e.control.update()


def crear_campo_texto(texto_ayuda: str = "", **opciones) -> ft.TextField:
    """Crea un campo de texto con estilo común y borde suave."""
    return ft.TextField(
        hint_text=texto_ayuda,
        text_size=13,
        filled=True,
        fill_color=WHITE,
        border={
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                border_radius=6,
                side=ft.BorderSide(color=BORDER),
            ),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                border_radius=6,
                side=ft.BorderSide(color=NAVY),
            ),
        },
        hint_style=ft.TextStyle(color="#7A8799", size=13),
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=12),
        on_change=_limpiar_error,
        **opciones,
    )


def crear_campo_etiquetado(texto: str, control: ft.Control) -> ft.Column:
    return ft.Column(
        spacing=6,
        expand=1,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[ft.Text(texto, size=13, weight=ft.FontWeight.BOLD, color=TEXT), control],
    )


def crear_tarjeta(contenido: ft.Control, padding=24, **opciones) -> ft.Container:
    return ft.Container(
        content=contenido,
        bgcolor=WHITE,
        border=ft.Border.all(1, BORDER),
        border_radius=10,
        padding=padding,
        **opciones,
    )


def estilo_boton_primario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor=NAVY,
        color=WHITE,
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding.symmetric(horizontal=28, vertical=18),
    )


def estilo_boton_secundario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=NAVY,
        side=ft.BorderSide(1, NAVY),
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding.symmetric(horizontal=28, vertical=18),
    )


def snackbar(page: ft.Page, texto: str):
    page.show_dialog(ft.SnackBar(ft.Text(texto), duration=4000))


# =====================================================================
# 1. LOGIN
# =====================================================================
def build_login(page: ft.Page, al_entrar) -> ft.View:
    correo = crear_campo_texto("usuario@acapulco.tecnm.mx", autofocus=True, keyboard_type=ft.KeyboardType.EMAIL)
    password = crear_campo_texto("Contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", color=ft.Colors.RED_700, size=13, weight=ft.FontWeight.W_600, visible=False)
    boton = ft.FilledButton(
        "Iniciar sesión",
        style=estilo_boton_primario(),
        height=46,
    )

    def bloquear_ui(bloqueado: bool):
        password.disabled = bloqueado
        boton.disabled = bloqueado

    async def cuenta_regresiva(segundos: int):
        fin = time.monotonic() + segundos
        try:
            while True:
                segundos_restantes = int(fin - time.monotonic() + 0.999)
                if segundos_restantes <= 0:
                    break
                aviso.value = (f"Cuenta bloqueada por demasiados intentos. "
                               f"Intenta de nuevo en {segundos_restantes // 60}:{segundos_restantes % 60:02d}.")
                aviso.visible = True
                page.update()
                await asyncio.sleep(1)
            aviso.visible = False
            bloquear_ui(False)
            password.value = ""
            page.update()
        except Exception:
            # Al cambiar de vista, Flet puede invalidar los controles que actualiza esta tarea.
            pass

    def autenticar(e=None):
        correo_normalizado = (correo.value or "").strip().lower()
        contrasena = password.value or ""
        correo.error = None
        password.error = None
        aviso.visible = False

        error_correo = v.validar_correo_login(correo_normalizado)
        if error_correo:
            correo.error = error_correo
            page.update()
            return
        if not contrasena:
            password.error = "Contraseña obligatoria"
            page.update()
            return

        # La llamada al API es síncrona; deshabilitar el botón evita solicitudes duplicadas.
        boton.disabled = True
        page.update()
        try:
            usuario = api.login(correo_normalizado, contrasena)
        except ApiError as ex:
            boton.disabled = False
            if ex.status == 423:        # El servidor centraliza el bloqueo y comunica el tiempo restante.
                bloquear_ui(True)
                page.update()
                page.run_task(cuenta_regresiva, int(ex.extra.get("segundos", 300)))
                return
            if ex.status == 401:        # El mensaje no distingue entre correo inexistente y contraseña incorrecta.
                restantes = ex.extra.get("intentos_restantes", 0)
                password.error = (f"Credenciales incorrectas. Te quedan {restantes} "
                                  f"intento{'s' if restantes != 1 else ''}.")
            else:
                aviso.value = ex.mensaje
                aviso.visible = True
            page.update()
            return
        boton.disabled = False
        password.value = ""
        al_entrar(usuario)

    boton.on_click = autenticar
    correo.on_submit = autenticar
    password.on_submit = autenticar

    def ayuda(e=None):
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Necesitas ayuda para acceder?"),
            content=ft.Text("Si olvidaste tu contraseña o tu cuenta fue bloqueada, "
                            "contacta al área de sistemas de tu campus."),
            actions=[ft.TextButton("Entendido", on_click=lambda _: page.pop_dialog())],
        ))

    panel_izq = ft.Container(
        expand=5,
        bgcolor=NAVY,
        padding=ft.Padding.only(left=76, right=40, top=140, bottom=100),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(spacing=8, controls=[
                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED, color=GOLD, size=60),
                    ft.Text("SIGE", size=68, weight=ft.FontWeight.BOLD, color=WHITE),
                    ft.Text("Sistema Integral de\nGestión Escolar", size=26, color=WHITE),
                    ft.Container(width=136, height=5, bgcolor=GOLD, margin=ft.Margin.only(top=18, bottom=14)),
                    ft.Text("TecNM • Campus Acapulco", size=20, color="#D5DDEA"),
                ]),
                ft.Column(spacing=4, controls=[
                    ft.Text("Servicios escolares y docentes", size=19, color=WHITE),
                    ft.Text("en una sola plataforma.", size=19, color="#D5DDEA"),
                ]),
            ],
        ),
    )

    tarjeta_login = ft.Container(
        width=620,
        bgcolor=WHITE,
        border=ft.Border.all(1, BORDER),
        border_radius=14,
        padding=52,
        content=ft.Column(
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Text("Bienvenido", size=36, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text("Ingresa con tu cuenta institucional.", size=16, color=MUTED),
                ft.Container(height=30),
                ft.Text("Correo institucional", size=13, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(height=6),
                correo,
                ft.Container(height=20),
                ft.Text("Contraseña", size=13, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(height=6),
                password,
                ft.Container(height=10),
                aviso,
                ft.Container(height=14),
                ft.Row(controls=[ft.Container(content=boton, expand=True)]),
                ft.Container(height=22),
                ft.Text("El sistema identifica tu perfil al iniciar sesión.", size=13, color=MUTED),
                ft.Container(height=14),
                ft.Row(controls=[ft.Container(
                    content=ft.Text("¿Necesitas ayuda para acceder?", size=14,
                                    weight=ft.FontWeight.BOLD, color=NAVY),
                    on_click=ayuda,
                )]),
            ],
        ),
    )

    panel_der = ft.Container(expand=7, bgcolor=BG, alignment=ft.Alignment.CENTER, content=tarjeta_login)

    return ft.View(
        route="/",
        padding=0,
        spacing=0,
        bgcolor=BG,
        controls=[ft.Row(expand=True, spacing=0, controls=[panel_izq, panel_der])],
    )


# =====================================================================
# 2. SHELL (barra lateral + encabezado) Y PANEL DE SECRETARÍA
# =====================================================================
class Shell:
    """Marco fijo de la aplicación: barra lateral + encabezado + pie.

    Se construye UNA sola vez por sesión y vive en una única `ft.View`. Al navegar
    solo se cambia `self.host.content` y el resaltado del menú; así la barra azul no
    se vuelve a crear ni hay transición de pantalla (el "zoom" de Flutter aparece
    cuando se reemplazan Views).
    """

    def __init__(self, page: ft.Page, usuario: dict, navegar, cerrar_sesion):
        self.page = page
        self.navegar = navegar
        self.activo: str | None = None
        self._items: dict[str, tuple[ft.Container, ft.Icon, ft.Text]] = {}
        self._controles_navegacion: list[ft.Container] = []

        items = []
        if usuario["rol"] == "Administrador":
            nav = ADMIN_NAV
        elif usuario["rol"] == "Secretaría":
            nav = NAV
        else:
            nav = DOCENTE_NAV
        for destino, nombre, icono in nav:
            ico = ft.Icon(icono, size=18, color="#C9D3E3")
            txt = ft.Text(nombre, size=14, color="#E1E8F3")
            cont = ft.Container(
                margin=ft.Margin.symmetric(horizontal=12, vertical=2),
                padding=ft.Padding.symmetric(horizontal=14, vertical=13),
                border_radius=6,
                ink=True,
                on_click=lambda e, d=destino, n=nombre: self._ir(d, n),
                content=ft.Row(spacing=14, controls=[ico, txt]),
            )
            self._items[destino] = (cont, ico, txt)
            self._controles_navegacion.append(cont)
            items.append(cont)

        def pie(icono, texto, on_click):
            control = ft.Container(
                padding=ft.Padding.symmetric(horizontal=26, vertical=10),
                ink=True,
                on_click=on_click,
                content=ft.Row(spacing=10, controls=[
                    ft.Icon(icono, size=16, color="#E1E8F3"),
                    ft.Text(texto, size=14, color="#E1E8F3"),
                ]),
            )
            self._controles_navegacion.append(control)
            return control

        barra_lateral = ft.Container(
            width=230,
            bgcolor=NAVY,
            content=ft.Column(
                spacing=0,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Column(spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=20, top=24, bottom=18),
                            content=ft.Column(spacing=4, controls=[
                                ft.Row(spacing=10, controls=[
                                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED, color=GOLD, size=40),
                                    ft.Text("SIGE", size=30, weight=ft.FontWeight.BOLD, color=WHITE),
                                ]),
                                ft.Text("Campus Acapulco", size=12, color="#D5DDEA"),
                            ]),
                        ),
                        ft.Divider(height=1, color="#2B4A78"),
                        ft.Container(height=4),
                        *items,
                    ]),
                    ft.Column(spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
                        pie(ft.Icons.HELP_OUTLINE, "Ayuda", lambda e: snackbar(
                            page, "Ayuda: contacta al área de sistemas del campus.")),
                        pie(ft.Icons.LOGOUT, "Cerrar sesión", lambda e: cerrar_sesion()),
                        ft.Container(height=14),
                    ]),
                ],
            ),
        )

        encabezado = ft.Container(
            height=72,
            bgcolor=WHITE,
            padding=ft.Padding.symmetric(horizontal=32),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Sistema Integral de Gestión Escolar", size=22,
                            weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Column(spacing=2, alignment=ft.MainAxisAlignment.CENTER, controls=[
                        ft.Text(usuario["nombre"], size=14, weight=ft.FontWeight.BOLD, color=TEXT),
                        ft.Text(usuario["rol"], size=12, color=MUTED),
                    ]),
                ],
            ),
        )

        # Mantener el marco fuera del scroll conserva fija la navegación; cada pantalla controla su propio desplazamiento.
        self.host = ft.Container(expand=True, bgcolor=BG, padding=32)

        self.view = ft.View(
            route="/secretaria",
            padding=0,
            spacing=0,
            bgcolor=BG,
            controls=[ft.Row(expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
                barra_lateral,
                ft.Column(expand=True, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                          controls=[encabezado, self.host]),
            ])],
        )

    def _ir(self, destino: str, nombre: str):
        if destino in IMPLEMENTADAS:
            self.navegar(destino)
        else:
            snackbar(self.page, f"El módulo «{nombre}» estará disponible próximamente.")

    def mostrar(self, ruta: str, contenido: ft.Control):
        """Cambia el contenido y el elemento activo del menú sin recrear el marco."""
        self.activo = ruta
        # Evita que los accesos laterales interrumpan la tabulación del formulario de altas.
        permitir_tab_navegacion = ruta != "/altas"
        for control in self._controles_navegacion:
            control.ink = permitir_tab_navegacion
        for r, (cont, ico, txt) in self._items.items():
            act = r == ruta
            cont.bgcolor = GOLD if act else None
            ico.color = WHITE if act else "#C9D3E3"
            txt.color = WHITE if act else "#E1E8F3"
            txt.weight = ft.FontWeight.BOLD if act else ft.FontWeight.NORMAL
        self.host.content = contenido


def titulo_pagina(titulo: str, subtitulo: str) -> ft.Column:
    return ft.Column(spacing=6, controls=[
        ft.Text(titulo, size=30, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.Text(subtitulo, size=15, color=MUTED),
    ])


def chip_estado(estado: str) -> ft.Container:
    ok = estado == "Completada"
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        border_radius=14,
        bgcolor=OK_BG if ok else WARN_BG,
        content=ft.Text(estado, size=12, weight=ft.FontWeight.BOLD, color=OK_FG if ok else WARN_FG),
    )


def build_panel(page: ft.Page, navegar, consultar_alumno=None) -> ft.Control:
    def estadistica(numero, texto):
        return ft.Container(
            col={"xs": 12, "sm": 6, "lg": 4},
            content=crear_tarjeta(ft.Column(spacing=8, controls=[
                ft.Text(str(numero), size=34, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(texto, size=13, color=MUTED),
            ]), padding=20),
        )

    def acceso(titulo, descripcion, destino, nombre):
        def click(e):
            if destino in IMPLEMENTADAS:
                navegar(destino)
            else:
                snackbar(page, f"El módulo «{nombre}» estará disponible próximamente.")
        return ft.Container(
            col={"xs": 12, "md": 4},
            ink=True,
            border_radius=10,
            on_click=click,
            content=crear_tarjeta(ft.Row(spacing=16, controls=[
                ft.Container(width=6, height=54, bgcolor=GOLD, border_radius=3),
                ft.Column(spacing=6, tight=True, controls=[
                    ft.Text(titulo, size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Text(descripcion, size=13, color=MUTED),
                ]),
            ]), padding=ft.Padding.symmetric(horizontal=18, vertical=18)),
        )

    # Si falla la API, el panel sigue siendo navegable y muestra un aviso en vez de ocultar el problema.
    error_panel = None
    try:
        resumen = api.resumen_panel()
    except ApiError as ex:
        error_panel = ex.mensaje
        resumen = {"alumnos_nuevo_ingreso": 0, "grupos": 0,
                   "reinscripciones_hoy": 0, "actividad": []}
    alumnos_actividad = resumen["actividad"]
    pagina_actual = 0
    tamano_pagina = 10

    aviso_error = ft.Container(
        bgcolor=WARN_BG, border_radius=8, padding=12,
        content=ft.Text(f"No se pudieron cargar los datos del servidor: {error_panel}",
                        size=13, color=WARN_FG),
    )

    def celda(texto_o_control, expand):
        c = ft.Text(texto_o_control, size=13, color=TEXT) if isinstance(texto_o_control, str) else texto_o_control
        return ft.Container(expand=expand, content=c)

    cabecera = ft.Container(
        bgcolor="#EEF1F6",
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        content=ft.Row(controls=[
            celda(ft.Text("Alumno", size=13, weight=ft.FontWeight.BOLD, color=TEXT), 4),
            celda(ft.Text("Número de control", size=13, weight=ft.FontWeight.BOLD, color=TEXT), 2),
            celda(ft.Text("Trámite", size=13, weight=ft.FontWeight.BOLD, color=TEXT), 3),
            celda(ft.Text("Estado", size=13, weight=ft.FontWeight.BOLD, color=TEXT), 3),
        ]),
    )
    lista_actividad = ft.Column(spacing=0)
    indicador_pagina = ft.Text("", size=12, color=MUTED)
    boton_anterior = ft.TextButton("Anterior")
    boton_siguiente = ft.TextButton("Siguiente")

    def abrir_expediente(numero_control: str):
        if consultar_alumno is not None:
            consultar_alumno(numero_control)
        else:
            navegar("/consultas")

    def actualizar_pagina(evento=None):
        nonlocal pagina_actual
        total_paginas = max(1, (len(alumnos_actividad) + tamano_pagina - 1) // tamano_pagina)
        pagina_actual = min(max(0, pagina_actual), total_paginas - 1)
        inicio = pagina_actual * tamano_pagina
        visibles = alumnos_actividad[inicio:inicio + tamano_pagina]
        lista_actividad.controls = [
            ft.Container(
                ink=True,
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                on_click=lambda _, numero=alumno["numero_control"]: abrir_expediente(numero),
                content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                    celda(alumno["alumno"], 4),
                    celda(alumno["numero_control"], 2),
                    celda(alumno["tramite"], 3),
                    ft.Container(expand=3, content=ft.Row([chip_estado(alumno["estado"])])),
                ]),
            )
            for alumno in visibles
        ] or [ft.Text("No hay alumnos para mostrar.", size=13, color=MUTED)]
        indicador_pagina.value = f"Página {pagina_actual + 1} de {total_paginas}"
        boton_anterior.disabled = pagina_actual == 0
        boton_siguiente.disabled = pagina_actual >= total_paginas - 1
        if evento is not False:
            page.update()

    def cambiar_pagina(delta: int):
        nonlocal pagina_actual
        pagina_actual += delta
        actualizar_pagina()

    boton_anterior.on_click = lambda _: cambiar_pagina(-1)
    boton_siguiente.on_click = lambda _: cambiar_pagina(1)
    actualizar_pagina(False)

    actividad = crear_tarjeta(ft.ExpansionTile(
        title=ft.Text("Actividad reciente", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
        controls=[
            cabecera,
            lista_actividad,
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[boton_anterior, indicador_pagina, boton_siguiente],
            ),
        ],
    ), col={"xs": 12, "lg": 8})

    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina("Panel de Secretaría", "Gestiona alumnos, expedientes y procesos escolares."),
        *([aviso_error] if error_panel else []),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[
            estadistica(resumen["alumnos_nuevo_ingreso"], "Alumnos de nuevo ingreso"),
            estadistica(resumen["grupos"], "Grupos registrados"),
            estadistica(resumen["reinscripciones_hoy"], "Reinscripciones del día"),
        ]),
        ft.Text("Accesos rápidos", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[
            acceso("Inscribir alumno", "Registra un nuevo ingreso.", "/altas", "Altas"),
            acceso("Consultar expediente", "Consulta datos y documentos.", "/consultas", "Consultas"),
            acceso("Reinscribir alumno", "Asigna grupo y horario.", "/reinscripcion", "Reinscripción"),
        ]),
        actividad,
    ])


def build_periodos_escolares(page: ft.Page) -> ft.Control:
    periodo = ft.TextField(label="Periodo (ej. AGO-DIC 2026)", max_length=20, expand=True)
    fecha_inicio = ft.TextField(
        label="Fecha de inicio de la semana 1",
        read_only=True,
        expand=True,
        suffix_icon=ft.Icons.CALENDAR_MONTH,
        on_click=lambda _: page.show_dialog(selector_fecha),
    )
    hoy = datetime.date.today()
    selector_fecha = ft.DatePicker(
        first_date=datetime.datetime(2000, 1, 1),
        last_date=datetime.datetime(2100, 12, 31),
        current_date=datetime.datetime.combine(hoy, datetime.time()),
        on_change=lambda e: fecha_elegida(e),
    )
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    listado = ft.Column(spacing=8)
    periodo_original: str | None = None
    boton_guardar = ft.FilledButton(
        "Guardar periodo",
        icon=ft.Icons.SAVE_OUTLINED,
    )

    def fecha_elegida(e):
        valor = e.control.value
        if valor is not None:
            fecha = valor.date() if isinstance(valor, datetime.datetime) else valor
            fecha_inicio.value = fecha.isoformat()
            page.update()

    def cargar():
        try:
            periodos = api.periodos_escolares()
        except ApiError as ex:
            aviso.value = ex.mensaje
            aviso.visible = True
            page.update()
            return
        listado.controls = [
            ft.Container(
                padding=12,
                border=ft.Border.all(1, BORDER),
                border_radius=8,
                ink=True,
                on_click=lambda e, p=item: seleccionar(p),
                content=ft.Row(controls=[
                    ft.Text(item["periodo"], weight=ft.FontWeight.BOLD, color=NAVY, expand=True),
                    ft.Text(str(item["fecha_inicio"]), color=TEXT),
                    ft.Text("Seleccionar para editar", size=11, color=MUTED),
                ]),
            )
            for item in periodos
        ] or [ft.Text("Aún no hay periodos configurados.", color=MUTED)]
        page.update()

    def seleccionar(item: dict):
        nonlocal periodo_original
        periodo_original = item["periodo"]
        periodo.value = item["periodo"]
        fecha_inicio.value = str(item["fecha_inicio"])
        fecha = datetime.date.fromisoformat(fecha_inicio.value)
        selector_fecha.current_date = datetime.datetime.combine(fecha, datetime.time())
        boton_guardar.text = "Guardar cambios"
        aviso.visible = False
        page.update()

    def guardar(_):
        nonlocal periodo_original
        aviso.visible = False
        nombre_periodo = (periodo.value or "").strip()
        try:
            fecha = datetime.date.fromisoformat((fecha_inicio.value or "").strip())
            api.guardar_periodo_escolar(nombre_periodo, fecha.isoformat(), periodo_original)
        except ValueError:
            aviso.value = "Selecciona una fecha válida con el calendario."
            aviso.visible = True
            page.update()
            return
        except ApiError as ex:
            aviso.value = ex.mensaje
            aviso.visible = True
            page.update()
            return
        snackbar(page, "Periodo escolar guardado.")
        periodo_original = nombre_periodo
        boton_guardar.text = "Guardar cambios"
        cargar()

    def limpiar():
        nonlocal periodo_original
        periodo_original = None
        periodo.value = ""
        fecha_inicio.value = ""
        boton_guardar.text = "Guardar periodo"
        aviso.visible = False
        page.update()

    boton_guardar.on_click = guardar
    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=18, controls=[
        titulo_pagina("Periodos escolares", "Configura el inicio de semana 1 para habilitar las evaluaciones."),
        crear_tarjeta(ft.Column(spacing=12, controls=[
            ft.Text("Configuración del periodo", size=18, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Text(
                "La semana indicada cuenta como semana 1. Las capturas se habilitan al comenzar "
                "las semanas 5, 9, 13 y 17. Puedes corregir el nombre y la fecha; las calificaciones "
                "registradas se conservan y el calendario se recalcula.",
                size=13, color=MUTED,
            ),
            ft.ResponsiveRow(controls=[
                ft.Container(col={"xs": 12, "md": 7}, content=periodo),
                ft.Container(col={"xs": 12, "md": 5}, content=fecha_inicio),
            ]),
            aviso,
            ft.Row(controls=[
                boton_guardar,
                ft.TextButton("Limpiar", on_click=lambda _: limpiar()),
            ]),
        ]), padding=18),
        crear_tarjeta(ft.Column(spacing=10, controls=[
            ft.Text("Periodos registrados", size=18, weight=ft.FontWeight.BOLD, color=NAVY),
            listado,
        ]), padding=18),
    ])


def build_inicio_docente(page: ft.Page, usuario: dict, navegar) -> ft.Control:
    grupos: list[dict] = []
    selector = ft.Dropdown(label="Grupo y materia", expand=True, options=[])
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    contenido = ft.Column(spacing=16)

    def descargar_pdf_docente(descargar, nombre: str):
        try:
            contenido_pdf = descargar()
            destino = _carpeta_pdf_temporal() / nombre
            destino.write_bytes(contenido_pdf)
            abrir_archivo(destino)
        except ApiError as ex:
            if ex.status == 401:
                navegar("/")
            else:
                snackbar(page, ex.mensaje)
        except OSError as ex:
            snackbar(page, f"No se pudo guardar el PDF: {ex}")

    def mostrar_grupo(id_grupo: int | None):
        grupo = next((item for item in grupos if item["id_grupo"] == id_grupo), None)
        if grupo is None:
            contenido.controls = [
                crear_tarjeta(ft.Text(
                    "No tienes grupos asignados en el periodo actual.",
                    size=14,
                    color=MUTED,
                ))
            ]
            page.update()
            return

        horarios = grupo["horarios"]
        resumen_horario = [
            ft.Container(
                col={"xs": 6, "md": 4, "lg": 2},
                content=crear_tarjeta(ft.Column(spacing=4, controls=[
                    ft.Text(horario["dia"], size=12, weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Text(f"{horario['inicio']} – {horario['fin']}", size=13, color=TEXT),
                ]), padding=12),
            )
            for horario in horarios
        ]
        if not resumen_horario:
            resumen_horario = [ft.Text("Este grupo no tiene horario publicado.", color=MUTED)]

        periodos_calificacion = (
            ("Semana 5", "semana_5"),
            ("Semana 9", "semana_9"),
            ("Semana 13", "semana_13"),
        )
        disponibles = set(grupo.get("evaluaciones_disponibles", []))

        def formato_calificacion(valor):
            return "—" if valor is None else f"{float(valor):.2f}".rstrip("0").rstrip(".")

        def guardar_calificacion(alumno, periodo, campo, entrada, aviso_error):
            entrada.error_text = None
            aviso_error.value = ""
            try:
                texto = (entrada.value or "").strip().replace(",", ".")
                valor = Decimal(texto)
                if (
                    not valor.is_finite()
                    or valor != valor.to_integral_value()
                    or (valor != 0 and not Decimal(70) <= valor <= Decimal(100))
                ):
                    raise ValueError
            except (InvalidOperation, ValueError):
                entrada.error_text = "Ingresa un entero: 0 o de 70 a 100."
                aviso_error.value = entrada.error_text
                page.update()
                return
            try:
                resultado = api.guardar_calificacion_docente(
                    grupo["id_grupo"], alumno["numero_control"], periodo, int(valor),
                )
            except ApiError as ex:
                if ex.status == 401:
                    navegar("/")
                    return
                entrada.error_text = ex.mensaje
                aviso_error.value = ex.mensaje
                page.update()
                return
            alumno[campo] = resultado["valor"]
            snackbar(page, f"{periodo} guardada para {alumno['nombre_completo']}.")
            mostrar_grupo(grupo["id_grupo"])

        def confirmar_final(alumno, promedio, valor_final):
            def guardar(_):
                page.pop_dialog()
                try:
                    resultado = api.confirmar_calificacion_final(
                        grupo["id_grupo"], alumno["numero_control"],
                    )
                except ApiError as ex:
                    snackbar(page, ex.mensaje)
                    return
                alumno["final"] = resultado["valor"]
                alumno["final_confirmada"] = True
                snackbar(page, "Calificación final confirmada; ya no se puede modificar.")
                mostrar_grupo(grupo["id_grupo"])

            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Confirmar calificación final"),
                content=ft.Text(
                    f"El promedio redondeado de los tres periodos es {promedio:.0f}. "
                    f"Se registrará {valor_final:.0f}"
                    f"{' porque el promedio exacto es menor a 70' if valor_final == 0 else ''}. "
                    "Después de confirmar, la calificación final no se podrá modificar. ¿Continuar?"
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("Confirmar final", on_click=guardar),
                ],
            ))

        encabezado_calificaciones = ft.ResponsiveRow(spacing=8, controls=[
            ft.Container(col={"xs": 12, "md": 4}, content=ft.Text("Alumno", weight=ft.FontWeight.BOLD, color=NAVY)),
            *[
                ft.Container(
                    col={"xs": 4, "md": 2},
                    content=ft.Text(etiqueta, size=12, weight=ft.FontWeight.BOLD, color=NAVY),
                )
                for etiqueta in ("Semana 5", "Semana 9", "Semana 13", "Final")
            ],
        ])

        filas_alumnos = []
        for alumno in grupo["alumnos"]:
            celdas = []
            for periodo, campo in periodos_calificacion:
                valor = alumno[campo]
                if periodo in disponibles:
                    entrada = ft.TextField(
                        value="" if valor is None else formato_calificacion(valor),
                        hint_text="0 o 70–100",
                        width=88,
                        dense=True,
                        text_size=12,
                        keyboard_type=ft.KeyboardType.NUMBER,
                        input_filter=ft.InputFilter(
                            regex_string=r"^[0-9]*$", allow=True, replacement_string="",
                        ),
                    )
                    aviso_error = ft.Text("", size=10, color=WARN_FG)
                    celda = ft.Column(spacing=2, controls=[
                        ft.Row(spacing=0, controls=[
                            entrada,
                            ft.IconButton(
                                icon=ft.Icons.SAVE_OUTLINED,
                                tooltip=f"Guardar {periodo}",
                                on_click=lambda e, a=alumno, p=periodo, c=campo,
                                    i=entrada, aviso=aviso_error:
                                    guardar_calificacion(a, p, c, i, aviso),
                            ),
                        ]),
                        aviso_error,
                    ])
                else:
                    celda = ft.Text(formato_calificacion(valor), size=13, color=MUTED if valor is None else TEXT)
                celdas.append(ft.Container(col={"xs": 4, "md": 2}, content=celda))

            valor_final = alumno["final"]
            if alumno.get("final_confirmada"):
                celda_final = ft.Row(spacing=3, controls=[
                    ft.Text(formato_calificacion(valor_final), size=13, color=TEXT),
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=14, color=MUTED),
                ])
            elif "Final" in disponibles:
                valores_periodos = [alumno[campo] for _, campo in periodos_calificacion]
                if all(valor is not None for valor in valores_periodos):
                    promedio_exacto = sum(
                        Decimal(str(valor)) for valor in valores_periodos
                    ) / Decimal(3)
                    promedio = promedio_exacto.quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP,
                    )
                    final_calculada = (
                        promedio if promedio_exacto >= 70 else Decimal("0")
                    )
                    celda_final = ft.Column(spacing=2, controls=[
                        ft.Text(f"Promedio final: {promedio:.0f}", size=11, color=MUTED),
                        ft.TextButton(
                            "Confirmar",
                            icon=ft.Icons.LOCK_OUTLINE,
                            on_click=lambda e, a=alumno, p=promedio, f=final_calculada:
                                confirmar_final(a, p, f),
                        ),
                    ])
                else:
                    celda_final = ft.Text("Faltan periodos", size=11, color=MUTED)
            else:
                celda_final = ft.Text(formato_calificacion(valor_final), size=13, color=MUTED if valor_final is None else TEXT)
            celdas.append(ft.Container(col={"xs": 4, "md": 2}, content=celda_final))

            filas_alumnos.append(ft.Container(
                padding=ft.Padding.symmetric(vertical=9),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                content=ft.ResponsiveRow(spacing=8, run_spacing=4, controls=[
                    ft.Container(
                        col={"xs": 12, "md": 4},
                        content=ft.Column(spacing=2, controls=[
                            ft.Text(alumno["nombre_completo"], size=13, color=TEXT),
                            ft.Text(alumno["numero_control"], size=11, color=MUTED),
                        ]),
                    ),
                    *celdas,
                ]),
            ))

        if not filas_alumnos:
            filas_alumnos = [ft.Text("Aún no hay alumnos inscritos en este grupo.", color=MUTED)]

        contenido.controls = [
            crear_tarjeta(ft.ResponsiveRow(spacing=16, run_spacing=12, controls=[
                ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Grupo", size=12, color=MUTED),
                    ft.Text(grupo["grupo"], size=15, weight=ft.FontWeight.BOLD, color=NAVY),
                ])),
                ft.Container(col={"xs": 6, "md": 5}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Materia", size=12, color=MUTED),
                    ft.Text(grupo["nombre_materia"], size=15, weight=ft.FontWeight.BOLD, color=NAVY),
                ])),
                ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Aula", size=12, color=MUTED),
                    ft.Text(grupo["aula"] or "Sin asignar", size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                    ft.Text("Turno", size=12, color=MUTED),
                    ft.Text(grupo["turno"], size=14, color=TEXT),
                ])),
                ft.Container(col={"xs": 12}, content=ft.Text(
                    f"Periodo: {grupo['periodo']} · {grupo['creditos']} créditos",
                    size=12,
                    color=MUTED,
                )),
            ]), padding=18),
            ft.Text("Horario semanal", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.ResponsiveRow(spacing=10, run_spacing=10, controls=resumen_horario),
            crear_tarjeta(ft.Column(spacing=12, controls=[
                ft.Text(
                    (
                        "Captura una calificación entera: 0 o de 70 a 100. Las evaluaciones se habilitan "
                        "al inicio de las semanas 5, 9, 13 y 17."
                    ),
                    size=12,
                    color=MUTED,
                ),
                ft.Text(
                    (
                        f"Semana actual: {grupo['semana_actual']}."
                        if grupo.get("semana_actual") is not None
                        else "El administrador aún no configuró la fecha de inicio del periodo."
                    ),
                    size=12,
                    color=MUTED,
                ),
                ft.Row(wrap=True, controls=[
                    ft.OutlinedButton(
                        "Descargar lista de alumnos",
                        icon=ft.Icons.GROUP_OUTLINED,
                        on_click=lambda _, gid=grupo["id_grupo"]:
                            descargar_pdf_docente(
                                lambda: api.descargar_lista_alumnos_docente(gid),
                                f"alumnos_{gid}.pdf",
                            ),
                    ),
                    ft.OutlinedButton(
                        "Descargar lista de calificaciones",
                        icon=ft.Icons.DOWNLOAD_OUTLINED,
                        on_click=lambda _, gid=grupo["id_grupo"]:
                            descargar_pdf_docente(
                                lambda: api.descargar_calificaciones_docente(gid),
                                f"calificaciones_{gid}.pdf",
                            ),
                    ),
                ]),
                ft.ExpansionTile(
                    title=ft.Text(
                        "Lista de alumnos y calificaciones",
                        size=19,
                        weight=ft.FontWeight.BOLD,
                        color=NAVY,
                    ),
                    controls=[
                        encabezado_calificaciones,
                        ft.Column(spacing=0, controls=filas_alumnos),
                    ],
                ),
            ]), padding=18),
        ]
        page.update()

    def seleccionar_grupo(e):
        try:
            mostrar_grupo(int(e.control.value) if e.control.value else None)
        except ValueError:
            selector.error_text = "Selecciona un grupo válido"
            page.update()

    def cargar(_=None):
        nonlocal grupos
        aviso.visible = False
        try:
            grupos = api.grupos_docente()
        except ApiError as ex:
            if ex.status == 401:
                navegar("/")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
            contenido.controls = []
            page.update()
            return

        selector.options = [
            ft.DropdownOption(
                key=str(grupo["id_grupo"]),
                text=f"{grupo['grupo']} · {grupo['nombre_materia']}",
            )
            for grupo in grupos
        ]
        grupo_inicial = grupos[0]["id_grupo"] if grupos else None
        selector.value = str(grupo_inicial) if grupo_inicial is not None else None
        mostrar_grupo(grupo_inicial)

    selector.on_select = seleccionar_grupo
    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=20, controls=[
        titulo_pagina(
            f"Bienvenido, {usuario['nombre']}",
            "Consulta tus grupos y horarios, y captura las calificaciones disponibles.",
        ),
        ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
            ft.Container(col={"xs": 12, "md": 6}, content=selector),
            ft.Container(col={"xs": 6, "md": 3}, content=ft.OutlinedButton(
                "Descargar grupos y horarios",
                icon=ft.Icons.DOWNLOAD_OUTLINED,
                on_click=lambda _: descargar_pdf_docente(
                    api.descargar_grupos_docente, "mis_grupos_horarios.pdf",
                ),
            )),
            ft.Container(col={"xs": 6, "md": 3}, content=ft.OutlinedButton(
                "Actualizar",
                icon=ft.Icons.REFRESH,
                style=estilo_boton_secundario(),
                on_click=cargar,
            )),
        ]),
        aviso,
        contenido,
    ])


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


def build_grupos_horarios(page: ft.Page, navegar) -> ft.Control:
    paquetes: list[dict] = []
    docentes: list[dict] = []
    paquete_seleccionado: int | None = None
    panel_grupo = ft.Column(spacing=16)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    selector = ft.Dropdown(label="Paquete / grupo", width=300, options=[])
    vista: ft.Column | None = None

    def mostrar_error(ex: ApiError):
        if ex.status == 401:
            navegar("/secretaria")
            return
        aviso.value = ex.mensaje
        aviso.visible = True
        panel_grupo.controls = []
        page.update()

    def guardar_docente(id_grupo: int, selector_docente: ft.Dropdown):
        try:
            id_docente = (
                int(selector_docente.value)
                if selector_docente.value not in (None, "none")
                else None
            )
            api.asignar_docente_grupo(id_grupo, id_docente)
            cargar_paquete()
            snackbar(page, "Asignación docente actualizada.")
        except ApiError as ex:
            if ex.status == 401:
                navegar("/secretaria")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
            page.update()
            if vista is not None:
                page.run_task(vista.scroll_to, offset=0, duration=300)
        except ValueError:
            snackbar(page, "Selecciona una cuenta de maestro válida.")

    def _materia_control(materia: dict) -> ft.Control:
        horarios = ", ".join(
            f"{fila['dia'][:3]} {fila['inicio']}-{fila['fin']}"
            for fila in materia["horarios"]
        ) or "Sin horario publicado"
        valor = str(materia["id_docente"]) if materia["id_docente"] is not None else "none"
        selector_docente = ft.Dropdown(
            label="Cuenta vinculada",
            value=valor,
            options=[
                ft.DropdownOption(key="none", text="Sin cuenta vinculada"),
                *[
                    ft.DropdownOption(
                        key=str(docente["id_docente"]),
                        text=f"{docente['nombres']} {docente['apellidos']}",
                    )
                    for docente in docentes
                ],
            ],
            width=260,
        )
        return crear_tarjeta(ft.Column(spacing=10, controls=[
            ft.Text(materia["nombre_materia"], size=15, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Text(
                f"Aula {materia['aula']} · {materia['creditos']} créditos · {horarios}",
                size=12,
                color=MUTED,
            ),
            ft.Text(
                f"Docente en horario: {materia['docente']}",
                size=12,
                color=TEXT,
            ),
            ft.Row(spacing=12, controls=[
                selector_docente,
                ft.OutlinedButton(
                    "Guardar docente",
                    style=estilo_boton_secundario(),
                    on_click=lambda _, gid=materia["id_grupo"], campo=selector_docente:
                        guardar_docente(gid, campo),
                ),
            ]),
        ]), padding=16)

    def descargar_lista(_=None):
        if paquete_seleccionado is None:
            return
        paquete = next(
            (item for item in paquetes if item["id_paquete"] == paquete_seleccionado),
            None,
        )
        if paquete is None:
            return
        try:
            contenido = api.descargar_lista_grupo(paquete_seleccionado)
            destino = _carpeta_pdf_temporal() / f"lista_{paquete['nombre']}.pdf"
            destino.write_bytes(contenido)
            abrir_archivo(destino)
        except ApiError as ex:
            mostrar_error(ex)
        except OSError as ex:
            snackbar(page, f"No se pudo guardar la lista PDF: {ex}")

    def cargar_paquete(_=None):
        nonlocal paquete_seleccionado
        if paquete_seleccionado is None:
            panel_grupo.controls = []
            page.update()
            return
        aviso.visible = False
        try:
            detalle = api.detalle_grupo_horario(paquete_seleccionado)
            lista = api.lista_alumnos_grupo(paquete_seleccionado)
        except ApiError as ex:
            mostrar_error(ex)
            return

        paquete = detalle["paquete"]
        alumnos = lista["alumnos"]
        materias = detalle["materias"]
        filas_alumnos = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                content=ft.Row(spacing=14, controls=[
                    ft.Text(f"{indice}.", width=35, size=13, color=MUTED),
                    ft.Text(alumno["numero_control"], width=125, size=13, color=TEXT),
                    ft.Text(
                        " ".join(filter(None, (
                            alumno["apellido_paterno"], alumno["apellido_materno"],
                            alumno["nombres"],
                        ))),
                        expand=True,
                        size=13,
                        color=NAVY,
                    ),
                ]),
            )
            for indice, alumno in enumerate(alumnos, 1)
        ]
        if not filas_alumnos:
            filas_alumnos = [ft.Text("Aún no hay alumnos inscritos en este grupo.", color=MUTED)]

        panel_grupo.controls = [
            crear_tarjeta(ft.ResponsiveRow(spacing=16, run_spacing=10, controls=[
                ft.Container(col={"xs": 12, "md": 5}, content=ft.Column(spacing=4, controls=[
                    ft.Text("Periodo", size=12, color=MUTED),
                    ft.Text(paquete["periodo"], size=14, weight=ft.FontWeight.BOLD, color=NAVY),
                ])),
                ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=4, controls=[
                    ft.Text("Alumnos inscritos", size=12, color=MUTED),
                    ft.Text(f"{len(alumnos)} / {paquete['cupo_maximo']}", size=14,
                            weight=ft.FontWeight.BOLD, color=NAVY),
                ])),
                ft.Container(col={"xs": 6, "md": 4}, content=ft.Column(spacing=4, controls=[
                    ft.Text("Lugares disponibles", size=12, color=MUTED),
                    ft.Text(str(paquete["lugares"]), size=14,
                            weight=ft.FontWeight.BOLD, color=NAVY),
                ])),
            ]), padding=18),
            ft.Text("Materias y asignación de maestros", size=19,
                    weight=ft.FontWeight.BOLD, color=NAVY),
            *[_materia_control(materia) for materia in materias],
            crear_tarjeta(ft.Column(spacing=12, controls=[
                ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                    ft.OutlinedButton(
                        "Descargar lista PDF",
                        icon=ft.Icons.DOWNLOAD_OUTLINED,
                        style=estilo_boton_secundario(),
                        on_click=descargar_lista,
                    ),
                ]),
                ft.ExpansionTile(
                    title=ft.Text(
                        "Alumnos del grupo",
                        size=19,
                        weight=ft.FontWeight.BOLD,
                        color=NAVY,
                    ),
                    controls=[ft.Column(spacing=0, controls=filas_alumnos)],
                ),
            ]), padding=18),
        ]
        page.update()

    def cambiar_paquete(e):
        nonlocal paquete_seleccionado
        paquete_seleccionado = int(e.control.value) if e.control.value else None
        cargar_paquete()

    def cargar(_=None):
        nonlocal paquetes, docentes, paquete_seleccionado
        aviso.visible = False
        try:
            paquetes = api.grupos_horario()
            docentes = api.docentes_horario()
        except ApiError as ex:
            mostrar_error(ex)
            return
        selector.options = [
            ft.DropdownOption(
                key=str(paquete["id_paquete"]),
                text=(
                    f"{paquete['nombre']} · {paquete['turno']} · "
                    f"{paquete['alumnos']} alumnos"
                ),
            )
            for paquete in paquetes
        ]
        if paquetes:
            ids_disponibles = {item["id_paquete"] for item in paquetes}
            if paquete_seleccionado not in ids_disponibles:
                paquete_seleccionado = paquetes[0]["id_paquete"]
            selector.value = str(paquete_seleccionado)
            cargar_paquete()
        else:
            paquete_seleccionado = None
            selector.value = None
            panel_grupo.controls = [crear_tarjeta(ft.Text(
                "No hay paquetes 1ISC configurados para el periodo activo. "
                "Reinicia el backend después de actualizar SIGE.",
                color=MUTED,
            ))]
            page.update()

    selector.on_select = cambiar_paquete
    vista = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=20, controls=[
        titulo_pagina(
            "Grupos y horarios",
            "Consulta las listas por sección y vincula las cuentas de maestros con el horario.",
        ),
        ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
            selector,
            ft.OutlinedButton(
                "Actualizar",
                icon=ft.Icons.REFRESH,
                style=estilo_boton_secundario(),
                on_click=cargar,
            ),
        ]),
        aviso,
        panel_grupo,
    ])
    cargar()
    return vista


def build_bitacora_admin(page: ft.Page, navegar) -> ft.Control:
    filas = ft.Column(spacing=0)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)

    def cargar(_=None):
        aviso.visible = False
        try:
            registros = api.bitacora()
        except ApiError as ex:
            if ex.status == 401:
                navegar("/consultas")
                return
            aviso.value = ex.mensaje
            aviso.visible = True
            filas.controls = []
        else:
            if not registros:
                filas.controls = [ft.Text("Aún no hay accesos registrados.", size=14, color=MUTED)]
            else:
                filas.controls = [
                    crear_tarjeta(ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
                        ft.Container(col={"xs": 12, "md": 3}, content=ft.Column(spacing=3, controls=[
                            ft.Text(registro["nombre"], size=14, weight=ft.FontWeight.BOLD, color=NAVY),
                            ft.Text(registro["correo"], size=12, color=MUTED),
                        ])),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Perfil", size=11, color=MUTED),
                            ft.Text(registro["rol"], size=13, color=TEXT),
                        ])),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Fecha", size=11, color=MUTED),
                            ft.Text(registro["fecha"], size=13, color=TEXT),
                        ])),
                        ft.Container(col={"xs": 6, "md": 2}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Entrada", size=11, color=MUTED),
                            ft.Text(registro["hora_entrada"], size=13, color=TEXT),
                        ])),
                        ft.Container(col={"xs": 6, "md": 3}, content=ft.Column(spacing=3, controls=[
                            ft.Text("Salida", size=11, color=MUTED),
                            ft.Text(registro["hora_salida"] or "Sesión en curso", size=13, color=TEXT),
                        ])),
                    ]), padding=ft.Padding.symmetric(horizontal=18, vertical=14))
                    for registro in registros
                ]
        page.update()

    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=20, controls=[
        titulo_pagina(
            "Bitácora de accesos",
            "Consulta los inicios y cierres de sesión registrados en el sistema.",
        ),
        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[
            ft.OutlinedButton("Actualizar", icon=ft.Icons.REFRESH, on_click=cargar),
        ]),
        aviso,
        filas,
    ])


# =====================================================================
# 3. FORMULARIO DE ALTAS (4 pasos) — según Algoritmo 3 del documento de contexto
# =====================================================================
class FormAltas:
    PASOS = ["Datos personales", "Datos académicos", "Documentos", "Confirmación"]

    def __init__(self, page: ft.Page, picker, al_cancelar, al_guardar):
        self.page = page
        self.picker = picker
        self.al_cancelar = al_cancelar
        self.al_guardar = al_guardar
        self.paso = 0
        self.fecha: datetime.date | None = None
        # nombre y tamaño se muestran en el formulario; path se envía junto con el alta.
        self.archivos: dict[str, dict] = {}
        self.errores_docs: dict[str, str] = {}

        letras = ft.InputFilter(regex_string=r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ '\-]*$", allow=True,
                                replacement_string="", unicode=True)
        alfanum = ft.InputFilter(regex_string=r"^[A-Za-z0-9&Ññ]*$", allow=True, replacement_string="")
        mayus = ft.TextCapitalization.CHARACTERS
        palabras = ft.TextCapitalization.WORDS

        # ---- Paso 1
        self.ficha = crear_campo_texto("Ej. 2026-00123", autofocus=True,
                        input_filter=ft.InputFilter(regex_string=r"^[0-9\-]*$", allow=True, replacement_string=""))
        self.nombre = crear_campo_texto("Ingresa el nombre o nombres", max_length=50, input_filter=letras, capitalization=palabras)
        self.ap_paterno = crear_campo_texto("Ingresa el apellido paterno", max_length=50, input_filter=letras, capitalization=palabras)
        self.ap_materno = crear_campo_texto("Ingresa el apellido materno", max_length=50, input_filter=letras, capitalization=palabras)
        self.date_picker = ft.DatePicker(
            first_date=datetime.datetime.combine(v.hace_anios(v.EDAD_MAXIMA), datetime.time()),
            last_date=datetime.datetime.combine(v.hace_anios(v.EDAD_MINIMA), datetime.time()),
            current_date=datetime.datetime.combine(v.hace_anios(18), datetime.time()),
            help_text="Fecha de nacimiento",
            on_change=self._fecha_elegida,
        )
        self.txt_fecha = crear_campo_texto("DD / MM / AAAA", read_only=True, suffix_icon=ft.Icons.CALENDAR_TODAY_OUTLINED)
        self.txt_fecha.on_click = lambda e: self.page.show_dialog(self.date_picker)
        self.curp = crear_campo_texto("Ingresa la CURP", input_filter=alfanum, capitalization=mayus)
        self.rfc = crear_campo_texto("Ingresa el RFC", input_filter=alfanum, capitalization=mayus)
        self.nss = crear_campo_texto("Ingresa el número de seguro social", keyboard_type=ft.KeyboardType.NUMBER,
                      input_filter=ft.NumbersOnlyInputFilter())
        self.ine = crear_campo_texto("Clave de elector (18 caracteres)", input_filter=alfanum, capitalization=mayus)
        self.genero = ft.Dropdown(
            hint_text="Selecciona",
            text_size=13,
            border_radius=6,
            border_color=BORDER,
            expand=True,
            options=[ft.DropdownOption(key=k, text=t) for k, t in v.GENEROS.items()],
            on_select=self._genero_elegido,
        )
        self.celular = crear_campo_texto("Número de 10 dígitos", keyboard_type=ft.KeyboardType.PHONE,
                          input_filter=ft.NumbersOnlyInputFilter())
        self.correo = crear_campo_texto("Correo electrónico del alumno", keyboard_type=ft.KeyboardType.EMAIL)
        self.domicilio = crear_campo_texto("Calle, número, colonia, ciudad y estado")

        # ---- Paso 2
        self.prepa = crear_campo_texto("Nombre de la preparatoria")
        self.promedio = crear_campo_texto("Ej. 9.5", keyboard_type=ft.KeyboardType.NUMBER,
                           input_filter=ft.InputFilter(regex_string=r"^[0-9.,]*$", allow=True, replacement_string=""))
        self.promedio.on_change = self._promedio_cambiado
        self.cel_emerg = crear_campo_texto("Número de 10 dígitos", keyboard_type=ft.KeyboardType.PHONE,
                            input_filter=ft.NumbersOnlyInputFilter())
        self.correo_emerg = crear_campo_texto("Correo del contacto de emergencia", keyboard_type=ft.KeyboardType.EMAIL)
        self.tipo_sangre = ft.Dropdown(
            hint_text="Selecciona",
            text_size=13,
            border_radius=6,
            border_color=BORDER,
            expand=True,
            options=[ft.DropdownOption(key=tipo, text=tipo) for tipo in v.TIPOS_SANGRE],
            on_select=self._tipo_sangre_elegido,
        )
        self.alergias = crear_campo_texto("Escribe las alergias o deja vacío si no tiene")
        self._primer_campo_por_paso = {
            0: self.ficha,
            1: self.prepa,
        }

        # ---- Contenedores dinámicos
        self.stepper = ft.Row(spacing=0)
        self.titulo_card = ft.Text("", size=21, weight=ft.FontWeight.BOLD, color=NAVY)
        # Los controles de navegación y el resumen permanecen visibles mientras se recorren los campos.
        self.cuerpo = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=0,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.botones = ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        self.res_estatus = ft.Container()
        self.res_turno = ft.Text("Se sugiere según el promedio", size=14, color=TEXT)
        self.res_expediente = ft.Text(f"0 de {len(DOCUMENTOS)} documentos", size=14, color=TEXT)
        self.res_horario = ft.Text("Se asigna desde Consultas después del alta", size=14, color=TEXT)
        self.aviso_docs = ft.Text("", size=13, color=ft.Colors.RED_700, visible=False)

        tarjeta_form = ft.Container(
            expand=True,
            bgcolor=WHITE,
            border=ft.Border.all(1, BORDER),
            border_radius=10,
            padding=24,
            content=ft.Column(spacing=18, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                              controls=[self.titulo_card, self.cuerpo, self.botones]),
        )
        lateral = ft.Container(
            width=340,
            content=ft.Column(spacing=20, scroll=ft.ScrollMode.AUTO,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                              controls=[self._resumen(), self._nota()]),
        )
        self.vista = ft.Column(expand=True, spacing=24, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            titulo_pagina("Inscripción de nuevo ingreso",
                          "Captura la información del alumno para iniciar su expediente."),
            self.stepper,
            ft.Row(expand=True, spacing=24, vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                   controls=[tarjeta_form, lateral]),
        ])
        self._pintar()

    # ------------------------------------------------------------------
    # Resumen lateral
    # ------------------------------------------------------------------
    def _resumen(self) -> ft.Control:
        def dato(titulo, valor):
            return ft.Column(spacing=3, controls=[
                ft.Text(titulo, size=13, color=MUTED),
                valor if isinstance(valor, ft.Control) else ft.Text(valor, size=14, color=TEXT),
            ])
        return crear_tarjeta(ft.Column(spacing=18, controls=[
            ft.Text("Resumen del registro", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Column(spacing=3, controls=[ft.Text("Estatus", size=13, color=MUTED), self.res_estatus]),
            dato("Número de control", "Se genera al finalizar"),
            dato("Turno", self.res_turno),
            dato("Paquete de horario", self.res_horario),
            dato("Expediente", self.res_expediente),
        ]))

    def _nota(self) -> ft.Control:
        return ft.Container(
            bgcolor=SOFT_BLUE,
            border_radius=10,
            padding=20,
            content=ft.Text("Los documentos se adjuntan en el paso 3 (solo PDF).", size=14, color=NAVY),
        )

    def _chip_estatus(self, texto, ok=False):
        self.res_estatus.bgcolor = OK_BG if ok else WARN_BG
        self.res_estatus.border_radius = 14
        self.res_estatus.padding = ft.Padding.symmetric(horizontal=12, vertical=4)
        self.res_estatus.content = ft.Text(texto, size=12, weight=ft.FontWeight.BOLD,
                                           color=OK_FG if ok else WARN_FG)

    def _refrescar_docs(self):
        documentos_cargados = len(self.archivos)
        self.res_expediente.value = f"{documentos_cargados} de {len(DOCUMENTOS)} documentos"

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def _fecha_elegida(self, e):
        valor = e.control.value
        if valor is None:
            return
        self.fecha = valor.date() if isinstance(valor, datetime.datetime) else valor
        self.txt_fecha.value = self.fecha.strftime("%d/%m/%Y")
        self.txt_fecha.error = None
        self._pintar()

    def _genero_elegido(self, e):
        self.genero.error_text = None
        self.page.update()

    def _tipo_sangre_elegido(self, e):
        self.tipo_sangre.error_text = None
        self.page.update()

    def _promedio_cambiado(self, e):
        self.promedio.error = None
        valor = self._texto_campo(self.promedio)
        if valor and v.validar_promedio(valor) is None:
            turno = v.turno_por_promedio(float(valor.replace(",", ".")))
            self.res_turno.value = f"{turno} (promedio {'≥' if turno == 'Matutino' else '<'} {v.TURNO_MATUTINO_MIN})"
        else:
            self.res_turno.value = "Se asigna según el promedio"
        self.page.update()

    async def _elegir_pdf(self, doc: str):
        """Abre el selector de archivos para un documento (solo PDF)."""
        try:
            archivos_seleccionados = await self.picker.pick_files(
                dialog_title=f"Selecciona: {doc}",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                allow_multiple=False,
            )
        except Exception as ex:  # Algunas plataformas no implementan el selector; el error se muestra en el formulario.
            self.errores_docs[doc] = f"No se pudo abrir el selector de archivos ({ex})"
            self._pintar()
            return
        if not archivos_seleccionados:
            return
        archivo_seleccionado = archivos_seleccionados[0]
        error_pdf = v.validar_pdf(
            archivo_seleccionado.name or "",
            archivo_seleccionado.size,
            archivo_seleccionado.path,
        )
        if error_pdf:
            self.archivos.pop(doc, None)
            self.errores_docs[doc] = error_pdf
        else:
            self.errores_docs.pop(doc, None)
            self.archivos[doc] = {
                "nombre": archivo_seleccionado.name,
                "path": archivo_seleccionado.path,
                "size": archivo_seleccionado.size,
            }
        self._pintar()

    def _quitar_pdf(self, doc: str):
        self.archivos.pop(doc, None)
        self.errores_docs.pop(doc, None)
        self._pintar()

    # ------------------------------------------------------------------
    # Validación
    # ------------------------------------------------------------------
    @staticmethod
    def _texto_campo(campo) -> str:
        return (campo.value or "").strip()

    def _requerido(self, campo: ft.TextField, validador=None, **kw) -> bool:
        valor = self._texto_campo(campo)
        campo.error = None
        if not valor:
            campo.error = "Campo obligatorio"
            return False
        error_validacion = validador(valor, **kw) if validador else None
        if error_validacion:
            campo.error = error_validacion
            return False
        return True

    def _no_duplicado(self) -> bool:
        """Pregunta al servidor si algún identificador ya está registrado."""
        try:
            duplicados = api.verificar(
                ficha=self._texto_campo(self.ficha),
                curp=self._texto_campo(self.curp).upper(),
                nss=self._texto_campo(self.nss),
                rfc=self._texto_campo(self.rfc).upper(),
                ine=self._texto_campo(self.ine).upper(),
                correo=self._texto_campo(self.correo),
            )
        except ApiError:
            # La consulta es preventiva; el servidor valida de nuevo al guardar el alta.
            return True
        campos = {
            "ficha": (self.ficha, "Esta ficha ya está registrada"),
            "curp": (self.curp, "Esta CURP ya está registrada"),
            "nss": (self.nss, "Este NSS ya está registrado"),
            "rfc": (self.rfc, "Este RFC ya está registrado"),
            "ine": (self.ine, "Esta INE ya está registrada"),
            "correo": (self.correo, "Este correo personal ya está registrado"),
        }
        sin_duplicados = True
        for clave, (campo, mensaje) in campos.items():
            if duplicados.get(clave):
                campo.error = mensaje
                sin_duplicados = False
        return sin_duplicados

    def validar_paso(self, paso: int) -> bool:
        paso_valido = True
        if paso == 0:
            paso_valido &= self._requerido(self.ficha, v.validar_ficha)
            paso_valido &= self._requerido(self.nombre, v.validar_nombre)
            paso_valido &= self._requerido(self.ap_paterno, v.validar_apellido)
            paso_valido &= self._requerido(self.ap_materno, v.validar_apellido)

            self.txt_fecha.error = v.validar_fecha_nacimiento(self.fecha)
            fecha_valida = self.txt_fecha.error is None
            paso_valido &= fecha_valida
            fecha_referencia = self.fecha if fecha_valida else None

            paso_valido &= self._requerido(
                self.curp,
                v.validar_curp,
                fecha=fecha_referencia,
                apellido_paterno=self._texto_campo(self.ap_paterno),
                apellido_materno=self._texto_campo(self.ap_materno),
                genero=self.genero.value,
            )
            mayor_de_18 = (
                self.fecha is not None
                and fecha_valida
                and v.es_mayor_de_18(self.fecha)
            )
            if mayor_de_18:
                paso_valido &= self._requerido(self.rfc, v.validar_rfc, fecha=fecha_referencia)
            else:
                self.rfc.error = v.validar_rfc(self._texto_campo(self.rfc), fecha=fecha_referencia)
            paso_valido &= self.rfc.error is None
            paso_valido &= self._requerido(self.nss, v.validar_nss)
            if mayor_de_18:
                paso_valido &= self._requerido(self.ine, v.validar_ine, fecha=fecha_referencia)
            else:
                self.ine.error = v.validar_ine(self._texto_campo(self.ine), fecha=fecha_referencia)
            paso_valido &= self.ine.error is None
            self.genero.error_text = v.validar_genero(self.genero.value)
            paso_valido &= self.genero.error_text is None
            paso_valido &= self._requerido(self.celular, v.validar_celular)
            paso_valido &= self._requerido(self.correo, v.validar_correo_con_dominio, maximo=100)
            paso_valido &= self._requerido(self.domicilio, v.validar_domicilio)
            if self.ficha.error is None and self.curp.error is None:
                paso_valido &= self._no_duplicado()
        elif paso == 1:
            paso_valido &= self._requerido(self.prepa, v.validar_preparatoria)
            paso_valido &= self._requerido(self.promedio, v.validar_promedio)
            paso_valido &= self._requerido(self.cel_emerg, v.validar_celular_emergencia,
                                  celular_alumno=self._texto_campo(self.celular))
            paso_valido &= self._requerido(self.correo_emerg, v.validar_correo_emergencia,
                                  correo_alumno=self._texto_campo(self.correo), maximo=100)
            self.tipo_sangre.error_text = v.validar_tipo_sangre(self.tipo_sangre.value)
            paso_valido &= self.tipo_sangre.error_text is None
            self.alergias.error = v.validar_alergias(self._texto_campo(self.alergias))
            paso_valido &= self.alergias.error is None
        elif paso == 2:
            faltan = [d for d in DOCUMENTOS if d not in self.archivos]
            if REQUIERE_TODOS_LOS_DOCUMENTOS and faltan:
                self.aviso_docs.value = "Falta cargar: " + ", ".join(faltan)
                self.aviso_docs.visible = True
                paso_valido = False
            else:
                self.aviso_docs.visible = False
        return bool(paso_valido)

    # ------------------------------------------------------------------
    # Navegación entre pasos
    # ------------------------------------------------------------------
    async def _scroll_arriba(self):
        try:
            await self.cuerpo.scroll_to(offset=0, duration=0)
        except Exception:
            # Al cambiar de paso, el control puede no estar montado todavía; el scroll no afecta la captura.
            pass

    async def _enfocar_primer_campo(self):
        primer_campo = self._primer_campo_por_paso.get(self.paso)
        if primer_campo is not None:
            await primer_campo.focus()

    def siguiente(self, e=None):
        if self.paso < 3 and not self.validar_paso(self.paso):
            self.page.update()
            return
        if self.paso == 3:
            self.finalizar()
            return
        self.paso += 1
        self._pintar()
        self.page.run_task(self._enfocar_primer_campo)
        self.page.run_task(self._scroll_arriba)

    def atras(self, e=None):
        if self.paso > 0:
            self.paso -= 1
            self._pintar()
            self.page.run_task(self._enfocar_primer_campo)
            self.page.run_task(self._scroll_arriba)

    def hay_datos(self) -> bool:
        campos = [self.ficha, self.nombre, self.ap_paterno, self.ap_materno, self.curp, self.rfc,
                  self.nss, self.ine, self.celular, self.correo, self.domicilio, self.prepa,
                  self.promedio, self.cel_emerg, self.correo_emerg, self.alergias]
        return (any(self._texto_campo(campo) for campo in campos) or self.fecha is not None
                or self.tipo_sangre.value is not None
                or self.genero.value is not None or bool(self.archivos))

    def cancelar(self, e=None):
        if not self.hay_datos():
            self.al_cancelar()
            return

        def si(_):
            self.page.pop_dialog()
            self.al_cancelar()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Cancelar la captura?"),
            content=ft.Text("Se perderán los datos capturados."),
            actions=[ft.TextButton("Sí, cancelar", on_click=si),
                     ft.TextButton("Seguir capturando", on_click=lambda _: self.page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def finalizar(self):
        # Valida otra vez por si los datos cambiaron después de avanzar de paso.
        for paso_a_validar in (0, 1, 2):
            if not self.validar_paso(paso_a_validar):
                self.paso = paso_a_validar
                self._pintar()
                return
        def si(_):
            self.page.pop_dialog()
            try:
                self.al_guardar(self.registro())
            except ApiError as ex:
                self._error_api(ex)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Confirmar el alta?"),
            content=ft.Text("Se registrará al alumno, se guardarán sus documentos y se generará "
                            "su número de control. El paquete de horario se asignará después "
                            "desde Consultas."),
            actions=[ft.TextButton("Sí", on_click=si),
                     ft.TextButton("No", on_click=lambda _: self.page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _error_api(self, ex: ApiError):
        """Muestra el error del servidor; si trae errores por campo, los marca en el
        formulario y regresa al primer paso afectado."""
        campos = {
            "ficha": (self.ficha, 0), "nombre": (self.nombre, 0), "ap_paterno": (self.ap_paterno, 0),
            "ap_materno": (self.ap_materno, 0), "fecha_nacimiento": (self.txt_fecha, 0),
            "curp": (self.curp, 0), "rfc": (self.rfc, 0), "nss": (self.nss, 0), "ine": (self.ine, 0),
            "celular": (self.celular, 0), "correo": (self.correo, 0), "domicilio": (self.domicilio, 0),
            "preparatoria": (self.prepa, 1), "promedio": (self.promedio, 1),
            "celular_emergencia": (self.cel_emerg, 1),
            "correo_emergencia": (self.correo_emerg, 1), "alergias": (self.alergias, 1),
        }
        pasos_con_error = []
        for campo, mensaje_error in ex.errores.items():
            if campo in campos:
                control, paso = campos[campo]
                control.error = mensaje_error
                pasos_con_error.append(paso)
            elif campo == "genero":
                self.genero.error_text = mensaje_error
                pasos_con_error.append(0)
            elif campo == "tipo_sangre":
                self.tipo_sangre.error_text = mensaje_error
                pasos_con_error.append(1)
            elif campo == "documentos":
                self.aviso_docs.value = mensaje_error
                self.aviso_docs.visible = True
                pasos_con_error.append(2)
        if pasos_con_error:
            self.paso = min(pasos_con_error)
        self._error_guardado(ex.mensaje)

    def _error_guardado(self, mensaje: str):
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("No se pudo completar el alta"),
            content=ft.Text(mensaje),
            actions=[ft.TextButton("Entendido", on_click=lambda _: self.page.pop_dialog())],
        ))
        self._pintar()

    def registro(self) -> dict:
        texto_campo = self._texto_campo
        return {
            "ficha": texto_campo(self.ficha),
            "nombre": texto_campo(self.nombre),
            "ap_paterno": texto_campo(self.ap_paterno),
            "ap_materno": texto_campo(self.ap_materno),
            "nombre_completo": f"{texto_campo(self.nombre)} {texto_campo(self.ap_paterno)} {texto_campo(self.ap_materno)}",
            "fecha_nacimiento": self.fecha,
            "curp": texto_campo(self.curp).upper(),
            "rfc": texto_campo(self.rfc).upper() or None,
            "nss": texto_campo(self.nss),
            "ine": texto_campo(self.ine).upper() or None,
            "genero": self.genero.value,
            "celular": texto_campo(self.celular),
            "correo": texto_campo(self.correo),
            "domicilio": texto_campo(self.domicilio),
            "preparatoria": texto_campo(self.prepa),
            "promedio": float(texto_campo(self.promedio).replace(",", ".")),
            "celular_emergencia": texto_campo(self.cel_emerg),
            "correo_emergencia": texto_campo(self.correo_emerg),
            "tipo_sangre": self.tipo_sangre.value,
            "alergias": texto_campo(self.alergias) or "Ninguna",
            "documentos": {
                documento: archivo["path"]
                for documento, archivo in self.archivos.items()
            },
        }

    # ------------------------------------------------------------------
    # Pintado de pasos
    # ------------------------------------------------------------------
    def _stepper(self):
        items = []
        for i, nombre in enumerate(self.PASOS):
            activo = i == self.paso
            hecho = i < self.paso
            burbuja = ft.Container(
                width=34, height=34, border_radius=17, alignment=ft.Alignment.CENTER,
                bgcolor=NAVY if (activo or hecho) else WHITE,
                border=ft.Border.all(1, NAVY if (activo or hecho) else BORDER),
                content=(ft.Icon(ft.Icons.CHECK, size=16, color=WHITE) if hecho
                         else ft.Text(str(i + 1), size=13, weight=ft.FontWeight.BOLD,
                                      color=WHITE if activo else MUTED)),
            )
            items.append(ft.Container(expand=1, content=ft.Row(spacing=12, controls=[
                burbuja,
                ft.Text(nombre, size=14, weight=ft.FontWeight.BOLD, color=NAVY if (activo or hecho) else MUTED),
            ])))
        self.stepper.controls = items

    @staticmethod
    def _crear_fila(*controles) -> ft.Row:
        return ft.Row(spacing=24, vertical_alignment=ft.CrossAxisAlignment.START, controls=list(controles))

    def _fila_documento(self, doc: str) -> ft.Control:
        archivo = self.archivos.get(doc)
        error_documento = self.errores_docs.get(doc)
        if archivo:
            estado = ft.Text(
                f"{archivo['nombre']} · {(archivo['size'] or 0) / 1024:,.0f} KB",
                size=12,
                color=OK_FG,
            )
            boton = ft.TextButton("Quitar", on_click=lambda e, d=doc: self._quitar_pdf(d))
            icono = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=OK_FG, size=20)
        else:
            estado = ft.Text(
                error_documento or "Pendiente",
                size=12,
                color=ft.Colors.RED_700 if error_documento else MUTED,
            )
            boton = ft.OutlinedButton("Seleccionar PDF", style=estilo_boton_secundario(),
                                      on_click=lambda e, d=doc: self.page.run_task(self._elegir_pdf, d))
            icono = ft.Icon(
                ft.Icons.ERROR_OUTLINE if error_documento else ft.Icons.RADIO_BUTTON_UNCHECKED,
                color=ft.Colors.RED_700 if error_documento else MUTED,
                size=20,
            )
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
            content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                icono,
                ft.Column(expand=True, spacing=2, controls=[
                    ft.Text(doc, size=14, weight=ft.FontWeight.BOLD, color=TEXT), estado]),
                boton,
            ]),
        )

    def _cuerpo_paso(self):
        crear_fila = self._crear_fila
        if self.paso == 0:
            self.titulo_card.value = "Datos personales"
            self.cuerpo.controls = [
                crear_fila(crear_campo_etiquetado("Número de ficha", self.ficha), crear_campo_etiquetado("Nombre(s)", self.nombre)),
                crear_fila(crear_campo_etiquetado("Apellido paterno", self.ap_paterno), crear_campo_etiquetado("Apellido materno", self.ap_materno)),
                crear_fila(crear_campo_etiquetado("Fecha de nacimiento", self.txt_fecha), crear_campo_etiquetado("CURP", self.curp)),
                crear_fila(crear_campo_etiquetado(self._etiqueta_rfc_ine("RFC"), self.rfc), crear_campo_etiquetado("Número de seguro social", self.nss)),
                crear_fila(crear_campo_etiquetado(self._etiqueta_rfc_ine("INE"), self.ine), crear_campo_etiquetado("Género", ft.Row([self.genero]))),
                crear_fila(crear_campo_etiquetado("Teléfono celular", self.celular), crear_campo_etiquetado("Correo personal", self.correo)),
                crear_fila(crear_campo_etiquetado("Domicilio", self.domicilio)),
            ]
        elif self.paso == 1:
            self.titulo_card.value = "Datos académicos"
            self.cuerpo.controls = [
                crear_fila(crear_campo_etiquetado("Nombre de la preparatoria", self.prepa),
                  crear_campo_etiquetado("Promedio general", self.promedio)),
                ft.Text("Contacto de emergencia y salud", size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                crear_fila(crear_campo_etiquetado("Celular de emergencia", self.cel_emerg),
                  crear_campo_etiquetado("Correo electrónico de emergencia", self.correo_emerg)),
                crear_fila(crear_campo_etiquetado("Tipo de sangre", self.tipo_sangre),
                  crear_campo_etiquetado("Alergias (opcional)", self.alergias)),
            ]
        elif self.paso == 2:
            self.titulo_card.value = "Documentos"
            self.cuerpo.controls = [
                ft.Text(f"Carga los {len(DOCUMENTOS)} documentos en formato PDF "
                        f"(máximo {v.MAX_PDF_MB} MB por archivo).", size=13, color=MUTED),
                self.aviso_docs,
                ft.Column(spacing=0, controls=[self._fila_documento(d) for d in DOCUMENTOS]),
            ]
        else:
            self.titulo_card.value = "Confirmación"
            self.cuerpo.controls = [
                ft.Text("Revisa la información antes de inscribir al alumno.", size=13, color=MUTED),
                self._resumen_final(),
            ]

    def _etiqueta_rfc_ine(self, campo: str) -> str:
        if self.fecha is None:
            return f"{campo} (obligatorio para mayores de edad)"
        requisito = "obligatorio" if v.es_mayor_de_18(self.fecha) else "opcional"
        return f"{campo} ({requisito})"

    def _resumen_final(self) -> ft.Control:
        texto_campo = self._texto_campo
        genero = v.GENEROS.get(self.genero.value, "—")
        promedio_texto = texto_campo(self.promedio)
        turno = (
            v.turno_por_promedio(float(promedio_texto.replace(",", ".")))
            if promedio_texto else "—"
        )
        pares = [
            ("Ficha", texto_campo(self.ficha)),
            ("Nombre", f"{texto_campo(self.nombre)} {texto_campo(self.ap_paterno)} {texto_campo(self.ap_materno)}"),
            ("Fecha de nacimiento", self.txt_fecha.value or "—"),
            ("CURP", texto_campo(self.curp).upper()), ("RFC", texto_campo(self.rfc).upper()),
            ("Seguro social", texto_campo(self.nss)), ("INE", texto_campo(self.ine).upper()),
            ("Género", genero),
            ("Celular", texto_campo(self.celular)), ("Correo personal", texto_campo(self.correo)),
            ("Domicilio", texto_campo(self.domicilio)),
            ("Preparatoria", texto_campo(self.prepa)), ("Promedio", promedio_texto), ("Turno", turno),
            ("Contacto de emergencia", f"{texto_campo(self.cel_emerg)} · {texto_campo(self.correo_emerg)}"),
            ("Tipo de sangre", self.tipo_sangre.value or "—"),
            ("Alergias", texto_campo(self.alergias) or "Ninguna"),
            ("Documentos PDF", f"{len(self.archivos)} de {len(DOCUMENTOS)} cargados"),
        ]
        return ft.Column(spacing=0, controls=[
            ft.Container(
                padding=ft.Padding.symmetric(vertical=9),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                    ft.Container(width=190, content=ft.Text(k, size=13, color=MUTED)),
                    ft.Container(expand=True, content=ft.Text(val, size=14, color=TEXT)),
                ]),
            ) for k, val in pares
        ])

    def _botones(self):
        ultimo = self.paso == 3
        derecha = []
        if self.paso > 0:
            derecha.append(ft.OutlinedButton("Atrás", style=estilo_boton_secundario(), on_click=self.atras))
        derecha.append(ft.FilledButton("Inscribir alumno" if ultimo else "Siguiente",
                                       style=estilo_boton_primario(), on_click=self.siguiente))
        self.botones.controls = [
            ft.OutlinedButton("Cancelar", style=estilo_boton_secundario(), on_click=self.cancelar),
            ft.Row(spacing=12, controls=derecha),
        ]

    def _pintar(self):
        self._stepper()
        self._cuerpo_paso()
        self.cuerpo.controls = [ft.Container(
            padding=ft.Padding.only(right=16),
            content=ft.Column(spacing=16, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                              controls=self.cuerpo.controls),
        )]
        self._botones()
        self._refrescar_docs()
        self._chip_estatus("Lista para confirmar" if self.paso == 3 else "En captura", ok=self.paso == 3)
        self.page.update()


def build_altas(page: ft.Page, picker, usuario: dict, navegar) -> ft.Control:
    def cancelar():
        navegar("/secretaria")

    def guardar(registro: dict):
        # El progreso visible evita que una carga larga parezca una interfaz congelada.
        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Registrando alumno"),
            content=ft.Row(tight=True, spacing=16, controls=[
                ft.ProgressRing(width=28, height=28),
                ft.Text("Guardando datos y subiendo documentos…"),
            ]),
        ))
        try:
            registro = api.registrar_alta(registro)
        finally:
            page.pop_dialog()
        navegar("/secretaria")
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Alta completada con éxito"),
            content=ft.Column(tight=True, spacing=10, controls=[
                ft.Text("Número de control generado", size=13, color=MUTED),
                ft.Text(registro["numero_control"], size=30, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(f"Alumno: {registro['nombre_completo']}", size=14),
                ft.Text(f"Correo institucional: {registro['correo_institucional']}", size=14),
                ft.Text(
                    f"Turno sugerido: {registro['turno']} · Horario pendiente de asignación"
                    if not registro.get("grupo")
                    else f"Turno: {registro['turno']} · Grupo {registro['grupo']}",
                    size=14,
                ),
                *([ft.Text(registro["aviso_turno"], size=13, color=WARN_FG)] if registro.get("aviso_turno") else []),
                ft.Text("Comunica este número de control al alumno.", size=13, color=MUTED),
            ]),
            actions=[ft.TextButton("Aceptar", on_click=lambda _: page.pop_dialog())],
        ))

    return FormAltas(page, picker, cancelar, guardar).vista


# =====================================================================
# 4. CONSULTAS — expediente del alumno
# =====================================================================
_dir_pdf: str | None = None


def _carpeta_pdf_temporal() -> Path:
    """Carpeta donde se descargan los PDF para abrirlos; se borra al cerrar la app."""
    global _dir_pdf
    if _dir_pdf is None:
        _dir_pdf = tempfile.mkdtemp(prefix="sige_pdf_")
        atexit.register(shutil.rmtree, _dir_pdf, ignore_errors=True)
    return Path(_dir_pdf)


def abrir_archivo(ruta: Path):
    """Abre el archivo con el visor predeterminado del sistema (app de escritorio)."""
    if sys.platform.startswith("win"):
        os.startfile(ruta)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(ruta)])
    else:
        subprocess.Popen(["xdg-open", str(ruta)])


def ordinal_semestre(n: int) -> str:
    return f"{n}.{'er' if n in (1, 3) else 'º'} semestre"


def chip(texto: str, ok: bool) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        border_radius=14,
        bgcolor=OK_BG if ok else WARN_BG,
        content=ft.Text(texto, size=12, weight=ft.FontWeight.BOLD, color=OK_FG if ok else WARN_FG),
    )


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
            ("ine", "Clave de elector (INE)"), ("nss", "Número de seguro social"),
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

    # --- acciones -------------------------------------------------------
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
            self.datos = api.expediente(q, self.es_admin and self.incluir_bajas)
            self.seccion = "personales"
            self.historial = []
            self.error_historial = None
            self.horario = None
            self.paquetes_horario = []
            self.error_horario = None
            if (
                self.usuario["rol"] == "Secretaría"
                and not self.modo_modificacion
                and not self.modo_bajas
            ):
                try:
                    self.horario = api.estado_horario(self.datos["numero_control"])
                    if (
                        not self.horario["asignado"]
                        or self.horario.get("puede_migrar", False)
                    ):
                        self.paquetes_horario = api.paquetes_horario(self.horario["semestre"])
                except ApiError as ex:
                    if ex.status == 401:
                        self.navegar("/consultas")
                        return
                    self.error_horario = ex.mensaje
            if self.es_admin:
                try:
                    self.historial = api.historial_alumno(self.datos["numero_control"])
                except ApiError as ex:
                    if ex.status == 401:
                        self.navegar("/consultas")
                        return
                    self.error_historial = ex.mensaje
        except ApiError as ex:
            self.datos = None
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
        numero = self.datos["numero_control"]
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
        es_migracion = self.horario["asignado"]
        detalle = (
            f"El alumno pasará de {self.horario['paquete']['nombre']} a {paquete['nombre']}. "
            "Se conservarán las calificaciones y asistencias de las materias que coincidan; "
            "si hay datos históricos en materias sin equivalente, la operación se cancelará."
            if es_migracion
            else (
                f"Se inscribirá al alumno en todas las materias de {paquete['nombre']} "
                f"para {paquete['periodo']}."
            )
        )
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Migrar al paquete seleccionado" if es_migracion else "Asignar paquete de horario"),
            content=ft.Text(
                f"{detalle} Al confirmar, el alumno quedará en un solo paquete para "
                f"{paquete['periodo']}."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Confirmar migración" if es_migracion else "Confirmar asignación",
                    style=estilo_boton_primario(),
                    on_click=lambda _: self._asignar_paquete(id_paquete),
                ),
            ],
        ))

    def _asignar_paquete(self, id_paquete: int):
        self.page.pop_dialog()
        try:
            if self.horario["asignado"]:
                self.horario = api.migrar_paquete(self.datos["numero_control"], id_paquete)
            else:
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

        if not self.horario["asignado"] or self.horario.get("puede_migrar", False):
            es_migracion = self.horario["asignado"]
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
            if es_migracion:
                mensaje = (
                    f"El alumno conserva el grupo anterior {self.horario['paquete']['nombre']}. "
                    "Elige manualmente uno de los grupos oficiales disponibles."
                )
            elif self.paquetes_horario:
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
                        "Migrar al grupo elegido" if es_migracion else "Asignar paquete",
                        style=estilo_boton_primario(),
                        disabled=not self.paquetes_horario or es_migracion and not self.horario.get("puede_migrar", False),
                        on_click=lambda _: self._confirmar_asignacion_paquete(selector),
                    ),
                ]),
                ft.Text(
                    (
                        "La migración conserva calificaciones y asistencias en materias "
                        "coincidentes y respeta los cupos."
                        if es_migracion
                        else "La asignación inscribe al alumno en todas las materias del paquete "
                        "y respeta el cupo de cada grupo."
                    ),
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
                    ft.Text("Horario y grupo", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
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

    # --- vista ----------------------------------------------------------
    def _pintar(self):
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
            "ine": crear_campo_texto(value="" if p["ine"] == "—" else p["ine"], label="INE (opcional)"),
            "genero": ft.Dropdown(
                label="Género",
                value=genero,
                options=[ft.DropdownOption(key=k, text=nombre) for k, nombre in v.GENEROS.items()],
            ),
            "celular": crear_campo_texto(value=c["celular"], label="Celular"),
            "correo": crear_campo_texto(value=c["correo_personal"], label="Correo personal"),
            "domicilio": crear_campo_texto(value=c["domicilio"], label="Domicilio"),
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
        contenido = ft.ResponsiveRow(
            spacing=12,
            run_spacing=8,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=campo)
                for campo in campos.values()
            ],
        )
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            bgcolor=WHITE,
            title=ft.Text("Modificar datos del alumno"),
            content=ft.Container(
                width=680,
                height=520,
                content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[contenido]),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Guardar cambios", style=estilo_boton_primario(),
                    on_click=lambda _: self._guardar_edicion(campos),
                ),
            ],
        ))

    def _guardar_edicion(self, campos: dict):
        datos = {clave: (campo.value or "").strip() for clave, campo in campos.items()}
        try:
            datos["fecha_nacimiento"] = datetime.date.fromisoformat(datos["fecha_nacimiento"]).isoformat()
            datos["promedio"] = float(datos["promedio"].replace(",", "."))
        except ValueError:
            snackbar(self.page, "Revisa la fecha (AAAA-MM-DD) y el promedio.")
            return
        datos["rfc"] = datos["rfc"] or None
        datos["ine"] = datos["ine"] or None

        try:
            api.actualizar_alumno(self.datos["numero_control"], datos)
        except ApiError as ex:
            if ex.status == 401:
                self.navegar("/consultas")
                return
            detalles = "; ".join(f"{campo}: {mensaje}" for campo, mensaje in ex.errores.items())
            snackbar(self.page, f"{ex.mensaje}{': ' + detalles if detalles else ''}")
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


# =====================================================================
# 5. APLICACIÓN Y RUTAS
# =====================================================================
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

    # FilePicker pertenece a la página y se reutiliza al cambiar de vista.
    selector_archivos = ft.FilePicker()
    if not any(service is selector_archivos for service in page.services):
        page.services.append(selector_archivos)

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
            api.logout()            # El cierre también se registra en la bitácora del servidor.
        except ApiError as ex:
            log.warning("No se pudo registrar el cierre de sesión: %s", ex.mensaje)
        sesion["usuario"] = None
        sesion["shell"] = None
        navegar("/")

    def cerrar_sesion_al_cerrar_app(e=None):
        try:
            api.logout()
        except ApiError as ex:
            log.warning("No se pudo registrar la salida de sesión al cerrar la aplicación: %s", ex.mensaje)

    def contenido_para(ruta: str, usuario: dict) -> ft.Control:
        if ruta == "/docente" and usuario["rol"] == "Docente":
            return build_inicio_docente(page, usuario, navegar)
        if ruta == "/altas":
            return build_altas(page, selector_archivos, usuario, navegar)
        if ruta == "/altas-maestros":
            return build_alta_maestro(page, navegar)
        if ruta == "/consulta-maestros":
            return build_consulta_maestros(page, navegar)
        if ruta == "/grupos-horarios":
            return build_grupos_horarios(page, navegar)
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
        # Un token rechazado invalida la sesión local para cerrar el acceso a rutas protegidas.
        sesion_expirada = False
        if api.sesion_vencida:
            api.sesion_vencida = False
            if sesion["usuario"] is not None:
                sesion["usuario"] = None
                sesion["shell"] = None
                sesion_expirada = True

        ruta = page.route or "/"
        usuario = sesion["usuario"]

        # La interfaz no permite navegar a contenido privado sin una sesión autenticada.
        if usuario is None:
            ruta = "/"
        elif usuario["rol"] == "Docente":
            if ruta != "/docente":
                ruta = "/docente"
        elif usuario["rol"] not in {"Administrador", "Secretaría"}:
            ruta = "/secretaria"
        elif usuario["rol"] == "Administrador" and ruta not in RUTAS_ADMIN:
            ruta = "/consultas"
        elif usuario["rol"] != "Administrador" and ruta in RUTAS_ADMIN - {"/consultas", "/modificacion"}:
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
        # Reutilizar el marco conserva la barra lateral al navegar entre rutas.
        if not page.views or page.views[0] is not shell.view:
            page.views.clear()
            page.views.append(shell.view)
        if shell.activo != ruta:               # No recrear la pantalla activa conserva su estado al repetir la navegación.
            contenido = contenido_para(ruta, usuario)
            if api.sesion_vencida:             # La carga detectó una sesión vencida; se redirige al login.
                route_change()
                return
            shell.mostrar(ruta, contenido)
        page.update()

    page.on_route_change = route_change
    page.on_close = cerrar_sesion_al_cerrar_app
    navegar("/")


if __name__ == "__main__":
    ft.run(main)