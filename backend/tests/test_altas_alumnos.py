"""Regresión de validaciones del formulario de altas antes de persistir."""
import datetime
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.deps import usuario_actual
from backend.esquemas import AltaIn
from backend.main import app
from backend.servicios import validar_alta


def datos_validos() -> dict:
    return {
        "ficha": "2026123456",
        "nombre": "Gael",
        "ap_paterno": "Castanon",
        "ap_materno": "Jesus",
        "fecha_nacimiento": "2005-03-02",
        "curp": "CAJG050302HGRSSLA4",
        "rfc": "CAJG050302AB1",
        "nss": "12345678901",
        "ine": "1234567890123",
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
    }


class ValidacionAltaAntesDePersistirTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[usuario_actual] = lambda: {
            "id_usuario": 1,
            "rol": "Secretaría",
        }
        self.client = TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)
        parche_catalogo = patch(
            "backend.routers.alumnos.servicios.validar_domicilio_catalogo",
            return_value={},
        )
        parche_catalogo.start()
        self.addCleanup(parche_catalogo.stop)

    def post_alta(self, payload: dict, incluir_documentos: bool = False):
        files = {
            campo: (f"{campo}.pdf", b"%PDF-1.4 documento de prueba", "application/pdf")
            for campo in (
                "doc_acta_nacimiento",
                "doc_curp",
                "doc_comprobante_domicilio",
                "doc_ine",
                "doc_certificado_preparatoria",
                "doc_certificado_medico",
            )
        } if incluir_documentos else None
        return self.client.post(
            "/alumnos",
            data={"datos": json.dumps(payload)},
            files=files,
        )

    def test_datos_validos_pasan_las_reglas_del_backend(self):
        datos = AltaIn.model_validate(datos_validos())

        self.assertEqual(validar_alta(datos), {})

    def test_domicilio_estructurado_valida_cp_y_campos_requeridos(self):
        payload = datos_validos()
        payload.update({"calle": "Avenida Costera", "numero_exterior": "123"})

        self.assertEqual(validar_alta(AltaIn.model_validate(payload)), {})

        payload["codigo_postal"] = "3900"
        with self.assertRaises(ValueError):
            AltaIn.model_validate(payload)

    def test_calle_y_numero_exterior_usan_reglas_flexibles_controladas(self):
        payload = datos_validos() | {
            "calle": "Av. Costera",
            "numero_exterior": "Manzana 4, Lote 12",
        }
        self.assertEqual(validar_alta(AltaIn.model_validate(payload)), {})

        for campo, valor in (
            ("calle", "AB"),
            ("calle", "nose"),
            ("calle", "asdfg"),
            ("calle", "ninguna"),
            ("calle", "aaaaaaaa"),
            ("numero_exterior", "Manzana B"),
            ("numero_exterior", "12@"),
        ):
            with self.subTest(campo=campo, valor=valor):
                errores = validar_alta(AltaIn.model_validate(datos_validos() | {campo: valor}))
                self.assertIn(campo, errores)

        payload = datos_validos()
        del payload["colonia"]
        with self.assertRaises(ValueError):
            AltaIn.model_validate(payload)

    def test_rechaza_combinacion_de_domicilio_que_no_existe_en_catalogo(self):
        error = "La colonia no corresponde al código postal seleccionado"
        with (
            patch(
                "backend.routers.alumnos.servicios.validar_domicilio_catalogo",
                return_value={"colonia": error},
            ),
            patch("backend.routers.alumnos.servicios.registrar_alta") as persistir,
        ):
            respuesta = self.post_alta(datos_validos())

        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(respuesta.json()["detail"]["errores"]["colonia"], error)
        persistir.assert_not_called()

    def test_consulta_cp_usa_el_catalogo_local(self):
        catalogo = {
            "codigo_postal": "39000",
            "estados": [{
                "estado": "Guerrero",
                "municipios": [{
                    "municipio": "Acapulco de Juárez",
                    "colonias": ["Centro"],
                }],
            }],
        }
        with patch(
            "backend.routers.alumnos.servicios.opciones_domicilio",
            return_value=catalogo,
        ) as consultar:
            respuesta = self.client.get("/alumnos/domicilios/39000")
            invalida = self.client.get("/alumnos/domicilios/3900")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), catalogo)
        self.assertEqual(invalida.status_code, 422)
        consultar.assert_called_once_with("39000")

    def test_consulta_preventiva_detecta_duplicados_de_identificadores(self):
        duplicados = {
            "nss": True,
            "rfc": True,
            "ine": True,
            "correo": True,
        }
        with patch(
            "backend.routers.alumnos.servicios.verificar_duplicados",
            return_value=duplicados,
        ) as verificar:
            respuesta = self.client.get(
                "/alumnos/verificar",
                params={
                    "ficha": "2026123456",
                    "curp": "CAJG050302HGRSSLA4",
                    "nss": "12345678901",
                    "rfc": "CAJG050302AB1",
                    "ine": "1234 5678 90123",
                    "correo": "alumno@gmail.com",
                },
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), duplicados)
        verificar.assert_called_once_with(
            "2026123456", "CAJG050302HGRSSLA4", "12345678901",
            "CAJG050302AB1", "1234567890123", "alumno@gmail.com",
        )

    def test_rechaza_campos_invalidos_sin_llamar_a_persistencia(self):
        casos_invalidos = {
            "ficha": "." * 10,
            "nombre": "...",
            "ap_paterno": "!!!",
            "ap_materno": "...",
            "fecha_nacimiento": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
            "curp": "!" * 18,
            "rfc": "." * 13,
            "nss": "." * 11,
            "ine": "123456789012a",
            "genero": "...",
            "celular": "." * 10,
            "correo": "." * 20,
            "domicilio": "." * 20,
            "preparatoria": "." * 20,
            "promedio": 5.99,
            "celular_emergencia": "." * 10,
            "correo_emergencia": "." * 20,
            "tipo_sangre": "C+",
            "alergias": "...!!!",
        }

        for campo, valor in casos_invalidos.items():
            with self.subTest(campo=campo), patch(
                "backend.routers.alumnos.servicios.registrar_alta"
            ) as persistir:
                payload = datos_validos()
                payload[campo] = valor

                respuesta = self.post_alta(payload)

                self.assertEqual(respuesta.status_code, 422)
                self.assertIn(campo, respuesta.json()["detail"]["errores"])
                persistir.assert_not_called()

    def test_rechaza_campos_no_definidos_en_el_esquema(self):
        payload = datos_validos() | {"campo_inesperado": "basura"}

        with patch("backend.routers.alumnos.servicios.registrar_alta") as persistir:
            respuesta = self.post_alta(payload)

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("campo_inesperado", respuesta.json()["detail"]["errores"])
        persistir.assert_not_called()

    def test_rechaza_campos_faltantes_tipos_incorrectos_y_fechas_imposibles(self):
        casos_invalidos = (
            ("nombre", lambda datos: datos.pop("nombre")),
            ("ine", lambda datos: datos.pop("ine")),
            ("ficha", lambda datos: datos.update(ficha=2026123456)),
            ("fecha_nacimiento", lambda datos: datos.update(fecha_nacimiento="2005-02-30")),
            ("fecha_nacimiento", lambda datos: datos.update(fecha_nacimiento=[])),
            ("promedio", lambda datos: datos.update(promedio="NaN")),
            ("promedio", lambda datos: datos.update(promedio="Infinity")),
            ("promedio", lambda datos: datos.update(promedio=[])),
        )
        with patch("backend.routers.alumnos.servicios.registrar_alta") as persistir:
            for campo, modificar in casos_invalidos:
                with self.subTest(campo=campo, modificar=modificar):
                    payload = datos_validos()
                    modificar(payload)

                    respuesta = self.post_alta(payload)

                    self.assertEqual(respuesta.status_code, 422)
                    self.assertIn(campo, respuesta.json()["detail"]["errores"])
            persistir.assert_not_called()

    def test_acepta_valores_en_los_limites_de_longitud_y_promedio(self):
        payload = datos_validos() | {
            "nombre": "A" * 50,
            "ap_paterno": "B" * 50,
            "ap_materno": "C" * 50,
            "curp": "BXCA050302HGRSSLA4",
            "correo": f"{'a' * 90}@gmail.com",
            "correo_emergencia": f"{'b' * 90}@gmail.com",
            "calle": "AB" * 75,
            "preparatoria": "E" * 100,
            "promedio": 7,
            "alergias": "F" * 200,
        }
        with patch(
            "backend.routers.alumnos.servicios.registrar_alta",
            return_value={
                "numero_control": "26320700",
                "correo_institucional": "al26320700@example.com",
                "nombre_completo": f"{'A' * 50} {'B' * 50} {'C' * 50}",
                "turno": "Vespertino",
                "documentos": 6,
            },
        ) as persistir:
            respuesta = self.post_alta(payload, incluir_documentos=True)

        self.assertEqual(respuesta.status_code, 201, msg=respuesta.text)
        persistir.assert_called_once()

    def test_rechaza_nombres_y_apellidos_de_51_caracteres_antes_de_persistir(self):
        with patch("backend.routers.alumnos.servicios.registrar_alta") as persistir:
            for campo in ("nombre", "ap_paterno", "ap_materno"):
                with self.subTest(campo=campo):
                    respuesta = self.post_alta(
                        datos_validos() | {campo: "A" * 51},
                    )

                    self.assertEqual(respuesta.status_code, 422)
                    self.assertIn(campo, respuesta.json()["detail"]["errores"])
            persistir.assert_not_called()

    def test_curp_coincide_con_apellidos_y_requiere_rfc_en_adultos(self):
        casos_invalidos = (
            ({"ap_paterno": "Lopez"}, "curp"),
            ({"genero": "hombre", "curp": "CAJG050302MGRSSLA4"}, "curp"),
            ({"rfc": None}, "rfc"),
        )
        with patch("backend.routers.alumnos.servicios.registrar_alta") as persistir:
            for cambios, campo_esperado in casos_invalidos:
                with self.subTest(cambios=cambios):
                    respuesta = self.post_alta(datos_validos() | cambios)
                    self.assertEqual(respuesta.status_code, 422)
                    self.assertIn(campo_esperado, respuesta.json()["detail"]["errores"])
            persistir.assert_not_called()

    def test_menor_de_edad_puede_omitir_rfc_e_ine_ocr(self):
        fecha = datetime.date.today().replace(year=datetime.date.today().year - 16)
        payload = datos_validos() | {
            "fecha_nacimiento": fecha.isoformat(),
            "curp": f"CAJG{fecha:%y%m%d}HGRSSLA4",
            "rfc": None,
            "ine": "",
        }
        datos = AltaIn.model_validate(payload)

        self.assertIsNone(datos.ine)
        self.assertEqual(validar_alta(datos), {})

    def test_alta_adulta_requiere_ine_ocr_de_13_digitos(self):
        payload = datos_validos() | {"ine": None}

        with patch("backend.routers.alumnos.servicios.registrar_alta") as persistir:
            respuesta = self.post_alta(payload)

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("ine", respuesta.json()["detail"]["errores"])
        persistir.assert_not_called()

    def test_alta_normaliza_espacios_del_ocr_antes_de_validar_y_guardar(self):
        payload = datos_validos() | {"ine": "1234 5678 90123"}
        datos = AltaIn.model_validate(payload)
        self.assertEqual(datos.ine, "1234567890123")
        self.assertEqual(validar_alta(datos), {})

    def test_rechaza_alta_con_excepcion_de_conflicto_del_servicio(self):
        from backend.servicios import Conflicto

        with patch(
            "backend.routers.alumnos.servicios.registrar_alta",
            side_effect=Conflicto("La ficha ya está registrada", {"ficha": "Duplicada"}),
        ) as persistir:
            respuesta = self.post_alta(datos_validos(), incluir_documentos=True)

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["detail"]["errores"]["ficha"], "Duplicada")
        persistir.assert_called_once()

    def test_mapea_excepciones_operativas_del_servicio(self):
        from backend.servicios import CupoLleno, Ocupado, SinGrupos

        casos = (
            (CupoLleno("No hay cupo"), 409, "cupo_lleno"),
            (SinGrupos("No hay grupos"), 503, None),
            (Ocupado(), 503, None),
            (OSError("Disco lleno"), 500, None),
        )
        for excepcion, status_esperado, codigo_esperado in casos:
            with self.subTest(excepcion=type(excepcion).__name__), patch(
                "backend.routers.alumnos.servicios.registrar_alta",
                side_effect=excepcion,
            ):
                respuesta = self.post_alta(
                    datos_validos(),
                    incluir_documentos=True,
                )

                self.assertEqual(respuesta.status_code, status_esperado)
                if codigo_esperado:
                    self.assertEqual(respuesta.json()["detail"]["codigo"], codigo_esperado)

    def test_excepcion_no_controlada_del_servicio_responde_500(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "backend.routers.alumnos.servicios.registrar_alta",
            side_effect=RuntimeError("Fallo inesperado"),
        ):
            respuesta = client.post(
                "/alumnos",
                data={"datos": json.dumps(datos_validos())},
                files={
                    campo: (f"{campo}.pdf", b"%PDF-1.4 documento de prueba", "application/pdf")
                    for campo in (
                        "doc_acta_nacimiento",
                        "doc_curp",
                        "doc_comprobante_domicilio",
                        "doc_ine",
                        "doc_certificado_preparatoria",
                        "doc_certificado_medico",
                    )
                },
            )

        self.assertEqual(respuesta.status_code, 500)

    def test_limita_correos_a_la_longitud_de_la_columna(self):
        correo_largo = f"{'a' * 91}@gmail.com"
        for campo in ("correo", "correo_emergencia"):
            with self.subTest(campo=campo), patch(
                "backend.routers.alumnos.servicios.registrar_alta"
            ) as persistir:
                payload = datos_validos()
                payload[campo] = correo_largo

                respuesta = self.post_alta(payload)

                self.assertEqual(respuesta.status_code, 422)
                self.assertIn(campo, respuesta.json()["detail"]["errores"])
                persistir.assert_not_called()

    def test_alta_valida_llama_a_persistencia_con_los_datos_normalizados(self):
        payload = datos_validos() | {"ine": "1234 5678 90123"}
        resultado_esperado = {
            "numero_control": "26320700",
            "correo_institucional": "al26320700@example.com",
            "nombre_completo": "Gael Castanon Jesus",
            "turno": "Matutino",
            "documentos": 6,
        }
        with patch(
            "backend.routers.alumnos.servicios.registrar_alta",
            return_value=resultado_esperado,
        ) as persistir:
            respuesta = self.post_alta(payload, incluir_documentos=True)

        self.assertEqual(respuesta.status_code, 201, msg=respuesta.text)
        self.assertEqual(respuesta.json()["numero_control"], resultado_esperado["numero_control"])
        self.assertEqual(respuesta.json()["documentos"], resultado_esperado["documentos"])
        persistir.assert_called_once()
        self.assertEqual(persistir.call_args.args[0].curp, payload["curp"])
        self.assertEqual(persistir.call_args.args[0].ine, "1234567890123")
        self.assertEqual(persistir.call_args.args[0].tipo_sangre, "O+")

    def test_tipo_sangre_es_obligatorio_en_el_alta(self):
        payload = datos_validos()
        del payload["tipo_sangre"]

        with patch("backend.routers.alumnos.servicios.registrar_alta") as persistir:
            respuesta = self.post_alta(payload)

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("tipo_sangre", respuesta.json()["detail"]["errores"])
        persistir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
