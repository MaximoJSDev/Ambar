"""API del SIGE.  Ejecutar desde la raíz del proyecto:  uvicorn backend.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from .config import settings
from .db import engine
from .routers import alumnos, auth, panel

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:          # falla al arrancar si la BD no responde
        conn.execute(text("SELECT 1"))
    yield


app = FastAPI(title="SIGE API", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(alumnos.router)
app.include_router(panel.router)


@app.get("/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "periodo": settings.periodo}
