# Proyecto Ambar - Sistema Integral de Gestión Escolar

Bienvenido al repositorio del **Proyecto Ambar**, un sistema de software diseñado para la gestión centralizada de los servicios escolares de una institución universitaria. Este sistema facilita la administración de inscripciones, reinscripciones, control académico, actividades docentes y generación de estadísticas institucionales.

## Arquitectura del Proyecto

El ecosistema del proyecto está construido 100% en Python, dividido en dos capas principales:
*   **Frontend (Cliente de Escritorio):** Construido con **Flet**, proporcionando una interfaz gráfica reactiva y moderna.
*   **Backend (Servidor/API):** Construido con **FastAPI**, encargado de la lógica de negocio, reglas de seguridad y conexión a la base de datos de manera asíncrona.

---

## 🛠 Requisitos Previos

Antes de comenzar, asegúrate de tener instalado lo siguiente en tu equipo:
*   [Python 3.10 o superior](https://www.python.org/downloads/)
*   [Git](https://git-scm.com/)

---

## ⚙️ Instalación y Configuración del Entorno

Sigue estos pasos para configurar el proyecto en tu entorno local. Es altamente recomendable utilizar un entorno virtual para no tener conflictos con otras librerías de Python.

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
Una vez activado el entorno, instala los frameworks necesarios (Flet, FastAPI y Uvicorn para el servidor):
```bash
pip install -r requirements.txt
```
*(Nota: Si más adelante se agregan nuevas dependencias, utiliza el comando `pip freeze > requirements.txt` para actualizar el archivo `requirements.txt`).*

---

## 🚀 Ejecución del Proyecto

### Ejecutar el Frontend (Cliente Flet)
Abre otra terminal, activa el entorno virtual y ejecuta el archivo principal de la interfaz:
```bash
# Ejecuta el archivo principal de la interfaz (por ejemplo, main.py)
flet run -d
```
*Esto abrirá la ventana de la aplicación de escritorio nativa.*

---

## 🗂 Estructura Recomendada del Proyecto

Para mantener el orden a medida que el sistema crezca, se sugiere la siguiente estructura de carpetas:

```text
proyecto-ambar/
│
├── frontend/src                 # Todo el código de Flet (Cliente)
│   ├── main.py               # Punto de entrada de la UI
│   ├── vistas/               # Archivos separados para vista_login, vista_altas, etc.
│   └── componentes/          # Botones personalizados, modales, tarjetas, etc.
│
├── backend/                  # Todo el código de FastAPI (Servidor)
│   ├── main_api.py           # Punto de entrada de la API
│   ├── rutas/                # Endpoints (login, alumnos, maestros)
│   ├── modelos/              # Modelos de base de datos y esquemas Pydantic
│   └── base_datos/           # Configuración de conexión a la BD
│
└── README.md                 # Este archivo
```