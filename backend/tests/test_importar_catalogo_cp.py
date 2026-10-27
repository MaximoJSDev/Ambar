import unittest

from backend.importar_catalogo_cp import leer_registros


class LeerCatalogoPostalTests(unittest.TestCase):
    def test_lee_txt_sepomex_sin_encabezado_y_conserva_ceros_iniciales(self):
        contenido = (
            "01000|San Ángel|Colonia|Álvaro Obregón|Ciudad de México|"
            "Ciudad de México|01000|09|01000|0|09|010|0001|Urbano|01\n"
        )

        self.assertEqual(leer_registros(contenido), [{
            "codigo_postal": "01000",
            "estado": "Ciudad de México",
            "municipio": "Álvaro Obregón",
            "colonia": "San Ángel",
        }])

    def test_lee_archivo_con_encabezados_y_elimina_duplicados(self):
        contenido = (
            "d_codigo|d_asenta|D_mnpio|d_estado\n"
            "39000|Centro|Acapulco de Juárez|Guerrero\n"
            "39000|Centro|Acapulco de Juárez|Guerrero\n"
        )

        self.assertEqual(leer_registros(contenido), [{
            "codigo_postal": "39000",
            "estado": "Guerrero",
            "municipio": "Acapulco de Juárez",
            "colonia": "Centro",
        }])

    def test_rechaza_archivo_sin_registros_validos(self):
        with self.assertRaisesRegex(ValueError, "No se encontraron"):
            leer_registros("encabezado incorrecto\n")


if __name__ == "__main__":
    unittest.main()
