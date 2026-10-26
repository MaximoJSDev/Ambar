import datetime
import unittest

from ambar_common import validators as v
from ambar_common.validators import (
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


class ValidacionesAltasTests(unittest.TestCase):
    def test_nombres_aceptan_los_limites_exactos_de_longitud(self):
        self.assertIsNone(v.validar_nombre("Ana"))
        self.assertIsNone(v.validar_nombre("A" * 50))
        self.assertIsNotNone(v.validar_nombre("An"))
        self.assertIsNotNone(v.validar_nombre("A" * 51))

        self.assertIsNotNone(v.validar_nombre_personal("A", maximo=50))
        self.assertIsNone(v.validar_nombre_personal("Ab", maximo=50))
        self.assertIsNone(v.validar_nombre_personal("A" * 50, maximo=50))
        self.assertIsNotNone(v.validar_nombre_personal("A" * 51, maximo=50))
        self.assertIsNone(v.validar_nombre_personal("A" * 50))
        self.assertIsNotNone(v.validar_nombre_personal("A" * 51))

    def test_correo_acepta_el_maximo_y_rechaza_un_caracter_mas(self):
        correo_100 = f"{'a' * 88}@example.com"
        self.assertEqual(len(correo_100), 100)
        self.assertIsNone(v.validar_correo(correo_100, maximo=100))
        self.assertIsNotNone(v.validar_correo(f"a{correo_100}", maximo=100))

    def test_domicilio_y_preparatoria_aceptan_limites_exactos(self):
        self.assertIsNone(v.validar_domicilio("Calle 1234"))
        domicilio_255 = "Calle " + "A" * 249
        self.assertEqual(len(domicilio_255), 255)
        self.assertIsNone(v.validar_domicilio(domicilio_255))
        self.assertIsNotNone(v.validar_domicilio(domicilio_255 + "A"))

        self.assertIsNone(v.validar_preparatoria("CBT"))
        preparatoria_100 = "A" * 100
        self.assertIsNone(v.validar_preparatoria(preparatoria_100))
        self.assertIsNotNone(v.validar_preparatoria(preparatoria_100 + "A"))

    def test_alergias_acepta_200_caracteres_y_rechaza_201(self):
        self.assertIsNone(v.validar_alergias("A" * 200))
        self.assertIsNotNone(v.validar_alergias("A" * 201))

    def test_promedio_acepta_los_extremos_y_rechaza_valores_adyacentes(self):
        for valor in ("7", "10", "7.00", "10.00", "7,00", "10,00"):
            with self.subTest(valor=valor):
                self.assertIsNone(v.validar_promedio(valor))

        for valor in ("6.99", "10.01", "6,99", "10,01"):
            with self.subTest(valor=valor):
                self.assertIsNotNone(v.validar_promedio(valor))

    def test_formato_de_telefono_admite_espacios_y_guiones_entre_digitos(self):
        for valor in ("7441234567", "7811234567", "744 123 4567", "781-123-4567"):
            with self.subTest(valor=valor):
                self.assertIsNone(v.validar_celular(valor))
        for valor in ("7431234567", "744123456", "74412345678", "744/123/4567"):
            with self.subTest(valor=valor):
                self.assertIsNotNone(v.validar_celular(valor))

    def test_fecha_nacimiento_respeta_limites_de_edad(self):
        hoy = datetime.date(2026, 10, 21)
        self.assertIsNone(v.validar_fecha_nacimiento(v.hace_anios(12, hoy), hoy))
        self.assertIsNone(v.validar_fecha_nacimiento(v.hace_anios(80, hoy), hoy))

        invalidas = (
            None,
            hoy + datetime.timedelta(days=1),
            v.hace_anios(12, hoy) + datetime.timedelta(days=1),
            v.hace_anios(80, hoy) - datetime.timedelta(days=1),
        )
        for fecha in invalidas:
            with self.subTest(fecha=fecha):
                self.assertIsNotNone(v.validar_fecha_nacimiento(fecha, hoy))

    def test_documentos_de_identificacion_solo_son_obligatorios_tras_cumplir_18(self):
        hoy = datetime.date(2026, 10, 21)
        self.assertFalse(v.es_mayor_de_18(v.hace_anios(17, hoy), hoy))
        self.assertTrue(v.es_mayor_de_18(v.hace_anios(18, hoy), hoy))
        self.assertTrue(v.es_mayor_de_18(v.hace_anios(19, hoy), hoy))
        self.assertIsNone(v.validar_rfc(None, hoy))
        self.assertIsNone(v.validar_ine(None, hoy))

    def test_curp_rfc_e_ine_validan_formato_y_coincidencia_de_fecha(self):
        nacimiento = datetime.date(2005, 11, 5)
        curp = "ABCD051105HGRXYZ09"
        rfc = "ABCD051105AB1"
        ine = "ABCDEF05110512H100"

        self.assertIsNone(v.validar_curp(curp, nacimiento))
        self.assertIsNone(v.validar_curp(curp.lower(), nacimiento))
        self.assertIsNone(v.validar_rfc(rfc, nacimiento))
        self.assertIsNone(v.validar_ine(ine, nacimiento))
        self.assertIsNotNone(v.validar_curp(curp, datetime.date(2005, 11, 6)))
        self.assertIsNotNone(v.validar_rfc(rfc, datetime.date(2005, 11, 6)))
        self.assertIsNotNone(v.validar_ine(ine, datetime.date(2005, 11, 6)))
        self.assertIsNone(v.validar_rfc(None, nacimiento))
        self.assertIsNone(v.validar_ine("", nacimiento))

    def test_curp_coincide_con_las_iniciales_de_los_apellidos(self):
        curp = "CAJG050302HGRSSLA4"
        self.assertIsNone(
            v.validar_curp(curp, datetime.date(2005, 3, 2), "Castañón", "De Jesús")
        )
        self.assertIsNotNone(
            v.validar_curp(curp, datetime.date(2005, 3, 2), "López", "De Jesús")
        )
        self.assertEqual(v.prefijo_curp_apellidos("De la Cruz", "Ñúñez"), "CUX")

    def test_curp_debe_coincidir_con_el_genero(self):
        curp_hombre = "CAJG050302HGRSSLA4"
        curp_mujer = "CAJG050302MGRSSLA4"
        curp_no_binario = "CAJG050302XGRSSLA4"

        self.assertIsNone(v.validar_curp(curp_hombre, genero="hombre"))
        self.assertIsNone(v.validar_curp(curp_mujer, genero="mujer"))
        self.assertIsNone(v.validar_curp(curp_no_binario, genero="no_binario"))
        self.assertIsNotNone(v.validar_curp(curp_mujer, genero="hombre"))
        self.assertIsNotNone(v.validar_curp(curp_hombre, genero="mujer"))
        self.assertIsNotNone(v.validar_curp(curp_hombre, genero="no_binario"))

    def test_opciones_de_genero_no_incluyen_prefiero_no_especificar(self):
        self.assertNotIn("no_especifica", v.GENEROS)
        self.assertIsNotNone(v.validar_genero("no_especifica"))

    def test_correo_institucional_requiere_dominio_tecnm(self):
        self.assertIsNone(v.validar_correo_institucional("persona@acapulco.tecnm.mx"))
        self.assertIsNone(v.validar_correo_institucional("PERSONA@ACAPULCO.TECNM.MX"))
        self.assertIsNotNone(v.validar_correo_institucional("persona@example.com"))
        self.assertIsNotNone(v.validar_correo_institucional("persona@sub.acapulco.tecnm.mx"))

    def test_nombre_rechaza_simbolos_y_acepta_nombres_compuestos(self):
        for valor in ("Ana", "María José", "Jean-Luc", "O'Brien", "Núñez"):
            with self.subTest(valor=valor):
                self.assertIsNone(v.validar_nombre(valor))

        for valor in ("...", "!!!", "Ana123", "Ana_"):
            with self.subTest(valor=valor):
                self.assertIsNotNone(v.validar_nombre(valor))

    def test_correo_respeta_formato_y_longitud_de_columna(self):
        self.assertIsNone(v.validar_correo("alumno@example.com", maximo=100))
        self.assertIsNotNone(v.validar_correo("............", maximo=100))
        self.assertIsNotNone(v.validar_correo(f"{'a' * 91}@example.com", maximo=100))
        self.assertIsNone(v.validar_correo(f"{'a' * 135}@example.com"))

    def test_domicilio_rechaza_simbolos_y_limita_el_tamano_de_base_de_datos(self):
        self.assertIsNone(v.validar_domicilio("Calle 1, Colonia Centro, Acapulco"))
        self.assertIsNotNone(v.validar_domicilio("." * 20))
        self.assertIsNotNone(v.validar_domicilio("123456789012"))
        self.assertIsNotNone(v.validar_domicilio("Calle!!! 123"))
        self.assertIsNotNone(v.validar_domicilio("Calle " + "x" * 250))

    def test_preparatoria_rechaza_simbolos_y_respeta_la_columna(self):
        self.assertIsNone(v.validar_preparatoria("CBTis 41"))
        self.assertIsNotNone(v.validar_preparatoria("." * 20))
        self.assertIsNotNone(v.validar_preparatoria("123456"))
        self.assertIsNotNone(v.validar_preparatoria("Prepa!!!"))
        self.assertIsNotNone(v.validar_preparatoria("P" * 101))

    def test_alergias_admite_vacio_pero_no_solo_simbolos(self):
        self.assertIsNone(v.validar_alergias(""))
        self.assertIsNone(v.validar_alergias("Penicilina, nueces"))
        self.assertIsNotNone(v.validar_alergias("...!!!"))
        self.assertIsNotNone(v.validar_alergias("Polen!!!"))
        self.assertIsNotNone(v.validar_alergias("A" * 201))

    def test_campos_estructurados_rechazan_simbolos_fuera_de_formato(self):
        self.assertIsNotNone(v.validar_ficha("." * 10))
        self.assertIsNotNone(v.validar_curp("!" * 18))
        self.assertIsNotNone(v.validar_rfc("." * 13))
        self.assertIsNotNone(v.validar_nss("." * 11))
        self.assertIsNotNone(v.validar_ine("." * 18))
        self.assertIsNotNone(v.validar_celular("." * 10))
        self.assertIsNotNone(v.validar_genero("..."))
        self.assertIsNotNone(v.validar_promedio("..."))
        self.assertIsNotNone(v.validar_promedio("8e0"))
        self.assertIsNotNone(v.validar_promedio("8.555"))
        self.assertIsNone(v.validar_promedio("8,55"))

    def test_contactos_de_emergencia_deben_ser_validos_y_distintos(self):
        self.assertIsNone(v.validar_celular_emergencia("781-123-4567", "7441234567"))
        self.assertIsNotNone(v.validar_celular_emergencia("744 123 4567", "7441234567"))
        self.assertIsNone(
            v.validar_correo_emergencia("contacto@example.com", "alumno@example.com", 100)
        )
        self.assertIsNotNone(
            v.validar_correo_emergencia("ALUMNO@example.com", "alumno@example.com", 100)
        )
        self.assertIsNotNone(
            v.validar_correo_emergencia(f"{'a' * 91}@example.com", maximo=100)
        )


if __name__ == "__main__":
    unittest.main()
