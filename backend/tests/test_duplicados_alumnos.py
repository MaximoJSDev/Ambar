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
            "ine": "CASTAN05030212H100",
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
            "castan05030212h100",
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


if __name__ == "__main__":
    unittest.main()
