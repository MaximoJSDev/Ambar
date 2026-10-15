import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.deps import usuario_actual
from backend.main import app
from backend import servicios


class AltaDocentesTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 1, "rol": "Secretaría"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_alta_requiere_rol_secretaria(self):
        self.usuario["rol"] = "Administrador"
        respuesta = self.client.post("/personal/docentes", json={
            "nombres": "María",
            "apellidos": "López",
            "correo": "maria@example.com",
            "password": "contraseña-segura",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_secretaria_crea_docente_sin_exponer_password(self):
        resultado = {
            "id_usuario": 8,
            "correo": "maria@example.com",
            "estatus": "Activo",
            "nombres": "María",
            "apellidos": "López",
        }
        with patch("backend.routers.personal.servicios.crear_docente", return_value=resultado) as crear:
            respuesta = self.client.post("/personal/docentes", json={
                "nombres": "María",
                "apellidos": "López",
                "correo": "MARIA@example.com",
                "password": "contraseña-segura",
            })

        self.assertEqual(respuesta.status_code, 201)
        self.assertNotIn("password", respuesta.json())
        crear.assert_called_once()
        self.assertEqual(crear.call_args.args[0].correo, "maria@example.com")

    def test_alta_rechaza_correo_invalido_y_password_corta(self):
        base = {
            "nombres": "María",
            "apellidos": "López",
        }
        for cambios in (
            {"correo": "no-es-correo", "password": "contraseña-segura"},
            {"correo": "maria@example.com", "password": "corta"},
        ):
            with self.subTest(cambios=cambios):
                respuesta = self.client.post(
                    "/personal/docentes",
                    json=base | cambios,
                )
                self.assertEqual(respuesta.status_code, 422)

    def test_correo_duplicado_se_muestra_como_conflicto(self):
        with patch(
            "backend.routers.personal.servicios.crear_docente",
            side_effect=servicios.Conflicto("Ya existe una cuenta con ese correo."),
        ):
            respuesta = self.client.post("/personal/docentes", json={
                "nombres": "María",
                "apellidos": "López",
                "correo": "maria@example.com",
                "password": "contraseña-segura",
            })

        self.assertEqual(respuesta.status_code, 409)

    def test_secretaria_puede_consultar_maestros(self):
        registros = [{
            "id_usuario": 8,
            "correo": "maria@example.com",
            "estatus": "Activo",
            "nombres": "María",
            "apellidos": "López",
        }]
        with patch("backend.routers.personal.servicios.listar_docentes", return_value=registros):
            respuesta = self.client.get("/personal/docentes")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), registros)

    def test_consulta_de_maestros_requiere_rol_secretaria(self):
        self.usuario["rol"] = "Administrador"
        respuesta = self.client.get("/personal/docentes")
        self.assertEqual(respuesta.status_code, 403)

    def test_secretaria_puede_dar_de_baja_maestro(self):
        registro = {
            "id_usuario": 8,
            "correo": "maria@example.com",
            "estatus": "Inactivo",
            "nombres": "María",
            "apellidos": "López",
        }
        with patch(
            "backend.routers.personal.servicios.dar_baja_docente",
            return_value=registro,
        ) as dar_baja:
            respuesta = self.client.delete("/personal/docentes/8")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["docente"], registro)
        dar_baja.assert_called_once_with(8)

    def test_dar_de_baja_maestro_inexistente_devuelve_404(self):
        with patch(
            "backend.routers.personal.servicios.dar_baja_docente",
            side_effect=servicios.NoEncontrado(),
        ):
            respuesta = self.client.delete("/personal/docentes/999")
        self.assertEqual(respuesta.status_code, 404)


if __name__ == "__main__":
    unittest.main()
