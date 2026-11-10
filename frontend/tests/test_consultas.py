import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from views.consultas import ConsultaExpediente


class ConsultaExpedienteTests(unittest.TestCase):
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
                    "views.consultas._carpeta_pdf_temporal",
                    return_value=Path(directorio),
                ),
                patch("views.consultas.abrir_archivo") as abrir,
            ):
                vista._descargar_horario()

            descargar.assert_called_once_with("26320200")
            abrir.assert_called_once_with(destino)
            self.assertEqual(destino.read_bytes(), b"%PDF-horario")


if __name__ == "__main__":
    unittest.main()
