import asyncio
import datetime
from pathlib import Path

import flet as ft

import storage
import validators as v

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

# Datos de ejemplo (sustituir por base de datos)
CREDENCIALES = {
    "secretaria@ambar.edu": {"password": "admin123", "nombre": "María López", "rol": "Secretaría"},
}
guard = v.LoginGuard(max_intentos=3, segundos_bloqueo=300)


# --- Reglas de Altas (documento de contexto, Algoritmo 3) -------------------
PLANTEL = 1                                  # número de plantel: Campus Acapulco
CUPO_POR_GRUPO = 25                          # 2 grupos de 25 alumnos de primer semestre
TURNOS = ("Matutino", "Vespertino")          # un grupo por turno
DOCUMENTOS = [
    "Acta de nacimiento",
    "CURP",
    "Comprobante de domicilio",
    "INE",
    "Certificado de preparatoria",
    "Certificado médico",
]
REQUIERE_TODOS_LOS_DOCUMENTOS = True         # False: permite dejar documentos pendientes
STORAGE_DIR = Path(__file__).resolve().parent / "expedientes"


class CupoLleno(Exception):
    """No hay lugares en ningún grupo de primer semestre."""


class Datos:
    """Almacén en memoria para la demo (sustituir por base de datos)."""
    # Alumnos de nuevo ingreso ya inscritos antes de abrir la aplicación (datos de ejemplo)
    base_por_turno = {"Matutino": 20, "Vespertino": 22}
    grupos = 11            # 2 de primer semestre + 1 por cada semestre de 2.º a 10.º
    pendientes_base = 6
    reinscripciones = 12
    registros: list[dict] = []
    actividad = [
        ("Ana Sofía Morales", "Alta", "Completada"),
        ("Luis Ángel Ramírez", "Reinscripción", "Completada"),
        ("Diego Torres", "Documentos", "Pendiente"),
    ]

    @classmethod
    def ocupados(cls, turno: str) -> int:
        return cls.base_por_turno[turno] + sum(1 for r in cls.registros if r["turno"] == turno)

    @classmethod
    def lugares(cls, turno: str) -> int:
        return CUPO_POR_GRUPO - cls.ocupados(turno)

    @classmethod
    def lugares_total(cls) -> int:
        return sum(cls.lugares(t) for t in TURNOS)

    @classmethod
    def total_alumnos(cls) -> int:
        return sum(cls.ocupados(t) for t in TURNOS)

    @classmethod
    def expedientes_pendientes(cls):
        return cls.pendientes_base + sum(1 for r in cls.registros if len(r["documentos"]) < len(DOCUMENTOS))

    @classmethod
    def asignar_turno(cls, turno: str) -> tuple[str, str | None]:
        """Devuelve (turno, aviso). Si el grupo del turno está lleno, usa el otro."""
        if cls.lugares(turno) > 0:
            return turno, None
        otro = next(t for t in TURNOS if t != turno)
        if cls.lugares(otro) > 0:
            return otro, f"El grupo {turno} está lleno; el alumno quedó en el grupo {otro}."
        raise CupoLleno("Los dos grupos de primer semestre ya tienen 25 alumnos.")

    @classmethod
    def registrar(cls, registro: dict, usuario: dict, storage_dir: Path | None = None) -> dict:
        """Asigna turno, grupo, número de control y correo institucional, guarda los
        PDF y agrega el registro. Si algo falla no se guarda nada."""
        turno, aviso = cls.asignar_turno(v.turno_por_promedio(registro["promedio"]))
        hoy = datetime.date.today()
        prefijo = v.prefijo_control(hoy.year, PLANTEL, registro["ap_paterno"])
        consecutivo = 1 + sum(1 for r in cls.registros if r["numero_control"].startswith(prefijo))
        numero = v.generar_numero_control(hoy.year, PLANTEL, registro["ap_paterno"], consecutivo)

        rutas = storage.guardar_pdfs(numero, registro["documentos"], storage_dir or STORAGE_DIR)

        registro.update(
            numero_control=numero,
            correo_institucional=v.correo_institucional(numero),
            turno=turno,
            grupo=f"1{'A' if turno == TURNOS[0] else 'B'}",
            aviso_turno=aviso,
            plantel=PLANTEL,
            documentos=rutas,
            registrado_por=usuario["nombre"],
            fecha_registro=datetime.datetime.now(),
        )
        cls.registros.append(registro)
        return registro


NAV = [
    ("/secretaria", "Inicio", ft.Icons.HOME_OUTLINED),
    ("/altas", "Altas", ft.Icons.ADD),
    ("/consultas", "Consultas", ft.Icons.LIST_ALT),
    ("/modificacion", "Modificación", ft.Icons.EDIT_OUTLINED),
    ("/bajas", "Bajas", ft.Icons.REMOVE),
    ("/reinscripcion", "Reinscripción", ft.Icons.REPLAY),
    ("/cambio_campus", "Cambio de campus", ft.Icons.SWAP_VERT),
    ("/estadisticas", "Estadísticas", ft.Icons.BAR_CHART),
    ("/bitacora", "Bitácora", ft.Icons.FORMAT_LIST_BULLETED),
]
IMPLEMENTADAS = {"/secretaria", "/altas"}


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
        border_radius=6,
        border_color=BORDER,
        focused_border_color=NAVY,
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

    async def cuenta_regresiva(clave: str):
        try:
            while True:
                s = guard.segundos_restantes(clave)
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
        if guard.bloqueado(clave):
            bloquear_ui(True)
            page.update()
            page.run_task(cuenta_regresiva, clave)
            return
        if not pwd:
            password.error = "Contraseña obligatoria"
            page.update()
            return

        usuario = CREDENCIALES.get(clave)
        if usuario and usuario["password"] == pwd:
            guard.registrar_exito(clave)
            password.value = ""
            al_entrar(usuario)
            return

        # Mensaje genérico: no revela si el correo existe
        restantes = guard.registrar_fallo(clave)
        if restantes == 0:
            bloquear_ui(True)
            page.update()
            page.run_task(cuenta_regresiva, clave)
            return
        password.error = (f"Credenciales incorrectas. Te quedan {restantes} "
                          f"intento{'s' if restantes != 1 else ''}.")
        page.update()

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
        for destino, nombre, icono in NAV:
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

        pie_pagina = ft.Container(
            bgcolor=WHITE,
            border=ft.Border.only(top=ft.BorderSide(1, BORDER)),
            padding=ft.Padding.symmetric(horizontal=32, vertical=8),
            content=ft.Text("Propuesta académica • Datos de ejemplo", size=11, color=MUTED),
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
                          controls=[encabezado, self.host, pie_pagina]),
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

    # Actividad reciente: altas nuevas primero, luego ejemplos
    nuevas = [(r["nombre_completo"], "Alta", "Completada") for r in reversed(Datos.registros)]
    filas_datos = (nuevas + Datos.actividad)[:6]

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
        ft.Text("4 certificados de preparatoria", size=14, color=TEXT),
        ft.Divider(height=1, color=BORDER),
        ft.Text("2 certificados médicos", size=14, color=TEXT),
        ft.Container(height=20),
        ft.OutlinedButton(
            "Revisar expedientes",
            style=estilo_secundario(),
            on_click=lambda e: snackbar(page, "El módulo «Consultas» estará disponible próximamente."),
        ),
    ]), col={"xs": 12, "lg": 4})

    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24, controls=[
        titulo_pagina("Panel de Secretaría", "Gestiona alumnos, expedientes y procesos escolares."),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[
            estadistica(Datos.total_alumnos(), "Alumnos de nuevo ingreso"),
            estadistica(Datos.grupos, "Grupos registrados"),
            estadistica(Datos.expedientes_pendientes(), "Expedientes pendientes"),
            estadistica(Datos.reinscripciones, "Reinscripciones del día"),
        ]),
        ft.Text("Accesos rápidos", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[
            acceso("Inscribir alumno", "Registra un nuevo ingreso.", "/altas", "Altas"),
            acceso("Consultar expediente", "Consulta datos y documentos.", "/consultas", "Consultas"),
            acceso("Reinscribir alumno", "Asigna grupo y horario.", "/reinscripcion", "Reinscripción"),
        ]),
        ft.ResponsiveRow(spacing=20, run_spacing=20, controls=[actividad, pendientes]),
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

        letras = ft.InputFilter(regex_string=r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ '\-]", allow=True,
                                replacement_string="", unicode=True)
        alfanum = ft.InputFilter(regex_string=r"[A-Za-z0-9&Ññ]", allow=True, replacement_string="")
        mayus = ft.TextCapitalization.CHARACTERS
        palabras = ft.TextCapitalization.WORDS

        # ---- Paso 1
        self.ficha = tf("Ej. 2026-00123", autofocus=True,
                        input_filter=ft.InputFilter(regex_string=r"[0-9\-]", allow=True, replacement_string=""))
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
        self.promedio = tf("Ej. 92.5", keyboard_type=ft.KeyboardType.NUMBER,
                           input_filter=ft.InputFilter(regex_string=r"[0-9.,]", allow=True, replacement_string=""))
        self.promedio.on_change = self._promedio_cambiado
        self.contacto = tf("Nombre del contacto de emergencia", input_filter=letras, capitalization=palabras)
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

    def _refrescar_cupo(self):
        self.res_cupo.value = " · ".join(f"{t} {Datos.lugares(t)}" for t in TURNOS)

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

    def validar_paso(self, paso: int) -> bool:
        ok = True
        if paso == 0:
            ok &= self._requerido(self.ficha, v.validar_ficha)
            ficha = self._txt(self.ficha)
            if self.ficha.error is None and any(r["ficha"] == ficha for r in Datos.registros):
                self.ficha.error = "Esta ficha ya está registrada"
                ok = False
            ok &= self._requerido(self.nombre, v.validar_nombre)
            ok &= self._requerido(self.ap_paterno, v.validar_apellido)
            ok &= self._requerido(self.ap_materno, v.validar_apellido)

            self.txt_fecha.error = v.validar_fecha_nacimiento(self.fecha)
            fecha_ok = self.txt_fecha.error is None
            ok &= fecha_ok
            ref = self.fecha if fecha_ok else None

            ok &= self._requerido(self.curp, v.validar_curp, fecha=ref)
            curp = self._txt(self.curp).upper()
            if self.curp.error is None and any(r["curp"] == curp for r in Datos.registros):
                self.curp.error = "Esta CURP ya está registrada"
                ok = False
            ok &= self._requerido(self.rfc, v.validar_rfc, fecha=ref)
            ok &= self._requerido(self.nss, v.validar_nss)
            ok &= self._requerido(self.ine, v.validar_ine, fecha=ref)
            self.genero.error_text = v.validar_genero(self.genero.value)
            ok &= self.genero.error_text is None
            ok &= self._requerido(self.celular, v.validar_celular)
            ok &= self._requerido(self.correo, v.validar_correo)
            ok &= self._requerido(self.domicilio, v.validar_domicilio)
        elif paso == 1:
            ok &= self._requerido(self.prepa, v.validar_preparatoria)
            ok &= self._requerido(self.promedio, v.validar_promedio)
            ok &= self._requerido(self.contacto, lambda t: v.validar_nombre(t, "Contacto"))
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
        if Datos.lugares_total() > 0:
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
                  self.promedio, self.contacto, self.cel_emerg, self.correo_emerg, self.alergias]
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
            except CupoLleno as ex:
                self._error_guardado(str(ex))
            except OSError as ex:
                self._error_guardado(f"No se pudieron guardar los archivos PDF: {ex}")

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Confirmar la inscripción?"),
            content=ft.Text("Se registrará al alumno, se guardarán sus documentos y se generará "
                            "su número de control."),
            actions=[ft.TextButton("Sí", on_click=si),
                     ft.TextButton("No", on_click=lambda _: self.page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

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
            "rfc": t(self.rfc).upper(),
            "nss": t(self.nss),
            "ine": t(self.ine).upper(),
            "genero": self.genero.value,
            "celular": t(self.celular),
            "correo": t(self.correo),
            "domicilio": t(self.domicilio),
            "preparatoria": t(self.prepa),
            "promedio": float(t(self.promedio).replace(",", ".")),
            "contacto_emergencia": t(self.contacto),
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
                f(etiqueta("RFC", self.rfc), etiqueta("Número de seguro social", self.nss)),
                f(etiqueta("INE", self.ine), etiqueta("Género", ft.Row([self.genero]))),
                f(etiqueta("Teléfono celular", self.celular), etiqueta("Correo personal", self.correo)),
                f(etiqueta("Domicilio", self.domicilio)),
            ]
        elif self.paso == 1:
            self.titulo_card.value = "Datos académicos"
            self.cuerpo.controls = [
                f(etiqueta("Nombre de la preparatoria", self.prepa),
                  etiqueta("Promedio general (1 a 100)", self.promedio)),
                ft.Text("Contacto de emergencia y salud", size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                f(etiqueta("Nombre del contacto", self.contacto),
                  etiqueta("Celular de emergencia", self.cel_emerg)),
                f(etiqueta("Correo electrónico de emergencia", self.correo_emerg),
                  etiqueta("Alergias (opcional)", self.alergias)),
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
            ("Contacto de emergencia", f"{t(self.contacto)} · {t(self.cel_emerg)} · {t(self.correo_emerg)}"),
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
        registro = Datos.registrar(registro, usuario)   # puede lanzar CupoLleno / OSError
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
# 4. APLICACIÓN Y RUTAS
# =====================================================================
def main(page: ft.Page):
    page.title = "SIGE - Sistema Integral de Gestión Escolar"
    page.padding = 0
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=NAVY)

    sesion: dict = {"usuario": None, "shell": None}

    # Un solo selector de archivos para toda la aplicación (servicio de Flet)
    selector_archivos = ft.FilePicker()
    page.services.append(selector_archivos)

    def navegar(ruta: str):
        page.route = ruta
        route_change()

    def entrar(usuario: dict):
        sesion["usuario"] = usuario
        navegar("/secretaria")

    def cerrar_sesion():
        sesion["usuario"] = None
        sesion["shell"] = None
        navegar("/")

    def contenido_para(ruta: str, usuario: dict) -> ft.Control:
        if ruta == "/altas":
            return build_altas(page, selector_archivos, usuario, navegar)
        return build_panel(page, navegar)

    def route_change(e=None):
        ruta = page.route or "/"
        usuario = sesion["usuario"]

        # Rutas protegidas: sin sesión siempre se vuelve al login
        if usuario is None:
            ruta = "/"
        elif ruta not in IMPLEMENTADAS:
            ruta = "/secretaria"
        page.route = ruta

        if ruta == "/":
            sesion["shell"] = None
            page.views.clear()
            page.views.append(build_login(page, entrar))
            page.update()
            return

        shell: Shell | None = sesion["shell"]
        if shell is None:
            shell = sesion["shell"] = Shell(page, usuario, navegar, cerrar_sesion)
        # La View del marco se agrega una sola vez; navegar solo cambia su contenido
        if not page.views or page.views[0] is not shell.view:
            page.views.clear()
            page.views.append(shell.view)
        if shell.activo != ruta:               # volver a pulsar la sección actual no reinicia nada
            shell.mostrar(ruta, contenido_para(ruta, usuario))
        page.update()

    page.on_route_change = route_change
    navegar("/")


if __name__ == "__main__":
    ft.run(main)