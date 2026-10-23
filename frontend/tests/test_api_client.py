import json
from pathlib import Path
import tempfile
import unittest

import httpx

from api_client import ApiClient


class ApiClientTests(unittest.TestCase):
    def test_expediente_puede_incluir_bajas(self):
        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/alumnos/expediente")
            self.assertEqual(request.url.params["q"], "26320700")
            self.assertEqual(request.url.params["incluir_bajas"], "true")
            return httpx.Response(200, json={"numero_control": "26320700"})

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            expediente = cliente.expediente("26320700", incluir_bajas=True)
            self.assertEqual(expediente["numero_control"], "26320700")
        finally:
            cliente._http.close()

    def test_baja_y_historial_usan_sus_endpoints(self):
        respuestas = []

        def responder(request: httpx.Request) -> httpx.Response:
            respuestas.append((request.method, request.url.path))
            return httpx.Response(200, json={"mensaje": "ok"})

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            cliente.eliminar_alumno("26320700")
            cliente.historial_alumno("26320700")
        finally:
            cliente._http.close()

        self.assertEqual(respuestas, [
            ("DELETE", "/alumnos/26320700"),
            ("GET", "/alumnos/26320700/historial"),
        ])

    def test_actualizar_documentos_envia_pdf_en_multipart(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / "curp.pdf"
            archivo.write_bytes(b"%PDF-1.4 contenido")
            constancia = Path(tmp) / "constancia.pdf"
            constancia.write_bytes(b"%PDF-1.4 constancia")

            def responder(request: httpx.Request) -> httpx.Response:
                self.assertEqual(request.method, "PUT")
                self.assertEqual(request.url.path, "/alumnos/26320700/documentos")
                self.assertIn("multipart/form-data", request.headers["content-type"])
                contenido = request.read()
                self.assertIn(b'name="doc_curp"', contenido)
                self.assertIn(b"%PDF-1.4 contenido", contenido)
                self.assertIn(b'name="doc_constancia_situacion_fiscal"', contenido)
                self.assertIn(b"%PDF-1.4 constancia", contenido)
                return httpx.Response(200, json={"mensaje": "ok"})

            cliente = ApiClient()
            cliente._http.close()
            cliente._http = httpx.Client(
                base_url="http://test",
                transport=httpx.MockTransport(responder),
            )
            try:
                cliente.actualizar_documentos("26320700", {
                    "CURP": str(archivo),
                    "Constancia de situación fiscal": str(constancia),
                })
            finally:
                cliente._http.close()

    def test_descargar_expediente_devuelve_el_contenido_pdf(self):
        pdf = b"%PDF-test"

        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/alumnos/expediente/pdf")
            self.assertEqual(request.url.params["q"], "26320700")
            self.assertEqual(request.url.params["incluir_bajas"], "false")
            self.assertEqual(request.headers["Authorization"], "Bearer token-de-prueba")
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        cliente.token = "token-de-prueba"
        try:
            self.assertEqual(cliente.descargar_expediente("26320700"), pdf)
        finally:
            cliente._http.close()

    def test_gestion_secretarias_usa_endpoints_de_administracion(self):
        solicitudes = []

        def responder(request: httpx.Request) -> httpx.Response:
            solicitudes.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json=[])
            return httpx.Response(200, json={"mensaje": "Cuenta dada de baja"})

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            self.assertEqual(cliente.secretarias(), [])
            cliente.crear_secretaria({
                "nombres": "Ana",
                "apellidos": "López",
                "correo": "ana@example.com",
                "password": "contraseña-segura",
            })
            cliente.dar_baja_secretaria(12)
        finally:
            cliente._http.close()

        self.assertEqual(solicitudes, [
            ("GET", "/administracion/secretarias"),
            ("POST", "/administracion/secretarias"),
            ("DELETE", "/administracion/secretarias/12"),
        ])

    def test_calificaciones_y_fechas_de_periodos_usan_sus_endpoints(self):
        solicitudes = []

        def responder(request: httpx.Request) -> httpx.Response:
            solicitudes.append((request.method, request.url.path, request.read()))
            return httpx.Response(200, json={"valor": 85})

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            cliente.guardar_calificacion_docente(7, "26320700", "Semana 5", 85)
            cliente.confirmar_calificacion_final(7, "26320700")
            cliente.guardar_periodo_escolar("AGO-DIC 2026", "2026-08-24")
            cliente.guardar_periodo_escolar(
                "AGO-DIC 2026", "2026-08-24", "ENE-JUN 2026",
            )
        finally:
            cliente._http.close()

        self.assertEqual(
            [(metodo, ruta) for metodo, ruta, _ in solicitudes],
            [
                ("PUT", "/horarios/docente/grupos/7/alumnos/26320700/calificaciones/Semana 5"),
                ("POST", "/horarios/docente/grupos/7/alumnos/26320700/calificaciones/final"),
                ("PUT", "/administracion/periodos"),
                ("PUT", "/administracion/periodos"),
            ],
        )
        self.assertEqual(json.loads(solicitudes[0][2]), {"valor": 85})
        self.assertEqual(json.loads(solicitudes[2][2]), {
            "periodo": "AGO-DIC 2026",
            "fecha_inicio": "2026-08-24",
            "periodo_anterior": None,
        })
        self.assertEqual(json.loads(solicitudes[3][2]), {
            "periodo": "AGO-DIC 2026",
            "fecha_inicio": "2026-08-24",
            "periodo_anterior": "ENE-JUN 2026",
        })

    def test_descargas_docentes_usan_endpoints_de_grupos_listas_y_calificaciones(self):
        solicitudes = []

        def responder(request: httpx.Request) -> httpx.Response:
            solicitudes.append(request.url.path)
            return httpx.Response(
                200,
                content=b"%PDF-test",
                headers={"content-type": "application/pdf"},
            )

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            self.assertEqual(cliente.descargar_grupos_docente(), b"%PDF-test")
            self.assertEqual(cliente.descargar_lista_alumnos_docente(7), b"%PDF-test")
            self.assertEqual(cliente.descargar_calificaciones_docente(7), b"%PDF-test")
        finally:
            cliente._http.close()

        self.assertEqual(solicitudes, [
            "/horarios/docente/grupos/pdf",
            "/horarios/docente/grupos/7/alumnos/pdf",
            "/horarios/docente/grupos/7/calificaciones/pdf",
        ])

    def test_bitacora_usa_endpoint_admin(self):
        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/administracion/bitacora")
            return httpx.Response(200, json=[])

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            self.assertEqual(cliente.bitacora(), [])
        finally:
            cliente._http.close()

    def test_crear_docente_usa_endpoint_de_personal(self):
        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/personal/docentes")
            self.assertEqual(json.loads(request.read()), {"nombres": "María"})
            return httpx.Response(201, json={"id_usuario": 1})

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            self.assertEqual(cliente.crear_docente({"nombres": "María"}), {"id_usuario": 1})
        finally:
            cliente._http.close()

    def test_docente_consulta_sus_grupos(self):
        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/horarios/docente/grupos")
            return httpx.Response(200, json=[{"id_grupo": 7, "grupo": "1ISC1"}])

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            self.assertEqual(cliente.grupos_docente(), [{"id_grupo": 7, "grupo": "1ISC1"}])
        finally:
            cliente._http.close()

    def test_consultar_y_dar_de_baja_maestro_usan_endpoints_personal(self):
        solicitudes = []

        def responder(request: httpx.Request) -> httpx.Response:
            solicitudes.append((request.method, request.url.path))
            if request.method == "DELETE":
                return httpx.Response(200, json={"mensaje": "Cuenta dada de baja"})
            return httpx.Response(200, json=[])

        cliente = ApiClient()
        cliente._http.close()
        cliente._http = httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(responder),
        )
        try:
            self.assertEqual(cliente.docentes(), [])
            self.assertEqual(
                cliente.dar_baja_docente(8),
                {"mensaje": "Cuenta dada de baja"},
            )
        finally:
            cliente._http.close()

        self.assertEqual(solicitudes, [
            ("GET", "/personal/docentes"),
            ("DELETE", "/personal/docentes/8"),
        ])
