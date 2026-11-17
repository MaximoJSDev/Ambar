import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import flet as ft

from views.consultas import ConsultaExpediente


class ConsultaExpedienteTests(unittest.TestCase):
    def test_encabezado_de_expediente_se_puede_renderizar(self):
        vista = ConsultaExpediente.__new__(ConsultaExpediente)
        vista.datos = {
            "numero_control": "26320703",
            "nombre_completo": "Alumno de prueba",
            "semestre_actual": 1,
            "estatus": "Activo",
            "eliminado": False,
            "personales": {"nombres": "Alumno", "apellido_paterno": "Prueba"},
            "academicos": {"turno": "Matutino"},
        }
        vista.boton_descargar = ft.Text("Descargar expediente PDF")
        vista.modo_modificacion = False
        vista.modo_bajas = False

        encabezado = vista._encabezado()

        self.assertIsInstance(encabezado, ft.Control)

    def test_descarga_horario_de_reinscripcion_sin_expediente(self):
        vista = ConsultaExpediente.__new__(ConsultaExpediente)
        vista.horario = {
            "asignado": True,
            "numero_control": "26320200",
        }
        vista.datos = None

        with tempfile.TemporaryDirectory() as directorio:
            destino = Path(directorio) / "horario_26320200.pdf"
            with (
                patch(
                    "views.consultas.api.descargar_horario_alumno",
                    return_value=b"%PDF-horario",
                ) as descargar,
                patch(
                    "ui.files.carpeta_pdf_temporal",
                    return_value=Path(directorio),
                ),
                patch("ui.files.abrir_archivo") as abrir,
            ):
                vista._descargar_horario()

            descargar.assert_called_once_with("26320200")
            abrir.assert_called_once_with(destino)
            self.assertEqual(destino.read_bytes(), b"%PDF-horario")


if __name__ == "__main__":
    unittest.main()
