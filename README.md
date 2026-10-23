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

Para crear además 10 alumnos ficticios, agrega `--alumnos-demo 10` al comando. La
seed asigna números de control y correos institucionales mediante el flujo normal
de altas; al no crear PDF, sus documentos aparecerán pendientes. Secretaría les
puede asignar un paquete desde **Consultas**. Los registros demo usan fichas
`9999-NNNNN` y se omiten si ya existen al volver a ejecutar la seed.

En **Consultas**, Secretaría puede buscar y revisar la información y los
documentos de los alumnos. La edición de datos y la baja de expedientes activos
se realizan desde **Modificación**. Las bajas desaparecen de las consultas de
Secretaría, pero conservan sus datos y documentos. Administración también tiene
acceso a **Modificación**, además de un inicio de sesión y una vista propios en
**Historial de alumnos** para consultar las bajas y revisar las versiones
anteriores de los datos junto con quién y cuándo hizo cada cambio. Al iniciar,
el backend elimina la antigua marca de ocultación si existe y crea las
estructuras de historial necesarias; las bases nuevas ya las incluyen desde
`ambar-db.sql`.

Administración también puede crear cuentas de secretarias desde **Alta de
secretaria** y revisar o dar de baja cuentas desde **Consulta de secretarias**.
Las bajas desactivan el acceso sin eliminar los datos de la cuenta.
La **Bitácora** de accesos queda disponible en el menú de Administración; las
opciones de Cambio de campus y Bitácora no aparecen en el menú de Secretaría.
Secretaría puede crear cuentas de maestros desde **Alta de maestros** y
consultarlas desde **Consulta de maestros**. Desde la consulta también puede
desactivar el acceso sin borrar los datos; cada cuenta queda asociada a un
registro docente y el correo debe ser único.

Al iniciar el backend se carga de forma idempotente el horario publicado de
primer semestre para **AGO-DIC 2026**, con los paquetes `1ISC1` a `1ISC7`. Al registrar un
alumno, el horario queda pendiente; Secretaría lo busca en **Consultas** y, si
aún no tiene grupo, le asigna un paquete completo del mismo semestre. La
asignación inscribe al alumno en todas las materias de esa sección y respeta los
cupos. Desde **Consultas** también se descarga el horario individual con
membrete. Desde **Grupos y horarios** se revisan las listas por sección, se
descargan con membrete y se vinculan las cuentas de maestros a las materias.
La asignación de docente se realiza por grupo y materia en **Grupos y horarios**.
En **Mis grupos**, cada maestro consulta solo sus asignaciones y puede descargar
con membrete su horario consolidado, la lista de alumnos de cada materia y su
lista de calificaciones.
Las listas de alumnos en pantalla y en PDF se ordenan alfabéticamente por
apellido paterno, apellido materno y nombre(s).
En el panel de Secretaría, la actividad muestra el número de control, se
recorre en páginas de 10 alumnos y permite abrir directamente cada expediente
en **Consultas**. El panel ya no muestra la sección de pendientes.
Los alumnos que ya estaban inscritos en `1A` o `1B` pueden migrarse desde
**Consultas**: Secretaría elige manualmente su sección oficial. La migración
conserva calificaciones y asistencias en materias coincidentes; si hay datos
históricos en una materia sin equivalente, la operación se cancela para no
perderlos.
Los horarios de otros semestres se incorporarán con el módulo de reinscripción.

Administración configura en **Periodos escolares** la fecha de inicio de la
semana 1 para cada periodo; el sistema habilita la captura al comenzar las
semanas 5, 9, 13 y 17. Los maestros pueden registrar calificaciones enteras:
0 o de 70 a 100 en sus grupos asignados, y modificar los tres periodos mientras
no se haya confirmado la final. En la semana 17, la final se calcula con el
promedio de los tres periodos, redondeado al entero más cercano; si el promedio
es menor a 70 se registra 0. La confirmación final requiere aceptación explícita
y bloquea tanto la final como sus periodos base.
Administración puede seleccionar un periodo registrado para corregir su nombre
o fecha de inicio desde el calendario. Al renombrarlo, también se actualiza el
periodo de sus grupos. Corregir la fecha conserva las calificaciones existentes
y recalcula automáticamente qué semanas están habilitadas.

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