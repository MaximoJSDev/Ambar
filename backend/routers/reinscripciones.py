"""Reinscripción de alumnos de segundo a décimo semestre."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import servicios
from ..constantes import ROL_SECRETARIA
from ..deps import requiere_roles

router = APIRouter(prefix="/reinscripciones", tags=["Reinscripciones"])
solo_secretaria = requiere_roles(ROL_SECRETARIA)


class AsignarPaqueteIn(BaseModel):
    id_paquete: int = Field(gt=0)


def _not_found():
    raise HTTPException(404, {"mensaje": "No se encontró el alumno, paquete o grupo solicitado"})


@router.get("/alumno")
def estado_reinscripcion(
    q: str = Query(..., min_length=1, max_length=100),
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.estado_reinscripcion_alumno(q)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.post(
    "/alumnos/{numero_control}/paquete",
    status_code=status.HTTP_201_CREATED,
)
def asignar_paquete(
    numero_control: str,
    datos: AsignarPaqueteIn,
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.asignar_paquete_reinscripcion(numero_control, datos.id_paquete)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.CupoLleno as ex:
        raise HTTPException(409, {"mensaje": str(ex)})
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})
