import unittest
from unittest.mock import MagicMock, patch

from backend.routers import panel


class PanelTests(unittest.TestCase):
    def test_estadisticas_calcula_porcentajes_por_grupo_y_generales(self):
        resultado_consulta = MagicMock()
        resultado_consulta.mappings.return_value.all.return_value = [
            {
                "id_paquete": 1,
                "grupo": "1A",
                "semestre": 1,
                "turno": "Matutino",
                "cupo_por_grupo": 25,
                "total": 4,
                "hombres": 1,
                "mujeres": 2,
                "no_binarios": 1,
                "sin_especificar": 0,
            },
            {
                "id_paquete": 2,
                "grupo": "1B",
                "semestre": 1,
                "turno": "Vespertino",
                "cupo_por_grupo": 25,
                "total": 0,
                "hombres": 0,
                "mujeres": 0,
                "no_binarios": 0,
                "sin_especificar": 0,
            },
        ]
        conn = MagicMock()
        conn.execute.return_value = resultado_consulta

        with patch("backend.routers.panel.engine.connect") as connect:
            connect.return_value.__enter__.return_value = conn
            resultado = panel.estadisticas({})

        self.assertEqual(resultado["grupos"][0]["porcentajes"], {
            "hombres": 25.0,
            "mujeres": 50.0,
            "no_binarios": 25.0,
            "sin_especificar": 0.0,
        })
        self.assertEqual(resultado["grupos"][1]["porcentajes"], {
            "hombres": 0.0,
            "mujeres": 0.0,
            "no_binarios": 0.0,
            "sin_especificar": 0.0,
        })
        self.assertEqual(resultado["totales"], {
            "total": 4,
            "hombres": 1,
            "mujeres": 2,
            "no_binarios": 1,
            "sin_especificar": 0,
            "porcentajes": {
                "hombres": 25.0,
                "mujeres": 50.0,
                "no_binarios": 25.0,
                "sin_especificar": 0.0,
            },
        })

    def test_resumen_entrega_todos_los_alumnos_con_numero_ordenados_por_apellidos(self):
        nuevos = MagicMock()
        nuevos.scalar_one.return_value = 23
        grupos = MagicMock()
        grupos.scalar_one.return_value = 2
        reinscripciones = MagicMock()
        reinscripciones.scalar_one.return_value = 3
        actividad = MagicMock()
        actividad.mappings.return_value.all.return_value = [
            {
                "numero_control": "26320700",
                "alumno": "Álvarez Pérez Ana",
                "apellido_paterno": "Álvarez",
                "apellido_materno": "Pérez",
                "nombres": "Ana",
                "docs": len(panel.TIPOS_REQUERIDOS),
            },
            {
                "numero_control": "26320701",
                "alumno": "Zúñiga López Luis",
                "apellido_paterno": "Zúñiga",
                "apellido_materno": "López",
                "nombres": "Luis",
                "docs": 1,
            },
        ]
        conn = MagicMock()
        conn.execute.side_effect = [nuevos, grupos, reinscripciones, actividad]

        with patch("backend.routers.panel.engine.connect") as connect:
            connect.return_value.__enter__.return_value = conn
            resultado = panel.resumen({})

        self.assertEqual(resultado["alumnos_nuevo_ingreso"], 23)
        self.assertEqual(resultado["grupos"], 2)
        self.assertEqual(resultado["reinscripciones_hoy"], 3)
        self.assertEqual(resultado["actividad"], [
            {
                "numero_control": "26320700",
                "alumno": "Álvarez Pérez Ana",
                "tramite": "Alta",
                "estado": "Completada",
            },
            {
                "numero_control": "26320701",
                "alumno": "Zúñiga López Luis",
                "tramite": "Documentos",
                "estado": "Pendiente",
            },
        ])
        self.assertNotIn("pendientes", resultado)
        self.assertNotIn("expedientes_pendientes", resultado)
        consulta = str(conn.execute.call_args_list[3].args[0])
        self.assertIn("a.numero_control", consulta)
        self.assertIn("ORDER BY a.apellido_paterno, a.apellido_materno, a.nombres", consulta)
        self.assertNotIn("LIMIT", consulta.upper())


if __name__ == "__main__":
    unittest.main()
