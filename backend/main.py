"""API del SIGE.  Ejecutar desde la raíz del proyecto:  uvicorn backend.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ambar_common.logging_config import configure_file_logging

from . import servicios
from .config import engine, settings
from .routers import admin, alumnos, auth, horarios, panel, personal, reinscripciones

log = logging.getLogger("sige")
logging.basicConfig(level=logging.INFO)
configure_file_logging("sige", "backend.log")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    with engine.begin() as conn:
        servicios.cargar_catalogo_1isc(conn)
    yield


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
