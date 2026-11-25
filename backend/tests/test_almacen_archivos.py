from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from backend import almacen_archivos
from backend.config import Settings
from backend.routers.alumnos import _preparar_pdfs
from ambar_common.validators import MAX_CLOUDINARY_FREE_PDF_BYTES
from starlette.datastructures import UploadFile


class AlmacenArchivosTests(unittest.TestCase):
    def test_cloudinary_obligatorio_rechaza_despliegue_sin_credenciales(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                db_user="ambar_app",
                db_password="test-password",
                jwt_secret="test-secret-" * 4,
                cloudinary_required=True,
            )

    def test_almacen_local_guarda_referencia_relativa_y_rechaza_travesia(self):
        with tempfile.TemporaryDirectory() as directorio:
            base = Path(directorio) / "expedientes"
            origen = Path(directorio) / "origen.pdf"
            origen.write_bytes(b"%PDF-1.4 test")
            configuracion = SimpleNamespace(
                cloudinary_configurado=False,
                storage_dir=base,
            )

            with patch.object(almacen_archivos, "settings", configuracion):
                locator = almacen_archivos.guardar_archivo(
                    origen,
                    "26320700/curp.pdf",
                )

                self.assertEqual(locator, "26320700/curp.pdf")
                self.assertTrue(almacen_archivos.existe_archivo(locator))
                self.assertEqual(
                    b"".join(almacen_archivos.transmitir_archivo(locator)),
                    b"%PDF-1.4 test",
                )
                almacen_archivos.eliminar_archivo(locator)
                self.assertFalse(almacen_archivos.existe_archivo(locator))

                outside = Path(directorio) / "outside.txt"
                outside.write_text("keep", encoding="utf-8")
                almacen_archivos.eliminar_archivo("../outside.txt")
                self.assertTrue(outside.exists())

    def test_cloudinary_almacena_documentos_con_entrega_privada(self):
        configuracion = SimpleNamespace(
            cloudinary_configurado=True,
            cloudinary_cloud_name="test-cloud",
            cloudinary_api_key="test-key",
            cloudinary_api_secret="test-secret",
        )
        with (
            tempfile.TemporaryDirectory() as directorio,
            patch.object(almacen_archivos, "settings", configuracion),
            patch.object(almacen_archivos, "_configurar_cloudinary"),
            patch.object(
                almacen_archivos.uploader,
                "upload_large",
                return_value={"public_id": "ambar/curp-test.pdf"},
            ) as upload,
        ):
            origen = Path(directorio) / "curp.pdf"
            origen.write_bytes(b"%PDF-1.4 test")

            locator = almacen_archivos.guardar_archivo(
                origen,
                "ambar/26320700/curp.pdf",
            )

        self.assertEqual(
            locator,
            "cloudinary:ambar/curp-test.pdf",
        )
        self.assertEqual(upload.call_args.kwargs["resource_type"], "raw")
        self.assertEqual(upload.call_args.kwargs["type"], "private")
        self.assertFalse(upload.call_args.kwargs["overwrite"])

    def test_cloudinary_descarga_usa_url_firmada_solo_en_el_backend(self):
        configuracion = SimpleNamespace(
            cloudinary_configurado=True,
            cloudinary_cloud_name="test-cloud",
            cloudinary_api_key="test-key",
            cloudinary_api_secret="test-secret",
        )
        response = MagicMock()
        response.iter_bytes.return_value = iter((b"%PDF-", b"1.4 test"))
        stream_context = MagicMock()
        stream_context.__enter__.return_value = response
        stream_context.__exit__.return_value = None

        with (
            patch.object(almacen_archivos, "settings", configuracion),
            patch.object(almacen_archivos, "_configurar_cloudinary"),
            patch.object(
                almacen_archivos,
                "private_download_url",
                return_value="https://signed-private-url",
            ),
            patch.object(
                almacen_archivos.httpx,
                "stream",
                return_value=stream_context,
            ) as request,
        ):
            contenido = b"".join(
                almacen_archivos.transmitir_archivo(
                    "cloudinary:ambar/curp-test.pdf",
                ),
            )

        self.assertEqual(contenido, b"%PDF-1.4 test")
        request.assert_called_once()
        self.assertEqual(request.call_args.args, ("GET", "https://signed-private-url"))

    def test_alta_rechaza_pdf_mayor_al_limite_del_plan_cloudinary_free(self):
        archivo = UploadFile(
            filename="curp.pdf",
            file=BytesIO(b"%PDF-" + b"x" * MAX_CLOUDINARY_FREE_PDF_BYTES),
        )
        configuracion = SimpleNamespace(cloudinary_configurado=True)

        with (
            tempfile.TemporaryDirectory() as directorio,
            patch("backend.routers.alumnos.settings", configuracion),
        ):
            pdfs, errores = _preparar_pdfs(
                Path(directorio),
                {"doc_curp": archivo},
            )

        self.assertEqual(pdfs, {})
        self.assertEqual(errores, ["CURP: El archivo excede 10 MB"])


if __name__ == "__main__":
    unittest.main()
