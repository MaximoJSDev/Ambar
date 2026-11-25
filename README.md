# Ambar - Sistema integral de gestión escolar

Ambar es una solución desarrollada para gestionar la operación escolar de una institución universitaria. Centraliza procesos clave como inscripciones, reinscripciones, grupos, docentes, calificaciones, administración de usuarios y consultas académicas.

El proyecto está dividido en dos partes principales:

- Frontend: aplicación de escritorio construida con Flet
- Backend: API desarrollada con FastAPI

Ambas partes trabajan con una base de datos MySQL/MariaDB y comparten la lógica del negocio y la seguridad del sistema.

---

## ¿Qué hace Ambar?

Ambar permite:

- Registrar y consultar alumnos
- Gestionar reinscripciones y bajas
- Administrar grupos, materias y horarios
- Asignar docentes a materias y grupos
- Capturar y consultar calificaciones por periodos
- Gestionar usuarios con roles como Secretaría, Administración y Docentes
- Generar documentos y reportes PDF
- Mantener bitácoras, historial de cambios y auditoría

---

## Requisitos previos

Antes de comenzar, necesitas tener instalado:

- [Python 3.10 a 3.14](https://www.python.org/downloads/) (se recomienda Python 3.12)
- [Git](https://git-scm.com/)
- [MySQL o MariaDB](https://www.mysql.com/) en ejecución

> El usuario de MySQL que configure debe poder crear bases de datos y modificar el esquema.

---

## Inicio rápido en Windows

La forma más sencilla de iniciar el sistema es usando el archivo `run-ambar.bat`.

1. Clona el repositorio
```bash
git clone <URL_DEL_REPOSITORIO>
cd Ambar
```

2. Ejecuta `run-ambar.bat`

Al abrirlo por primera vez, el lanzador:

- crea el entorno virtual si hace falta
- instala dependencias
- solicita la configuración de la base de datos
- crea la base `ambar_escolar` si no existe
- importa el esquema y datos iniciales
- solicita la creación de una cuenta de Secretaría
- guarda la configuración en `backend/.env`

Si la base de datos ya existe, el lanzador no la modifica de forma automática ni crea usuarios nuevos. En ese caso puedes crear o actualizar la cuenta con:

```bash
python -m backend.seed --correo TU_CORREO --nombres TU_NOMBRE --apellidos TUS_APELLIDOS
```

---

## Publicar en Oracle Cloud y Render

La arquitectura prevista para instalaciones de escritorio es:

```text
Ambar.exe → API FastAPI en Render → TiDB Cloud Starter (compatible con MySQL)
                                └→ PDF privados en Cloudinary
```

La aplicación de escritorio requiere internet. El cliente nunca se conecta directamente a MySQL ni recibe enlaces públicos de Cloudinary: FastAPI verifica la sesión y transmite los PDF desde recursos privados.

### 1. Inicializar TiDB Cloud

1. Crea una instancia **Starter**, elige **MySQL Compatible** y deja el límite de gasto en **0 USD**. Usa AWS Oregon si Render utiliza la región predeterminada del Blueprint. [Creación de instancias en TiDB Cloud](https://docs.pingcap.com/tidbcloud/create-tidb-cluster-serverless/)
2. Habilita el endpoint público y limita el acceso a tu IP y a los rangos de salida de tu servicio de Render. Conéctate como administrador con el usuario completo que muestra **Connect**, el puerto `4000` y TLS en modo `VERIFY_IDENTITY`. [Firewall de TiDB](https://docs.pingcap.com/tidbcloud/configure-serverless-firewall-rules-for-public-endpoints/) · [Conexiones TLS](https://docs.pingcap.com/tidbcloud/secure-connections-to-serverless-clusters/)
3. Desde la raíz de Ámbar, ejecuta `python -m backend.preparar_esquema_tidb` para generar `ambar-db-tidb.sql`. En la sesión de MySQL conectada a TiDB, ejecuta `SET GLOBAL tidb_enable_check_constraint = ON;` y luego importa el archivo generado. Verifica las tablas con `SHOW TABLES FROM ambar_escolar;`. [Restricciones CHECK](https://docs.pingcap.com/tidbcloud/constraints/)
4. Usa las variables `DB_TIDB=true` y `DB_PORT=4000` para FastAPI. En este modo el backend actualiza el cupo en la misma transacción que modifica la inscripción.

### 2. Desplegar FastAPI en Render

1. Sube el repositorio a GitHub y crea un Blueprint en Render usando [`render.yaml`](./render.yaml); el servicio se configura en el plan gratuito.
2. Configura `DB_HOST`, `DB_USER`, `DB_PASSWORD` y las credenciales de Cloudinary en Render. Usa un usuario de base de datos dedicado para FastAPI. Agrega `isrgrootx1.pem` como **Secret File** y configura `DB_SSL_CA=/etc/secrets/isrgrootx1.pem`.
3. Usa el plan gratuito solo teniendo en cuenta sus límites: Render puede dormir el servicio tras inactividad y su disco local es temporal. Por eso los documentos se guardan en Cloudinary, no en el disco de Render.
4. En Cloudinary, usa credenciales de servidor. El backend guarda los PDF como recursos privados y la API los transmite después de validar la sesión; no expongas URLs públicas. En el plan Free, Cloudinary limita cada archivo raw a **10 MB**, así que el ejecutable también valida ese máximo.
5. Importa el esquema antes del primer arranque. Luego crea la primera cuenta administrativa/Secretaría desde un entorno autorizado con `python -m backend.seed`; no publiques sus credenciales ni las agregues a Git.

El plan gratuito puede tardar en despertar después de estar inactivo. Los rangos de salida de Render se consultan en **Dashboard → servicio → Connect → Outbound**. Las solicitudes a una base externa también cuentan con los límites de tráfico saliente de Render. Cloudinary Free admite PDF raw de hasta 10 MB; consulta el [comparativo de planes](https://cloudinary.com/pricing/compare-plans).

### 3. Generar el ejecutable de Windows

Cuando Render muestre la URL HTTPS real del servicio:

```powershell
.\backend\venv\Scripts\python.exe -m pip install "pyinstaller>=6,<7"
.\build-windows.ps1 -ApiUrl "https://URL-REAL-DE-TU-API.onrender.com"
```

El script usa Flet Pack e integra la dirección de la API en `dist\Ambar.exe`. Comparte ese archivo. En una PC con Windows x64 e internet, basta con abrirlo e iniciar sesión con una cuenta de Ámbar. Windows puede mostrar una advertencia de SmartScreen si el archivo se distribuye sin firma digital.

No uses registros escolares reales hasta que la institución apruebe los proveedores y se haya probado una restauración de respaldo. Los planes gratuitos no ofrecen las mismas garantías de disponibilidad, privacidad contractual ni continuidad que un servicio productivo.

---

## Instalación manual del entorno

Estos pasos son opcionales si usarás `run-ambar.bat`.

### 1. Clonar el repositorio
```bash
git clone <URL_DEL_REPOSITORIO>
cd Ambar
```

### 2. Crear el entorno virtual
```bash
# Windows
python -m venv venv

# macOS/Linux
python3 -m venv venv
```

### 3. Activar el entorno virtual
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 4. Instalar dependencias
```bash
pip install -r requirements.txt
```

Si el frontend tiene dependencias separadas, instálalas dentro de esa carpeta:

```bash
cd frontend
pip install -r requirements.txt
```

---

## Ejecutar el backend (FastAPI)

Desde la raíz del repositorio, con el entorno virtual activado:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Si te encuentras dentro de la carpeta `backend`, usa:

```bash
uvicorn backend.main:app --app-dir .. --host 0.0.0.0 --port 8000 --reload
```

Importante: no uses `uvicorn main:app` desde `backend`, porque el proyecto usa imports relativos y la app debe cargarse como parte del paquete `backend`.

---

## Ejecutar el frontend (Flet)

Abre otra terminal, activa el entorno virtual y ejecuta la interfaz:

```bash
cd frontend
flet run -d
```

Esto abrirá la aplicación de escritorio nativa.

---

## Configuración inicial y primer arranque

Durante la primera ejecución, el sistema:

- crea la base de datos `ambar_escolar` si no existe
- aplica las migraciones pendientes
- importa el catálogo postal inicial (si la tabla está vacía)
- crea las estructuras necesarias para roles y permisos
- permite registrar una cuenta de Secretaría inicial

La configuración se guarda en `backend/.env` para que no se vuelva a pedir en arranques posteriores.

### Comandos útiles de inicialización

Crear una cuenta de Secretaría:
```bash
python -m backend.seed --correo TU_CORREO --nombres TU_NOMBRE --apellidos TUS_APELLIDOS
```

Crear una cuenta de Administración:
```bash
python -m backend.seed --admin-correo CORREO_ADMINISTRADOR
```

El sistema pedirá la contraseña de forma interactiva.

### Catálogo postal

El primer inicio carga automáticamente el catálogo postal nacional si la tabla local está vacía. Para importarlo manualmente desde la raíz del proyecto:

```bash
python -m backend.importar_catalogo_cp SERVICIO_POSTAL_MEXICANO.txt
```

Esto permite buscar códigos postales sin depender de internet. El sistema conserva las combinaciones existentes y agrega nuevas entradas.

---

## Roles y permisos

### Secretaría

Puede:

- registrar y consultar alumnos
- gestionar expedientes y documentos
- asignar grupos y paquetes
- revisar información académica
- manejar reinscripciones
- gestionar bajas y consultas

### Administración

Tiene acceso extra para:

- crear y dar de baja cuentas de Secretaría
- revisar historial y auditoría
- configurar periodos escolares
- supervisar la operación general

### Docentes

Pueden:

- consultar sus grupos asignados
- registrar calificaciones
- revisar listas de alumnos y promedios

---

## Funcionalidades clave

### Grupos y horarios

El sistema carga el horario publicado de primero a noveno semestre para un periodo específico. La asignación de docentes se realiza por grupo y materia, y los docentes pueden consultar únicamente sus grupos asignados.

### Reinscripción

La reinscripción se maneja de forma separada y valida:

- número de control único
- semestre permitido
- paquete con cupo disponible
- bloqueo de cambios si ya existen calificaciones

### Calificaciones y periodos

Administración configura los periodos escolares y las semanas habilitadas para captura. Los docentes pueden registrar calificaciones enteras dentro de los rangos permitidos, y el sistema calcula la final al cierre del periodo.

### Historial y auditoría

El sistema mantiene registros de cambios, bajas, accesos y evolución académica para permitir revisión posterior.

---

## Estructura del proyecto

```text
Ambar/
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
│   ├── seed.py               # Datos iniciales
│   └── assets/               # Recursos visuales del sistema
├── README.md
├── requirements.txt
├── run-ambar.bat
└── ...
```

---

## Logs de diagnóstico

El sistema guarda logs rotativos en:

- Windows: `%USERPROFILE%\.ambar\logs`
- macOS/Linux: `~/.ambar/logs`

Se generan archivos como:

- `frontend.log`
- `backend.log`

Cada archivo conserva varios respaldos de hasta 5 MB. Puedes cambiar la ubicación con la variable de entorno `SIGE_LOG_DIR` antes de iniciar ambos procesos.

Los logs registran rutas, códigos de respuesta, tiempos y etapas del login, pero no guardan contraseñas ni tokens.

---

## Notas importantes

- Los números de control siguen un formato que incluye año, tecnológico, carrera y consecutivo.
- El sistema aplica migraciones automáticamente al iniciar.
- Las contraseñas temporales generadas para nuevas cuentas se guardan en un archivo de credenciales privado; compártelo solo por un canal seguro.
- El catálogo postal, los roles y la configuración académica son parte central del funcionamiento del sistema.

---

## Sugerencia de uso

Para trabajar en el proyecto:

1. Configura MySQL/MariaDB
2. Clona el repositorio
3. Ejecuta el arranque inicial con `run-ambar.bat` o realiza la instalación manual
4. Inicia el backend
5. Inicia el frontend
6. Crea la cuenta inicial de Secretaría o Administración
7. Comienza con la carga y configuración del catálogo y los datos base

Si necesitas una versión más detallada de alguna parte del flujo escolar (inscripciones, grupos, calificaciones o administración), puedes ampliar la documentación por módulo.
