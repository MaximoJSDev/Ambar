"""Administración de registros de personal a cargo de Secretaría."""
from fastapi import APIRouter, Depends, HTTPException, status

from .. import servicios
from ..constantes import ROL_SECRETARIA
from ..deps import requiere_roles
from ..esquemas import DocenteCreate

router = APIRouter(prefix="/personal", tags=["Personal"])
solo_secretaria = requiere_roles(ROL_SECRETARIA)


@router.post("/docentes", status_code=status.HTTP_201_CREATED)
def crear_docente(
    datos: DocenteCreate,
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.crear_docente(datos)
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.get("/docentes")
def listar_docentes(_: dict = Depends(solo_secretaria)):
    return servicios.listar_docentes()


@router.delete("/docentes/{id_usuario}")
def dar_baja_docente(
    id_usuario: int,
    _: dict = Depends(solo_secretaria),
):
    try:
        docente = servicios.dar_baja_docente(id_usuario)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró la cuenta del maestro"})
    return {"mensaje": "Cuenta del maestro dada de baja", "docente": docente}
