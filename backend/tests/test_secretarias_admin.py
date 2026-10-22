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

    def test_administrador_puede_crear_secretaria_sin_exponer_password(self):
        resultado = {
            "id_usuario": 8,
            "correo": "nueva@example.com",
            "estatus": "Activo",
            "nombres": "Ana",
            "apellidos": "López",
        }
        with patch("backend.routers.admin.servicios.crear_secretaria", return_value=resultado) as crear:
            respuesta = self.client.post("/administracion/secretarias", json={
                "nombres": "Ana",
                "apellidos": "López",
                "correo": "ana@example.com",
                "password": "contraseña-segura",
            })

        self.assertEqual(respuesta.status_code, 201)
        self.assertNotIn("password", respuesta.json())
        crear.assert_called_once()

    def test_alta_rechaza_nombres_y_correos_formados_por_puntos(self):
        base = {
            "nombres": "Ana",
            "apellidos": "López",
            "correo": "ana@example.com",
            "password": "contraseña-segura",
        }
        for cambios in (
            {"nombres": "...."},
            {"apellidos": "...."},
            {"correo": "....@....com"},
            {"correo": "ana@example..com"},
        ):
            with self.subTest(cambios=cambios), patch(
                "backend.routers.admin.servicios.crear_secretaria"
            ) as crear:
                respuesta = self.client.post(
                    "/administracion/secretarias",
                    json=base | cambios,
                )
                self.assertEqual(respuesta.status_code, 422)
                crear.assert_not_called()

    def test_alta_rechaza_password_corta(self):
        respuesta = self.client.post("/administracion/secretarias", json={
            "nombres": "Ana",
            "apellidos": "López",
            "correo": "ana@example.com",
            "password": "corta",
        })
        self.assertEqual(respuesta.status_code, 422)

    def test_crear_secretaria_requiere_rol_administrador(self):
        self.usuario["rol"] = "Secretaría"
        with patch("backend.routers.admin.servicios.crear_secretaria") as crear:
            respuesta = self.client.post("/administracion/secretarias", json={
                "nombres": "Ana",
                "apellidos": "López",
                "correo": "ana@example.com",
                "password": "contraseña-segura",
            })

        self.assertEqual(respuesta.status_code, 403)
        crear.assert_not_called()

    def test_conflicto_de_correo_se_muestra_como_conflicto(self):
        with patch(
            "backend.routers.admin.servicios.crear_secretaria",
            side_effect=servicios.Conflicto("Ya existe una cuenta con ese correo."),
        ):
            respuesta = self.client.post("/administracion/secretarias", json={
                "nombres": "Ana",
                "apellidos": "López",
                "correo": "ana@example.com",
                "password": "contraseña-segura",
            })

        self.assertEqual(respuesta.status_code, 409)

    def test_baja_de_secretaria_requiere_administrador(self):
        self.usuario["rol"] = "Secretaría"
        respuesta = self.client.delete("/administracion/secretarias/7")
        self.assertEqual(respuesta.status_code, 403)


if __name__ == "__main__":
    unittest.main()
