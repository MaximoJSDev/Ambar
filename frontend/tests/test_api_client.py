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
