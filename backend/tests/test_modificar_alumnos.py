"""Pruebas de validación al modificar datos de un expediente de alumno."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import servicios
from backend.deps import usuario_actual
from backend.esquemas import AltaIn
from backend.main import app


def datos_alumno(**cambios) -> dict:
    return {
        "ficha": "2026123456",
        "nombre": "Gael",
        "ap_paterno": "Castanon",
        "ap_materno": "Jesus",
        "fecha_nacimiento": "2005-03-02",
        "curp": "CAJG050302HGRSSLA4",
        "ine": "1234567890123",
        "nss": "12345678901",
        "genero": "hombre",
        "celular": "7441234567",
        "correo": "alumno@gmail.com",
        "codigo_postal": "39000",
        "estado": "Guerrero",
        "municipio": "Acapulco de Juárez",
        "colonia": "Centro",
        "calle": "Calle 1",
        "numero_exterior": "12",
        "preparatoria": "Preparatoria de prueba",
        "promedio": 9.5,
        "celular_emergencia": "7447654321",
        "correo_emergencia": "contacto@gmail.com",
        "tipo_sangre": "O+",
        "alergias": "Ninguna",
    } | cambios


class ModificarAlumnoTests(unittest.TestCase):
    def setUp(self):
        self.usuario = {"id_usuario": 17, "rol": "Secretaría"}
        app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.client = TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)
        parche_catalogo = patch(
            "backend.routers.alumnos.servicios.validar_domicilio_catalogo",
            return_value={},
        )
        self.validar_catalogo = parche_catalogo.start()
        self.addCleanup(parche_catalogo.stop)

    def test_cp_ausente_del_catalogo_se_permite_solo_en_validacion_de_edicion(self):
        datos = AltaIn.model_validate(datos_alumno(codigo_postal="39814"))
        with (
            patch(
                "backend.servicios.opciones_domicilio",
                return_value={"codigo_postal": "39814", "estados": []},
            ),
            patch("backend.servicios.engine.connect") as conectar,
        ):
            errores = servicios.validar_domicilio_catalogo(
                datos,
                permitir_cp_sin_catalogo=True,
            )

        self.assertEqual(errores, {})
        conectar.assert_not_called()

    def test_actualizacion_valida_persiste_datos_y_registra_actor(self):
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(),
            )

        self.assertEqual(
            respuesta.status_code,
            200,
            msg=respuesta.text,
        )
        self.assertEqual(respuesta.json(), {"mensaje": "Datos del alumno actualizados"})
        actualizar.assert_called_once()
        numero_control, datos, id_usuario = actualizar.call_args.args
        self.assertEqual(numero_control, "26320700")
        self.assertEqual(datos.curp, "CAJG050302HGRSSLA4")
        self.assertEqual(id_usuario, 17)
        self.assertTrue(self.validar_catalogo.call_args.kwargs["permitir_cp_sin_catalogo"])

    def test_actualizacion_permite_editar_domicilio_con_cp_ausente_del_catalogo(self):
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(
                    codigo_postal="39814",
                    estado="Guerrero",
                    municipio="Acapulco",
                    colonia="Nueva colonia",
                    calle="Carretera Cayaco",
                    numero_exterior="64",
                ),
            )

        self.assertEqual(respuesta.status_code, 200, msg=respuesta.text)
        self.assertTrue(
            self.validar_catalogo.call_args.kwargs["permitir_cp_sin_catalogo"]
        )
        actualizar.assert_called_once()

    def test_curp_y_rfc_se_validan_al_modificar(self):
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(rfc="CAJG050302KU3"),
            )

        self.assertEqual(respuesta.status_code, 200, msg=respuesta.text)
        actualizar.assert_called_once()

        casos_invalidos = (
            ({"curp": "!" * 18}, "curp"),
            ({"fecha_nacimiento": "2005-03-03"}, "curp"),
            ({"ap_paterno": "López"}, "curp"),
            ({"genero": "mujer"}, "curp"),
            ({"rfc": "!" * 13}, "rfc"),
            ({"rfc": "CAJG050303KU3"}, "rfc"),
        )
        actualizar.reset_mock()
        for cambios, campo in casos_invalidos:
            with self.subTest(cambios=cambios):
                respuesta = self.client.put(
                    "/alumnos/26320700",
                    json=datos_alumno(**{"rfc": "CAJG050302KU3", **cambios}),
                )
                self.assertEqual(respuesta.status_code, 422)
                self.assertIn(campo, respuesta.json()["detail"]["errores"])
        actualizar.assert_not_called()

    def test_rechaza_datos_invalidos_sin_modificar_el_registro(self):
        casos_invalidos = (
            {"nombre": "...."},
            {"nombre": "A" * 51},
            {"ap_paterno": "A" * 51},
            {"ap_materno": "A" * 51},
            {"curp": "!" * 18},
            {"nss": "." * 11},
            {"correo": "....@....com"},
            {"correo": f"{'a' * 91}@gmail.com"},
            {"tipo_sangre": "C+"},
            {"calle": "!!!"},
            {"calle": "nose"},
            {"numero_exterior": "Manzana B"},
            {"preparatoria": "!!!"},
            {"promedio": 10.01},
            {"alergias": "!!!"},
        )
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            for cambios in casos_invalidos:
                with self.subTest(cambios=cambios):
                    respuesta = self.client.put(
                        "/alumnos/26320700",
                        json=datos_alumno(**cambios),
                    )
                    self.assertEqual(respuesta.status_code, 422)
                    self.assertTrue(respuesta.json()["detail"]["errores"])
            actualizar.assert_not_called()

    def test_rechaza_tipos_incorrectos_campos_omitidos_y_promedios_no_finitos(self):
        casos_invalidos = (
            {"nombre": 123},
            {"fecha_nacimiento": "2005-02-30"},
            {"fecha_nacimiento": []},
            {"promedio": "NaN"},
            {"promedio": "Infinity"},
            {"promedio": []},
            {"alergias": None},
        )
        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            for cambios in casos_invalidos:
                with self.subTest(cambios=cambios):
                    respuesta = self.client.put(
                        "/alumnos/26320700",
                        json=datos_alumno(**cambios),
                    )
                    self.assertEqual(respuesta.status_code, 422)
            payload = datos_alumno()
            del payload["curp"]
            respuesta = self.client.put("/alumnos/26320700", json=payload)

            self.assertEqual(respuesta.status_code, 422)
            actualizar.assert_not_called()

    def test_falla_inesperada_del_servicio_responde_500(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "backend.routers.alumnos.servicios.actualizar_alumno",
            side_effect=RuntimeError("Fallo de almacenamiento"),
        ):
            respuesta = client.put(
                "/alumnos/26320700",
                json=datos_alumno(),
            )

        self.assertEqual(respuesta.status_code, 500)

    def test_administrador_tambien_puede_modificar_y_se_registra_como_actor(self):
        self.usuario.update({"id_usuario": 31, "rol": "Administrador"})

        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(),
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(actualizar.call_args.args[2], 31)

    def test_usuario_sin_permiso_no_puede_modificar(self):
        self.usuario["rol"] = "Docente"

        with patch("backend.routers.alumnos.servicios.actualizar_alumno") as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(),
            )

        self.assertEqual(respuesta.status_code, 403)
        actualizar.assert_not_called()

    def test_alumno_inexistente_devuelve_404(self):
        with patch(
            "backend.routers.alumnos.servicios.actualizar_alumno",
            side_effect=servicios.NoEncontrado(),
        ) as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(),
            )

        self.assertEqual(respuesta.status_code, 404)
        actualizar.assert_called_once()

    def test_conflicto_de_datos_duplicados_devuelve_409(self):
        with patch(
            "backend.routers.alumnos.servicios.actualizar_alumno",
            side_effect=servicios.Conflicto(
                "La CURP ya está registrada",
                {"curp": "Duplicada"},
            ),
        ) as actualizar:
            respuesta = self.client.put(
                "/alumnos/26320700",
                json=datos_alumno(),
            )

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["detail"]["errores"]["curp"], "Duplicada")
        actualizar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
