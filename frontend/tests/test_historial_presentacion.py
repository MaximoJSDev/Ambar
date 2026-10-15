import unittest

import main


class HistorialPresentacionTests(unittest.TestCase):
    def test_muestra_solo_campos_modificados_con_etiquetas_humanas(self):
        cambios = main._cambios_historial({
            "accion": "MODIFICACION",
            "datos_anteriores": {
                "id_usuario": None,
                "numero_control": "26320700",
                "nombres": "Ana",
                "apellido_paterno": "López",
                "fecha_nacimiento": "2005-03-02",
                "genero": "mujer",
            },
            "datos_nuevos": {
                "id_usuario": None,
                "numero_control": "26320700",
                "nombres": "Ana María",
                "apellido_paterno": "López",
                "fecha_nacimiento": "2005-03-02",
                "genero": "mujer",
            },
        })

        self.assertEqual(list(cambios), ["Identificación"])
        self.assertEqual(cambios["Identificación"], [{
            "campo": "Nombre(s)",
            "antes": "Ana",
            "despues": "Ana María",
        }])

    def test_formatea_fecha_genero_promedio_y_valores_vacios(self):
        cambios = main._cambios_historial({
            "accion": "MODIFICACION",
            "datos_anteriores": {
                "fecha_nacimiento": "2005-03-02",
                "genero": "hombre",
                "promedio_preparatoria": "8.5",
                "rfc": None,
            },
            "datos_nuevos": {
                "fecha_nacimiento": "2005-04-03",
                "genero": "mujer",
                "promedio_preparatoria": "9.75",
                "rfc": "ABC123",
            },
        })

        self.assertEqual(cambios["Datos personales"][0]["antes"], "02/03/2005")
        self.assertEqual(cambios["Datos personales"][0]["despues"], "03/04/2005")
        self.assertEqual(cambios["Datos personales"][1]["antes"], "Hombre")
        self.assertEqual(cambios["Datos personales"][1]["despues"], "Mujer")
        self.assertEqual(cambios["Datos personales"][2]["antes"], "Sin dato")
        self.assertEqual(cambios["Trayectoria académica"][0]["antes"], "8.50")
        self.assertEqual(cambios["Trayectoria académica"][0]["despues"], "9.75")

    def test_baja_se_presenta_como_cambio_de_estado(self):
        cambios = main._cambios_historial({
            "accion": "BAJA",
            "datos_anteriores": {"numero_control": "26320700"},
            "datos_nuevos": {"numero_control": "26320700", "eliminado": True},
        })

        self.assertEqual(cambios, {
            "Situación del expediente": [{
                "campo": "Estado",
                "antes": "Activo",
                "despues": "Dado de baja",
            }],
        })


if __name__ == "__main__":
    unittest.main()
