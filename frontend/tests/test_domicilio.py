import unittest
from unittest.mock import Mock, patch

import main


class DomicilioCamposTests(unittest.TestCase):
    def test_formatea_numero_de_ficha_con_guion_despues_de_cuatro_digitos(self):
        for entrada, esperado in (
            ("", ""),
            ("1234", "1234"),
            ("12345", "1234-5"),
            ("123456789", "1234-56789"),
            ("1234567890", "1234-567890"),
            ("1234-56789", "1234-56789"),
        ):
            with self.subTest(entrada=entrada):
                self.assertEqual(main.formatear_ficha(entrada), esperado)

    def test_filtra_municipio_y_colonia_segun_codigo_postal(self):
        catalogo = {
            "codigo_postal": "39000",
            "estados": [{
                "estado": "Guerrero",
                "municipios": [
                    {"municipio": "Acapulco", "colonias": ["Centro", "Costa Azul"]},
                    {"municipio": "Iguala", "colonias": ["Centro"]},
                ],
            }],
        }
        with patch.object(main.api, "opciones_domicilio", return_value=catalogo) as consultar:
            domicilio = main.DomicilioCampos(Mock())
            domicilio.codigo_postal.value = "39000"
            domicilio._codigo_postal_cambiado(None)

        consultar.assert_called_once_with("39000")
        self.assertEqual(domicilio.estado.value, "Guerrero")
        self.assertEqual(
            [opcion.key for opcion in domicilio.municipio.options],
            ["Acapulco", "Iguala"],
        )

        domicilio.municipio.value = "Acapulco"
        domicilio._municipio_cambiado(None)
        self.assertEqual(
            [opcion.key for opcion in domicilio.colonia.options],
            ["Centro", "Costa Azul"],
        )

        domicilio.colonia.value = "Centro"
        domicilio.calle.value = "Avenida Costera"
        domicilio.numero_exterior.value = "123"
        self.assertTrue(domicilio.validar())
        self.assertEqual(domicilio.datos(), {
            "codigo_postal": "39000",
            "estado": "Guerrero",
            "municipio": "Acapulco",
            "colonia": "Centro",
            "calle": "Avenida Costera",
            "numero_exterior": "123",
        })

    def test_cambio_de_cp_limpia_selecciones_dependientes(self):
        catalogo = {
            "codigo_postal": "39000",
            "estados": [{
                "estado": "Guerrero",
                "municipios": [{
                    "municipio": "Acapulco",
                    "colonias": ["Centro", "Costa Azul"],
                }],
            }],
        }
        with patch.object(main.api, "opciones_domicilio", return_value=catalogo):
            domicilio = main.DomicilioCampos(Mock())
            domicilio.codigo_postal.value = "39000"
            domicilio._codigo_postal_cambiado(None)
            domicilio.colonia.value = "Centro"
            domicilio.codigo_postal.value = "39001"
            domicilio._codigo_postal_cambiado(None)

        self.assertIsNone(domicilio.colonia.value)

    def test_valida_calle_y_numero_exterior(self):
        domicilio = main.DomicilioCampos(Mock())
        domicilio.codigo_postal.value = "39000"
        domicilio.estado.value = "Guerrero"
        domicilio.municipio.value = "Acapulco"
        domicilio.colonia.value = "Centro"

        for calle in ("AB", "nose", "asdfg", "ninguna", "aaaaaaa"):
            with self.subTest(calle=calle):
                domicilio.calle.value = calle
                domicilio.numero_exterior.value = "124-B"
                self.assertFalse(domicilio.validar())

        domicilio.calle.value = "Av. Costera"
        for numero in ("124-B", "45-Bis", "102 A", "14-A", "SN", "S/N", "S.N.", "Manzana 4, Lote 12"):
            with self.subTest(numero=numero):
                domicilio.numero_exterior.value = numero
                self.assertTrue(domicilio.validar())

        domicilio.numero_exterior.value = "Manzana B"
        self.assertFalse(domicilio.validar())
