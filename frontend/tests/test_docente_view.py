from unittest.mock import Mock, patch

import main


def _textos(control):
    valor = getattr(control, "value", None)
    if isinstance(valor, str):
        yield valor
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
            "nombre_completo": "Ana Prueba",
            "semana_5": 90,
            "semana_9": None,
            "semana_13": 88.5,
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
        "Ana Prueba",
        "Sem. 5",
        "Sem. 9",
        "Sem. 13",
        "Final",
        "90",
        "88.5",
    ):
        assert esperado in texto_vista
