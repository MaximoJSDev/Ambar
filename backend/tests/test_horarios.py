import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import servicios
from backend.catalogo_horarios import CATALOGO_1ISC, PERIODO_1ISC
from backend.deps import usuario_actual
from backend.main import app
from backend.reportes import generar_horario_alumno_pdf, generar_lista_grupo_pdf


class HorariosTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 1, "rol": "Secretaría"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_catalogo_contiene_las_siete_secciones_y_seis_materias(self):
        self.assertEqual(PERIODO_1ISC, "AGO-DIC 2026")
        self.assertEqual(set(CATALOGO_1ISC), {f"1ISC{i}" for i in range(1, 8)})
        self.assertTrue(all(len(materias) == 6 for materias in CATALOGO_1ISC.values()))
        self.assertIsNone(CATALOGO_1ISC["1ISC1"][0][4][0])
        self.assertIsNone(CATALOGO_1ISC["1ISC6"][0][4][1])
        self.assertIsNone(CATALOGO_1ISC["1ISC1"][1][3])

    def test_endpoints_de_horarios_solo_admiten_secretaria(self):
        self.usuario["rol"] = "Administrador"
        respuesta = self.client.get("/horarios/grupos")
        self.assertEqual(respuesta.status_code, 403)

    def test_docente_consulta_solo_sus_grupos_y_calificaciones(self):
        self.usuario.update({"id_usuario": 42, "rol": "Docente"})
        grupos = [{
            "id_grupo": 7,
            "grupo": "1ISC1",
            "nombre_materia": "Cálculo Diferencial",
            "horarios": [{"dia": "Lunes", "inicio": "08:00", "fin": "09:00"}],
            "alumnos": [{
                "numero_control": "26320700",
                "nombre_completo": "Ana Prueba",
                "semana_5": 90,
                "semana_9": None,
                "semana_13": None,
                "final": None,
            }],
        }]
        with patch(
            "backend.routers.horarios.servicios.listar_grupos_docente",
            return_value=grupos,
        ) as listar:
            respuesta = self.client.get("/horarios/docente/grupos")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), grupos)
        listar.assert_called_once_with(42)

    def test_consulta_de_grupos_docente_rechaza_otros_roles(self):
        for rol in ("Secretaría", "Administrador"):
            with self.subTest(rol=rol):
                self.usuario["rol"] = rol
                with patch("backend.routers.horarios.servicios.listar_grupos_docente") as listar:
                    respuesta = self.client.get("/horarios/docente/grupos")

                self.assertEqual(respuesta.status_code, 403)
                listar.assert_not_called()

    def test_servicio_entrega_horarios_y_calificaciones_de_grupos_asignados(self):
        resultado_grupos = MagicMock()
        resultado_grupos.mappings.return_value.all.return_value = [
            {
                "id_grupo": 7,
                "id_paquete": 2,
                "grupo": "1ISC1",
                "nombre_materia": "Cálculo Diferencial",
                "aula": "G301",
                "creditos": 5,
                "turno": "Matutino",
                "periodo_escolar": PERIODO_1ISC,
                "dia_semana": 1,
                "hora_inicio": "08:00:00",
                "hora_fin": "09:00:00",
            },
            {
                "id_grupo": 7,
                "id_paquete": 2,
                "grupo": "1ISC1",
                "nombre_materia": "Cálculo Diferencial",
                "aula": "G301",
                "creditos": 5,
                "turno": "Matutino",
                "periodo_escolar": PERIODO_1ISC,
                "dia_semana": 3,
                "hora_inicio": "08:00:00",
                "hora_fin": "09:00:00",
            },
        ]
        resultado_alumnos = MagicMock()
        resultado_alumnos.mappings.return_value.all.return_value = [{
            "id_grupo": 7,
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": None,
            "semana_5": 90,
            "semana_9": None,
            "semana_13": 88,
            "final": None,
        }]
        conn = MagicMock()
        conn.execute.side_effect = [resultado_grupos, resultado_alumnos]

        with patch("backend.servicios.engine.connect") as conectar:
            conectar.return_value.__enter__.return_value = conn
            grupos = servicios.listar_grupos_docente(42)

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]["horarios"], [
            {"dia": "Lunes", "inicio": "08:00", "fin": "09:00"},
            {"dia": "Miércoles", "inicio": "08:00", "fin": "09:00"},
        ])
        self.assertEqual(grupos[0]["alumnos"], [{
            "numero_control": "26320700",
            "nombre_completo": "Ana Prueba",
            "semana_5": 90,
            "semana_9": None,
            "semana_13": 88,
            "final": None,
        }])
        self.assertEqual(conn.execute.call_args_list[0].args[1]["usuario"], 42)
        self.assertIn("g.id_docente = d.id_docente", str(conn.execute.call_args_list[0].args[0]))

    def test_secretaria_puede_consultar_paquetes_del_semestre(self):
        paquetes = [{"id_paquete": 5, "nombre": "1ISC1", "semestre": 1}]
        with patch("backend.routers.horarios.servicios.listar_paquetes_horario",
                   return_value=paquetes) as listar:
            respuesta = self.client.get("/horarios/paquetes?semestre=1")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), paquetes)
        listar.assert_called_once_with(1)

    def test_alta_consulta_horario_sin_paquete(self):
        estado = {
            "numero_control": "26320700",
            "semestre": 1,
            "periodo": PERIODO_1ISC,
            "asignado": False,
            "paquete": None,
            "materias": [],
        }
        with patch("backend.routers.horarios.servicios.estado_horario_alumno", return_value=estado):
            respuesta = self.client.get("/horarios/alumnos/26320700")

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.json()["asignado"])

    def test_secretaria_asigna_un_paquete_completo(self):
        estado = {
            "numero_control": "26320700",
            "semestre": 1,
            "periodo": PERIODO_1ISC,
            "asignado": True,
            "paquete": {"id_paquete": 12, "nombre": "1ISC3"},
            "materias": [{"nombre_materia": "Taller de Ética"}],
        }
        with patch(
            "backend.routers.horarios.servicios.asignar_paquete_horario",
            return_value=estado,
        ) as asignar:
            respuesta = self.client.post(
                "/horarios/alumnos/26320700/paquete",
                json={"id_paquete": 12},
            )

        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue(respuesta.json()["asignado"])
        asignar.assert_called_once_with("26320700", 12)

    def test_rechaza_paquete_que_no_corresponde_al_semestre(self):
        with patch(
            "backend.routers.horarios.servicios.asignar_paquete_horario",
            side_effect=servicios.Conflicto("El paquete no corresponde al semestre."),
        ):
            respuesta = self.client.post(
                "/horarios/alumnos/26320700/paquete",
                json={"id_paquete": 99},
            )

        self.assertEqual(respuesta.status_code, 409)

    def test_secretaria_puede_migrar_un_alumno_de_grupo_anterior(self):
        estado = {
            "numero_control": "26320700",
            "semestre": 1,
            "periodo": PERIODO_1ISC,
            "asignado": True,
            "paquete": {"id_paquete": 12, "nombre": "1ISC3"},
            "materias": [],
        }
        with patch(
            "backend.routers.horarios.servicios.reasignar_paquete_horario",
            return_value=estado,
        ) as migrar:
            respuesta = self.client.put(
                "/horarios/alumnos/26320700/paquete",
                json={"id_paquete": 12},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["paquete"]["nombre"], "1ISC3")
        migrar.assert_called_once_with("26320700", 12)

    def test_servicio_no_asigna_paquetes_ajenos_al_catalogo_oficial(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 1,
            "estatus": "Activo",
            "eliminado": False,
        }
        paquete_legacy = MagicMock()
        paquete_legacy.mappings.return_value.first.return_value = {
            "id_paquete": 99,
            "nombre_paquete": "1A",
            "semestre": 1,
        }
        transaccion = MagicMock()
        transaccion.execute.side_effect = [alumno, paquete_legacy]

        with patch("backend.servicios.engine.begin") as begin:
            begin.return_value.__enter__.return_value = transaccion
            with self.assertRaises(servicios.Conflicto):
                servicios.asignar_paquete_horario("26320700", 99)

        self.assertEqual(transaccion.execute.call_count, 2)

    def test_migracion_conserva_inscripcion_con_historial_de_materia_coincidente(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 1,
            "estatus": "Activo",
            "eliminado": False,
        }
        paquete = MagicMock()
        paquete.mappings.return_value.first.return_value = {
            "id_paquete": 12,
            "nombre_paquete": "1ISC3",
            "semestre": 1,
        }
        destino = MagicMock()
        destino.mappings.return_value.all.return_value = [
            {
                "id_grupo": index + 100,
                "id_materia": index + 10,
                "turno": "Matutino",
                "cupo_disponible": 10,
            }
            for index in range(6)
        ]
        actual = MagicMock()
        actual.mappings.return_value.all.return_value = [{
            "id_inscripcion": 8,
            "id_grupo": 31,
            "id_materia": 10,
            "nombre_paquete": "1A",
        }]
        reserva = MagicMock(rowcount=1)
        transaccion = MagicMock()
        transaccion.execute.side_effect = [
            alumno,
            paquete,
            destino,
            actual,
            reserva,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.estado_horario_alumno", return_value={"asignado": True}),
        ):
            begin.return_value.__enter__.return_value = transaccion
            estado = servicios.reasignar_paquete_horario("26320700", 12)

        self.assertTrue(estado["asignado"])
        consultas = [str(llamada.args[0]) for llamada in transaccion.execute.call_args_list]
        self.assertTrue(any("UPDATE inscripciones_grupos SET id_grupo" in sql for sql in consultas))
        self.assertFalse(any("DELETE FROM inscripciones_grupos" in sql for sql in consultas))

    def test_migracion_se_detiene_antes_de_borrar_historial_sin_equivalencia(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 1,
            "estatus": "Activo",
            "eliminado": False,
        }
        paquete = MagicMock()
        paquete.mappings.return_value.first.return_value = {
            "id_paquete": 12,
            "nombre_paquete": "1ISC3",
            "semestre": 1,
        }
        destino = MagicMock()
        destino.mappings.return_value.all.return_value = [
            {
                "id_grupo": index + 100,
                "id_materia": index + 10,
                "turno": "Matutino",
                "cupo_disponible": 10,
            }
            for index in range(6)
        ]
        actual = MagicMock()
        actual.mappings.return_value.all.return_value = [{
            "id_inscripcion": 8,
            "id_grupo": 31,
            "id_materia": 99,
            "nombre_paquete": "1A",
        }]
        dependencias = MagicMock()
        dependencias.scalar_one.return_value = 1
        transaccion = MagicMock()
        transaccion.execute.side_effect = [alumno, paquete, destino, actual, dependencias]

        with patch("backend.servicios.engine.begin") as begin:
            begin.return_value.__enter__.return_value = transaccion
            with self.assertRaises(servicios.Conflicto):
                servicios.reasignar_paquete_horario("26320700", 12)

        self.assertEqual(transaccion.execute.call_count, 5)

    def test_horario_individual_se_descarga_como_pdf(self):
        estado = {
            "numero_control": "26320700",
            "nombre_completo": "Ana Prueba",
            "semestre": 1,
            "periodo": PERIODO_1ISC,
            "asignado": True,
            "paquete": {"nombre": "1ISC1"},
            "materias": [{"nombre_materia": "Cálculo Diferencial"}],
        }
        with (
            patch("backend.routers.horarios.servicios.estado_horario_alumno", return_value=estado),
            patch("backend.routers.horarios.reportes.generar_horario_alumno_pdf",
                  return_value=b"%PDF-horario"),
        ):
            respuesta = self.client.get("/horarios/alumnos/26320700/pdf")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["content-type"], "application/pdf")
        self.assertEqual(respuesta.content, b"%PDF-horario")

    def test_generadores_crean_los_dos_reportes_pdf(self):
        horario = generar_horario_alumno_pdf({
            "alumno": {
                "numero_control": "26320700",
                "nombre_completo": "Ana Prueba",
                "semestre": 1,
            },
            "paquete": {
                "nombre": "1ISC1",
                "semestre": 1,
                "periodo": PERIODO_1ISC,
            },
            "materias": [{
                "nombre_materia": "Cálculo Diferencial",
                "horarios": [{"dia": "Lunes", "inicio": "08:00", "fin": "09:00"}],
                "aula": "A-1",
                "docente": "Por asignar",
                "creditos": 5,
            }],
        })
        lista = generar_lista_grupo_pdf({
            "paquete": {
                "nombre": "1ISC1",
                "semestre": 1,
                "periodo": PERIODO_1ISC,
            },
            "alumnos": [{
                "numero_control": "26320700",
                "nombres": "Ana",
                "apellido_paterno": "Prueba",
                "apellido_materno": "",
                "correo_institucional": "ana@example.edu",
            }],
        })

        self.assertTrue(horario.startswith(b"%PDF-"))
        self.assertTrue(lista.startswith(b"%PDF-"))

    def test_endpoints_de_horario_se_publican(self):
        paths = app.openapi()["paths"]
        self.assertIn("post", paths["/horarios/alumnos/{numero_control}/paquete"])
        self.assertIn("put", paths["/horarios/alumnos/{numero_control}/paquete"])
        self.assertIn("get", paths["/horarios/grupos/{id_paquete}/alumnos/pdf"])
        self.assertIn("put", paths["/horarios/grupos/{id_grupo}/docente"])
        self.assertIn("get", paths["/horarios/docente/grupos"])


if __name__ == "__main__":
    unittest.main()
