import asyncio
import atexit
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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

# Cliente del backend FastAPI (URL en la variable de entorno SIGE_API_URL).
# El bloqueo por intentos fallidos, los cupos y los PDF ahora viven en el servidor.
api = ApiClient()


# --- Reglas de Altas (documento de contexto, Algoritmo 3) -------------------
TURNOS = ("Matutino", "Vespertino")          # un grupo por turno
DOCUMENTOS = [                               # deben coincidir con api_client.CAMPO_DOCUMENTO
    "Acta de nacimiento",
    "CURP",
    "Comprobante de domicilio",
    "INE",
    "Certificado de preparatoria",
    "Certificado médico",
]
REQUIERE_TODOS_LOS_DOCUMENTOS = True         # False: permite dejar documentos pendientes
                                             # (el servidor tiene su propia opción: REQUIERE_TODOS_LOS_DOCUMENTOS)


NAV = [
    ("/secretaria", "Inicio", ft.Icons.HOME_OUTLINED),
    ("/altas", "Altas", ft.Icons.ADD),
    ("/altas-maestros", "Alta de maestros", ft.Icons.PERSON_ADD_ALT_1),
    ("/consulta-maestros", "Consulta de maestros", ft.Icons.GROUP_OUTLINED),
    ("/consultas", "Consultas", ft.Icons.LIST_ALT),
    ("/modificacion", "Modificación", ft.Icons.EDIT_OUTLINED),
    ("/bajas", "Bajas", ft.Icons.REMOVE),
    ("/reinscripcion", "Reinscripción", ft.Icons.REPLAY),
    ("/estadisticas", "Estadísticas", ft.Icons.BAR_CHART),
]
ADMIN_NAV = [
    ("/consultas", "Historial de alumnos", ft.Icons.HISTORY),
    ("/administracion/secretarias/alta", "Alta de secretaría", ft.Icons.PERSON_ADD_ALT_1),
    ("/administracion/secretarias", "Consulta de secretarías", ft.Icons.LIST_ALT),
    ("/bitacora", "Bitácora", ft.Icons.FORMAT_LIST_BULLETED),
]
RUTAS_ADMIN = {
    "/consultas",
    "/administracion/secretarias/alta",
    "/administracion/secretarias",
    "/bitacora",
}
IMPLEMENTADAS = {
    "/secretaria", "/altas", "/altas-maestros", "/consulta-maestros", *RUTAS_ADMIN,
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


def tf(hint: str = "", **kw) -> ft.TextField:
    """TextField con el estilo del diseño (etiqueta aparte, borde suave)."""
    return ft.TextField(
        hint_text=hint,
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
        **kw,
    )


def etiqueta(texto: str, control: ft.Control) -> ft.Column:
    return ft.Column(
        spacing=6,
        expand=1,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,   # el campo ocupa todo el ancho
        controls=[ft.Text(texto, size=13, weight=ft.FontWeight.BOLD, color=TEXT), control],
    )


def tarjeta(content: ft.Control, padding=24, **kw) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=WHITE,
        border=ft.Border.all(1, BORDER),
        border_radius=10,
        padding=padding,
        **kw,
    )


def estilo_primario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor=NAVY,
        color=WHITE,
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding.symmetric(horizontal=28, vertical=18),
    )


def estilo_secundario() -> ft.ButtonStyle:
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
    correo = tf("usuario@acapulco.tecnm.mx", autofocus=True, keyboard_type=ft.KeyboardType.EMAIL)
    password = tf("Contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", color=ft.Colors.RED_700, size=13, weight=ft.FontWeight.W_600, visible=False)
    boton = ft.FilledButton(
        "Iniciar sesión",
        style=estilo_primario(),
        height=46,
    )

    def bloquear_ui(bloqueado: bool):
        password.disabled = bloqueado
        boton.disabled = bloqueado

    async def cuenta_regresiva(segundos: int):
        fin = time.monotonic() + segundos
        try:
            while True:
                s = int(fin - time.monotonic() + 0.999)
                if s <= 0:
                    break
                aviso.value = (f"Cuenta bloqueada por demasiados intentos. "
                               f"Intenta de nuevo en {s // 60}:{s % 60:02d}.")
                aviso.visible = True
                page.update()
                await asyncio.sleep(1)
            aviso.visible = False
            bloquear_ui(False)
            password.value = ""
            page.update()
        except Exception:
            # La vista pudo cerrarse mientras corría el contador
            pass

    def autenticar(e=None):
        clave = (correo.value or "").strip().lower()
        pwd = password.value or ""
        correo.error = None
        password.error = None
        aviso.visible = False

        err = v.validar_correo_login(clave)
        if err:
            correo.error = err
            page.update()
            return
        if not pwd:
            password.error = "Contraseña obligatoria"
            page.update()
            return

        boton.disabled = True           # evita doble clic mientras responde el servidor
        page.update()
        try:
            usuario = api.login(clave, pwd)
        except ApiError as ex:
            boton.disabled = False
            if ex.status == 423:        # bloqueada: el servidor indica cuántos segundos faltan
                bloquear_ui(True)
                page.update()
                page.run_task(cuenta_regresiva, int(ex.extra.get("segundos", 300)))
                return
            if ex.status == 401:        # mensaje genérico: no revela si el correo existe
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

        items = []
        if usuario["rol"] == "Administrador":
            nav = ADMIN_NAV
        elif usuario["rol"] == "Secretaría":
            nav = NAV
        else:
            nav = [("/secretaria", "Inicio", ft.Icons.HOME_OUTLINED)]
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
            items.append(cont)

        def pie(icono, texto, on_click):
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=26, vertical=10),
                ink=True,
                on_click=on_click,
                content=ft.Row(spacing=10, controls=[
                    ft.Icon(icono, size=16, color="#E1E8F3"),
                    ft.Text(texto, size=14, color="#E1E8F3"),
                ]),
            )

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

        # Zona de contenido: cada página decide si hace scroll (el panel) o si solo
        # una parte interna lo hace (el formulario de Altas).
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


def build_panel(page: ft.Page, navegar) -> ft.Control:
    def estadistica(numero, texto):
        return ft.Container(
            col={"xs": 12, "sm": 6, "lg": 3},
            content=tarjeta(ft.Column(spacing=8, controls=[
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
            content=tarjeta(ft.Row(spacing=16, controls=[
                ft.Container(width=6, height=54, bgcolor=GOLD, border_radius=3),
                ft.Column(spacing=6, tight=True, controls=[
                    ft.Text(titulo, size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                    ft.Text(descripcion, size=13, color=MUTED),
                ]),
            ]), padding=ft.Padding.symmetric(horizontal=18, vertical=18)),
        )

    # Datos reales desde la API; si falla, el panel se muestra en ceros con un aviso
    error_panel = None
    try:
        resumen = api.resumen_panel()
    except ApiError as ex:
        error_panel = ex.mensaje
        resumen = {"alumnos_nuevo_ingreso": 0, "grupos": 0, "expedientes_pendientes": 0,
                   "reinscripciones_hoy": 0, "pendientes": [], "actividad": []}
    filas_datos = [(a["alumno"], a["tramite"], a["estado"]) for a in resumen["actividad"]]

    lineas_pendientes: list[ft.Control] = []
    for p in resumen["pendientes"]:
        if lineas_pendientes:
            lineas_pendientes.append(ft.Divider(height=1, color=BORDER))
        lineas_pendientes.append(ft.Text(f"{p['cantidad']} · {p['documento']}", size=14, color=TEXT))
    if not lineas_pendientes:
        lineas_pendientes.append(ft.Text("Sin documentos pendientes", size=14, color=MUTED))

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
            celda(ft.Text("Trámite", size=13, weight=ft.FontWeight.BOLD, color=TEXT), 3),
            celda(ft.Text("Estado", size=13, weight=ft.FontWeight.BOLD, color=TEXT), 3),
        ]),
    )
    filas = [cabecera]
    for alumno, tramite, estado in filas_datos:
        filas.append(ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
            content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                celda(alumno, 4), celda(tramite, 3),
                ft.Container(expand=3, content=ft.Row([chip_estado(estado)])),
            ]),
        ))

    actividad = tarjeta(ft.Column(spacing=12, controls=[
        ft.Text("Actividad reciente", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.Column(spacing=0, controls=filas),
    ]), col={"xs": 12, "lg": 8})

    pendientes = tarjeta(ft.Column(spacing=14, controls=[
        ft.Text("Pendientes", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.Container(height=4),
        *lineas_pendientes,
        ft.Container(height=20),
        ft.OutlinedButton(
            "Revisar expedientes",
            style=estilo_secundario(),
            on_click=lambda e: navegar("/consultas"),
        ),
    ]), col={"xs": 12, "lg": 4})

    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina("Panel de Secretaría", "Gestiona alumnos, expedientes y procesos escolares."),
        *([aviso_error] if error_panel else []),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[
            estadistica(resumen["alumnos_nuevo_ingreso"], "Alumnos de nuevo ingreso"),
            estadistica(resumen["grupos"], "Grupos registrados"),
            estadistica(resumen["expedientes_pendientes"], "Expedientes pendientes"),
            estadistica(resumen["reinscripciones_hoy"], "Reinscripciones del día"),
        ]),
        ft.Text("Accesos rápidos", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[
            acceso("Inscribir alumno", "Registra un nuevo ingreso.", "/altas", "Altas"),
            acceso("Consultar expediente", "Consulta datos y documentos.", "/consultas", "Consultas"),
            acceso("Reinscribir alumno", "Asigna grupo y horario.", "/reinscripcion", "Reinscripción"),
        ]),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[actividad, pendientes]),
    ])


def build_inicio_docente(usuario: dict) -> ft.Control:
    return ft.Column(spacing=24, controls=[
        titulo_pagina(
            f"Bienvenido, {usuario['nombre']}",
            "Tu cuenta de maestro está activa.",
        ),
        tarjeta(ft.Row(spacing=16, controls=[
            ft.Icon(ft.Icons.INFO_OUTLINE, color=NAVY, size=24),
            ft.Text(
                "Las funciones para docentes todavía no están disponibles.",
                size=14,
                color=TEXT,
            ),
        ])),
    ])


def build_alta_secretaria(page: ft.Page, navegar) -> ft.Control:
    nombres = tf("Nombre(s)")
    apellidos = tf("Apellidos")
    correo = tf("correo@institucion.edu.mx", keyboard_type=ft.KeyboardType.EMAIL)
    password = tf("Contraseña (mínimo 10 caracteres)", password=True, can_reveal_password=True)
    confirmar = tf("Confirma la contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    boton = ft.FilledButton("Crear cuenta de Secretaría", style=estilo_primario())

    def crear(_):
        for campo in (nombres, apellidos, correo, password, confirmar):
            campo.error = None
        aviso.visible = False
        errores = []
        if not (nombres.value or "").strip():
            nombres.error = "Escribe el nombre"
            errores.append(True)
        if not (apellidos.value or "").strip():
            apellidos.error = "Escribe los apellidos"
            errores.append(True)
        if not (correo.value or "").strip():
            correo.error = "Escribe el correo"
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
            "Alta de secretaría",
            "Crea una cuenta de acceso para personal de Secretaría.",
        ),
        tarjeta(ft.Column(spacing=18, controls=[
            ft.ResponsiveRow(spacing=16, run_spacing=14, controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Nombre(s)", nombres)),
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Apellidos", apellidos)),
                ft.Container(col={"xs": 12}, content=etiqueta("Correo de acceso", correo)),
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Contraseña", password)),
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Confirmar contraseña", confirmar)),
            ]),
            ft.Text("La contraseña debe tener al menos 10 caracteres.", size=12, color=MUTED),
            aviso,
            ft.Row(alignment=ft.MainAxisAlignment.END, controls=[boton]),
        ])),
    ])


def build_alta_maestro(page: ft.Page, navegar) -> ft.Control:
    nombres = tf("Nombre(s)")
    apellidos = tf("Apellidos")
    correo = tf("correo@institucion.edu.mx", keyboard_type=ft.KeyboardType.EMAIL)
    password = tf("Contraseña (mínimo 10 caracteres)", password=True, can_reveal_password=True)
    confirmar = tf("Confirma la contraseña", password=True, can_reveal_password=True)
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    boton = ft.FilledButton("Crear cuenta de maestro", style=estilo_primario())

    def crear(_):
        for campo in (nombres, apellidos, correo, password, confirmar):
            campo.error = None
        aviso.visible = False
        errores = []
        if not (nombres.value or "").strip():
            nombres.error = "Escribe el nombre"
            errores.append(True)
        if not (apellidos.value or "").strip():
            apellidos.error = "Escribe los apellidos"
            errores.append(True)
        if not (correo.value or "").strip():
            correo.error = "Escribe el correo"
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
        tarjeta(ft.Column(spacing=18, controls=[
            ft.ResponsiveRow(spacing=16, run_spacing=14, controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Nombre(s)", nombres)),
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Apellidos", apellidos)),
                ft.Container(col={"xs": 12}, content=etiqueta("Correo de acceso", correo)),
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Contraseña", password)),
                ft.Container(col={"xs": 12, "md": 6}, content=etiqueta("Confirmar contraseña", confirmar)),
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
                filas.controls = [ft.Text("Aún no hay cuentas de Secretaría.", size=14, color=MUTED)]
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
                style=estilo_secundario(),
                on_click=lambda _, r=registro: dar_baja(r),
            ))
        return tarjeta(ft.Row(
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controles,
        ), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

    cargar()
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina(
            "Consulta de secretarías",
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
                style=estilo_secundario(),
                on_click=lambda _, r=registro: dar_baja(r),
            ))
        return tarjeta(ft.Row(
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
                    tarjeta(ft.ResponsiveRow(spacing=12, run_spacing=8, controls=[
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
        # documento -> {"nombre", "path", "size"}
        self.archivos: dict[str, dict] = {}
        self.errores_docs: dict[str, str] = {}

        letras = ft.InputFilter(regex_string=r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ '\-]*$", allow=True,
                                replacement_string="", unicode=True)
        alfanum = ft.InputFilter(regex_string=r"^[A-Za-z0-9&Ññ]*$", allow=True, replacement_string="")
        mayus = ft.TextCapitalization.CHARACTERS
        palabras = ft.TextCapitalization.WORDS

        # ---- Paso 1
        self.ficha = tf("Ej. 2026-00123", autofocus=True,
                        input_filter=ft.InputFilter(regex_string=r"^[0-9\-]*$", allow=True, replacement_string=""))
        self.nombre = tf("Ingresa el nombre o nombres", input_filter=letras, capitalization=palabras)
        self.ap_paterno = tf("Ingresa el apellido paterno", input_filter=letras, capitalization=palabras)
        self.ap_materno = tf("Ingresa el apellido materno", input_filter=letras, capitalization=palabras)
        self.date_picker = ft.DatePicker(
            first_date=datetime.datetime.combine(v.hace_anios(v.EDAD_MAXIMA), datetime.time()),
            last_date=datetime.datetime.combine(v.hace_anios(v.EDAD_MINIMA), datetime.time()),
            current_date=datetime.datetime.combine(v.hace_anios(18), datetime.time()),
            help_text="Fecha de nacimiento",
            on_change=self._fecha_elegida,
        )
        self.txt_fecha = tf("DD / MM / AAAA", read_only=True, suffix_icon=ft.Icons.CALENDAR_TODAY_OUTLINED)
        self.txt_fecha.on_click = lambda e: self.page.show_dialog(self.date_picker)
        self.curp = tf("Ingresa la CURP", input_filter=alfanum, capitalization=mayus)
        self.rfc = tf("Ingresa el RFC", input_filter=alfanum, capitalization=mayus)
        self.nss = tf("Ingresa el número de seguro social", keyboard_type=ft.KeyboardType.NUMBER,
                      input_filter=ft.NumbersOnlyInputFilter())
        self.ine = tf("Clave de elector (18 caracteres)", input_filter=alfanum, capitalization=mayus)
        self.genero = ft.Dropdown(
            hint_text="Selecciona",
            text_size=13,
            border_radius=6,
            border_color=BORDER,
            expand=True,    # junto con ft.Row([...]) hace que ocupe todo el ancho de su columna
            options=[ft.DropdownOption(key=k, text=t) for k, t in v.GENEROS.items()],
            on_select=self._genero_elegido,
        )
        self.celular = tf("Número de 10 dígitos", keyboard_type=ft.KeyboardType.PHONE,
                          input_filter=ft.NumbersOnlyInputFilter())
        self.correo = tf("Correo electrónico del alumno", keyboard_type=ft.KeyboardType.EMAIL)
        self.domicilio = tf("Calle, número, colonia, ciudad y estado")

        # ---- Paso 2
        self.prepa = tf("Nombre de la preparatoria")
        self.promedio = tf("Ej. 9.5", keyboard_type=ft.KeyboardType.NUMBER,
                           input_filter=ft.InputFilter(regex_string=r"^[0-9.,]*$", allow=True, replacement_string=""))
        self.promedio.on_change = self._promedio_cambiado
        self.cel_emerg = tf("Número de 10 dígitos", keyboard_type=ft.KeyboardType.PHONE,
                            input_filter=ft.NumbersOnlyInputFilter())
        self.correo_emerg = tf("Correo del contacto de emergencia", keyboard_type=ft.KeyboardType.EMAIL)
        self.alergias = tf("Escribe las alergias o deja vacío si no tiene")

        # ---- Contenedores dinámicos
        self.stepper = ft.Row(spacing=0)
        self.titulo_card = ft.Text("", size=21, weight=ft.FontWeight.BOLD, color=NAVY)
        # Solo esta columna hace scroll; título, stepper, botones y resumen quedan fijos
        self.cuerpo = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=0,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.botones = ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        self.res_estatus = ft.Container()
        self.res_turno = ft.Text("Se asigna según el promedio", size=14, color=TEXT)
        self.res_expediente = ft.Text(f"0 de {len(DOCUMENTOS)} documentos", size=14, color=TEXT)
        self.res_cupo = ft.Text("", size=14, color=TEXT)
        self.aviso_docs = ft.Text("", size=13, color=ft.Colors.RED_700, visible=False)
        self._refrescar_cupo()

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
        return tarjeta(ft.Column(spacing=18, controls=[
            ft.Text("Resumen del registro", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Column(spacing=3, controls=[ft.Text("Estatus", size=13, color=MUTED), self.res_estatus]),
            dato("Número de control", "Se genera al finalizar"),
            dato("Turno", self.res_turno),
            dato("Cupo disponible (primer semestre)", self.res_cupo),
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

    def _refrescar_cupo(self) -> dict | None:
        """Consulta los lugares al servidor y actualiza el resumen lateral."""
        try:
            cupo = api.cupo()
        except ApiError:
            self.res_cupo.value = "No disponible"
            return None
        self.res_cupo.value = " · ".join(f"{t} {cupo['turnos'].get(t, 0)}" for t in TURNOS)
        return cupo

    def _refrescar_docs(self):
        n = len(self.archivos)
        self.res_expediente.value = f"{n} de {len(DOCUMENTOS)} documentos"

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
        self.page.update()

    def _genero_elegido(self, e):
        self.genero.error_text = None
        self.page.update()

    def _promedio_cambiado(self, e):
        self.promedio.error = None
        valor = self._txt(self.promedio)
        if valor and v.validar_promedio(valor) is None:
            turno = v.turno_por_promedio(float(valor.replace(",", ".")))
            self.res_turno.value = f"{turno} (promedio {'≥' if turno == 'Matutino' else '<'} {v.TURNO_MATUTINO_MIN})"
        else:
            self.res_turno.value = "Se asigna según el promedio"
        self.page.update()

    async def _elegir_pdf(self, doc: str):
        """Abre el selector de archivos para un documento (solo PDF)."""
        try:
            res = await self.picker.pick_files(
                dialog_title=f"Selecciona: {doc}",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                allow_multiple=False,
            )
        except Exception as ex:  # selector no disponible en la plataforma
            self.errores_docs[doc] = f"No se pudo abrir el selector de archivos ({ex})"
            self._pintar()
            return
        if not res:
            return
        f = res[0]
        err = v.validar_pdf(f.name or "", f.size, f.path)
        if err:
            self.archivos.pop(doc, None)
            self.errores_docs[doc] = err
        else:
            self.errores_docs.pop(doc, None)
            self.archivos[doc] = {"nombre": f.name, "path": f.path, "size": f.size}
        self._pintar()

    def _quitar_pdf(self, doc: str):
        self.archivos.pop(doc, None)
        self.errores_docs.pop(doc, None)
        self._pintar()

    # ------------------------------------------------------------------
    # Validación
    # ------------------------------------------------------------------
    @staticmethod
    def _txt(c) -> str:
        return (c.value or "").strip()

    def _requerido(self, campo: ft.TextField, validador=None, **kw) -> bool:
        valor = self._txt(campo)
        campo.error = None
        if not valor:
            campo.error = "Campo obligatorio"
            return False
        err = validador(valor, **kw) if validador else None
        if err:
            campo.error = err
            return False
        return True

    def _no_duplicado(self) -> bool:
        """Pregunta al servidor si la ficha o la CURP ya están registradas."""
        try:
            dup = api.verificar(self._txt(self.ficha), self._txt(self.curp).upper())
        except ApiError:
            return True     # sin respuesta no se bloquea: el servidor vuelve a validar al guardar
        ok = True
        if dup.get("ficha"):
            self.ficha.error = "Esta ficha ya está registrada"
            ok = False
        if dup.get("curp"):
            self.curp.error = "Esta CURP ya está registrada"
            ok = False
        return ok

    def validar_paso(self, paso: int) -> bool:
        ok = True
        if paso == 0:
            ok &= self._requerido(self.ficha, v.validar_ficha)
            ok &= self._requerido(self.nombre, v.validar_nombre)
            ok &= self._requerido(self.ap_paterno, v.validar_apellido)
            ok &= self._requerido(self.ap_materno, v.validar_apellido)

            self.txt_fecha.error = v.validar_fecha_nacimiento(self.fecha)
            fecha_ok = self.txt_fecha.error is None
            ok &= fecha_ok
            ref = self.fecha if fecha_ok else None

            ok &= self._requerido(self.curp, v.validar_curp, fecha=ref)
            self.rfc.error = v.validar_rfc(self._txt(self.rfc), fecha=ref)
            ok &= self.rfc.error is None
            ok &= self._requerido(self.nss, v.validar_nss)
            self.ine.error = v.validar_ine(self._txt(self.ine), fecha=ref)
            ok &= self.ine.error is None
            self.genero.error_text = v.validar_genero(self.genero.value)
            ok &= self.genero.error_text is None
            ok &= self._requerido(self.celular, v.validar_celular)
            ok &= self._requerido(self.correo, v.validar_correo)
            ok &= self._requerido(self.domicilio, v.validar_domicilio)
            if self.ficha.error is None and self.curp.error is None:
                ok &= self._no_duplicado()
        elif paso == 1:
            ok &= self._requerido(self.prepa, v.validar_preparatoria)
            ok &= self._requerido(self.promedio, v.validar_promedio)
            ok &= self._requerido(self.cel_emerg, v.validar_celular_emergencia,
                                  celular_alumno=self._txt(self.celular))
            ok &= self._requerido(self.correo_emerg, v.validar_correo_emergencia,
                                  correo_alumno=self._txt(self.correo))
            self.alergias.error = v.validar_alergias(self._txt(self.alergias))
            ok &= self.alergias.error is None
        elif paso == 2:
            faltan = [d for d in DOCUMENTOS if d not in self.archivos]
            if REQUIERE_TODOS_LOS_DOCUMENTOS and faltan:
                self.aviso_docs.value = "Falta cargar: " + ", ".join(faltan)
                self.aviso_docs.visible = True
                ok = False
            else:
                self.aviso_docs.visible = False
        return bool(ok)

    # ------------------------------------------------------------------
    # Navegación entre pasos
    # ------------------------------------------------------------------
    def _sin_cupo(self) -> bool:
        cupo = self._refrescar_cupo()
        if cupo is None or cupo["total"] > 0:   # sin respuesta no se bloquea: el servidor valida al guardar
            return False
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Cupo completo"),
            content=ft.Text("Los dos grupos de primer semestre ya tienen 25 alumnos. "
                            "No es posible inscribir más alumnos de nuevo ingreso."),
            actions=[ft.TextButton("Entendido", on_click=lambda _: self.page.pop_dialog())],
        ))
        return True

    async def _scroll_arriba(self):
        try:
            await self.cuerpo.scroll_to(offset=0, duration=0)
        except Exception:
            pass  # aún no montado o sin scroll: no es crítico

    def siguiente(self, e=None):
        if self.paso == 0 and self._sin_cupo():
            return
        if self.paso < 3 and not self.validar_paso(self.paso):
            self.page.update()
            return
        if self.paso == 3:
            self.finalizar()
            return
        self.paso += 1
        self._pintar()
        self.page.run_task(self._scroll_arriba)

    def atras(self, e=None):
        if self.paso > 0:
            self.paso -= 1
            self._pintar()
            self.page.run_task(self._scroll_arriba)

    def hay_datos(self) -> bool:
        campos = [self.ficha, self.nombre, self.ap_paterno, self.ap_materno, self.curp, self.rfc,
                  self.nss, self.ine, self.celular, self.correo, self.domicilio, self.prepa,
                  self.promedio, self.cel_emerg, self.correo_emerg, self.alergias]
        return (any(self._txt(c) for c in campos) or self.fecha is not None
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
        # Revalida todo por si se modificó algo
        for p in (0, 1, 2):
            if not self.validar_paso(p):
                self.paso = p
                self._pintar()
                return
        if self._sin_cupo():
            return

        def si(_):
            self.page.pop_dialog()
            try:
                self.al_guardar(self.registro())
            except ApiError as ex:
                self._error_api(ex)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Confirmar la inscripción?"),
            content=ft.Text("Se registrará al alumno, se guardarán sus documentos y se generará "
                            "su número de control."),
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
        pasos = []
        for campo, msg in ex.errores.items():
            if campo in campos:
                control, paso = campos[campo]
                control.error = msg
                pasos.append(paso)
            elif campo == "genero":
                self.genero.error_text = msg
                pasos.append(0)
            elif campo == "documentos":
                self.aviso_docs.value = msg
                self.aviso_docs.visible = True
                pasos.append(2)
        if pasos:
            self.paso = min(pasos)
        self._error_guardado(ex.mensaje)

    def _error_guardado(self, mensaje: str):
        self._refrescar_cupo()
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("No se pudo completar el alta"),
            content=ft.Text(mensaje),
            actions=[ft.TextButton("Entendido", on_click=lambda _: self.page.pop_dialog())],
        ))
        self._pintar()

    def registro(self) -> dict:
        t = self._txt
        return {
            "ficha": t(self.ficha),
            "nombre": t(self.nombre),
            "ap_paterno": t(self.ap_paterno),
            "ap_materno": t(self.ap_materno),
            "nombre_completo": f"{t(self.nombre)} {t(self.ap_paterno)} {t(self.ap_materno)}",
            "fecha_nacimiento": self.fecha,
            "curp": t(self.curp).upper(),
            "rfc": t(self.rfc).upper() or None,
            "nss": t(self.nss),
            "ine": t(self.ine).upper() or None,
            "genero": self.genero.value,
            "celular": t(self.celular),
            "correo": t(self.correo),
            "domicilio": t(self.domicilio),
            "preparatoria": t(self.prepa),
            "promedio": float(t(self.promedio).replace(",", ".")),
            "celular_emergencia": t(self.cel_emerg),
            "correo_emergencia": t(self.correo_emerg),
            "alergias": t(self.alergias) or "Ninguna",
            "documentos": {d: a["path"] for d, a in self.archivos.items()},
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
    def _fila(*cols) -> ft.Row:
        return ft.Row(spacing=24, vertical_alignment=ft.CrossAxisAlignment.START, controls=list(cols))

    def _fila_documento(self, doc: str) -> ft.Control:
        a = self.archivos.get(doc)
        err = self.errores_docs.get(doc)
        if a:
            estado = ft.Text(f"{a['nombre']} · {(a['size'] or 0) / 1024:,.0f} KB", size=12, color=OK_FG)
            boton = ft.TextButton("Quitar", on_click=lambda e, d=doc: self._quitar_pdf(d))
            icono = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=OK_FG, size=20)
        else:
            estado = ft.Text(err or "Pendiente", size=12, color=ft.Colors.RED_700 if err else MUTED)
            boton = ft.OutlinedButton("Seleccionar PDF", style=estilo_secundario(),
                                      on_click=lambda e, d=doc: self.page.run_task(self._elegir_pdf, d))
            icono = ft.Icon(ft.Icons.ERROR_OUTLINE if err else ft.Icons.RADIO_BUTTON_UNCHECKED,
                            color=ft.Colors.RED_700 if err else MUTED, size=20)
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
        f = self._fila
        if self.paso == 0:
            self.titulo_card.value = "Datos personales"
            self.cuerpo.controls = [
                f(etiqueta("Número de ficha", self.ficha), etiqueta("Nombre(s)", self.nombre)),
                f(etiqueta("Apellido paterno", self.ap_paterno), etiqueta("Apellido materno", self.ap_materno)),
                f(etiqueta("Fecha de nacimiento", self.txt_fecha), etiqueta("CURP", self.curp)),
                f(etiqueta("RFC (opcional)", self.rfc), etiqueta("Número de seguro social", self.nss)),
                f(etiqueta("INE (opcional)", self.ine), etiqueta("Género", ft.Row([self.genero]))),
                f(etiqueta("Teléfono celular", self.celular), etiqueta("Correo personal", self.correo)),
                f(etiqueta("Domicilio", self.domicilio)),
            ]
        elif self.paso == 1:
            self.titulo_card.value = "Datos académicos"
            self.cuerpo.controls = [
                f(etiqueta("Nombre de la preparatoria", self.prepa),
                  etiqueta("Promedio general (1 a 10)", self.promedio)),
                ft.Text("Contacto de emergencia y salud", size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                f(etiqueta("Celular de emergencia", self.cel_emerg),
                  etiqueta("Correo electrónico de emergencia", self.correo_emerg)),
                f(etiqueta("Alergias (opcional)", self.alergias)),
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

    def _resumen_final(self) -> ft.Control:
        t = self._txt
        genero = v.GENEROS.get(self.genero.value, "—")
        prom = t(self.promedio)
        turno = v.turno_por_promedio(float(prom.replace(",", "."))) if prom else "—"
        pares = [
            ("Ficha", t(self.ficha)),
            ("Nombre", f"{t(self.nombre)} {t(self.ap_paterno)} {t(self.ap_materno)}"),
            ("Fecha de nacimiento", self.txt_fecha.value or "—"),
            ("CURP", t(self.curp).upper()), ("RFC", t(self.rfc).upper()),
            ("Seguro social", t(self.nss)), ("INE", t(self.ine).upper()), ("Género", genero),
            ("Celular", t(self.celular)), ("Correo personal", t(self.correo)),
            ("Domicilio", t(self.domicilio)),
            ("Preparatoria", t(self.prepa)), ("Promedio", prom), ("Turno", turno),
            ("Contacto de emergencia", f"{t(self.cel_emerg)} · {t(self.correo_emerg)}"),
            ("Alergias", t(self.alergias) or "Ninguna"),
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
            derecha.append(ft.OutlinedButton("Atrás", style=estilo_secundario(), on_click=self.atras))
        derecha.append(ft.FilledButton("Inscribir alumno" if ultimo else "Siguiente",
                                       style=estilo_primario(), on_click=self.siguiente))
        self.botones.controls = [
            ft.OutlinedButton("Cancelar", style=estilo_secundario(), on_click=self.cancelar),
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
        # La subida de los PDF puede tardar: diálogo modal con progreso mientras responde la API
        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Registrando alumno"),
            content=ft.Row(tight=True, spacing=16, controls=[
                ft.ProgressRing(width=28, height=28),
                ft.Text("Guardando datos y subiendo documentos…"),
            ]),
        ))
        try:
            registro = api.registrar_alta(registro)     # puede lanzar ApiError
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
                ft.Text(f"Turno: {registro['turno']} · Grupo {registro['grupo']}", size=14),
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

    def __init__(self, page: ft.Page, picker: ft.FilePicker, usuario: dict, navegar):
        self.page = page
        self.picker = picker
        self.usuario = usuario
        self.es_admin = usuario["rol"] == "Administrador"
        self.navegar = navegar
        self.datos: dict | None = None
        self.incluir_bajas = False
        self.historial: list[dict] = []
        self.error_historial: str | None = None
        self.seccion = "personales"
        self.boton_descargar = ft.OutlinedButton(
            "Descargar expediente PDF",
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            style=estilo_secundario(),
            on_click=lambda e: self.page.run_task(self.descargar_pdf),
        )

        self.entrada = tf("Número de control o CURP", on_submit=self.buscar,
                          capitalization=ft.TextCapitalization.CHARACTERS)
        self.boton = ft.FilledButton("Buscar", style=estilo_primario(), height=46, on_click=self.buscar)
        self.filtro_bajas = ft.Checkbox(
            label="Incluir alumnos dados de baja",
            value=False,
            on_change=self._cambiar_filtro_bajas,
        )
        self.aviso = ft.Text("", color=ft.Colors.RED_700, size=13, weight=ft.FontWeight.W_600, visible=False)
        self.resultado = ft.Column(spacing=20)
        self._pintar()

        buscador = tarjeta(ft.Column(spacing=8, controls=[
            ft.Row(vertical_alignment=ft.CrossAxisAlignment.END, spacing=16, controls=[
                etiqueta("Número de control o CURP", self.entrada),
                self.boton,
            ]),
            *([self.filtro_bajas] if self.es_admin else []),
            self.aviso,
        ]), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

        self.vista = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
            titulo_pagina(
                "Historial administrativo" if self.es_admin else "Expediente del alumno",
                "Consulta expedientes, bajas y versiones anteriores."
                if self.es_admin else "Consulta la información académica y los documentos del estudiante.",
            ),
            buscador,
            self.resultado,
        ])

    # --- acciones -------------------------------------------------------
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
            if ex.status == 401:            # sesión vencida: route_change regresa al login
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

    # --- vista ----------------------------------------------------------
    def _pintar(self):
        if self.datos is None:
            self.resultado.controls = [tarjeta(
                ft.Text("Busca un alumno por número de control o CURP para ver su expediente.",
                        size=14, color=MUTED))]
            return
        self.resultado.controls = [
            self._encabezado(),
            self._pestanas(),
            *([self._panel_historial()] if self.es_admin else []),
        ]

    def _encabezado(self) -> ft.Control:
        d = self.datos
        p = d["personales"]
        iniciales = (p["nombres"][:1] + p["apellido_paterno"][:1]).upper()
        activo = d["estatus"] == "Activo"
        return tarjeta(ft.Row(spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
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
                *([] if d["eliminado"] else [
                    ft.Row(spacing=8, controls=[
                        ft.OutlinedButton(
                            "Modificar datos", style=estilo_secundario(),
                            on_click=self._editar_alumno,
                        ),
                        ft.OutlinedButton(
                            "Dar de baja", style=estilo_secundario(),
                            on_click=self._confirmar_baja,
                        ),
                    ]),
                ]),
            ]),
        ]), padding=ft.Padding.symmetric(horizontal=20, vertical=16))

    def _editar_alumno(self, e=None):
        d = self.datos
        p, c, a = d["personales"], d["contacto"], d["academicos"]
        genero = next((key for key, valor in v.GENEROS.items() if valor == p["genero"]), "no_especifica")
        campos = {
            "ficha": tf(value=a["numero_ficha"], label="Número de ficha"),
            "nombre": tf(value=p["nombres"], label="Nombre(s)"),
            "ap_paterno": tf(value=p["apellido_paterno"], label="Apellido paterno"),
            "ap_materno": tf(value=p["apellido_materno"], label="Apellido materno"),
            "fecha_nacimiento": tf(
                value=datetime.datetime.strptime(p["fecha_nacimiento"], "%d/%m/%Y").date().isoformat(),
                label="Fecha de nacimiento (AAAA-MM-DD)",
            ),
            "curp": tf(value=p["curp"], label="CURP"),
            "rfc": tf(value="" if p["rfc"] == "—" else p["rfc"], label="RFC (opcional)"),
            "nss": tf(value=p["nss"], label="Número de seguro social"),
            "ine": tf(value="" if p["ine"] == "—" else p["ine"], label="INE (opcional)"),
            "genero": ft.Dropdown(
                label="Género",
                value=genero,
                options=[ft.DropdownOption(key=k, text=nombre) for k, nombre in v.GENEROS.items()],
            ),
            "celular": tf(value=c["celular"], label="Celular"),
            "correo": tf(value=c["correo_personal"], label="Correo personal"),
            "domicilio": tf(value=c["domicilio"], label="Domicilio"),
            "preparatoria": tf(value=a["preparatoria"], label="Preparatoria"),
            "promedio": tf(value=a["promedio"], label="Promedio"),
            "celular_emergencia": tf(value=c["celular_emergencia"], label="Celular de emergencia"),
            "correo_emergencia": tf(value=c["correo_emergencia"], label="Correo de emergencia"),
            "alergias": tf(value=c["alergias"], label="Alergias"),
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
            title=ft.Text("Modificar datos del alumno"),
            content=ft.Container(
                width=680,
                height=520,
                content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[contenido]),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(
                    "Guardar cambios", style=estilo_primario(),
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
                    "Confirmar baja", style=estilo_primario(),
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
            return tarjeta(ft.Text(
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
        return tarjeta(ft.Column(spacing=12, controls=[
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
            accion = (ft.TextButton("Ver PDF", style=ft.ButtonStyle(color=NAVY),
                                    on_click=lambda e, d=doc: self.ver_pdf(d))
                      if recibido else ft.Text("—", size=16, weight=ft.FontWeight.BOLD, color=TEXT))
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


def build_consultas(page: ft.Page, picker: ft.FilePicker, usuario: dict, navegar) -> ft.Control:
    return ConsultaExpediente(page, picker, usuario, navegar).vista


# =====================================================================
# 5. APLICACIÓN Y RUTAS
# =====================================================================
def main(page: ft.Page):
    page.title = "SIGE - Sistema Integral de Gestión Escolar"
    page.padding = 0
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=NAVY)

    sesion: dict = {"usuario": None, "shell": None}

    # Montar el servicio en la página y conservarlo al reemplazar las vistas.
    selector_archivos = ft.FilePicker()
    if not any(service is selector_archivos for service in page.services):
        page.services.append(selector_archivos)

    def navegar(ruta: str):
        page.route = ruta
        route_change()

    def entrar(usuario: dict):
        sesion["usuario"] = usuario
        navegar("/consultas" if usuario["rol"] == "Administrador" else "/secretaria")

    def cerrar_sesion():
        try:
            api.logout()            # registra la hora de salida en la bitácora
        except ApiError:
            pass
        sesion["usuario"] = None
        sesion["shell"] = None
        navegar("/")

    def contenido_para(ruta: str, usuario: dict) -> ft.Control:
        if ruta == "/secretaria" and usuario["rol"] == "Docente":
            return build_inicio_docente(usuario)
        if ruta == "/altas":
            return build_altas(page, selector_archivos, usuario, navegar)
        if ruta == "/altas-maestros":
            return build_alta_maestro(page, navegar)
        if ruta == "/consulta-maestros":
            return build_consulta_maestros(page, navegar)
        if ruta == "/consultas":
            return build_consultas(page, selector_archivos, usuario, navegar)
        if ruta == "/administracion/secretarias/alta":
            return build_alta_secretaria(page, navegar)
        if ruta == "/administracion/secretarias":
            return build_consulta_secretarias(page, navegar)
        if ruta == "/bitacora":
            return build_bitacora_admin(page, navegar)
        return build_panel(page, navegar)

    def route_change(e=None):
        # Si el servidor rechazó el token (venció o la cuenta se desactivó), volver al login
        expirada = False
        if api.sesion_vencida:
            api.sesion_vencida = False
            if sesion["usuario"] is not None:
                sesion["usuario"] = None
                sesion["shell"] = None
                expirada = True

        ruta = page.route or "/"
        usuario = sesion["usuario"]

        # Rutas protegidas: sin sesión siempre se vuelve al login
        if usuario is None:
            ruta = "/"
        elif usuario["rol"] not in {"Administrador", "Secretaría"}:
            ruta = "/secretaria"
        elif usuario["rol"] == "Administrador" and ruta not in RUTAS_ADMIN:
            ruta = "/consultas"
        elif usuario["rol"] != "Administrador" and ruta in RUTAS_ADMIN - {"/consultas"}:
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
            if expirada:
                snackbar(page, "Tu sesión expiró. Inicia sesión de nuevo.")
            return

        shell: Shell | None = sesion["shell"]
        if shell is None:
            shell = sesion["shell"] = Shell(page, usuario, navegar, cerrar_sesion)
        # La View del marco se agrega una sola vez; navegar solo cambia su contenido
        if not page.views or page.views[0] is not shell.view:
            page.views.clear()
            page.views.append(shell.view)
        if shell.activo != ruta:               # volver a pulsar la sección actual no reinicia nada
            contenido = contenido_para(ruta, usuario)
            if api.sesion_vencida:             # la API devolvió 401 al cargar la vista
                route_change()
                return
            shell.mostrar(ruta, contenido)
        page.update()

    page.on_route_change = route_change
    navegar("/")


if __name__ == "__main__":
    ft.run(main)