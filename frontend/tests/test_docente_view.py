import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main


def _textos(control):
    if isinstance(control, str):
        yield control
        return
    valor = getattr(control, "value", None)
    if isinstance(valor, str):
        yield valor
    texto = getattr(control, "text", None)
    if isinstance(texto, str):
        yield texto
    elif isinstance(getattr(texto, "value", None), str):
        yield texto.value
    titulo = getattr(control, "title", None)
    if titulo is not None:
        yield from _textos(titulo)
    controles = getattr(control, "controls", None) or []
    for hijo in controles:
        yield from _textos(hijo)
    contenido = getattr(control, "content", None)
    if contenido is not None:
        yield from _textos(contenido)


def test_vista_docente_muestra_horario_lista_y_calificaciones():
    datos_grupos = [{
        "id_grupo": 7,
        "grupo": "1ISC1",
        "nombre_materia": "Cálculo Diferencial",
        "aula": "G301",
        "creditos": 5,
        "turno": "Matutino",
        "periodo": "AGO-DIC 2026",
        "horarios": [{"dia": "Lunes", "inicio": "08:00", "fin": "09:00"}],
        "alumnos": [{
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": "Zúñiga",
            "nombre_completo": "Prueba Zúñiga Ana",
            "semana_5": 90,
            "semana_9": None,
            "semana_13": 88,
            "final": None,
        }],
    }]
    page = Mock()
    with patch.object(main.api, "grupos_docente", return_value=datos_grupos) as cargar:
        vista = main.build_inicio_docente(page, {"nombre": "Docente de prueba"}, Mock())

    cargar.assert_called_once_with()
    assert isinstance(vista, main.ft.Column)
    texto_vista = list(_textos(vista))
    for esperado in (
        "Cálculo Diferencial",
        "Lunes",
        "08:00 – 09:00",
        "Prueba Zúñiga Ana",
        "Semana 5",
        "Semana 9",
        "Semana 13",
        "Final",
        "90",
        "88",
        "Descargar grupos y horarios",
        "Lista de alumnos y calificaciones",
        "Descargar lista de alumnos",
        "Descargar lista de calificaciones",
    ):
        assert esperado in texto_vista
    assert "Lista de alumnos y calificaciones (1)" not in texto_vista
    listas = [
        control for control in _controles(vista)
        if isinstance(control, main.ft.ExpansionTile)
    ]
    assert len(listas) == 1
    assert listas[0].expanded is False


def test_error_de_calificacion_invalida_se_muestra_junto_al_campo():
    datos_grupos = [{
        "id_grupo": 7,
        "grupo": "1ISC1",
        "nombre_materia": "Cálculo Diferencial",
        "aula": "G301",
        "creditos": 5,
        "turno": "Matutino",
        "periodo": "AGO-DIC 2026",
        "semana_actual": 9,
        "evaluaciones_disponibles": ["Semana 5", "Semana 9"],
        "horarios": [],
        "alumnos": [{
            "numero_control": "26320700",
            "nombre_completo": "Ana Prueba",
            "semana_5": None,
            "semana_9": None,
            "semana_13": None,
            "final": None,
        }],
    }]
    page = Mock()
    with (
        patch.object(main.api, "grupos_docente", return_value=datos_grupos),
        patch.object(main.api, "guardar_calificacion_docente") as guardar,
    ):
        vista = main.build_inicio_docente(page, {"nombre": "Docente de prueba"}, Mock())
        controles = list(_controles(vista))
        entrada = next(
            control for control in controles
            if isinstance(control, main.ft.TextField) and control.hint_text == "0 o 70–100"
        )
        entrada.value = "1"
        boton_guardar = next(
            control for control in controles
            if isinstance(control, main.ft.IconButton) and control.tooltip == "Guardar Semana 5"
        )
        boton_guardar.on_click(None)

    guardar.assert_not_called()
    assert entrada.error_text == "Ingresa un entero: 0 o de 70 a 100."
    assert entrada.error_text in list(_textos(vista))


def _controles(control):
    yield control
    for hijo in getattr(control, "controls", None) or []:
        yield from _controles(hijo)
    contenido = getattr(control, "content", None)
    if contenido is not None:
        yield from _controles(contenido)


def test_periodo_existente_se_edita_con_calendario_y_se_puede_renombrar():
    periodo = {"periodo": "ENE-JUN 2026", "fecha_inicio": "2026-01-19"}
    page = Mock()
    with (
        patch.object(main.api, "periodos_escolares", side_effect=[[periodo], []]),
        patch.object(main.api, "guardar_periodo_escolar") as guardar,
    ):
        vista = main.build_periodos_escolares(page)
        controles = list(_controles(vista))
        campo_fecha = next(
            control for control in controles
            if isinstance(control, main.ft.TextField)
            and control.label == "Fecha de inicio de la semana 1"
        )
        campo_periodo = next(
            control for control in controles
            if isinstance(control, main.ft.TextField)
            and control.label == "Periodo (ej. AGO-DIC 2026)"
        )
        boton_guardar = next(
            control for control in controles
            if isinstance(control, main.ft.FilledButton)
        )
        elemento_periodo = next(
            control for control in controles
            if isinstance(control, main.ft.Container) and control.on_click is not None
        )

        elemento_periodo.on_click(None)
        assert campo_periodo.value == "ENE-JUN 2026"
        assert campo_fecha.value == "2026-01-19"

        campo_fecha.on_click(None)
        selector_fecha = page.show_dialog.call_args.args[0]
        selector_fecha.on_change(SimpleNamespace(
            control=SimpleNamespace(value=datetime.datetime(2026, 1, 26)),
        ))
        assert campo_fecha.value == "2026-01-26"

        campo_periodo.value = "AGO-DIC 2026"
        boton_guardar.on_click(None)

    guardar.assert_called_once_with(
        "AGO-DIC 2026",
        "2026-01-26",
        "ENE-JUN 2026",
    )


def test_actividad_reciente_de_secretaria_inicia_plegada():
    resumen = {
        "alumnos_nuevo_ingreso": 3,
        "grupos": 2,
        "reinscripciones_hoy": 0,
        "actividad": [{
            "numero_control": "26320700",
            "alumno": "Pérez López Ana",
            "tramite": "Alta",
            "estado": "Completada",
        }],
    }
    with patch.object(main.api, "resumen_panel", return_value=resumen):
        vista = main.build_panel(Mock(), Mock())

    listas = [
        control for control in _controles(vista)
        if isinstance(control, main.ft.ExpansionTile)
    ]
    assert len(listas) == 1
    assert listas[0].expanded is False
    textos = list(_textos(vista))
    assert "Pendientes" not in textos
    assert "Expedientes pendientes" not in textos
    assert "Número de control" in textos


def test_actividad_pagina_de_diez_y_abre_consultas_con_numero_de_control():
    alumnos = [{
        "numero_control": f"263207{indice:02}",
        "alumno": f"Apellido{indice:02} Materno Nombre{indice:02}",
        "tramite": "Alta",
        "estado": "Completada",
    } for indice in range(23)]
    consultar = Mock()
    with patch.object(main.api, "resumen_panel", return_value={
        "alumnos_nuevo_ingreso": 23,
        "grupos": 2,
        "reinscripciones_hoy": 0,
        "actividad": alumnos,
    }):
        vista = main.build_panel(Mock(), Mock(), consultar)

    tile = next(
        control for control in _controles(vista)
        if isinstance(control, main.ft.ExpansionTile)
    )
    lista = tile.controls[1]
    paginas = tile.controls[2]
    assert len(lista.controls) == 10
    assert "26320700" in list(_textos(lista.controls[0]))
    assert "Página 1 de 3" in list(_textos(paginas))

    boton_siguiente = next(
        control for control in paginas.controls
        if isinstance(control, main.ft.TextButton)
        and "Siguiente" in list(_textos(control))
    )
    boton_siguiente.on_click(None)
    assert len(lista.controls) == 10
    assert "Página 2 de 3" in list(_textos(paginas))

    lista.controls[0].on_click(None)
    consultar.assert_called_once_with("26320710")


def test_consulta_de_expediente_acepta_numero_inicial_para_busqueda_automatica():
    page = Mock()
    consulta = main.ConsultaExpediente(
        page,
        Mock(),
        {"rol": "Secretaría"},
        Mock(),
        numero_control_inicial="26320700",
    )

    assert consulta.entrada.value == "26320700"
    assert page.run_task.call_args.args == (consulta._buscar_inicial,)


def test_lista_de_grupo_de_secretaria_inicia_plegada_y_deja_descarga_visible():
    paquete = {
        "id_paquete": 5,
        "nombre": "1ISC1",
        "turno": "Matutino",
        "alumnos": 1,
        "semestre": 1,
        "periodo": "AGO-DIC 2026",
        "cupo_maximo": 25,
        "lugares": 24,
    }
    detalle = {
        "paquete": paquete,
        "materias": [],
    }
    lista = {
        "paquete": paquete,
        "alumnos": [{
            "numero_control": "26320700",
            "apellido_paterno": "Pérez",
            "apellido_materno": "López",
            "nombres": "Ana",
        }],
    }
    with (
        patch.object(main.api, "grupos_horario", return_value=[paquete]),
        patch.object(main.api, "docentes_horario", return_value=[]),
        patch.object(main.api, "detalle_grupo_horario", return_value=detalle),
        patch.object(main.api, "lista_alumnos_grupo", return_value=lista),
    ):
        vista = main.build_grupos_horarios(Mock(), Mock())

    listas = [
        control for control in _controles(vista)
        if isinstance(control, main.ft.ExpansionTile)
    ]
    assert len(listas) == 1
    assert listas[0].expanded is False
    assert "Alumnos del grupo" in list(_textos(listas[0].title))
    botones_descarga = [
        control for control in _controles(vista)
        if isinstance(control, main.ft.OutlinedButton)
        and "Descargar lista PDF" in list(_textos(control))
    ]
    assert len(botones_descarga) == 1


def test_error_al_asignar_maestro_desplaza_la_vista_arriba():
    paquete = {
        "id_paquete": 5,
        "nombre": "1ISC1",
        "turno": "Matutino",
        "alumnos": 0,
        "semestre": 1,
        "periodo": "AGO-DIC 2026",
        "cupo_maximo": 25,
        "lugares": 25,
    }
    materia = {
        "id_grupo": 8,
        "nombre_materia": "Cálculo",
        "aula": "G301",
        "creditos": 5,
        "id_docente": None,
        "docente": "Por asignar",
        "horarios": [{"dia": "Lunes", "inicio": "10:00", "fin": "11:00"}],
    }
    with (
        patch.object(main.api, "grupos_horario", return_value=[paquete]),
        patch.object(main.api, "docentes_horario", return_value=[]),
        patch.object(
            main.api,
            "detalle_grupo_horario",
            return_value={"paquete": paquete, "materias": [materia]},
        ),
        patch.object(main.api, "lista_alumnos_grupo", return_value={"alumnos": []}),
        patch.object(
            main.api,
            "asignar_docente_grupo",
            side_effect=main.ApiError(409, "El maestro ya tiene un traslape."),
        ) as asignar,
    ):
        page = Mock()
        vista = main.build_grupos_horarios(page, Mock())
        controles = list(_controles(vista))
        selector_docente = next(
            control for control in controles
            if isinstance(control, main.ft.Dropdown) and control.label == "Cuenta vinculada"
        )
        selector_docente.value = "12"
        boton_guardar = next(
            control for control in controles
            if isinstance(control, main.ft.OutlinedButton)
            and "Guardar docente" in list(_textos(control))
        )
        boton_guardar.on_click(None)

    asignar.assert_called_once_with(8, 12)
    assert page.run_task.call_args.args == (vista.scroll_to,)
    assert page.run_task.call_args.kwargs == {"offset": 0, "duration": 300}
