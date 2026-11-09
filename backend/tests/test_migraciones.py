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
        resultado.scalar_one_or_none.side_effect = [
            "2026_11_04_domicilio_estructurado",
            "2026_11_08_registro_reinscripciones",
            "2026_11_08_reinscripciones_en_grupos",
            "2026_11_08_bajas_reinscripciones",
            "2026_11_09_apellidos_reinscripciones",
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        self.assertFalse(any("ALTER TABLE alumnos" in sql for sql in consultas))
        self.assertFalse(any("CREATE TABLE IF NOT EXISTS reinscripciones" in sql for sql in consultas))

    def test_aplica_migracion_de_reinscripciones_a_esquema_actualizado(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        resultado = MagicMock()
        resultado.scalar_one_or_none.side_effect = [
            "2026_11_04_domicilio_estructurado",
            None,
            None,
            None,
            None,
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        tabla = next(sql for sql in consultas if "CREATE TABLE IF NOT EXISTS reinscripciones" in sql)
        self.assertIn("semestre IN (2, 3)", tabla)
        self.assertTrue(any("2026_11_08_registro_reinscripciones" in str(llamada.args[1])
                            for llamada in conn.execute.call_args_list if len(llamada.args) > 1))
        self.assertIn("eliminado BOOLEAN NOT NULL DEFAULT FALSE", tabla)

    def test_migra_columnas_para_baja_logica_de_reinscripciones(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        inspector.get_columns.return_value = [
            {"name": "numero_control"},
            {"name": "nombre"},
            {"name": "apellidos"},
            {"name": "semestre"},
            {"name": "creado_en"},
        ]
        inspector.get_foreign_keys.return_value = []
        resultado = MagicMock()
        resultado.scalar_one_or_none.side_effect = [
            "2026_11_04_domicilio_estructurado",
            "2026_11_08_registro_reinscripciones",
            "2026_11_08_reinscripciones_en_grupos",
            None,
            None,
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        self.assertIn(
            "ALTER TABLE reinscripciones ADD COLUMN eliminado BOOLEAN NOT NULL DEFAULT FALSE",
            consultas,
        )
        self.assertIn("ALTER TABLE reinscripciones ADD COLUMN baja_en TIMESTAMP NULL", consultas)
        self.assertIn(
            "ALTER TABLE reinscripciones ADD COLUMN baja_id_usuario INT NULL",
            consultas,
        )
        self.assertIn(
            "ALTER TABLE reinscripciones ADD CONSTRAINT fk_reinscripciones_baja_usuario "
            "FOREIGN KEY (baja_id_usuario) REFERENCES usuarios(id_usuario)",
            consultas,
        )

    def test_separa_apellidos_anteriores_y_elimina_la_columna_legada(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        inspector.get_columns.return_value = [
            {"name": "numero_control"},
            {"name": "nombre"},
            {"name": "apellidos"},
            {"name": "semestre"},
        ]
        resultado = MagicMock()
        resultado.scalar_one_or_none.side_effect = [
            "2026_11_04_domicilio_estructurado",
            "2026_11_08_registro_reinscripciones",
            "2026_11_08_reinscripciones_en_grupos",
            "2026_11_08_bajas_reinscripciones",
            None,
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        agregar_paterno = next(
            indice for indice, consulta in enumerate(consultas)
            if "ADD COLUMN apellido_paterno" in consulta
        )
        agregar_materno = next(
            indice for indice, consulta in enumerate(consultas)
            if "ADD COLUMN apellido_materno" in consulta
        )
        separar_apellidos = next(
            indice for indice, consulta in enumerate(consultas)
            if "SUBSTRING_INDEX(TRIM(apellidos)" in consulta
        )
        eliminar_legado = next(
            indice for indice, consulta in enumerate(consultas)
            if "DROP COLUMN apellidos" in consulta
        )
        self.assertLess(agregar_paterno, separar_apellidos)
        self.assertLess(agregar_materno, separar_apellidos)
        self.assertLess(separar_apellidos, eliminar_legado)
        self.assertIn("LOCATE(' ', TRIM(apellidos))", consultas[separar_apellidos])

    def test_quita_fk_de_alumnos_para_permitir_reinscritos_en_grupos(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        inspector.get_foreign_keys.return_value = [{
            "name": "inscripciones_grupos_ibfk_1",
            "referred_table": "alumnos",
            "constrained_columns": ["numero_control"],
        }]
        resultado = MagicMock()
        resultado.scalar_one_or_none.side_effect = [
            "2026_11_04_domicilio_estructurado",
            "2026_11_08_registro_reinscripciones",
            None,
            None,
            None,
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado

        with patch("backend.migraciones.inspect", return_value=inspector):
            migraciones.aplicar_migraciones(conn)

        consultas = [str(llamada.args[0]) for llamada in conn.execute.call_args_list]
        self.assertIn(
            "ALTER TABLE inscripciones_grupos DROP FOREIGN KEY `inscripciones_grupos_ibfk_1`",
            consultas,
        )

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
