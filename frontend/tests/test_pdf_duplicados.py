import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import main


class PdfDuplicadosTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        self.addCleanup(self.directorio.cleanup)
        self.ruta = Path(self.directorio.name)
        self.formulario = object.__new__(main.FormAltas)
        self.formulario.selector_archivos = Mock()
        self.formulario.selector_archivos._i = 9
        self.formulario.page = Mock(route="/altas")
        self.formulario.errores_por_documento = {}
        self.formulario.documentos_seleccionados = {}
        self.formulario._actualizar_vista_del_formulario = Mock()

    def _crear_pdf_temporal(self, nombre_archivo: str, contenido_pdf: bytes) -> Path:
        ruta_pdf = self.ruta / nombre_archivo
        ruta_pdf.write_bytes(contenido_pdf)
        return ruta_pdf

    async def _seleccionar_documento(self, nombre_documento: str, ruta_pdf: Path):
        self.formulario.selector_archivos.pick_files = AsyncMock(return_value=[
            SimpleNamespace(
                name=ruta_pdf.name,
                size=ruta_pdf.stat().st_size,
                path=str(ruta_pdf),
            )
        ])
        await self.formulario._seleccionar_y_validar_pdf(nombre_documento)

    async def test_rechaza_el_mismo_pdf_aunque_tenga_otro_nombre(self):
        contenido = b"%PDF-1.4\ncontenido"
        original = self._crear_pdf_temporal("acta.pdf", contenido)
        copia = self._crear_pdf_temporal("curp-copia.pdf", contenido)
        self.formulario.documentos_seleccionados["Acta de nacimiento"] = {
            "nombre": original.name,
            "path": str(original),
            "size": original.stat().st_size,
            "huella": main.FormAltas._calcular_hash_sha256_del_pdf(str(original)),
        }

        await self._seleccionar_documento("CURP", copia)

        self.assertNotIn("CURP", self.formulario.documentos_seleccionados)
        self.assertIn("Acta de nacimiento", self.formulario.errores_por_documento["CURP"])

    async def test_acepta_pdf_distinto_aunque_tenga_el_mismo_nombre(self):
        existente = self._crear_pdf_temporal("documento.pdf", b"%PDF-1.4\ncontenido uno")
        seleccionado = self._crear_pdf_temporal(
            "documento-seleccionado.pdf",
            b"%PDF-1.4\ncontenido dos",
        )
        self.formulario.documentos_seleccionados["Acta de nacimiento"] = {
            "nombre": existente.name,
            "path": str(existente),
            "size": existente.stat().st_size,
            "huella": main.FormAltas._calcular_hash_sha256_del_pdf(str(existente)),
        }

        await self._seleccionar_documento("CURP", seleccionado)

        self.assertEqual(
            self.formulario.documentos_seleccionados["CURP"]["path"],
            str(seleccionado),
        )
        self.assertNotIn("CURP", self.formulario.errores_por_documento)

    async def test_registra_el_timeout_del_selector_en_el_log(self):
        error = RuntimeError(
            "Timeout waiting for invoke method listener for FilePicker(9).pick_files"
        )
        self.formulario.selector_archivos.pick_files = AsyncMock(side_effect=error)

        with self.assertLogs("sige.frontend", level="ERROR") as capturado:
            await self.formulario._seleccionar_y_validar_pdf("CURP")

        self.assertIn("FilePicker.pick_files", capturado.output[0])
        self.assertIn("control=9", capturado.output[0])
        self.assertIn("Timeout waiting for invoke method listener", capturado.output[0])
        self.assertIn(
            "No se pudo abrir el selector",
            self.formulario.errores_por_documento["CURP"],
        )


if __name__ == "__main__":
    unittest.main()
