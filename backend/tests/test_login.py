"""Pruebas de autenticación sin conexión a una base de datos real."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.seguridad import LoginGuard


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.guard = LoginGuard(3, 300)
        self.guard_patch = patch("backend.routers.auth.guard", self.guard)
        self.guard_patch.start()
        self.addCleanup(self.guard_patch.stop)

    def _engine_mocks(self, fila):
        conexion_lookup = MagicMock()
        conexion_lookup.__enter__.return_value.execute.return_value.mappings.return_value.first.return_value = fila
        conexion_registro = MagicMock()
        conexion_registro.__enter__.return_value.execute.return_value.lastrowid = 41
        return (
            patch("backend.routers.auth.engine.connect", return_value=conexion_lookup),
            patch("backend.routers.auth.engine.begin", return_value=conexion_registro),
        )

    def test_login_exitoso_normaliza_correo_y_devuelve_token_y_usuario(self):
        fila = {
            "id_usuario": 7,
            "correo": "ana@example.com",
            "password": "hash",
            "estatus": "Activo",
            "nombre": "Ana López",
            "rol": "Secretaría",
        }
        lookup, registro = self._engine_mocks(fila)
        with (
            lookup as conectar,
            registro as comenzar,
            patch("backend.routers.auth.seguridad.verificar", return_value=True),
            patch("backend.routers.auth.seguridad.crear_token", return_value="token-prueba"),
        ):
            respuesta = self.client.post(
                "/auth/login",
                json={"correo": " ANA@EXAMPLE.COM ", "password": "secreto"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["token"], "token-prueba")
        self.assertEqual(respuesta.json()["usuario"]["correo"], "ana@example.com")
        self.assertEqual(respuesta.json()["usuario"]["rol"], "Secretaría")
        self.assertNotIn("password", respuesta.json()["usuario"])
        conectar.assert_called_once_with()
        self.assertTrue(comenzar.called)

    def test_credenciales_incorrectas_tienen_respuesta_generica(self):
        lookup, _ = self._engine_mocks(None)
        with (
            lookup,
            patch("backend.routers.auth.seguridad.verificar", return_value=False),
        ):
            respuesta = self.client.post(
                "/auth/login",
                json={"correo": "desconocido@example.com", "password": "incorrecta"},
            )

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.json()["detail"]["mensaje"], "Credenciales incorrectas")
        self.assertEqual(respuesta.json()["detail"]["intentos_restantes"], 2)

    def test_cuenta_inactiva_no_puede_iniciar_sesion(self):
        fila = {
            "id_usuario": 7,
            "correo": "ana@example.com",
            "password": "hash",
            "estatus": "Inactivo",
            "nombre": "Ana López",
            "rol": "Secretaría",
        }
        lookup, _ = self._engine_mocks(fila)
        with (
            lookup,
            patch("backend.routers.auth.seguridad.verificar", return_value=True),
        ):
            respuesta = self.client.post(
                "/auth/login",
                json={"correo": "ana@example.com", "password": "secreto"},
            )

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.json()["detail"]["mensaje"], "Credenciales incorrectas")

    def test_cuenta_bloqueada_no_consulta_la_base_de_datos(self):
        self.guard.registrar_fallo("ana@example.com")
        self.guard.registrar_fallo("ana@example.com")
        self.guard.registrar_fallo("ana@example.com")

        with patch("backend.routers.auth.engine.connect") as conectar:
            respuesta = self.client.post(
                "/auth/login",
                json={"correo": "ana@example.com", "password": "secreto"},
            )

        self.assertEqual(respuesta.status_code, 423)
        self.assertGreater(respuesta.json()["detail"]["segundos"], 0)
        conectar.assert_not_called()

    def test_esquema_rechaza_login_sin_contrasena(self):
        respuesta = self.client.post("/auth/login", json={"correo": "ana@example.com", "password": ""})

        self.assertEqual(respuesta.status_code, 422)

    def test_esquema_rechaza_campos_omitidos_tipos_incorrectos_y_limites_excedidos(self):
        casos_invalidos = (
            {},
            {"correo": "ana@example.com"},
            {"correo": 123, "password": "secreto"},
            {"correo": "ana@example.com", "password": []},
            {"correo": "a" * 151 + "@example.com", "password": "secreto"},
            {"correo": "ana@example.com", "password": "x" * 201},
        )
        for datos in casos_invalidos:
            with self.subTest(datos=datos):
                respuesta = self.client.post("/auth/login", json=datos)
                self.assertEqual(respuesta.status_code, 422)

    def test_fallo_al_consultar_base_responde_500_y_no_se_convierte_en_error_de_credenciales(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "backend.routers.auth.engine.connect",
            side_effect=RuntimeError("Base de datos no disponible"),
        ):
            respuesta = client.post(
                "/auth/login",
                json={"correo": "ana@example.com", "password": "secreto"},
            )

        self.assertEqual(respuesta.status_code, 500)
        self.assertNotIn("Credenciales incorrectas", respuesta.text)


if __name__ == "__main__":
    unittest.main()
