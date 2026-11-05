import unittest
from unittest.mock import MagicMock, patch

from backend import sincronizacion_docentes


class SincronizacionDocentesTests(unittest.TestCase):
    def test_normaliza_nombres_sin_perder_la_identidad(self):
        self.assertEqual(
            sincronizacion_docentes._normalizar_nombre("José Luis Sotelo Jaimes"),
            sincronizacion_docentes._normalizar_nombre("Jose  Luis Sotelo Jaimes"),
        )

    def test_generar_cuenta_separa_nombre_y_apellidos_y_usa_dominio_institucional(self):
        cuenta = sincronizacion_docentes._datos_cuenta(
            "Roberto Carlos Carrasquedo De La Cruz M."
        )

        self.assertEqual(cuenta.nombres, "Roberto")
        self.assertEqual(cuenta.apellidos, "Carlos Carrasquedo De La Cruz M")
        self.assertTrue(cuenta.correo.endswith("@acapulco.tecnm.mx"))
        self.assertGreaterEqual(len(cuenta.password), 10)

    def test_planifica_docentes_programados_y_conserva_sin_asignar(self):
        grupos = [
            {
                "id_grupo": 1,
                "docente_programado": "José Luis Sotelo Jaimes",
                "nombre_paquete": "1ISC1",
                "nombre_materia": "Matemáticas",
            },
            {
                "id_grupo": 2,
                "docente_programado": None,
                "nombre_paquete": "1ISC1",
                "nombre_materia": "Programación",
            },
            {
                "id_grupo": 3,
                "docente_programado": "Carolina Astudillo Hernández",
                "nombre_paquete": "7ISC1",
                "nombre_materia": "Gestión de Proyectos de Software",
            },
        ]
        por_nombre = {
            sincronizacion_docentes._normalizar_nombre("José Luis Sotelo Jaimes"): 8,
            sincronizacion_docentes._normalizar_nombre("Carolina Astudillo Hernández"): 9,
        }

        asignaciones = sincronizacion_docentes._planificar_asignaciones(grupos, por_nombre)

        self.assertEqual(asignaciones, {1: 8, 2: None, 3: None})

    def test_rechaza_traslapes_del_mismo_docente(self):
        grupos = [
            {
                "id_grupo": 1,
                "id_docente": None,
                "dia_semana": 1,
                "hora_inicio": "10:00:00",
                "hora_fin": "11:00:00",
                "nombre_materia": "Materia A",
            },
            {
                "id_grupo": 2,
                "id_docente": None,
                "dia_semana": 1,
                "hora_inicio": "10:30:00",
                "hora_fin": "11:30:00",
                "nombre_materia": "Materia B",
            },
        ]

        with self.assertRaisesRegex(RuntimeError, "materias traslapadas"):
            sincronizacion_docentes._validar_traslapes(grupos, {1: 4, 2: 4})

    def test_acepta_materias_consecutivas_del_mismo_docente(self):
        grupos = [
            {
                "id_grupo": 1,
                "id_docente": None,
                "dia_semana": 1,
                "hora_inicio": "10:00:00",
                "hora_fin": "11:00:00",
                "nombre_materia": "Materia A",
            },
            {
                "id_grupo": 2,
                "id_docente": None,
                "dia_semana": 1,
                "hora_inicio": "11:00:00",
                "hora_fin": "12:00:00",
                "nombre_materia": "Materia B",
            },
        ]

        sincronizacion_docentes._validar_traslapes(grupos, {1: 4, 2: 4})

    def test_no_repite_una_sincronizacion_registrada(self):
        conn = MagicMock()
        conn.execute.return_value.scalar_one_or_none.return_value = (
            "2026_11_04_docentes_horario"
        )
        transaccion = MagicMock()
        transaccion.__enter__.return_value = conn

        with patch(
            "backend.sincronizacion_docentes.engine.begin",
            return_value=transaccion,
        ):
            sincronizacion_docentes.sincronizar_docentes_horario()

        conn.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
