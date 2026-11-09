"""Registro de reinscripciones de segundo y tercer semestre."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from .. import servicios
from ..constantes import ROL_ADMINISTRADOR, ROL_SECRETARIA
from ..deps import requiere_roles

router = APIRouter(prefix="/reinscripciones", tags=["Reinscripciones"])
solo_secretaria = requiere_roles(ROL_SECRETARIA)
secretaria_o_administrador = requiere_roles(ROL_SECRETARIA, ROL_ADMINISTRADOR)


class ReinscripcionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    numero_control: str
    nombre: str
    apellidos: str
    semestre: int


class RegistrarReinscripcionIn(ReinscripcionIn):
    id_paquete: int = Field(gt=0)


class ModificarReinscripcionIn(ReinscripcionIn):
    id_paquete: int | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def registrar_reinscripcion(
    datos: RegistrarReinscripcionIn,
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.registrar_reinscripcion(datos.model_dump())
    except servicios.NumeroControlDuplicado as ex:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"mensaje": ex.mensaje, "errores": ex.errores},
        )
    except servicios.Conflicto as ex:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"mensaje": ex.mensaje, "errores": ex.errores},
        )
    except servicios.Ocupado:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"mensaje": "El servidor está procesando otra alta. Intenta de nuevo."},
        )
    except servicios.CupoLleno as ex:
        raise HTTPException(status.HTTP_409_CONFLICT, {"mensaje": str(ex)})


@router.get("/{numero_control}")
def obtener_reinscripcion(
    numero_control: str,
    _: dict = Depends(secretaria_o_administrador),
):
    try:
        return servicios.obtener_reinscripcion(numero_control)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró la reinscripción"})


@router.put("/{numero_control}")
def modificar_reinscripcion(
    numero_control: str,
    datos: ModificarReinscripcionIn,
    _: dict = Depends(secretaria_o_administrador),
):
    try:
        return servicios.modificar_reinscripcion(
            numero_control, datos.model_dump(exclude_none=True),
        )
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró la reinscripción"})
    except servicios.NumeroControlDuplicado as ex:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"mensaje": ex.mensaje, "errores": ex.errores},
        )
    except servicios.Conflicto as ex:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"mensaje": ex.mensaje, "errores": ex.errores},
        )
    except servicios.Ocupado:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"mensaje": "El servidor está procesando otra alta. Intenta de nuevo."},
        )
    except servicios.CupoLleno as ex:
        raise HTTPException(status.HTTP_409_CONFLICT, {"mensaje": str(ex)})
