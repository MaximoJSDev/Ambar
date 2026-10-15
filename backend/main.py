"""API del SIGE.  Ejecutar desde la raíz del proyecto:  uvicorn backend.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from ambar_common.logging_config import configure_file_logging

from .config import engine, settings
from .routers import admin, alumnos, auth, panel, personal

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
        conn.execute(text("SELECT 1"))
    yield


app = FastAPI(title="SIGE API", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(alumnos.router)
app.include_router(panel.router)
app.include_router(admin.router)
app.include_router(personal.router)


@app.get("/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "periodo": settings.periodo}
