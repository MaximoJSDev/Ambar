import unittest
from unittest.mock import MagicMock, patch

import flet as ft
import main


def controles(control):
    vistos = set()
    pendientes = [control]
    while pendientes:
        actual = pendientes.pop()
        if id(actual) in vistos:
            continue
        vistos.add(id(actual))
        yield actual
        pendientes.extend(getattr(actual, "controls", []) or [])
        contenido = getattr(actual, "content", None)
        if contenido is not None:
            pendientes.append(contenido)


class ReinscripcionFormTests(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock()
        self.vista = main.build_reinscripcion(self.page, lambda _: None)
        self.controles = list(controles(self.vista))

    def campo(self, hint):
        return next(
            control for control in self.controles
            if isinstance(control, ft.TextField) and control.hint_text == hint
        )

    def boton(self, etiqueta):
        return next(
            control for control in self.controles
            if isinstance(control, (ft.FilledButton, ft.OutlinedButton))
            and control.content == etiqueta
        )

    def test_semestre_sin_seleccionar_muestra_el_error_bajo_el_selector(self):
        selector_semestre = next(
            control for control in self.controles
            if isinstance(control, ft.Dropdown) and control.label == "Semestre"
        )

        self.boton("Registrar reinscripción").on_click(None)

        self.assertEqual(selector_semestre.error_text, "Selecciona segundo o tercer semestre")

    def test_paquete_es_obligatorio_antes_de_registrar(self):
        self.campo("8 dígitos").value = "26320700"
        self.campo("Nombre(s)").value = "Ana"
        self.campo("Apellidos").value = "Prueba"
        selector_semestre = next(
            control for control in self.controles
            if isinstance(control, ft.Dropdown) and control.label == "Semestre"
        )
        selector_semestre.value = "2"
        with patch.object(main.api, "paquetes_horario", return_value=[]):
            selector_semestre.on_select(None)
            self.boton("Registrar reinscripción").on_click(None)

        selector_paquete = next(
            control for control in self.controles
            if isinstance(control, ft.Dropdown) and control.label == "Paquete asignado"
        )
        self.assertEqual(
            selector_paquete.error_text,
            "Selecciona un paquete con lugares disponibles",
        )

    def test_busqueda_cambia_boton_y_actualizacion_muestra_toast(self):
        registro = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 10,
            "paquete": "2ISC1",
        }
        paquetes = [{"id_paquete": 10, "nombre": "2ISC1", "turno": "Matutino", "lugares": 3}]
        with patch.object(main.api, "reinscripcion", return_value=registro), patch.object(
            main.api, "paquetes_horario", return_value=paquetes,
        ), patch.object(
            main.api, "modificar_reinscripcion", return_value=registro,
        ) as modificar:
            self.campo("8 dígitos").value = "26320700"
            self.boton("Buscar para modificar").on_click(None)
            actualizar = self.boton("Actualizar reinscripción")
            self.assertEqual(actualizar.content, "Actualizar reinscripción")
            self.assertTrue(self.campo("8 dígitos").read_only)

            self.campo("Nombre(s)").value = "Ana María"
            actualizar.on_click(None)

        modificar.assert_called_once_with(
            "26320700",
            {
                "numero_control": "26320700",
                "nombre": "Ana María",
                "apellidos": "Prueba",
                "semestre": 2,
                "id_paquete": 10,
            },
        )
        self.assertIn("actualizada", self.page.show_dialog.call_args.args[0].content.value)

    def test_registro_muestra_toast_con_el_paquete_de_horario(self):
        resultado = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 11,
            "paquete": "2ISC1",
        }
        paquetes = [
            {"id_paquete": 11, "nombre": "2ISC1", "turno": "Matutino", "lugares": 3},
            {"id_paquete": 12, "nombre": "2ISC2", "turno": "Vespertino", "lugares": 0},
        ]
        with patch.object(
            main.api, "paquetes_horario", return_value=paquetes,
        ), patch.object(
            main.api, "registrar_reinscripcion", return_value=resultado,
        ) as registrar:
            self.campo("8 dígitos").value = "26320700"
            self.campo("Nombre(s)").value = "Ana"
            self.campo("Apellidos").value = "Prueba"
            selector_semestre = next(
                control for control in self.controles
                if isinstance(control, ft.Dropdown) and control.label == "Semestre"
            )
            selector_semestre.value = "2"
            selector_semestre.on_select(None)
            selector_paquete = next(
                control for control in self.controles
                if isinstance(control, ft.Dropdown) and control.label == "Paquete asignado"
            )
            self.assertTrue(selector_paquete.visible)
            self.assertEqual([opcion.key for opcion in selector_paquete.options], ["11"])
            selector_paquete.value = "11"
            self.boton("Registrar reinscripción").on_click(None)

        registrar.assert_called_once_with({
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 11,
        })
        self.assertIn("2ISC1", self.page.show_dialog.call_args.args[0].content.value)

    def test_modificacion_muestra_paquetes_en_desplegable_y_envia_la_seleccion(self):
        registro = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 10,
            "paquete": "2ISC1",
        }
        paquetes = [
            {"id_paquete": 10, "nombre": "2ISC1", "turno": "Matutino", "lugares": 0},
            {"id_paquete": 11, "nombre": "2ISC2", "turno": "Vespertino", "lugares": 4},
            {"id_paquete": 12, "nombre": "2ISC3", "turno": "Mixto", "lugares": 0},
        ]
        expediente = main.ConsultaExpediente.__new__(main.ConsultaExpediente)
        expediente.page = MagicMock()
        expediente.navegar = MagicMock()
        expediente.reinscripcion_data = registro
        expediente.entrada = MagicMock()
        expediente._pintar = MagicMock()
        actualizada = registro | {"id_paquete": 11, "paquete": "2ISC2"}

        with patch.object(main.api, "paquetes_horario", return_value=paquetes), patch.object(
            main.api, "modificar_reinscripcion", return_value=actualizada,
        ) as modificar, patch.object(
            main.api, "reinscripcion", return_value=actualizada,
        ):
            expediente._editar_reinscripcion()
            dialogo = expediente.page.show_dialog.call_args.args[0]
            campos = list(controles(dialogo.content))
            selector_paquete = next(
                control for control in campos
                if isinstance(control, ft.Dropdown) and control.label == "Paquete asignado"
            )
            self.assertEqual(selector_paquete.value, "10")
            numero = next(
                control for control in campos
                if isinstance(control, ft.TextField) and control.label == "Número de control"
            )
            self.assertTrue(numero.read_only)
            self.assertEqual(
                [opcion.key for opcion in selector_paquete.options],
                ["10", "11"],
            )
            selector_paquete.value = "11"
            boton_actualizar = next(
                control for control in dialogo.actions
                if isinstance(control, ft.FilledButton)
            )
            boton_actualizar.on_click(None)

        self.assertEqual(modificar.call_args.args[1]["id_paquete"], 11)

    def test_consultas_y_bajas_muestran_reinscripciones_por_numero_de_control(self):
        registro = {
            "numero_control": "26320700",
            "nombre": "Ana",
            "apellidos": "Prueba",
            "semestre": 2,
            "id_paquete": 10,
            "paquete": "2ISC1",
        }
        for rol, modo_bajas in (("Secretaría", False), ("Administrador", True)):
            with self.subTest(rol=rol, modo_bajas=modo_bajas):
                expediente = main.ConsultaExpediente.__new__(main.ConsultaExpediente)
                expediente.page = MagicMock()
                expediente.usuario = {"rol": rol}
                expediente.es_admin = rol == "Administrador"
                expediente.modo_modificacion = False
                expediente.modo_bajas = modo_bajas
                expediente.navegar = MagicMock()
                expediente.datos = None
                expediente.reinscripcion_data = None
                expediente.incluir_bajas = False
                expediente.historial = []
                expediente.error_historial = None
                expediente.horario = None
                expediente.paquetes_horario = []
                expediente.error_horario = None
                expediente.seccion = "personales"
                expediente.resultado = ft.Column(spacing=20)
                expediente.entrada = ft.TextField(value="26320700")
                expediente.boton = ft.FilledButton("Buscar")
                expediente.aviso = ft.Text("", visible=False)

                with patch.object(main.api, "reinscripcion", return_value=registro), patch.object(
                    main.api, "expediente",
                ) as buscar_expediente:
                    expediente.buscar()

                self.assertEqual(expediente.reinscripcion_data, registro)
                buscar_expediente.assert_not_called()
                textos = {
                    control.value for control in controles(expediente.resultado)
                    if isinstance(control, ft.Text)
                }
                self.assertIn("Ana", textos)
                self.assertIn("Prueba", textos)
                self.assertIn("26320700", textos)


if __name__ == "__main__":
    unittest.main()
