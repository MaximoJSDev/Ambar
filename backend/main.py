"""API del SIGE.  Ejecutar desde la raíz del proyecto:  uvicorn backend.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from ambar_common.logging_config import configure_file_logging

from . import servicios
from .config import engine, settings
from .routers import admin, alumnos, auth, horarios, panel, personal

log = logging.getLogger("sige")
logging.basicConfig(level=logging.INFO)
configure_file_logging("sige", "backend.log")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    with engine.begin() as conn:
        if conn.execute(text("SHOW COLUMNS FROM alumnos LIKE 'oculto_consultas'")).first() is not None:
            conn.execute(text("ALTER TABLE alumnos DROP COLUMN oculto_consultas"))
        if conn.execute(text("SHOW COLUMNS FROM alumnos LIKE 'eliminado'")).first() is None:
            conn.execute(text(
                "ALTER TABLE alumnos ADD COLUMN eliminado BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS historial_alumnos (
            id_historial INT AUTO_INCREMENT PRIMARY KEY,
            numero_control VARCHAR(20) NOT NULL,
            accion ENUM('MODIFICACION', 'BAJA') NOT NULL,
            datos_anteriores LONGTEXT NOT NULL,
            datos_nuevos LONGTEXT,
            id_usuario INT NOT NULL,
            fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (numero_control) REFERENCES alumnos(numero_control)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
            INDEX idx_historial_alumno_fecha (numero_control, fecha)
        )"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS periodos_escolares (
            periodo VARCHAR(20) PRIMARY KEY,
            fecha_inicio DATE NOT NULL,
            actualizado_por INT NOT NULL,
            actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (actualizado_por) REFERENCES usuarios(id_usuario)
        )"""))
        if conn.execute(text("SHOW COLUMNS FROM calificaciones LIKE 'confirmada'")).first() is None:
            conn.execute(text(
                "ALTER TABLE calificaciones ADD COLUMN confirmada BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            conn.execute(text("""UPDATE calificaciones
                                 SET confirmada = TRUE
                                 WHERE periodo_evaluacion = 'Final' AND valor IS NOT NULL"""))
        if conn.execute(text("""SELECT COUNT(*) FROM calificaciones
                                WHERE valor IS NOT NULL
                                  AND (valor <> FLOOR(valor)
                                       OR (valor <> 0 AND (valor < 70 OR valor > 100)))""")).scalar_one():
            raise RuntimeError(
                "Hay calificaciones existentes que no son 0 ni un entero de 70 a 100; "
                "corrígelas antes de iniciar para activar la validación entera."
            )
        if conn.execute(text("""SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
                                WHERE TABLE_SCHEMA = DATABASE()
                                  AND TABLE_NAME = 'calificaciones'
                                  AND CONSTRAINT_NAME = 'chk_calificacion_entera'
                                  AND CONSTRAINT_TYPE = 'CHECK'""")).scalar_one() == 0:
            conn.execute(text("""ALTER TABLE calificaciones
                                 ADD CONSTRAINT chk_calificacion_entera
                                 CHECK (valor IS NULL OR
                                        (valor = FLOOR(valor) AND
                                         (valor = 0 OR (valor >= 70 AND valor <= 100))))"""))
        servicios.migrar_docente_sin_asignar(conn)
        servicios.migrar_horarios(conn)
        servicios.cargar_catalogo_1isc(conn)
        conn.execute(text("SELECT 1"))
    yield


app = FastAPI(title="SIGE API", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(alumnos.router)
app.include_router(panel.router)
app.include_router(admin.router)
app.include_router(personal.router)
app.include_router(horarios.router)


@app.get("/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "periodo": settings.periodo}
