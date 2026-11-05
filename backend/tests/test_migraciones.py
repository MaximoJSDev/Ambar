import unittest
from unittest.mock import MagicMock, patch

from backend import migraciones


class MigracionesTests(unittest.TestCase):
    def test_migra_el_domicilio_antiguo_y_lo_registra(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        inspector.get_columns.return_value = [{"name": "numero_control"}, {"name": "domicilio"}]
        conn = MagicMock()
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = None
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        crear_domicilios = next(i for i, sql in enumerate(consultas) if "CREATE TABLE IF NOT EXISTS domicilios" in sql)
        copiar_domicilios = next(i for i, sql in enumerate(consultas) if "INSERT INTO domicilios" in sql)
        quitar_columna = next(i for i, sql in enumerate(consultas) if "DROP COLUMN domicilio" in sql)
        registrar = next(i for i, sql in enumerate(consultas) if "INSERT INTO ambar_schema_migrations" in sql)
        self.assertLess(crear_domicilios, copiar_domicilios)
        self.assertLess(copiar_domicilios, quitar_columna)
        self.assertLess(quitar_columna, registrar)
        self.assertIn("LEFT JOIN domicilios", consultas[copiar_domicilios])

    def test_no_repite_una_migracion_registrada(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = "2026_11_04_domicilio_estructurado"
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        self.assertFalse(any("ALTER TABLE alumnos" in sql for sql in consultas))

    def test_falla_con_error_claro_si_falta_la_tabla_alumnos(self):
        inspector = MagicMock()
        inspector.has_table.return_value = False

        with (
            patch("backend.migraciones.inspect", return_value=inspector),
            self.assertRaisesRegex(RuntimeError, "No existe la tabla alumnos"),
        ):
            migraciones.aplicar_migraciones(MagicMock())


if __name__ == "__main__":
    unittest.main()
