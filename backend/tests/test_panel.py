import unittest
from unittest.mock import MagicMock, patch

from backend.routers import panel


class PanelTests(unittest.TestCase):
    def test_resumen_entrega_todos_los_alumnos_con_numero_ordenados_por_apellidos(self):
        nuevos = MagicMock()
        nuevos.scalar_one.return_value = 23
        grupos = MagicMock()
        grupos.scalar_one.return_value = 2
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
        conn.execute.side_effect = [nuevos, grupos, actividad]

        with patch("backend.routers.panel.engine.connect") as connect:
            connect.return_value.__enter__.return_value = conn
            resultado = panel.resumen({})

        self.assertEqual(resultado["alumnos_nuevo_ingreso"], 23)
        self.assertEqual(resultado["grupos"], 2)
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
        consulta = str(conn.execute.call_args_list[2].args[0])
        self.assertIn("a.numero_control", consulta)
        self.assertIn("ORDER BY a.apellido_paterno, a.apellido_materno, a.nombres", consulta)
        self.assertNotIn("LIMIT", consulta.upper())


if __name__ == "__main__":
    unittest.main()
