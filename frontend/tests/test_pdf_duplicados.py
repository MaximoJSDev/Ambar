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
        self.formulario.picker = Mock()
        self.formulario.picker._i = 9
        self.formulario.page = Mock(route="/altas")
        self.formulario.errores_docs = {}
        self.formulario.archivos = {}
        self.formulario._pintar = Mock()

    def _pdf(self, nombre: str, contenido: bytes) -> Path:
        ruta = self.ruta / nombre
        ruta.write_bytes(contenido)
        return ruta

    async def _seleccionar(self, doc: str, ruta: Path):
        self.formulario.picker.pick_files = AsyncMock(return_value=[
            SimpleNamespace(name=ruta.name, size=ruta.stat().st_size, path=str(ruta))
        ])
        await self.formulario._elegir_pdf(doc)

    async def test_rechaza_el_mismo_pdf_aunque_tenga_otro_nombre(self):
        contenido = b"%PDF-1.4\ncontenido"
        original = self._pdf("acta.pdf", contenido)
        copia = self._pdf("curp-copia.pdf", contenido)
        self.formulario.archivos["Acta de nacimiento"] = {
            "nombre": original.name,
            "path": str(original),
            "size": original.stat().st_size,
            "huella": main.FormAltas._huella_pdf(str(original)),
        }

        await self._seleccionar("CURP", copia)

        self.assertNotIn("CURP", self.formulario.archivos)
        self.assertIn("Acta de nacimiento", self.formulario.errores_docs["CURP"])

    async def test_acepta_pdf_distinto_aunque_tenga_el_mismo_nombre(self):
        existente = self._pdf("documento.pdf", b"%PDF-1.4\ncontenido uno")
        seleccionado = self._pdf("documento-seleccionado.pdf", b"%PDF-1.4\ncontenido dos")
        self.formulario.archivos["Acta de nacimiento"] = {
            "nombre": existente.name,
            "path": str(existente),
            "size": existente.stat().st_size,
            "huella": main.FormAltas._huella_pdf(str(existente)),
        }

        await self._seleccionar("CURP", seleccionado)

        self.assertEqual(self.formulario.archivos["CURP"]["path"], str(seleccionado))
        self.assertNotIn("CURP", self.formulario.errores_docs)

    async def test_registra_el_timeout_del_selector_en_el_log(self):
        error = RuntimeError(
            "Timeout waiting for invoke method listener for FilePicker(9).pick_files"
        )
        self.formulario.picker.pick_files = AsyncMock(side_effect=error)

        with self.assertLogs("sige.frontend", level="ERROR") as capturado:
            await self.formulario._elegir_pdf("CURP")

        self.assertIn("FilePicker.pick_files", capturado.output[0])
        self.assertIn("control=9", capturado.output[0])
        self.assertIn("Timeout waiting for invoke method listener", capturado.output[0])
        self.assertIn("No se pudo abrir el selector", self.formulario.errores_docs["CURP"])


if __name__ == "__main__":
    unittest.main()
