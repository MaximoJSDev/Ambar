"""Pruebas de detección de datos identificadores duplicados."""
import unittest
from unittest.mock import Mock

from backend.servicios import duplicados


class DuplicadosAlumnoTests(unittest.TestCase):
    def test_detecta_identificadores_y_correo_sin_distinguir_mayusculas(self):
        fila = {
            "numero_ficha": "2026123456",
            "curp": "CAJG050302HGRSSLA4",
            "nss": "12345678901",
            "rfc": "CAJG050302AB1",
            "ine": "1234 5678 90123",
            "correo_personal": "Alumno@Example.com",
        }
        resultado = Mock()
        resultado.mappings.return_value.all.return_value = [fila]
        conn = Mock()
        conn.execute.return_value = resultado

        duplicados_encontrados = duplicados(
            conn,
            "2026123456",
            "cajg050302hgrssla4",
            "12345678901",
            "cajg050302ab1",
            "1234 5678 90123",
            "alumno@example.com",
        )

        self.assertEqual(
            duplicados_encontrados,
            {
                "ficha": True,
                "curp": True,
                "nss": True,
                "rfc": True,
                "ine": True,
                "correo": True,
            },
        )
        parametros = conn.execute.call_args.args[1]
        self.assertEqual(parametros["correo"], "alumno@example.com")
        self.assertEqual(parametros["ine"], "1234567890123")
        self.assertIn("REPLACE(UPPER(ine), ' ', '')", str(conn.execute.call_args.args[0]))

    def test_no_consulta_si_no_se_envian_identificadores(self):
        conn = Mock()

        resultado = duplicados(conn, "", "")

        self.assertEqual(set(resultado.values()), {False})
        conn.execute.assert_not_called()

    def test_excluye_el_expediente_actual_al_editar(self):
        resultado = Mock()
        resultado.mappings.return_value.all.return_value = []
        conn = Mock()
        conn.execute.return_value = resultado

        duplicados(conn, "2026123456", "CAJG050302HGRSSLA4", excluir_numero_control="26320700")

        consulta, parametros = conn.execute.call_args.args
        self.assertIn("numero_control != :excluir_numero_control", str(consulta))
        self.assertEqual(parametros["excluir_numero_control"], "26320700")

    def test_detecta_ine_al_normalizar_espacios_de_la_base(self):
        fila = {
            "numero_ficha": "",
            "curp": "",
            "nss": "",
            "rfc": "",
            "ine": "1234 5678 90123",
            "correo_personal": "",
        }
        resultado = Mock()
        resultado.mappings.return_value.all.return_value = [fila]
        conn = Mock()
        conn.execute.return_value = resultado

        duplicados_encontrados = duplicados(conn, "", "", ine="1234567890123")

        self.assertTrue(duplicados_encontrados["ine"])


if __name__ == "__main__":
    unittest.main()
