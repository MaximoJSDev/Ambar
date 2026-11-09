"""Secretary dashboard and school-period management screens."""

import datetime

import flet as ft
from api_client import ApiError

from app_state import api
from ui.components import chip_estado, crear_tarjeta, snackbar, titulo_pagina
from ui.navigation import IMPLEMENTADAS
from ui.theme import BORDER, GOLD, MUTED, NAVY, TEXT, WARN_BG, WARN_FG



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
            acceso("Reinscribir alumno", "Registra datos de segundo o tercer semestre.", "/reinscripcion", "Reinscripción"),
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
