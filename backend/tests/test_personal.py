import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend import servicios
from backend.deps import usuario_actual
from backend.main import app


class AltaDocentesTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 1, "rol": "Secretaría"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

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

    def test_lista_de_maestros_solo_depende_de_perfiles_reales(self):
        registros = [{
            "id_usuario": 8,
            "correo": "maria@example.com",
            "estatus": "Activo",
            "nombres": "María",
            "apellidos": "López",
        }]
        with patch("backend.servicios.engine.connect") as conectar:
            ejecutar = conectar.return_value.__enter__.return_value.execute
            ejecutar.return_value.mappings.return_value.all.return_value = registros
            resultado = servicios.listar_docentes()

        self.assertEqual(resultado, registros)
        consulta, parametros = ejecutar.call_args.args
        self.assertNotIn("por.asignar", str(consulta))
        self.assertEqual(parametros, {"rol": "Docente"})

    def test_migracion_elimina_marcador_sin_borrar_historial(self):
        conn = Mock()

        def ejecutar(consulta, parametros=None):
            sql = str(consulta)
            resultado = Mock()
            if "SHOW COLUMNS" in sql:
                resultado.mappings.return_value.first.return_value = {"Null": "YES"}
            elif "SELECT u.id_usuario, d.id_docente" in sql:
                resultado.mappings.return_value.first.return_value = {
                    "id_usuario": 17,
                    "id_docente": 23,
                }
            elif "SELECT" in sql and "AS total" in sql:
                resultado.scalar_one.return_value = 3
            return resultado

        conn.execute.side_effect = ejecutar
        servicios.migrar_docente_sin_asignar(conn)

        consultas = [str(c.args[0]) for c in conn.execute.call_args_list]
        self.assertTrue(any("UPDATE grupos SET id_docente = NULL" in sql for sql in consultas))
        self.assertTrue(any("DELETE FROM empleados_docentes" in sql for sql in consultas))
        self.assertTrue(any("UPDATE usuarios SET estatus = 'Inactivo'" in sql for sql in consultas))
        self.assertFalse(any("DELETE FROM usuarios" in sql for sql in consultas))

    def test_migracion_elimina_cuenta_marcadora_sin_referencias(self):
        conn = Mock()

        def ejecutar(consulta, parametros=None):
            sql = str(consulta)
            resultado = Mock()
            if "SHOW COLUMNS" in sql:
                resultado.mappings.return_value.first.return_value = {"Null": "NO"}
            elif "SELECT u.id_usuario, d.id_docente" in sql:
                resultado.mappings.return_value.first.return_value = {
                    "id_usuario": 17,
                    "id_docente": 23,
                }
            elif "SELECT" in sql and "AS total" in sql:
                resultado.scalar_one.return_value = 0
            return resultado

        conn.execute.side_effect = ejecutar
        servicios.migrar_docente_sin_asignar(conn)

        consultas = [str(c.args[0]) for c in conn.execute.call_args_list]
        self.assertTrue(any("ALTER TABLE grupos MODIFY id_docente INT NULL" in sql for sql in consultas))
        self.assertTrue(any("DELETE FROM empleados_docentes" in sql for sql in consultas))
        self.assertTrue(any("DELETE FROM usuarios" in sql for sql in consultas))

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
