# Tutorial: probar Ambar

Las pruebas del backend usan `unittest` (incluido con Python) y
`fastapi.testclient.TestClient`. No necesitan conectarse a MySQL: las pruebas
simulan las respuestas de la base de datos y verifican que las rutas llamen o
no llamen a los servicios correspondientes.

## 1. Preparar el entorno

Desde la raíz del repositorio, instala las dependencias de desarrollo del
backend. `httpx2` permite que `TestClient` funcione con la versión instalada de
Starlette:

```powershell
cd backend
python -m pip install -r requirements-dev.txt
cd ..
```

Usa el Python del entorno virtual del proyecto si tienes uno. No configures las
pruebas con credenciales de una base de datos de producción.

## 2. Ejecutar las pruebas

Desde la raíz del repositorio:

```powershell
python -m unittest discover -v
```

Ejecutar solo una categoría:

```powershell
python -m unittest backend.tests.test_login -v
python -m unittest backend.tests.test_altas_alumnos -v
python -m unittest backend.tests.test_altas_docentes -v
python -m unittest backend.tests.test_altas_secretarias -v
python -m unittest backend.tests.test_modificar_alumnos -v
```

Las validaciones compartidas entre frontend y backend están en
`ambar_common/tests/test_validators.py` y también se ejecutan con el comando
general.

## 3. Dónde está cada prueba

| Archivo | Qué protege |
| --- | --- |
| `test_login.py` | Login correcto, credenciales erróneas, cuentas inactivas y bloqueo temporal |
| `test_altas_alumnos.py` | Alta de alumnos, formatos de entrada, datos basura y rechazo antes de persistir |
| `test_altas_docentes.py` | Alta de docentes, nombres/apellidos de 2–50 caracteres, permisos y correo duplicado |
| `test_altas_secretarias.py` | Alta de secretarías, nombres/apellidos de 2–50 caracteres, permisos y correo duplicado |
| `test_modificar_alumnos.py` | Reglas de validación y permisos al modificar un alumno |
| `test_personal.py` | Consulta y baja de docentes y migración de cuentas antiguas |
| `test_secretarias_admin.py` | Consulta de secretarías, bitácora y baja |
| `test_alumnos_admin.py` | Documentos, bajas e historial de expedientes |
| `test_horarios.py` | Asignaciones y consultas de horarios |
| `test_reportes.py` | Generación y entrega de PDF |

## 4. Escribir una prueba nueva

Una buena prueba se enfoca en un comportamiento observable:

1. Prepara los datos del caso.
2. Ejecuta la ruta con `TestClient`.
3. Comprueba el código HTTP y el contenido de la respuesta.
4. Comprueba el efecto secundario importante, como si se llamó al servicio.

Ejemplo: una entrada inválida debe responder `422` y nunca llegar al guardado:

```python
from unittest.mock import patch

def test_alta_rechaza_nombre_de_puros_simbolos(self):
    datos = datos_alumno(nombre="....")

    with patch("backend.routers.alumnos.servicios.actualizar_alumno") as guardar:
        respuesta = self.client.put("/alumnos/26320700", json=datos)

    self.assertEqual(respuesta.status_code, 422)
    guardar.assert_not_called()
```

Para cada ruta crítica, prueba tanto un caso válido como entradas inválidas,
límites (por ejemplo, longitud máxima), campos omitidos y permisos incorrectos.
Usa `subTest` para agrupar valores que deben cumplir la misma regla. Simula
servicios externos o la base de datos con `unittest.mock.patch`; no hagas que
una prueba dependa de datos creados por otra.

Para probar un límite exacto, verifica el valor aceptado y el vecino rechazado
(por ejemplo, 100 y 101 caracteres). Para probar errores del servicio, simula
la excepción con `side_effect` y comprueba tanto el estado HTTP como que no se
filtre información interna en la respuesta. Los errores inesperados se pueden
observar con `TestClient(app, raise_server_exceptions=False)` y deben dar una
respuesta 500; no los conviertas en respuestas exitosas ni en errores de
validación.

Al cambiar una regla de validación, añade casos válidos y no válidos a
`ambar_common/tests/test_validators.py` y una prueba de endpoint cuando importe
comprobar que el backend rechaza la petición antes de persistir.
