import datetime
import os
import tempfile
import unittest
from pathlib import Path

import storage
import validators as v

HOY = datetime.date(2026, 10, 9)
NAC = datetime.date(2005, 11, 5)  # CURP/RFC con 051105


class TestCampos(unittest.TestCase):
    def test_ficha(self):
        for ok in ("2026001230", "2026-00123"):
            self.assertIsNone(v.validar_ficha(ok), ok)
        for mal in ("", "123", "20260012345", "2026-0123", "abcdefghij", "2026_00123"):
            self.assertIsNotNone(v.validar_ficha(mal), mal)

    def test_nombre(self):
        for ok in ("Ana", "María José", "Jean-Luc", "O'Brien", "Núñez", "x" * 20):
            self.assertIsNone(v.validar_nombre(ok), ok)
        for mal in ("", "Al", "Ana123", "x" * 21, "   ", "Ana_"):
            self.assertIsNotNone(v.validar_nombre(mal), repr(mal))
        self.assertIsNone(v.validar_nombre("  Ana  "))  # se recortan los espacios

    def test_fecha(self):
        self.assertIsNone(v.validar_fecha_nacimiento(NAC, HOY))
        self.assertIsNotNone(v.validar_fecha_nacimiento(None, HOY))
        self.assertIsNotNone(v.validar_fecha_nacimiento(datetime.date(2015, 1, 1), HOY))   # 11 años
        self.assertIsNotNone(v.validar_fecha_nacimiento(datetime.date(1940, 1, 1), HOY))   # 86 años
        # límites exactos
        self.assertIsNone(v.validar_fecha_nacimiento(v.hace_anios(16, HOY), HOY))
        self.assertIsNone(v.validar_fecha_nacimiento(v.hace_anios(70, HOY), HOY))
        self.assertIsNotNone(v.validar_fecha_nacimiento(v.hace_anios(16, HOY) + datetime.timedelta(days=1), HOY))

    def test_hace_anios_bisiesto(self):
        self.assertEqual(v.hace_anios(1, datetime.date(2024, 2, 29)), datetime.date(2023, 2, 28))

    def test_curp(self):
        curp = "ABCD051105HGRXYZ09"
        self.assertIsNone(v.validar_curp(curp, NAC))
        self.assertIsNone(v.validar_curp(curp.lower(), NAC))
        self.assertIsNone(v.validar_curp(curp))  # sin fecha de referencia
        self.assertIn("fecha", v.validar_curp(curp, datetime.date(2005, 11, 6)))
        self.assertIn("18", v.validar_curp("ABCD051105HGR"))
        self.assertIsNotNone(v.validar_curp("ABCD051105QGRXYZ09"))  # sexo inválido
        self.assertIsNotNone(v.validar_curp("ABCD051105HXXXYZ09"))  # entidad inválida

    def test_rfc(self):
        self.assertIsNone(v.validar_rfc("ABCD051105AB1", NAC))
        self.assertIsNotNone(v.validar_rfc("ABCD051105AB", NAC))
        self.assertIsNotNone(v.validar_rfc("ABCD051106AB1", NAC))
        self.assertIsNotNone(v.validar_rfc("1BCD051105AB1"))

    def test_nss(self):
        self.assertIsNone(v.validar_nss("12345678901"))
        for mal in ("1234567890", "123456789012", "1234567890a"):
            self.assertIsNotNone(v.validar_nss(mal))

    def test_celular(self):
        for ok in ("7441234567", "7811234567", "744 123 4567", "744-123-4567"):
            self.assertIsNone(v.validar_celular(ok), ok)
        for mal in ("5551234567", "744123456", "74412345678", "x7441234567", "7441234567x"):
            self.assertIsNotNone(v.validar_celular(mal), mal)

    def test_correo(self):
        self.assertIsNone(v.validar_correo("a.b+c@dom.mx"))
        for mal in ("", "a@b", "a@@b.com", "sin arroba.com", "a@b.c"):
            self.assertIsNotNone(v.validar_correo(mal), mal)

    def test_promedio(self):
        for ok in ("1", "8.7", "8,7", "100", " 95 "):
            self.assertIsNone(v.validar_promedio(ok), ok)
        for mal in ("", "0", "101", "-5", "abc", "8.7.1"):
            self.assertIsNotNone(v.validar_promedio(mal), mal)

    def test_ine(self):
        ine = "ABCDEF05110512H100"
        self.assertIsNone(v.validar_ine(ine))
        self.assertIsNone(v.validar_ine(ine, NAC))
        self.assertIn("fecha", v.validar_ine(ine, datetime.date(2005, 11, 6)))
        self.assertIsNotNone(v.validar_ine(""))
        self.assertIsNotNone(v.validar_ine("ABC"))
        self.assertIsNotNone(v.validar_ine("ABCDEF05110512X100"))

    def test_genero_y_domicilio(self):
        for k in ("hombre", "mujer", "no_binario", "no_especifica"):
            self.assertIsNone(v.validar_genero(k))
        self.assertIsNotNone(v.validar_genero(None))
        self.assertIsNotNone(v.validar_genero("Mujer"))  # la clave es minúscula
        self.assertIsNotNone(v.validar_domicilio("Calle 1"))
        self.assertIsNone(v.validar_domicilio("Av. Costera 100, Centro, Acapulco, Gro."))

    def test_emergencia(self):
        self.assertIsNone(v.validar_celular_emergencia("7811234567", "7441234567"))
        self.assertIn("distinto", v.validar_celular_emergencia("744 123 4567", "7441234567"))
        self.assertIsNotNone(v.validar_celular_emergencia("5551234567"))
        self.assertIsNone(v.validar_correo_emergencia("mama@mail.com", "ana@mail.com"))
        self.assertIn("distinto", v.validar_correo_emergencia("ANA@mail.com", "ana@mail.com"))
        self.assertIsNotNone(v.validar_correo_emergencia("x"))

    def test_alergias(self):
        self.assertIsNone(v.validar_alergias(""))
        self.assertIsNone(v.validar_alergias("Penicilina"))
        self.assertIsNotNone(v.validar_alergias("x" * 201))


class TestReglasAltas(unittest.TestCase):
    def test_turno(self):
        self.assertEqual(v.turno_por_promedio(90), "Matutino")
        self.assertEqual(v.turno_por_promedio(100), "Matutino")
        self.assertEqual(v.turno_por_promedio(89.99), "Vespertino")
        self.assertEqual(v.turno_por_promedio(1), "Vespertino")

    def test_indice_letra(self):
        self.assertEqual(v.indice_letra("Álvarez"), 1)
        self.assertEqual(v.indice_letra("Morales"), 13)
        self.assertEqual(v.indice_letra("Ñandú"), 14)   # Ñ -> N
        self.assertEqual(v.indice_letra("zamora"), 26)
        with self.assertRaises(ValueError):
            v.indice_letra("123")

    def test_numero_control(self):
        self.assertEqual(v.generar_numero_control(2026, 1, "Morales", 1), "20260113001")
        self.assertEqual(v.generar_numero_control(2026, 1, "Morales", 25), "20260113025")
        self.assertEqual(v.generar_numero_control(2026, 12, "Zamora", 7), "20261226007")
        self.assertTrue(v.generar_numero_control(2026, 1, "Morales", 2).startswith(
            v.prefijo_control(2026, 1, "Moreno")))  # misma letra -> mismo prefijo

    def test_correo_institucional(self):
        self.assertEqual(v.correo_institucional("20260113001"), "al20260113001@acapulco.tecnm.mx")

    def test_pdf(self):
        d = tempfile.mkdtemp()
        ok, fake, vacio, txt = (os.path.join(d, n) for n in ("a.pdf", "b.pdf", "c.pdf", "d.txt"))
        Path(ok).write_bytes(b"%PDF-1.7\n...")
        Path(fake).write_bytes(b"MZ\x90\x00 no soy pdf")
        Path(vacio).write_bytes(b"")
        Path(txt).write_bytes(b"%PDF-")
        self.assertIsNone(v.validar_pdf("a.pdf", 12, ok))
        self.assertIsNone(v.validar_pdf("A.PDF", 12, ok))
        self.assertIn("válido", v.validar_pdf("b.pdf", 20, fake))       # extensión .pdf pero contenido falso
        self.assertIn("vacío", v.validar_pdf("c.pdf", 0, vacio))
        self.assertIn("PDF", v.validar_pdf("d.txt", 5, txt))
        self.assertIn("leer", v.validar_pdf("x.pdf", 10, os.path.join(d, "no_existe.pdf")))
        # límite de tamaño (sin ruta: se confía en el tamaño que reporta el selector)
        self.assertIsNone(v.validar_pdf("a.pdf", v.MAX_PDF_BYTES))
        self.assertIn("500", v.validar_pdf("a.pdf", v.MAX_PDF_BYTES + 1))


class TestStorage(unittest.TestCase):
    def test_guardar_y_rollback(self):
        d = Path(tempfile.mkdtemp())
        src = d / "orig.pdf"; src.write_bytes(b"%PDF-1.4 hola")
        base = d / "exp"
        res = storage.guardar_pdfs("20260113001", {"Acta de nacimiento": str(src),
                                                   "Certificado médico": str(src)}, base)
        self.assertEqual(sorted(Path(p).name for p in res.values()),
                         ["acta_de_nacimiento.pdf", "certificado_medico.pdf"])
        self.assertEqual(Path(res["CURP"] if "CURP" in res else res["Acta de nacimiento"]).read_bytes(),
                         b"%PDF-1.4 hola")
        # segundo intento con el mismo número de control: no sobrescribe
        with self.assertRaises(FileExistsError):
            storage.guardar_pdfs("20260113001", {"CURP": str(src)}, base)
        # fallo a la mitad -> se elimina lo copiado
        with self.assertRaises(OSError):
            storage.guardar_pdfs("20260113002", {"CURP": str(src), "INE": ""}, base)
        self.assertFalse((base / "20260113002").exists())
        with self.assertRaises(FileNotFoundError):
            storage.guardar_pdfs("20260113003", {"CURP": str(d / "no_existe.pdf")}, base)
        self.assertFalse((base / "20260113003").exists())


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestLoginGuard(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.g = v.LoginGuard(3, 300, self.reloj)
        self.c = "secretaria@ambar.edu"

    def test_bloquea_al_tercer_fallo(self):
        self.assertEqual(self.g.registrar_fallo(self.c), 2)
        self.assertEqual(self.g.registrar_fallo(self.c), 1)
        self.assertFalse(self.g.bloqueado(self.c))
        self.assertEqual(self.g.registrar_fallo(self.c), 0)
        self.assertTrue(self.g.bloqueado(self.c))

    def test_correo_no_distingue_mayusculas(self):
        for _ in range(3):
            self.g.registrar_fallo(self.c.upper())
        self.assertTrue(self.g.bloqueado(self.c))

    def test_desbloqueo_por_tiempo(self):
        for _ in range(3):
            self.g.registrar_fallo(self.c)
        self.reloj.t += 299
        self.assertTrue(self.g.bloqueado(self.c))
        self.assertEqual(self.g.segundos_restantes(self.c), 1)
        self.reloj.t += 2
        self.assertFalse(self.g.bloqueado(self.c))
        self.assertEqual(self.g.intentos_restantes(self.c), 3)  # contador reiniciado

    def test_exito_reinicia(self):
        self.g.registrar_fallo(self.c)
        self.g.registrar_fallo(self.c)
        self.g.registrar_exito(self.c)
        self.assertEqual(self.g.intentos_restantes(self.c), 3)

    def test_otro_usuario_no_afectado(self):
        for _ in range(3):
            self.g.registrar_fallo(self.c)
        self.assertFalse(self.g.bloqueado("otro@ambar.edu"))

    def test_bloqueo_permanente(self):
        g = v.LoginGuard(3, 0, self.reloj)
        for _ in range(3):
            g.registrar_fallo(self.c)
        self.reloj.t += 10**6
        self.assertTrue(g.bloqueado(self.c))


if __name__ == "__main__":
    unittest.main()