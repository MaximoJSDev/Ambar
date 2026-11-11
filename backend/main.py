"""API del SIGE.  Ejecutar desde la raíz del proyecto:  uvicorn backend.main:app"""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from ambar_common.logging_config import configure_file_logging

from . import migraciones, servicios, sincronizacion_docentes
from .config import engine, settings
from .routers import admin, alumnos, auth, horarios, panel, personal, reinscripciones

log = logging.getLogger("sige")
logging.basicConfig(level=logging.INFO)
configure_file_logging("sige", "backend.log")


async def _monitorear_avance_semestre() -> None:
    while True:
        try:
            await asyncio.to_thread(servicios.avanzar_semestre_si_corresponde)
        except SQLAlchemyError:
            log.exception("No se pudo verificar el avance automático de semestre")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    with engine.begin() as conn:
        migraciones.aplicar_migraciones(conn)
        servicios.cargar_catalogo_horarios(conn)
        servicios.preparar_avances_semestre(conn)
    sincronizacion_docentes.sincronizar_docentes_horario()
    sincronizacion_docentes.asignar_docentes_disponibles()
    monitor = asyncio.create_task(_monitorear_avance_semestre())
    try:
        yield
    finally:
        monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor


app = FastAPI(title="SIGE API", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(alumnos.router)
app.include_router(panel.router)
app.include_router(admin.router)
app.include_router(personal.router)
app.include_router(horarios.router)
app.include_router(reinscripciones.router)


@app.get("/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "periodo": settings.periodo}
