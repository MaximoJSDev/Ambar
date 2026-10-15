# Proyecto Ambar - Sistema Integral de Gestión Escolar

Bienvenido al repositorio del **Proyecto Ambar**, un sistema de software diseñado para la gestión centralizada de los servicios escolares de una institución universitaria. Este sistema facilita la administración de inscripciones, reinscripciones, control académico, actividades docentes y generación de estadísticas institucionales.

## Arquitectura del Proyecto

El ecosistema del proyecto está construido 100% en Python, dividido en dos capas principales:
*   **Frontend (Cliente de Escritorio):** Construido con **Flet**, proporcionando una interfaz gráfica reactiva y moderna.
*   **Backend (Servidor/API):** Construido con **FastAPI**, encargado de la lógica de negocio, reglas de seguridad y conexión a la base de datos de manera asíncrona.

---

## Requisitos Previos

Antes de comenzar, asegúrate de tener instalado lo siguiente en tu equipo:
*   [Python 3.10 o superior](https://www.python.org/downloads/)
*   [Git](https://git-scm.com/)

---

## Instalación manual del entorno

Estos pasos son opcionales si vas a iniciar Ambar con `run-ambar.bat`: el
lanzador crea y usa su propio entorno sin que tengas que activarlo.

**1. Clonar el repositorio**
```bash
git clone <URL_DEL_REPOSITORIO>
cd proyecto-ambar
```

**2. Crear un entorno virtual (Virtual Environment)**
```bash
# En Windows:
python -m venv venv

# En macOS/Linux:
python3 -m venv venv
```

**3. Activar el entorno virtual**
```bash
# En Windows:
venv\Scripts\activate

# En macOS/Linux:
source venv/bin/activate
```

**4. Instalar las dependencias**
Instala las dependencias de cada aplicación desde su carpeta para que también se resuelva el paquete compartido local:
```bash
cd backend
pip install -r requirements.txt

cd ../frontend
pip install -r requirements.txt
```

---

## Ejecución del Proyecto

### Inicio sencillo en Windows
Haz doble clic en `run-ambar.bat`. La primera vez instalará las dependencias y
pedirá los datos de un servidor MySQL en ejecución. Si la base `ambar_escolar`
no existe, la creará usando `ambar-db.sql` y pedirá los datos para crear una
cuenta de Secretaría. La configuración se guarda localmente en `backend/.env`;
no se vuelve a pedir en los siguientes inicios.

Necesitas tener instalado Python 3 y MySQL o MariaDB. El usuario de MySQL
configurado debe poder conectarse y crear la base de datos. Se abrirán una
ventana para el backend y la aplicación de escritorio; cierra ambas para salir.
Si ya tienes una base de datos, el lanzador no la modifica ni crea usuarios:
puedes crear o actualizar el usuario ejecutando
`python -m backend.seed --correo TU_CORREO --nombres TU_NOMBRE --apellidos TUS_APELLIDOS`
desde la carpeta del proyecto.

Para crear una cuenta independiente de Administración, ejecuta
`python -m backend.seed --admin-correo CORREO_ADMINISTRADOR`; se solicitará su
contraseña de forma interactiva. Ese comando también prepara los roles y grupos,
pero no cambia la cuenta de Secretaría.

Para crear además 10 alumnos ficticios dados de alta e inscritos en los grupos del
periodo actual, agrega `--alumnos-demo 10` al comando. La seed asigna números de
control y correos institucionales mediante el flujo normal de altas; al no crear
PDF, sus documentos aparecerán pendientes. Los registros demo usan fichas
`9999-NNNNN` y se omiten si ya existen al volver a ejecutar la seed.

En **Consultas**, Secretaría y Administración pueden modificar datos y dar de
baja expedientes activos. Las bajas desaparecen de las consultas de Secretaría,
pero conservan sus datos y documentos. Administración tiene un inicio de sesión
y una vista propios para consultar las bajas y revisar las versiones anteriores
de los datos junto con quién y cuándo hizo cada cambio. Al iniciar, el backend
elimina la antigua marca de ocultación si existe y crea las estructuras de
historial necesarias; las bases nuevas ya las incluyen desde `ambar-db.sql`.

Administración también puede crear cuentas de Secretaría desde **Alta de
secretaría** y revisar o dar de baja cuentas desde **Consulta de secretarías**.
Las bajas desactivan el acceso sin eliminar los datos de la cuenta.
La **Bitácora** de accesos queda disponible en el menú de Administración; las
opciones de Cambio de campus y Bitácora no aparecen en el menú de Secretaría.
Secretaría puede crear cuentas de maestros desde **Alta de maestros** y
consultarlas desde **Consulta de maestros**. Desde la consulta también puede
desactivar el acceso sin borrar los datos; cada cuenta queda asociada a un
registro docente y el correo debe ser único.

### Ejecutar el Backend (FastAPI)
Desde la raíz del repositorio y con el entorno virtual del backend activado:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Si la terminal ya está dentro de `backend`, indica la raíz del repositorio como directorio de la aplicación:
```bash
uvicorn backend.main:app --app-dir .. --host 0.0.0.0 --port 8000 --reload
```
No uses `uvicorn main:app` desde `backend`: los imports relativos (`from .config ...`) requieren que Python cargue `main` como parte del paquete `backend`.

### Ejecutar el Frontend (Cliente Flet)
Abre otra terminal, activa el entorno virtual y ejecuta el archivo principal de la interfaz:
```bash
# Ejecuta el archivo principal de la interfaz (por ejemplo, main.py)
cd frontend
flet run -d
```
*Esto abrirá la ventana de la aplicación de escritorio nativa.*

### Logs de diagnóstico
El cliente y el servidor guardan logs rotativos en `~/.ambar/logs` (`frontend.log`
y `backend.log`, con hasta tres respaldos de 5 MB cada uno). En Windows, la ruta
predeterminada es `%USERPROFILE%\.ambar\logs`. Para guardar ambos archivos en otra
ubicación, configura `SIGE_LOG_DIR` en los dos procesos antes de iniciarlos. Los
logs registran rutas de API, códigos de respuesta, tiempos y etapas del login;
no registran contraseñas ni tokens.

---

## Estructura del Proyecto

```text
proyecto-ambar/
├── frontend/
│   └── src/main.py           # Aplicación de escritorio Flet
├── backend/
│   ├── main.py               # Aplicación FastAPI
│   ├── config.py             # Configuración y conexión a la base de datos
│   ├── routers/              # Endpoints de sesión, alumnos y panel
│   ├── servicios.py          # Lógica de alumnos, expedientes y archivos
│   ├── seguridad.py          # Contraseñas, JWT y control de intentos
│   ├── deps.py               # Autenticación y permisos de rutas
│   ├── esquemas.py           # Modelos de entrada y salida
│   ├── constantes.py         # Reglas y valores compartidos
│   └── seed.py               # Datos iniciales
└── README.md
```

Los números de control se generan con el formato `AA TT CC SS`: año de dos
dígitos, número de tecnológico (`32`), número de carrera (`07`) y consecutivo
de dos dígitos. La secuencia comienza en `00`; al llegar a `99`, aumenta el
código de carrera y reinicia el consecutivo. El tecnológico y la carrera inicial
se pueden configurar con `NUMERO_TECNOLOGICO` y `NUMERO_CARRERA` en
`backend/.env`.

En **Consultas**, al buscar un alumno, el botón **Descargar expediente PDF**
genera un expediente con secciones de información personal, contacto, trayectoria
académica y documentación. Incluye la imagen original del membrete en
`backend/assets/membrete_institucional.png` y se guarda desde el diálogo del
sistema. Es informativo y no tiene validez oficial.