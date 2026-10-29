import unittest
import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import reportes, servicios
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

    def test_asignar_docente_rechaza_traslape_de_horario_en_mismo_dia(self):
        grupo = MagicMock()
        grupo.mappings.return_value.first.return_value = {"id_grupo": 7}
        paquete = MagicMock()
        paquete.scalar_one.return_value = 3
        docente = MagicMock()
        docente.first.return_value = {"id_docente": 12}
        traslape = MagicMock()
        traslape.mappings.return_value.first.return_value = {
            "nombre_materia": "Cálculo Diferencial",
            "dia_semana": 1,
            "hora_inicio": datetime.timedelta(hours=11),
            "hora_fin": datetime.timedelta(hours=12),
        }
        conn = MagicMock()
        conn.execute.side_effect = [grupo, paquete, docente, traslape]

        with patch("backend.servicios.engine.begin") as begin:
            begin.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(
                servicios.Conflicto,
                "Cálculo Diferencial.*lunes de 11:00 a 12:00",
            ):
                servicios.actualizar_docente_grupo(8, 12)

        self.assertEqual(conn.execute.call_count, 4)
        consulta_traslape = str(conn.execute.call_args_list[3].args[0])
        self.assertIn("nuevo.hora_inicio < h.hora_fin", consulta_traslape)
        self.assertIn("h.hora_inicio < nuevo.hora_fin", consulta_traslape)
        self.assertNotIn(
            "UPDATE grupos SET id_docente",
            " ".join(str(llamada.args[0]) for llamada in conn.execute.call_args_list),
        )

    def test_asignar_docente_acepta_horarios_adyacentes_sin_traslape(self):
        grupo = MagicMock()
        grupo.mappings.return_value.first.return_value = {"id_grupo": 7}
        paquete = MagicMock()
        paquete.scalar_one.return_value = 3
        docente = MagicMock()
        docente.first.return_value = {"id_docente": 12}
        sin_traslape = MagicMock()
        sin_traslape.mappings.return_value.first.return_value = None
        conn = MagicMock()
        conn.execute.side_effect = [grupo, paquete, docente, sin_traslape, MagicMock()]
        detalle = {"paquete": {"id_paquete": 3}, "materias": []}

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.detalle_paquete_horario", return_value=detalle),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.actualizar_docente_grupo(8, 12)

        self.assertEqual(resultado, detalle)
        self.assertIn(
            "UPDATE grupos SET id_docente",
            str(conn.execute.call_args_list[4].args[0]),
        )

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

    def test_docente_descarga_sus_grupos_con_membrete(self):
        self.usuario.update({"id_usuario": 42, "rol": "Docente"})
        grupos = [{
            "id_grupo": 7,
            "grupo": "1ISC1",
            "nombre_materia": "Cálculo Diferencial",
            "docente": "Docente Prueba",
            "horarios": [],
            "alumnos": [],
        }]
        with (
            patch("backend.routers.horarios.servicios.listar_grupos_docente", return_value=grupos) as listar,
            patch("backend.routers.horarios.reportes.generar_grupos_docente_pdf", return_value=b"%PDF-grupos") as pdf,
        ):
            respuesta = self.client.get("/horarios/docente/grupos/pdf")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.content, b"%PDF-grupos")
        self.assertEqual(respuesta.headers["content-type"], "application/pdf")
        listar.assert_called_once_with(42)
        pdf.assert_called_once_with({"docente": "Docente Prueba", "grupos": grupos})

    def test_docente_descarga_listas_solo_de_sus_grupos(self):
        self.usuario.update({"id_usuario": 42, "rol": "Docente"})
        grupos = [{
            "id_grupo": 7,
            "grupo": "1ISC1",
            "docente": "Docente Prueba",
            "alumnos": [],
        }]
        with (
            patch("backend.routers.horarios.servicios.listar_grupos_docente", return_value=grupos) as listar,
            patch("backend.routers.horarios.reportes.generar_lista_docente_pdf", return_value=b"%PDF-lista") as pdf,
        ):
            alumnos = self.client.get("/horarios/docente/grupos/7/alumnos/pdf")
            calificaciones = self.client.get("/horarios/docente/grupos/7/calificaciones/pdf")
            ajeno = self.client.get("/horarios/docente/grupos/8/alumnos/pdf")

        self.assertEqual(alumnos.status_code, 200)
        self.assertEqual(calificaciones.status_code, 200)
        self.assertEqual(alumnos.content, b"%PDF-lista")
        self.assertEqual(calificaciones.content, b"%PDF-lista")
        self.assertEqual(ajeno.status_code, 404)
        self.assertEqual(listar.call_count, 3)
        pdf.assert_any_call(grupos[0])
        pdf.assert_any_call(grupos[0], incluir_calificaciones=True)
        self.assertEqual(pdf.call_count, 2)

    def test_descarga_pdf_docente_rechaza_otros_roles(self):
        self.usuario["rol"] = "Secretaría"
        with patch("backend.routers.horarios.servicios.listar_grupos_docente") as listar:
            respuesta = self.client.get("/horarios/docente/grupos/pdf")

        self.assertEqual(respuesta.status_code, 403)
        listar.assert_not_called()

    def test_consulta_de_grupos_docente_rechaza_otros_roles(self):
        for rol in ("Secretaría", "Administrador"):
            with self.subTest(rol=rol):
                self.usuario["rol"] = rol
                with patch("backend.routers.horarios.servicios.listar_grupos_docente") as listar:
                    respuesta = self.client.get("/horarios/docente/grupos")

                self.assertEqual(respuesta.status_code, 403)
                listar.assert_not_called()

    def test_docente_guarda_calificacion_valida_de_periodo_habilitado(self):
        self.usuario.update({"id_usuario": 42, "rol": "Docente"})
        with patch(
            "backend.routers.horarios.servicios.guardar_calificacion_docente",
            return_value={"valor": 85},
        ) as guardar:
            respuesta = self.client.put(
                "/horarios/docente/grupos/7/alumnos/26320700/calificaciones/Semana%205",
                json={"valor": 85},
            )

        self.assertEqual(respuesta.status_code, 200)
        guardar.assert_called_once_with(42, 7, "26320700", "Semana 5", 85)

    def test_docente_no_guarda_calificaciones_reprobatorias_distintas_de_cero(self):
        self.usuario.update({"id_usuario": 42, "rol": "Docente"})
        with patch("backend.routers.horarios.servicios.guardar_calificacion_docente") as guardar:
            respuesta = self.client.put(
                "/horarios/docente/grupos/7/alumnos/26320700/calificaciones/Semana%205",
                json={"valor": 69},
            )

        self.assertEqual(respuesta.status_code, 422)
        guardar.assert_not_called()

    def test_docente_confirma_calificacion_final(self):
        self.usuario.update({"id_usuario": 42, "rol": "Docente"})
        final = {"valor": 90, "confirmada": True}
        with patch(
            "backend.routers.horarios.servicios.confirmar_calificacion_final_docente",
            return_value=final,
        ) as confirmar:
            respuesta = self.client.post(
                "/horarios/docente/grupos/7/alumnos/26320700/calificaciones/final",
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), final)
        confirmar.assert_called_once_with(42, 7, "26320700")

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
                "docente_nombres": "Docente",
                "docente_apellidos": "Prueba",
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
                "docente_nombres": "Docente",
                "docente_apellidos": "Prueba",
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
            "final_confirmada": 0,
        }]
        resultado_inicio = MagicMock()
        resultado_inicio.scalar_one_or_none.return_value = datetime.date(2026, 8, 24)
        conn = MagicMock()
        conn.execute.side_effect = [resultado_inicio, resultado_grupos, resultado_alumnos]

        with patch("backend.servicios.engine.connect") as conectar:
            conectar.return_value.__enter__.return_value = conn
            grupos = servicios.listar_grupos_docente(42)

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]["horarios"], [
            {"dia": "Lunes", "inicio": "08:00", "fin": "09:00"},
            {"dia": "Miércoles", "inicio": "08:00", "fin": "09:00"},
        ])
        self.assertEqual(grupos[0]["docente"], "Docente Prueba")
        self.assertEqual(grupos[0]["alumnos"], [{
            "numero_control": "26320700",
            "nombres": "Ana",
            "apellido_paterno": "Prueba",
            "apellido_materno": None,
            "nombre_completo": "Prueba Ana",
            "semana_5": 90,
            "semana_9": None,
            "semana_13": 88,
            "final": None,
            "final_confirmada": False,
        }])
        self.assertEqual(conn.execute.call_args_list[1].args[1]["usuario"], 42)
        self.assertIn("g.id_docente = d.id_docente", str(conn.execute.call_args_list[1].args[0]))
        self.assertIn(
            "ORDER BY i.id_grupo, a.apellido_paterno, a.apellido_materno",
            str(conn.execute.call_args_list[2].args[0]),
        )

    def test_secretaria_puede_consultar_paquetes_del_semestre(self):
        paquetes = [{"id_paquete": 5, "nombre": "1ISC1", "semestre": 1}]
        with patch("backend.routers.horarios.servicios.listar_paquetes_horario",
                   return_value=paquetes) as listar:
            respuesta = self.client.get("/horarios/paquetes?semestre=1")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), paquetes)
        listar.assert_called_once_with(1)

    def test_asignar_docente_devuelve_conflicto_si_hay_traslape(self):
        mensaje = "El maestro ya tiene asignada la materia «Cálculo» el lunes de 11:00 a 12:00."
        with patch(
            "backend.routers.horarios.servicios.actualizar_docente_grupo",
            side_effect=servicios.Conflicto(mensaje),
        ) as asignar:
            respuesta = self.client.put(
                "/horarios/grupos/8/docente",
                json={"id_docente": 12},
            )

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["detail"]["mensaje"], mensaje)
        asignar.assert_called_once_with(8, 12)

    def test_alta_consulta_horario_sin_paquete(self):
        estado = {
            "numero_control": "26320700",
            "semestre": 1,
            "periodo": PERIODO_1ISC,
            "docente": "Docente Prueba",
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

    def test_no_hay_endpoint_para_reasignar_paquetes(self):
        respuesta = self.client.put(
            "/horarios/alumnos/26320700/paquete",
            json={"id_paquete": 12},
        )
        self.assertEqual(respuesta.status_code, 405)

    def test_servicio_no_asigna_paquetes_ajenos_al_catalogo_oficial(self):
        alumno = MagicMock()
        alumno.mappings.return_value.first.return_value = {
            "semestre_actual": 1,
            "estatus": "Activo",
            "eliminado": False,
        }
        paquete_no_oficial = MagicMock()
        paquete_no_oficial.mappings.return_value.first.return_value = {
            "id_paquete": 99,
            "nombre_paquete": "NO-OFICIAL",
            "semestre": 1,
        }
        transaccion = MagicMock()
        transaccion.execute.side_effect = [alumno, paquete_no_oficial]

        with patch("backend.servicios.engine.begin") as begin:
            begin.return_value.__enter__.return_value = transaccion
            with self.assertRaises(servicios.Conflicto):
                servicios.asignar_paquete_horario("26320700", 99)

        self.assertEqual(transaccion.execute.call_count, 2)

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
        datos_docente = {
            "docente": "Docente Prueba",
            "grupo": "1ISC1",
            "nombre_materia": "Cálculo Diferencial",
            "periodo": PERIODO_1ISC,
            "alumnos": [{
                "numero_control": "26320700",
                "nombre_completo": "Ana Prueba",
                "semana_5": 90,
                "semana_9": None,
                "semana_13": 88,
                "final": 89,
            }],
        }
        grupos_docente = reportes.generar_grupos_docente_pdf({
            "docente": "Docente Prueba",
            "grupos": [{
                **datos_docente,
                "horarios": [{"dia": "Lunes", "inicio": "08:00", "fin": "09:00"}],
                "aula": "A-1",
                "turno": "Matutino",
            }],
        })
        lista_docente = reportes.generar_lista_docente_pdf(datos_docente)
        calificaciones_docente = reportes.generar_lista_docente_pdf(
            datos_docente, incluir_calificaciones=True,
        )

        self.assertTrue(horario.startswith(b"%PDF-"))
        self.assertTrue(lista.startswith(b"%PDF-"))
        self.assertTrue(grupos_docente.startswith(b"%PDF-"))
        self.assertTrue(lista_docente.startswith(b"%PDF-"))
        self.assertTrue(calificaciones_docente.startswith(b"%PDF-"))

    def test_endpoints_de_horario_se_publican(self):
        paths = app.openapi()["paths"]
        self.assertIn("post", paths["/horarios/alumnos/{numero_control}/paquete"])
        self.assertNotIn("put", paths["/horarios/alumnos/{numero_control}/paquete"])
        self.assertIn("get", paths["/horarios/grupos/{id_paquete}/alumnos/pdf"])
        self.assertIn("put", paths["/horarios/grupos/{id_grupo}/docente"])
        self.assertIn("get", paths["/horarios/docente/grupos"])
        self.assertIn("get", paths["/horarios/docente/grupos/pdf"])
        self.assertIn("get", paths["/horarios/docente/grupos/{id_grupo}/alumnos/pdf"])
        self.assertIn("get", paths["/horarios/docente/grupos/{id_grupo}/calificaciones/pdf"])


if __name__ == "__main__":
    unittest.main()
