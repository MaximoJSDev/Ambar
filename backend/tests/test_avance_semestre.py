import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from backend import servicios


class AvanceSemestreTests(unittest.TestCase):
    def test_no_avanza_antes_de_la_semana_18(self):
        periodo = MagicMock()
        periodo.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 8, 24),
        }
        conn = MagicMock()
        conn.execute.return_value = periodo

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=17),
        ):
            begin.return_value.__enter__.return_value = conn
            self.assertIsNone(servicios.avanzar_semestre_si_corresponde())

        conn.execute.assert_called_once()

    def test_avanza_una_vez_a_todos_los_alumnos_activos_y_cap_en_decimo(self):
        periodo = MagicMock()
        periodo.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 8, 24),
        }
        avance = MagicMock()
        avance.scalar_one_or_none.return_value = None
        actualizacion = MagicMock()
        actualizacion.rowcount = 3
        conn = MagicMock()
        conn.execute.side_effect = [periodo, avance, MagicMock(), actualizacion, MagicMock()]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=18),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.avanzar_semestre_si_corresponde()

        self.assertEqual(
            resultado,
            {"periodo": "AGO-DIC 2026", "semana": 18, "alumnos_avanzados": 3},
        )
        consulta = str(conn.execute.call_args_list[3].args[0])
        self.assertIn("LEAST(semestre_actual + 1, 10)", consulta)
        self.assertIn("estatus = 'Activo'", consulta)
        self.assertIn("eliminado = FALSE", consulta)
        self.assertIn("semestre_actual < 10", consulta)

    def test_no_repite_el_avance_de_un_periodo(self):
        periodo = MagicMock()
        periodo.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 8, 24),
        }
        avance = MagicMock()
        avance.scalar_one_or_none.return_value = "AGO-DIC 2026"
        conn = MagicMock()
        conn.execute.side_effect = [periodo, avance]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=18),
        ):
            begin.return_value.__enter__.return_value = conn
            self.assertIsNone(servicios.avanzar_semestre_si_corresponde())

        self.assertEqual(conn.execute.call_count, 2)

    def test_no_avanza_si_el_periodo_no_tiene_fecha_configurada(self):
        periodo = MagicMock()
        periodo.mappings.return_value.first.return_value = None
        conn = MagicMock()
        conn.execute.return_value = periodo

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
        ):
            begin.return_value.__enter__.return_value = conn
            self.assertIsNone(servicios.avanzar_semestre_si_corresponde())

        conn.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
