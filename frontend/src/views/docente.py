"""Teacher grading and schedule-management screens."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import flet as ft
from api_client import ApiError

from app_state import api
from ui.components import crear_tarjeta, estilo_boton_secundario, snackbar, titulo_pagina
from ui.files import abrir_archivo, carpeta_pdf_temporal as _carpeta_pdf_temporal
from ui.theme import BORDER, MUTED, NAVY, TEXT, WARN_FG



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
        contenedores_finales: dict[str, ft.Container] = {}

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
            entrada.value = formato_calificacion(resultado["valor"])
            contenedor_final = contenedores_finales.get(alumno["numero_control"])
            if contenedor_final is not None:
                contenedor_final.content = crear_celda_final(alumno)
            snackbar(page, f"{periodo} guardada para {alumno['nombre_completo']}.")
            page.update()

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
                contenedor_final = contenedores_finales.get(alumno["numero_control"])
                if contenedor_final is not None:
                    contenedor_final.content = crear_celda_final(alumno)
                snackbar(page, "Calificación final confirmada; ya no se puede modificar.")
                page.update()

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

        def crear_celda_final(alumno):
            valor_final = alumno["final"]
            if alumno.get("final_confirmada"):
                return ft.Row(spacing=3, controls=[
                    ft.Text(formato_calificacion(valor_final), size=13, color=TEXT),
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=14, color=MUTED),
                ])
            if "Final" in disponibles:
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
                    return ft.Column(spacing=2, controls=[
                        ft.Text(f"Promedio final: {promedio:.0f}", size=11, color=MUTED),
                        ft.TextButton(
                            "Confirmar",
                            icon=ft.Icons.LOCK_OUTLINE,
                            on_click=lambda _, a=alumno, p=promedio, f=final_calculada:
                                confirmar_final(a, p, f),
                        ),
                    ])
                return ft.Text("Faltan periodos", size=11, color=MUTED)
            return ft.Text(
                formato_calificacion(valor_final),
                size=13,
                color=MUTED if valor_final is None else TEXT,
            )

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

            contenedor_final = ft.Container(
                col={"xs": 4, "md": 2},
                content=crear_celda_final(alumno),
            )
            contenedores_finales[alumno["numero_control"]] = contenedor_final
            celdas.append(contenedor_final)

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
                ft.Text(
                    "Lista de alumnos y calificaciones",
                    size=19,
                    weight=ft.FontWeight.BOLD,
                    color=NAVY,
                ),
                encabezado_calificaciones,
                ft.Column(spacing=0, controls=filas_alumnos),
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


def build_grupos_horarios(page: ft.Page, navegar) -> ft.Control:
    paquetes: list[dict] = []
    paquete_seleccionado: int | None = None
    semestre_seleccionado = 1
    panel_grupo = ft.Column(
        spacing=16,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    aviso = ft.Text("", size=13, color=WARN_FG, visible=False)
    selector_semestre = ft.Dropdown(
        label="Semestre",
        width=180,
        value=str(semestre_seleccionado),
        options=[
            ft.DropdownOption(key=str(semestre), text=f"{semestre}.º semestre")
            for semestre in range(1, 4)
        ],
    )
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

    def _materia_control(materia: dict) -> ft.Control:
        horarios = ", ".join(
            f"{fila['dia'][:3]} {fila['inicio']}-{fila['fin']}"
            for fila in materia["horarios"]
        ) or "Sin horario publicado"
        return crear_tarjeta(ft.Column(spacing=10, controls=[
            ft.Text(materia["nombre_materia"], size=15, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Text(
                f"Aula {materia['aula']} · {materia['creditos']} créditos · {horarios}",
                size=12,
                color=MUTED,
            ),
            ft.Column(spacing=3, controls=[
                ft.Text("Maestro asignado", size=11, color=MUTED),
                ft.Text(
                    materia["docente"],
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=NAVY,
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

    def cambiar_semestre(e):
        nonlocal semestre_seleccionado, paquete_seleccionado
        semestre_seleccionado = int(e.control.value)
        paquete_seleccionado = None
        cargar()

    def cargar(_=None):
        nonlocal paquetes, paquete_seleccionado
        aviso.visible = False
        try:
            paquetes_por_turno = {}
            for paquete in api.paquetes_horario(semestre_seleccionado):
                turno = paquete["turno"]
                if turno in ("Matutino", "Vespertino"):
                    paquetes_por_turno.setdefault(turno, paquete)
            paquetes = [
                paquetes_por_turno[turno]
                for turno in ("Matutino", "Vespertino")
                if turno in paquetes_por_turno
            ]
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
                f"No hay horarios configurados para el {semestre_seleccionado}.º semestre "
                "en el periodo activo.",
                color=MUTED,
            ))]
            page.update()

    selector.on_select = cambiar_paquete
    selector_semestre.on_select = cambiar_semestre
    vista = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=20, controls=[
        titulo_pagina(
            "Grupos y horarios",
            "Consulta horarios y listas por sección de los primeros tres semestres.",
        ),
        ft.Row(wrap=True, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
            ft.Row(wrap=True, controls=[selector_semestre, selector]),
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
