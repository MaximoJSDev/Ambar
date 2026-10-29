import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import servicios
from backend.deps import usuario_actual
from backend.main import app


class ReinscripcionesApiTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 1, "rol": "Secretaría"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_busqueda_retorna_estado_y_paquetes_disponibles(self):
        estado = {
            "numero_control": "26320700",
            "semestre": 4,
            "periodo": "ENE-JUN 2027",
            "asignado": False,
            "paquetes": [{"id_paquete": 12}],
        }
        with patch(
            "backend.routers.reinscripciones.servicios.estado_reinscripcion_alumno",
            return_value=estado,
        ) as consultar:
            respuesta = self.client.get(
                "/reinscripciones/alumno",
                params={"q": "26320700"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), estado)
        consultar.assert_called_once_with("26320700")

    def test_busqueda_rechaza_semestre_fuera_del_rango(self):
        with patch(
            "backend.routers.reinscripciones.servicios.estado_reinscripcion_alumno",
            side_effect=servicios.Conflicto("Disponible únicamente de 2 a 10."),
        ):
            respuesta = self.client.get(
                "/reinscripciones/alumno", params={"q": "26320700"},
            )

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["detail"]["mensaje"], "Disponible únicamente de 2 a 10.")

    def test_asignacion_envia_numero_y_paquete_al_servicio(self):
        estado = {"asignado": True, "paquete": {"id_paquete": 12}}
        with patch(
            "backend.routers.reinscripciones.servicios.asignar_paquete_reinscripcion",
            return_value=estado,
        ) as asignar:
            respuesta = self.client.post(
                "/reinscripciones/alumnos/26320700/paquete",
                json={"id_paquete": 12},
            )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json(), estado)
        asignar.assert_called_once_with("26320700", 12)

    def test_api_de_reinscripcion_solo_admite_secretaria(self):
        self.usuario["rol"] = "Administrador"
        respuesta = self.client.get(
            "/reinscripciones/alumno", params={"q": "26320700"},
        )
        self.assertEqual(respuesta.status_code, 403)


class ReinscripcionesServiceTests(unittest.TestCase):
    def test_estado_usa_semestre_guardado_y_periodo_activo(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": None,
            "semestre_actual": 4,
            "estatus": "Activo",
            "eliminado": 0,
        }
        existentes = MagicMock()
        existentes.scalars.return_value.all.return_value = []
        conn = MagicMock()
        conn.execute.side_effect = [alumno, existentes]

        with (
            patch("backend.servicios.engine.connect") as conectar,
            patch("backend.servicios.settings.periodo_escolar", "ENE-JUN 2027"),
            patch(
                "backend.servicios._resumen_paquetes_horario",
                return_value=[{"id_paquete": 12}],
            ) as resumen,
        ):
            conectar.return_value.__enter__.return_value = conn
            estado = servicios.estado_reinscripcion_alumno(" 26320700 ")

        self.assertEqual(estado["semestre"], 4)
        self.assertEqual(estado["periodo"], "ENE-JUN 2027")
        self.assertFalse(estado["asignado"])
        self.assertEqual(estado["paquetes"], [{"id_paquete": 12}])
        resumen.assert_called_once_with(conn, "ENE-JUN 2027", 4, solo_catalogo=False)
        self.assertEqual(
            conn.execute.call_args_list[0].args[1]["consulta"],
            "26320700",
        )

    def test_estado_rechaza_alumno_fuera_de_semestres_2_a_10(self):
        resultado = MagicMock()
        resultado.mappings.return_value.first.return_value = {
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": None,
            "semestre_actual": 1,
            "estatus": "Activo",
            "eliminado": 0,
        }
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.servicios.engine.connect") as conectar:
            conectar.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(servicios.Conflicto, "semestres 2 a 10"):
                servicios.estado_reinscripcion_alumno("26320700")

        conn.execute.assert_called_once()

    def test_asignacion_inscribe_todos_los_grupos_y_no_cambia_semestre(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 4,
            "estatus": "Activo",
            "eliminado": 0,
        }
        paquete = MagicMock()
        paquete.mappings.return_value.first.return_value = {"id_paquete": 12}
        existentes = MagicMock()
        existentes.scalars.return_value.all.return_value = []
        grupos = MagicMock()
        grupos.mappings.return_value.all.return_value = [
            {"id_grupo": 30, "turno": "Matutino", "cupo_disponible": 3},
            {"id_grupo": 31, "turno": "Matutino", "cupo_disponible": 1},
        ]
        conn = MagicMock()
        conn.execute.side_effect = [
            alumno, paquete, existentes, grupos, MagicMock(), MagicMock(),
        ]
        estado_final = {"asignado": True}

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings.periodo_escolar", "ENE-JUN 2027"),
            patch(
                "backend.servicios.estado_reinscripcion_alumno",
                return_value=estado_final,
            ),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.asignar_paquete_reinscripcion("26320700", 12)

        self.assertEqual(resultado, estado_final)
        insercion = conn.execute.call_args_list[4]
        self.assertEqual(insercion.args[1], [
            {"numero": "26320700", "grupo": 30},
            {"numero": "26320700", "grupo": 31},
        ])
        consulta_periodo = " ".join(
            str(llamada.args[0]) for llamada in conn.execute.call_args_list
        )
        self.assertIn("periodo_escolar = :periodo", consulta_periodo)
        self.assertNotIn("UPDATE alumnos SET semestre_actual", consulta_periodo)

    def test_asignacion_impide_duplicar_paquete_en_el_periodo(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 4,
            "estatus": "Activo",
            "eliminado": 0,
        }
        paquete = MagicMock()
        paquete.mappings.return_value.first.return_value = {"id_paquete": 12}
        existentes = MagicMock()
        existentes.scalars.return_value.all.return_value = ["4ISC1"]
        conn = MagicMock()
        conn.execute.side_effect = [alumno, paquete, existentes]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings.periodo_escolar", "ENE-JUN 2027"),
        ):
            begin.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(servicios.Conflicto, "ya tiene un paquete asignado"):
                servicios.asignar_paquete_reinscripcion("26320700", 12)

        self.assertEqual(conn.execute.call_count, 3)

    def test_asignacion_rechaza_paquete_sin_cupo(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 4,
            "estatus": "Activo",
            "eliminado": 0,
        }
        paquete = MagicMock()
        paquete.mappings.return_value.first.return_value = {"id_paquete": 12}
        existentes = MagicMock()
        existentes.scalars.return_value.all.return_value = []
        grupos = MagicMock()
        grupos.mappings.return_value.all.return_value = [
            {"id_grupo": 30, "turno": "Matutino", "cupo_disponible": 0},
        ]
        conn = MagicMock()
        conn.execute.side_effect = [alumno, paquete, existentes, grupos]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings.periodo_escolar", "ENE-JUN 2027"),
        ):
            begin.return_value.__enter__.return_value = conn
            with self.assertRaises(servicios.CupoLleno):
                servicios.asignar_paquete_reinscripcion("26320700", 12)

        self.assertEqual(conn.execute.call_count, 4)
