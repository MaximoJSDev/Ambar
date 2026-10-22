"""Pruebas del alta de docentes y sus reglas de acceso y validación."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import servicios
from backend.deps import usuario_actual
from backend.main import app


class AltaDocentesTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 1, "rol": "Secretaría"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)

    @staticmethod
    def payload(**cambios):
        return {
            "nombres": "María",
            "apellidos": "López",
            "correo": "maria@acapulco.tecnm.mx",
            "password": "contraseña-segura",
        } | cambios

    def test_secretaria_crea_docente_y_no_expone_password(self):
        docente = {
            "id_usuario": 8,
            "correo": "maria@acapulco.tecnm.mx",
            "estatus": "Activo",
            "nombres": "María",
            "apellidos": "López",
        }
        with patch(
            "backend.routers.personal.servicios.crear_docente",
            return_value=docente,
        ) as crear:
            respuesta = self.client.post(
                "/personal/docentes",
                json=self.payload(correo="MARIA@ACAPULCO.TECNM.MX"),
            )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json(), docente)
        self.assertNotIn("password", respuesta.json())
        crear.assert_called_once()
        self.assertEqual(crear.call_args.args[0].correo, "maria@acapulco.tecnm.mx")

    def test_alta_requiere_rol_secretaria(self):
        self.usuario["rol"] = "Administrador"

        with patch("backend.routers.personal.servicios.crear_docente") as crear:
            respuesta = self.client.post("/personal/docentes", json=self.payload())

        self.assertEqual(respuesta.status_code, 403)
        crear.assert_not_called()

    def test_rechaza_datos_invalidos_sin_intentar_crear_cuenta(self):
        casos_invalidos = (
            {"nombres": "A"},
            {"apellidos": "B"},
            {"nombres": " "},
            {"apellidos": "  "},
            {"nombres": "...."},
            {"apellidos": "!!!"},
            {"correo": "ana@example..com"},
            {"correo": "no-es-correo"},
            {"correo": "maria@example.com"},
            {"password": "corta"},
            {"password": "          "},
        )
        with patch("backend.routers.personal.servicios.crear_docente") as crear:
            for cambios in casos_invalidos:
                with self.subTest(cambios=cambios):
                    respuesta = self.client.post(
                        "/personal/docentes",
                        json=self.payload(**cambios),
                    )
                    self.assertEqual(respuesta.status_code, 422)
            crear.assert_not_called()

    def test_acepta_longitudes_maximas_de_nombre_y_apellido(self):
        datos = self.payload(nombres="A" * 50, apellidos="B" * 50)
        with patch(
            "backend.routers.personal.servicios.crear_docente",
            return_value={"id_usuario": 8, "correo": "maria@acapulco.tecnm.mx"},
        ) as crear:
            respuesta = self.client.post("/personal/docentes", json=datos)

        self.assertEqual(respuesta.status_code, 201, msg=respuesta.text)
        crear.assert_called_once()

    def test_rechaza_un_caracter_mas_que_los_limites_de_nombre_y_apellido(self):
        with patch("backend.routers.personal.servicios.crear_docente") as crear:
            for campo, longitud in (("nombres", 51), ("apellidos", 51)):
                with self.subTest(campo=campo):
                    respuesta = self.client.post(
                        "/personal/docentes",
                        json=self.payload(**{campo: "A" * longitud}),
                    )
                    self.assertEqual(respuesta.status_code, 422)
            crear.assert_not_called()

    def test_error_no_controlado_del_servicio_responde_500(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "backend.routers.personal.servicios.crear_docente",
            side_effect=RuntimeError("Fallo de almacenamiento"),
        ):
            respuesta = client.post(
                "/personal/docentes",
                json=self.payload(),
            )

        self.assertEqual(respuesta.status_code, 500)

    def test_correo_duplicado_devuelve_conflicto(self):
        with patch(
            "backend.routers.personal.servicios.crear_docente",
            side_effect=servicios.Conflicto("Ya existe una cuenta con ese correo."),
        ):
            respuesta = self.client.post("/personal/docentes", json=self.payload())

        self.assertEqual(respuesta.status_code, 409)


if __name__ == "__main__":
    unittest.main()
