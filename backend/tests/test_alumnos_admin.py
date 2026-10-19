import datetime
from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from backend.esquemas import AltaIn
from backend.main import app
from backend.routers.alumnos import (
    actualizar_alumno,
    actualizar_documentos,
    eliminar_alumno,
    expediente,
    historial_alumno,
    secretaria_o_administrador,
)


class GestionConsultasTests(unittest.TestCase):
    def test_incluir_bajas_solo_funciona_para_administrador(self):
        admin = {"rol": "Administrador"}
        secretaria = {"rol": "Secretaría"}
        esperado = {"numero_control": "26320700"}

        with patch("backend.routers.alumnos.servicios.buscar_expediente", return_value=esperado) as buscar:
            self.assertEqual(expediente("26320700", admin, True), esperado)
        buscar.assert_called_once_with("26320700", True)

        with self.assertRaises(HTTPException) as error:
            expediente("26320700", secretaria, True)
        self.assertEqual(error.exception.status_code, 403)

    def test_actualizacion_registra_el_usuario_que_la_hizo(self):
        datos = AltaIn(
            ficha="2026123456",
            nombre="Gael",
            ap_paterno="Castanon",
            ap_materno="Jesus",
            fecha_nacimiento=datetime.date(2005, 3, 2),
            curp="CAJG050302HGRSSLA4",
            nss="12345678901",
            genero="hombre",
            celular="7441234567",
            correo="alumno@example.com",
            domicilio="Calle 1, Colonia Centro, Acapulco",
            preparatoria="Preparatoria de prueba",
            promedio=9.5,
            celular_emergencia="7447654321",
            correo_emergencia="contacto@example.com",
        )
        usuario = {"id_usuario": 17}
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            resultado = actualizar_alumno("26320700", datos, usuario)

        self.assertEqual(resultado, {"mensaje": "Datos del alumno actualizados"})
        actualizar.assert_called_once_with("26320700", datos, 17)

    def test_administrador_puede_actualizar_y_se_registra_como_actor(self):
        datos = AltaIn(
            ficha="2026123456",
            nombre="Gael",
            ap_paterno="Castanon",
            ap_materno="Jesus",
            fecha_nacimiento=datetime.date(2005, 3, 2),
            curp="CAJG050302HGRSSLA4",
            nss="12345678901",
            genero="hombre",
            celular="7441234567",
            correo="alumno@example.com",
            domicilio="Calle 1, Colonia Centro, Acapulco",
            preparatoria="Preparatoria de prueba",
            promedio=9.5,
            celular_emergencia="7447654321",
            correo_emergencia="contacto@example.com",
        )
        usuario = {"id_usuario": 31, "rol": "Administrador"}
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            resultado = actualizar_alumno("26320700", datos, usuario)

        self.assertEqual(resultado, {"mensaje": "Datos del alumno actualizados"})
        actualizar.assert_called_once_with("26320700", datos, 31)

    def test_documentos_puede_agregar_un_pdf_a_un_expediente(self):
        archivo = UploadFile(
            filename="curp.pdf",
            file=BytesIO(b"%PDF-1.4 contenido de prueba"),
        )
        usuario = {"id_usuario": 17, "rol": "Secretaría"}
        with patch("backend.routers.alumnos.servicios.actualizar_documentos") as actualizar:
            resultado = actualizar_documentos(
                "26320700",
                doc_acta_nacimiento=None,
                doc_curp=archivo,
                doc_comprobante_domicilio=None,
                doc_ine=None,
                doc_certificado_preparatoria=None,
                doc_certificado_medico=None,
                doc_constancia_situacion_fiscal=None,
                usuario=usuario,
            )

        self.assertEqual(resultado, {"mensaje": "Documentos del expediente actualizados"})
        actualizado = actualizar.call_args.args
        self.assertEqual(actualizado[0], "26320700")
        self.assertEqual(set(actualizado[1]), {"CURP"})

    def test_documentos_rechaza_archivos_que_no_son_pdf(self):
        archivo = UploadFile(filename="curp.txt", file=BytesIO(b"contenido"))
        with patch("backend.routers.alumnos.servicios.actualizar_documentos") as actualizar:
            with self.assertRaises(HTTPException) as error:
                actualizar_documentos(
                    "26320700",
                    doc_acta_nacimiento=None,
                    doc_curp=archivo,
                    doc_comprobante_domicilio=None,
                    doc_ine=None,
                    doc_certificado_preparatoria=None,
                    doc_certificado_medico=None,
                    doc_constancia_situacion_fiscal=None,
                    usuario={"rol": "Secretaría"},
                )

        self.assertEqual(error.exception.status_code, 422)
        actualizar.assert_not_called()

    def test_baja_es_logica_y_registra_el_actor(self):
        usuario = {"id_usuario": 23}
        with patch("backend.routers.alumnos.servicios.eliminar_alumno") as eliminar:
            resultado = eliminar_alumno("26320700", usuario)

        self.assertEqual(
            resultado,
            {"mensaje": "Expediente dado de baja; el historial se conserva"},
        )
        eliminar.assert_called_once_with("26320700", 23)

    def test_administrador_puede_dar_de_baja_y_se_registra_como_actor(self):
        usuario = {"id_usuario": 32, "rol": "Administrador"}
        with patch("backend.routers.alumnos.servicios.eliminar_alumno") as eliminar:
            resultado = eliminar_alumno("26320700", usuario)

        self.assertEqual(
            resultado,
            {"mensaje": "Expediente dado de baja; el historial se conserva"},
        )
        eliminar.assert_called_once_with("26320700", 32)

    def test_gestion_de_alumnos_admite_secretaria_y_administracion(self):
        for rol in ("Secretaría", "Administrador"):
            with self.subTest(rol=rol):
                self.assertEqual(secretaria_o_administrador({"rol": rol}), {"rol": rol})

        with self.assertRaises(HTTPException) as error:
            secretaria_o_administrador({"rol": "Docente"})
        self.assertEqual(error.exception.status_code, 403)

    def test_historial_consulta_el_registro_actual_incluidas_las_bajas(self):
        with (
            patch(
                "backend.routers.alumnos.servicios.buscar_expediente",
                return_value={"numero_control": "26320700"},
            ) as buscar,
            patch(
                "backend.routers.alumnos.servicios.historial_alumno",
                return_value=[{"accion": "BAJA"}],
            ) as historial,
        ):
            resultado = historial_alumno("26320700")

        self.assertEqual(resultado, [{"accion": "BAJA"}])
        buscar.assert_called_once_with("26320700", incluir_bajas=True)
        historial.assert_called_once_with("26320700")

    def test_endpoints_de_administracion_estan_publicados(self):
        paths = app.openapi()["paths"]
        self.assertIn("put", paths["/alumnos/{numero_control}"])
        self.assertIn("put", paths["/alumnos/{numero_control}/documentos"])
        self.assertIn("delete", paths["/alumnos/{numero_control}"])
        self.assertIn("get", paths["/alumnos/{numero_control}/historial"])


if __name__ == "__main__":
    unittest.main()
