import unittest

import httpx

from api_client import ApiClient


class ApiClientTests(unittest.TestCase):
    def test_descargar_expediente_devuelve_el_contenido_pdf(self):
        pdf = b"%PDF-test"

        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/alumnos/expediente/pdf")
            self.assertEqual(request.url.params["q"], "26320700")
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
