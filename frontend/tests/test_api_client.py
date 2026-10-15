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
