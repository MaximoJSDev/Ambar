import unittest
from unittest.mock import patch

from backend import reportes
from backend.reportes import _clave_orden_alumno, generar_expediente_pdf
from backend.routers.alumnos import descargar_expediente_pdf
from backend.main import app


class ReporteExpedienteTests(unittest.TestCase):
    def test_estadisticas_pdf_incluye_totales_generales_por_genero(self):
        datos = {
            "periodo": "AGO-DIC 2026",
            "grupos": [
                {
                    "grupo": "1A", "semestre": 1, "turno": "Matutino",
                    "total": 3, "hombres": 1, "mujeres": 2, "no_binarios": 0,
                    "sin_especificar": 0, "cupo": 25, "lugares_disponibles": 22,
                },
                {
                    "grupo": "2ISC1", "semestre": 2, "turno": "Vespertino",
                    "total": 2, "hombres": 2, "mujeres": 0, "no_binarios": 0,
                    "sin_especificar": 0, "cupo": 25, "lugares_disponibles": 23,
                },
            ],
        }

        with patch("backend.reportes.Table", wraps=reportes.Table) as crear_tabla:
            contenido = reportes.generar_estadisticas_grupos_pdf(datos)

        ultima_fila = crear_tabla.call_args.args[0][-1]
        self.assertEqual(
            [celda.getPlainText() if hasattr(celda, "getPlainText") else celda for celda in ultima_fila],
            ["TOTAL GENERAL", "", "", "5", "3", "2", "0", "0", ""],
        )
        self.assertTrue(contenido.startswith(b"%PDF-"))

    def test_clave_de_lista_ordena_primero_por_apellido_sin_distinguir_acentos(self):
        alumnos = [
            {
                "apellido_paterno": "Zúñiga",
                "apellido_materno": "López",
                "nombres": "Ana",
                "numero_control": "3",
            },
            {
                "apellido_paterno": "Álvarez",
                "apellido_materno": "Pérez",
                "nombres": "Luis",
                "numero_control": "2",
            },
            {
                "apellido_paterno": "Alvarez",
                "apellido_materno": "García",
                "nombres": "Ana",
                "numero_control": "1",
            },
        ]

        ordenados = sorted(alumnos, key=_clave_orden_alumno)

        self.assertEqual(
            [alumno["numero_control"] for alumno in ordenados],
            ["1", "2", "3"],
        )

    def setUp(self):
        self.datos = {
            "numero_control": "26320700",
            "nombre_completo": "Gael Alexander Castañón De Jesus",
            "semestre_actual": 1,
            "estatus": "Activo",
            "personales": {
                "nombres": "Gael Alexander",
                "apellido_paterno": "Castañón",
                "apellido_materno": "De Jesus",
                "fecha_nacimiento": "02/03/2005",
                "genero": "Hombre",
                "curp": "CAJG050302HGRSSLA4",
                "rfc": "—",
                "ine": "1234567890123",
                "nss": "12345678901",
            },
            "contacto": {
                "domicilio": "Calle 1 & Avenida 2",
                "celular": "7441234567",
                "correo_personal": "alumno@example.com",
                "correo_institucional": "al26320700@example.com",
                "celular_emergencia": "7447654321",
                "correo_emergencia": "contacto@example.com",
                "tipo_sangre": "O+",
                "alergias": "Ninguna",
            },
            "academicos": {
                "numero_ficha": "2026123456",
                "preparatoria": "Preparatoria de prueba",
                "promedio": "9.50",
                "turno": "Matutino",
                "semestre": "1",
                "grupo": "1A",
                "periodo": "AGO-DIC 2026",
                "estatus": "Activo",
            },
            "documentos": [
                {"documento": "Acta de nacimiento", "estado": "Recibido"},
                {"documento": "CURP", "estado": "Pendiente"},
            ],
        }

    def test_genera_pdf_con_cabecera_y_final_pdf(self):
        contenido = generar_expediente_pdf(self.datos)
        self.assertTrue(contenido.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", contenido)
        self.assertIn(b"/Subtype /Image", contenido)
        self.assertGreater(len(contenido), 1000)

    def test_endpoint_entrega_pdf_con_nombre_del_expediente(self):
        with patch("backend.routers.alumnos.servicios.buscar_expediente", return_value=self.datos):
            respuesta = descargar_expediente_pdf("26320700", False)
        self.assertEqual(respuesta.media_type, "application/pdf")
        self.assertEqual(
            respuesta.headers["content-disposition"],
            'attachment; filename="expediente_26320700.pdf"',
        )
        self.assertTrue(respuesta.body.startswith(b"%PDF-"))

    def test_endpoint_pdf_esta_registrado_en_la_api(self):
        self.assertIn("/alumnos/expediente/pdf", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
