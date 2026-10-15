"""Administración de cuentas del personal de Secretaría."""
from fastapi import APIRouter, Depends, HTTPException, status

from .. import servicios
from ..constantes import ROL_ADMINISTRADOR
from ..deps import requiere_roles
from ..esquemas import SecretariaCreate

router = APIRouter(prefix="/administracion", tags=["Administración"])
solo_administrador = requiere_roles(ROL_ADMINISTRADOR)


@router.get("/secretarias")
def listar_secretarias(_: dict = Depends(solo_administrador)):
    return servicios.listar_secretarias()


@router.get("/bitacora")
def listar_bitacora(_: dict = Depends(solo_administrador)):
    return servicios.listar_bitacora_accesos()


@router.post("/secretarias", status_code=status.HTTP_201_CREATED)
def crear_secretaria(
    datos: SecretariaCreate,
    _: dict = Depends(solo_administrador),
):
    try:
        return servicios.crear_secretaria(datos)
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.delete("/secretarias/{id_usuario}")
def dar_baja_secretaria(
    id_usuario: int,
    _: dict = Depends(solo_administrador),
):
    try:
        secretaria = servicios.dar_baja_secretaria(id_usuario)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró la cuenta de Secretaría"})
    return {"mensaje": "Cuenta de Secretaría dada de baja", "secretaria": secretaria}
