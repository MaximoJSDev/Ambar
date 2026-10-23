import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from backend import servicios
from backend.esquemas import CalificacionIn


class CalificacionesTests(unittest.TestCase):
    def test_editar_periodo_renombra_configuracion_y_grupos_vinculados(self):
        existente = MagicMock()
        existente.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 1, 19),
        }
        duplicado = MagicMock()
        duplicado.scalar_one.return_value = False
        grupos_destino = MagicMock()
        grupos_destino.scalar_one.return_value = False
        guardado = MagicMock()
        guardado.mappings.return_value.one.return_value = {
            "periodo": "AGO-DIC 2026",
            "fecha_inicio": datetime.date(2026, 8, 24),
        }
        conn = MagicMock()
        conn.execute.side_effect = [
            existente, duplicado, grupos_destino, MagicMock(), MagicMock(), guardado,
        ]
        configuracion = SimpleNamespace(periodo="ENE-JUN 2026", periodo_escolar="ENE-JUN 2026")

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", configuracion),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.guardar_periodo_escolar(
                "AGO-DIC 2026",
                datetime.date(2026, 8, 24),
                1,
                "ENE-JUN 2026",
            )

        self.assertEqual(resultado["periodo"], "AGO-DIC 2026")
        self.assertEqual(configuracion.periodo_escolar, "AGO-DIC 2026")
        self.assertIn(
            "UPDATE grupos SET periodo_escolar",
            str(conn.execute.call_args_list[3].args[0]),
        )
        self.assertIn(
            "UPDATE periodos_escolares",
            str(conn.execute.call_args_list[4].args[0]),
        )

    def test_corregir_fecha_no_consulta_ni_elimina_calificaciones(self):
        existente = MagicMock()
        existente.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 8, 24),
        }
        guardado = MagicMock()
        guardado.mappings.return_value.one.return_value = {
            "periodo": "AGO-DIC 2026",
            "fecha_inicio": datetime.date(2026, 8, 31),
        }
        conn = MagicMock()
        conn.execute.side_effect = [existente, MagicMock(), guardado]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="OTRO 2026")),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.guardar_periodo_escolar(
                "AGO-DIC 2026",
                datetime.date(2026, 8, 31),
                1,
                "AGO-DIC 2026",
            )

        self.assertEqual(resultado["fecha_inicio"], datetime.date(2026, 8, 31))
        self.assertEqual(conn.execute.call_count, 3)
        self.assertNotIn("calificaciones", " ".join(
            str(llamada.args[0]) for llamada in conn.execute.call_args_list
        ))

    def test_renombrar_periodo_existente_rechaza_nombre_duplicado(self):
        existente = MagicMock()
        existente.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 1, 19),
        }
        duplicado = MagicMock()
        duplicado.scalar_one.return_value = True
        conn = MagicMock()
        conn.execute.side_effect = [existente, duplicado]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="ENE-JUN 2026")),
        ):
            begin.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(servicios.Conflicto, "Ya existe un periodo"):
                servicios.guardar_periodo_escolar(
                    "AGO-DIC 2026",
                    datetime.date(2026, 8, 24),
                    1,
                    "ENE-JUN 2026",
                )

        self.assertEqual(conn.execute.call_count, 2)

    def test_renombrar_periodo_no_combina_grupos_de_otro_periodo(self):
        existente = MagicMock()
        existente.mappings.return_value.first.return_value = {
            "fecha_inicio": datetime.date(2026, 1, 19),
        }
        duplicado_periodo = MagicMock()
        duplicado_periodo.scalar_one.return_value = False
        grupos_destino = MagicMock()
        grupos_destino.scalar_one.return_value = True
        conn = MagicMock()
        conn.execute.side_effect = [existente, duplicado_periodo, grupos_destino]

        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="ENE-JUN 2026")),
        ):
            begin.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(servicios.Conflicto, "no se pueden combinar"):
                servicios.guardar_periodo_escolar(
                    "AGO-DIC 2026",
                    datetime.date(2026, 8, 24),
                    1,
                    "ENE-JUN 2026",
                )

        self.assertEqual(conn.execute.call_count, 3)

    def test_calificacion_permite_cero_o_valores_aprobatorios(self):
        for valor in (0, 70, 100):
            with self.subTest(valor=valor):
                self.assertEqual(CalificacionIn(valor=valor).valor, valor)
        self.assertEqual(CalificacionIn(valor=70.0).valor, 70)

    def test_calificacion_rechaza_valores_no_aprobatorios_y_fuera_de_rango(self):
        for valor in (-1, 1, 69, 101, 70.25, 90.5):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                CalificacionIn(valor=valor)

    def test_semana_actual_habilita_evaluaciones_al_inicio_de_cada_semana(self):
        inicio = datetime.date(2026, 8, 24)
        casos = (
            (datetime.date(2026, 9, 20), 4),
            (datetime.date(2026, 9, 21), 5),
            (datetime.date(2026, 10, 19), 9),
            (datetime.date(2026, 11, 16), 13),
            (datetime.date(2026, 12, 14), 17),
        )
        for fecha, semana in casos:
            with self.subTest(fecha=fecha):
                self.assertEqual(servicios._semana_del_periodo(inicio, fecha), semana)

    def test_rechaza_captura_antes_de_que_se_active_la_semana(self):
        resultado_inscripcion = MagicMock()
        resultado_inscripcion.mappings.return_value.first.return_value = {"id_inscripcion": 8}
        resultado_inicio = MagicMock()
        resultado_inicio.scalar_one_or_none.return_value = datetime.date(2026, 8, 24)
        conn = MagicMock()
        conn.execute.side_effect = [resultado_inscripcion, resultado_inicio]
        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=4),
        ):
            begin.return_value.__enter__.return_value = conn
            with self.assertRaises(servicios.Conflicto):
                servicios.guardar_calificacion_docente(
                    42, 7, "26320700", "Semana 5", 80,
                )

        self.assertEqual(conn.execute.call_count, 2)

    def test_periodos_no_se_pueden_cambiar_despues_de_confirmar_final(self):
        resultado_inscripcion = MagicMock()
        resultado_inscripcion.mappings.return_value.first.return_value = {"id_inscripcion": 8}
        resultado_inicio = MagicMock()
        resultado_inicio.scalar_one_or_none.return_value = datetime.date(2026, 8, 24)
        resultado_final = MagicMock()
        resultado_final.scalar_one_or_none.return_value = True
        conn = MagicMock()
        conn.execute.side_effect = [resultado_inscripcion, resultado_inicio, resultado_final]
        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=17),
        ):
            begin.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(servicios.Conflicto, "después de confirmar"):
                servicios.guardar_calificacion_docente(
                    42, 7, "26320700", "Semana 5", 80,
                )

        self.assertEqual(conn.execute.call_count, 3)

    def test_final_es_el_promedio_de_tres_periodos_y_se_confirma(self):
        resultado_inscripcion = MagicMock()
        resultado_inscripcion.mappings.return_value.first.return_value = {"id_inscripcion": 8}
        resultado_inicio = MagicMock()
        resultado_inicio.scalar_one_or_none.return_value = datetime.date(2026, 8, 24)
        resultado_final = MagicMock()
        resultado_final.scalar_one_or_none.return_value = None
        resultado_periodos = MagicMock()
        resultado_periodos.mappings.return_value.all.return_value = [
            {"periodo_evaluacion": "Semana 5", "valor": Decimal("80")},
            {"periodo_evaluacion": "Semana 9", "valor": Decimal("90")},
            {"periodo_evaluacion": "Semana 13", "valor": Decimal("100")},
        ]
        conn = MagicMock()
        conn.execute.side_effect = [
            resultado_inscripcion, resultado_inicio, resultado_final, resultado_periodos,
            MagicMock(),
        ]
        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=17),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.confirmar_calificacion_final_docente(42, 7, "26320700")

        self.assertEqual(resultado["valor"], Decimal("90"))
        self.assertTrue(resultado["confirmada"])
        self.assertIn("confirmada", str(conn.execute.call_args_list[-1].args[0]))

    def test_final_reprueba_si_el_promedio_es_menor_a_setenta(self):
        resultado_inscripcion = MagicMock()
        resultado_inscripcion.mappings.return_value.first.return_value = {"id_inscripcion": 8}
        resultado_inicio = MagicMock()
        resultado_inicio.scalar_one_or_none.return_value = datetime.date(2026, 8, 24)
        resultado_final = MagicMock()
        resultado_final.scalar_one_or_none.return_value = None
        resultado_periodos = MagicMock()
        resultado_periodos.mappings.return_value.all.return_value = [
            {"periodo_evaluacion": "Semana 5", "valor": Decimal("70")},
            {"periodo_evaluacion": "Semana 9", "valor": Decimal("70")},
            {"periodo_evaluacion": "Semana 13", "valor": Decimal("0")},
        ]
        conn = MagicMock()
        conn.execute.side_effect = [
            resultado_inscripcion, resultado_inicio, resultado_final, resultado_periodos,
            MagicMock(),
        ]
        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=17),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.confirmar_calificacion_final_docente(42, 7, "26320700")

        self.assertEqual(resultado["valor"], Decimal("0.00"))

    def test_promedio_final_se_redondea_a_entero(self):
        resultado_inscripcion = MagicMock()
        resultado_inscripcion.mappings.return_value.first.return_value = {"id_inscripcion": 8}
        resultado_inicio = MagicMock()
        resultado_inicio.scalar_one_or_none.return_value = datetime.date(2026, 8, 24)
        resultado_final = MagicMock()
        resultado_final.scalar_one_or_none.return_value = None
        resultado_periodos = MagicMock()
        resultado_periodos.mappings.return_value.all.return_value = [
            {"periodo_evaluacion": "Semana 5", "valor": Decimal("70")},
            {"periodo_evaluacion": "Semana 9", "valor": Decimal("71")},
            {"periodo_evaluacion": "Semana 13", "valor": Decimal("71")},
        ]
        conn = MagicMock()
        conn.execute.side_effect = [
            resultado_inscripcion, resultado_inicio, resultado_final, resultado_periodos,
            MagicMock(),
        ]
        with (
            patch("backend.servicios.engine.begin") as begin,
            patch("backend.servicios.settings", SimpleNamespace(periodo="AGO-DIC 2026")),
            patch("backend.servicios._semana_del_periodo", return_value=17),
        ):
            begin.return_value.__enter__.return_value = conn
            resultado = servicios.confirmar_calificacion_final_docente(42, 7, "26320700")

        self.assertEqual(resultado["valor"], Decimal("71"))
