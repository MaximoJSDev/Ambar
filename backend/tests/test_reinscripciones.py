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

    def test_registra_reinscripcion_con_los_datos_solicitados(self):
        datos = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 10,
        }
        with patch(
            "backend.routers.reinscripciones.servicios.registrar_reinscripcion",
            return_value=datos | {"paquete": "2ISC1"},
        ) as registrar:
            respuesta = self.client.post("/reinscripciones", json=datos)

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json(), datos | {"paquete": "2ISC1"})
        registrar.assert_called_once_with(datos)

    def test_devuelve_error_de_numero_de_control_duplicado(self):
        datos = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 10,
        }
        with patch(
            "backend.routers.reinscripciones.servicios.registrar_reinscripcion",
            side_effect=servicios.NumeroControlDuplicado(
                "El número de control ya existe",
                {"numero_control": "El número de control ya existe"},
            ),
        ):
            respuesta = self.client.post("/reinscripciones", json=datos)

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(
            respuesta.json()["detail"]["errores"]["numero_control"],
            "El número de control ya existe",
        )

    def test_valida_el_anio_del_numero_antes_de_persistir(self):
        respuesta = self.client.post(
            "/reinscripciones",
            json={
                "numero_control": "26320700",
                "nombre": "Ana",
                "apellidos": "Prueba",
                "semestre": 3,
                "id_paquete": 10,
            },
        )

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("2025", respuesta.json()["detail"]["errores"]["numero_control"])

    def test_api_de_reinscripcion_solo_admite_secretaria(self):
        self.usuario["rol"] = "Administrador"
        respuesta = self.client.post(
            "/reinscripciones",
            json={
                "numero_control": "26320700",
                "nombre": "Ana",
                "apellidos": "Prueba",
                "semestre": 2,
                "id_paquete": 10,
            },
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_api_rechaza_registro_sin_paquete_seleccionado(self):
        respuesta = self.client.post(
            "/reinscripciones",
            json={
                "numero_control": "26320700",
                "nombre": "Ana",
                "apellidos": "Prueba",
                "semestre": 2,
            },
        )
        self.assertEqual(respuesta.status_code, 422)

    def test_busca_y_actualiza_los_datos_de_una_reinscripcion(self):
        datos = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
        }
        datos_actualizacion = datos | {"id_paquete": 11}
        with (
            patch(
                "backend.routers.reinscripciones.servicios.obtener_reinscripcion",
                return_value=datos,
            ) as obtener,
            patch(
                "backend.routers.reinscripciones.servicios.modificar_reinscripcion",
                return_value=datos,
            ) as modificar,
        ):
            respuesta_get = self.client.get("/reinscripciones/26320700")
            respuesta_put = self.client.put(
                "/reinscripciones/26320700", json=datos_actualizacion,
            )

        self.assertEqual(respuesta_get.status_code, 200)
        self.assertEqual(respuesta_put.status_code, 200)
        obtener.assert_called_once_with("26320700")
        modificar.assert_called_once_with("26320700", datos_actualizacion)

    def test_administracion_puede_consultar_reinscripcion(self):
        self.usuario["rol"] = "Administrador"
        with patch(
            "backend.routers.reinscripciones.servicios.obtener_reinscripcion",
            return_value={"numero_control": "26320700"},
        ), patch(
            "backend.routers.reinscripciones.servicios.modificar_reinscripcion",
            return_value={"numero_control": "26320700"},
        ):
            respuesta = self.client.get("/reinscripciones/26320700")
            actualizacion = self.client.put(
                "/reinscripciones/26320700",
                json={
                    "numero_control": "26320700",
                    "nombre": "Ana",
                    "apellidos": "Prueba",
                    "semestre": 2,
                },
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(actualizacion.status_code, 200)


class ReinscripcionesServiceTests(unittest.TestCase):
    def setUp(self):
        self.datos = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 30,
        }

    def test_valida_campos_y_anio_segun_semestre(self):
        self.assertEqual(servicios.validar_reinscripcion(self.datos), {})
        self.assertEqual(
            servicios.validar_reinscripcion(self.datos | {"semestre": 3}),
            {"numero_control": "Para 3° semestre, el número de control debe corresponder al año 2025"},
        )
        self.assertEqual(
            servicios.validar_reinscripcion(self.datos | {"numero_control": "abc"}),
            {"numero_control": "Debe contener exactamente 8 dígitos"},
        )
        errores = servicios.validar_reinscripcion(
            self.datos | {"nombre": "A1", "apellidos": "", "semestre": 4}
        )
        self.assertEqual(set(errores), {"nombre", "apellidos", "semestre"})

    def test_inserta_reinscripcion_si_el_numero_no_existe(self):
        consulta_alumnos = MagicMock()
        consulta_alumnos.scalar_one_or_none.return_value = None
        consulta_reinscripciones = MagicMock()
        consulta_reinscripciones.scalar_one_or_none.return_value = None
        paquetes = MagicMock()
        paquetes.mappings.return_value.all.return_value = [
            {"nombre_paquete": "2ISC1", "id_grupo": grupo, "cupo_disponible": 3}
            for grupo in range(30, 35)
        ]
        conn = MagicMock()
        conn.execute.side_effect = [
            consulta_alumnos,
            consulta_reinscripciones,
            paquetes,
            MagicMock(),
            MagicMock(),
        ]

        bloqueo = MagicMock()
        bloqueo.execute.return_value.scalar.return_value = 1
        with (
            patch("backend.servicios.engine.connect") as connect,
            patch("backend.servicios.engine.begin") as begin,
        ):
            connect.return_value.__enter__.return_value = bloqueo
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.registrar_reinscripcion(self.datos)

        self.assertEqual(resultado, self.datos | {"paquete": "2ISC1"})
        self.assertEqual(conn.execute.call_count, 5)
        self.assertEqual(
            conn.execute.call_args_list[3].args[1],
            {
                "numero_control": self.datos["numero_control"],
                "nombre": self.datos["nombre"],
                "apellidos": self.datos["apellidos"],
                "semestre": self.datos["semestre"],
            },
        )
        self.assertEqual(
            conn.execute.call_args_list[2].args[1]["id_paquete"],
            self.datos["id_paquete"],
        )
        self.assertEqual(
            conn.execute.call_args_list[4].args[1],
            [{"numero": "26320700", "grupo": grupo} for grupo in range(30, 35)],
        )

    def test_rechaza_numero_de_control_que_ya_esta_en_alumnos(self):
        existente = MagicMock()
        existente.scalar_one_or_none.return_value = "26320700"
        conn = MagicMock()
        conn.execute.side_effect = [existente, MagicMock()]
        bloqueo = MagicMock()
        bloqueo.execute.return_value.scalar.return_value = 1

        with (
            patch("backend.servicios.engine.connect") as connect,
            patch("backend.servicios.engine.begin") as begin,
            self.assertRaisesRegex(servicios.Conflicto, "El número de control ya existe"),
        ):
            connect.return_value.__enter__.return_value = bloqueo
            begin.return_value.__enter__.return_value = conn
            servicios.registrar_reinscripcion(self.datos)

        self.assertEqual(conn.execute.call_count, 2)

    def test_elige_el_primer_paquete_completo_con_cupo(self):
        resultado = MagicMock()
        resultado.mappings.return_value.all.return_value = [
            {"nombre_paquete": "2ISC1", "id_grupo": 10, "cupo_disponible": 0},
            {"nombre_paquete": "2ISC1", "id_grupo": 11, "cupo_disponible": 3},
            {"nombre_paquete": "2ISC1", "id_grupo": 12, "cupo_disponible": 3},
            {"nombre_paquete": "2ISC1", "id_grupo": 13, "cupo_disponible": 3},
            {"nombre_paquete": "2ISC1", "id_grupo": 14, "cupo_disponible": 3},
            {"nombre_paquete": "2ISC2", "id_grupo": 20, "cupo_disponible": 2},
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        grupos = servicios._grupos_paquete_reinscripcion(conn, 2)

        self.assertEqual([grupo["id_grupo"] for grupo in grupos], [20])

    def test_selecciona_el_paquete_solicitado_para_reinscripcion(self):
        resultado = MagicMock()
        resultado.mappings.return_value.all.return_value = [
            {"nombre_paquete": "2ISC1", "id_grupo": 10, "cupo_disponible": 3},
            {"nombre_paquete": "2ISC2", "id_grupo": 20, "cupo_disponible": 2},
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        grupos = servicios._grupos_paquete_reinscripcion(conn, 2, id_paquete=22)

        self.assertEqual([grupo["id_grupo"] for grupo in grupos], [20])
        self.assertEqual(conn.execute.call_args.args[1]["id_paquete"], 22)

    def test_paquete_seleccionado_debe_pertenecer_al_semestre_y_tener_cupo(self):
        resultado = MagicMock()
        resultado.mappings.return_value.all.return_value = [
            {"nombre_paquete": "2ISC1", "id_grupo": 10, "cupo_disponible": 0},
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        with self.assertRaisesRegex(servicios.Conflicto, "no está disponible"):
            servicios._grupos_paquete_reinscripcion(conn, 3, id_paquete=22)

        self.assertEqual(conn.execute.call_args.args[1]["semestre"], 3)
        self.assertEqual(conn.execute.call_args.args[1]["id_paquete"], 22)

    def test_rechaza_numero_de_control_modificado(self):
        anterior = MagicMock()
        anterior.mappings.return_value.first.return_value = {
            "numero_control": "26320700",
            "semestre": 2,
        }
        conn = MagicMock()
        conn.execute.return_value = anterior
        bloqueo = MagicMock()
        bloqueo.execute.return_value.scalar.return_value = 1

        with (
            patch("backend.servicios.engine.connect") as connect,
            patch("backend.servicios.engine.begin") as begin,
            self.assertRaisesRegex(servicios.Conflicto, "No se puede modificar el número"),
        ):
            connect.return_value.__enter__.return_value = bloqueo
            begin.return_value.__enter__.return_value = conn
            servicios.modificar_reinscripcion(
                "26320700",
                self.datos | {"numero_control": "26320701"},
            )

        self.assertEqual(conn.execute.call_count, 1)

    def test_modifica_datos_sin_perder_el_horario_existente(self):
        anterior = MagicMock()
        anterior.mappings.return_value.first.return_value = {
            "numero_control": "26320700",
            "semestre": 2,
        }
        duplicado = MagicMock()
        duplicado.scalar_one_or_none.return_value = None
        horario = MagicMock()
        horario.mappings.return_value.one.return_value = {
            "inscripciones": 5,
            "calificaciones": 0,
        }
        conn = MagicMock()
        conn.execute.side_effect = [anterior, duplicado, horario, MagicMock()]
        bloqueo = MagicMock()
        bloqueo.execute.return_value.scalar.return_value = 1

        with (
            patch("backend.servicios.engine.connect") as connect,
            patch("backend.servicios.engine.begin") as begin,
        ):
            connect.return_value.__enter__.return_value = bloqueo
            begin.return_value.__enter__.return_value = conn
            datos_modificacion = {
                clave: valor for clave, valor in self.datos.items()
                if clave != "id_paquete"
            }
            resultado = servicios.modificar_reinscripcion(
                "26320700", datos_modificacion,
            )

        self.assertEqual(resultado, datos_modificacion)
        self.assertEqual(conn.execute.call_count, 4)
        self.assertIn(
            "UPDATE reinscripciones",
            str(conn.execute.call_args_list[-1].args[0]),
        )

    def test_lista_de_grupo_incluye_reinscritos(self):
        resumen = MagicMock()
        resumen.mappings.return_value.all.return_value = [{
            "id_paquete": 20,
            "nombre": "2ISC2",
        }]
        reinscritos = MagicMock()
        reinscritos.mappings.return_value.all.return_value = [{
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": None,
            "correo_institucional": None,
        }]
        conn = MagicMock()
        conn.execute.side_effect = [resumen, reinscritos]

        with patch("backend.servicios.engine.connect") as connect:
            connect.return_value.__enter__.return_value = conn
            resultado = servicios.lista_alumnos_paquete(20)

        self.assertEqual(resultado["alumnos"][0]["numero_control"], "26320700")
        consulta = str(conn.execute.call_args_list[1].args[0])
        self.assertIn("LEFT JOIN reinscripciones r", consulta)
        self.assertIn("COALESCE(a.nombres, r.nombre)", consulta)

    def test_consulta_de_horario_reconoce_reinscritos(self):
        registro = MagicMock()
        registro.mappings.return_value.first.return_value = {
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": None,
            "semestre_actual": 2,
            "estatus": "Activo",
            "eliminado": 0,
        }
        grupos = MagicMock()
        grupos.scalars.return_value.all.return_value = []
        conn = MagicMock()
        conn.execute.side_effect = [registro, grupos]

        with patch("backend.servicios.engine.connect") as connect:
            connect.return_value.__enter__.return_value = conn
            estado = servicios.estado_horario_alumno("26320700")

        self.assertEqual(estado["semestre"], 2)
        self.assertFalse(estado["asignado"])
        self.assertIn(
            "FROM reinscripciones WHERE numero_control = :numero",
            str(conn.execute.call_args_list[0].args[0]),
        )
