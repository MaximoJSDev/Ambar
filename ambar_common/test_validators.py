import unittest

from .validators import (
    generar_numero_control,
    prefijo_control,
    siguiente_carrera_secuencia,
)


class NumeroControlTests(unittest.TestCase):
    def test_formato_inicial(self):
        self.assertEqual(prefijo_control(2026, 32), "2632")
        self.assertEqual(generar_numero_control(2026, 32, 7, 0), "26320700")

    def test_numero_de_dos_digitos(self):
        self.assertEqual(generar_numero_control(2026, 32, 7, 9), "26320709")
        self.assertEqual(generar_numero_control(2026, 32, 7, 99), "26320799")

    def test_avanza_secuencialmente_y_cambia_carrera_al_llegar_a_100(self):
        self.assertEqual(siguiente_carrera_secuencia(None, 7), (7, 0))
        self.assertEqual(siguiente_carrera_secuencia(798, 7), (7, 99))
        self.assertEqual(siguiente_carrera_secuencia(799, 7), (8, 0))
        self.assertEqual(siguiente_carrera_secuencia(899, 7), (9, 0))

    def test_no_reutiliza_huecos_y_respeta_la_carrera_inicial(self):
        self.assertEqual(siguiente_carrera_secuencia(701, 7), (7, 2))
        self.assertEqual(siguiente_carrera_secuencia(699, 7), (7, 0))

    def test_rechaza_agotamiento_del_campo_de_carrera(self):
        with self.assertRaises(OverflowError):
            siguiente_carrera_secuencia(9999, 7)


if __name__ == "__main__":
    unittest.main()
