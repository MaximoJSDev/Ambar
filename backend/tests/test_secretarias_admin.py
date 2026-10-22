import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.deps import usuario_actual
from backend import servicios


class GestionSecretariasAdminTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 1, "rol": "Administrador"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_listar_secretarias_requiere_rol_administrador(self):
        self.usuario["rol"] = "Secretaría"
        respuesta = self.client.get("/administracion/secretarias")
        self.assertEqual(respuesta.status_code, 403)

    def test_bitacora_requiere_rol_administrador(self):
        self.usuario["rol"] = "Secretaría"
        respuesta = self.client.get("/administracion/bitacora")
        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_puede_consultar_bitacora(self):
        registros = [{
            "id_bitacora": 1,
            "fecha": "15/10/2026",
            "hora_entrada": "15:00:00",
            "hora_salida": None,
            "correo": "admin@example.com",
            "rol": "Administrador",
            "nombre": "Admin",
        }]
        with patch("backend.routers.admin.servicios.listar_bitacora_accesos", return_value=registros):
            respuesta = self.client.get("/administracion/bitacora")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), registros)

    def test_formatea_horas_mysql_recibidas_como_timedelta(self):
        self.assertEqual(
            servicios._formatear_hora(timedelta(hours=9, minutes=5, seconds=7)),
            "09:05:07",
        )
        self.assertEqual(
            servicios._formatear_hora(timedelta(hours=25, minutes=5)),
            "25:05:00",
        )
        self.assertIsNone(servicios._formatear_hora(None))

    def test_administrador_puede_consultar_secretarias(self):
        registros = [{
            "id_usuario": 7,
            "correo": "secretaria@example.com",
            "estatus": "Activo",
            "nombres": "Ana",
            "apellidos": "López",
        }]
        with patch("backend.routers.admin.servicios.listar_secretarias", return_value=registros):
            respuesta = self.client.get("/administracion/secretarias")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), registros)

    def test_baja_de_secretaria_requiere_administrador(self):
        self.usuario["rol"] = "Secretaría"
        respuesta = self.client.delete("/administracion/secretarias/7")
        self.assertEqual(respuesta.status_code, 403)


if __name__ == "__main__":
    unittest.main()
