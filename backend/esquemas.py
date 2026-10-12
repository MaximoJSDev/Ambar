"""Modelos de entrada/salida de la API."""
import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginIn(BaseModel):
    correo: str = Field(max_length=150)
    password: str = Field(min_length=1, max_length=200)


class UsuarioOut(BaseModel):
    id_usuario: int
    correo: str
    nombre: str
    rol: str


class LoginOut(BaseModel):
    token: str
    tipo: str = "bearer"
    usuario: UsuarioOut


class AltaIn(BaseModel):
    """Datos del alumno de nuevo ingreso (los PDF viajan aparte, en multipart)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    ficha: str
    nombre: str
    ap_paterno: str
    ap_materno: str
    fecha_nacimiento: datetime.date
    curp: str
    rfc: str
    nss: str
    ine: str
    genero: str
    celular: str
    correo: str
    domicilio: str
    preparatoria: str
    promedio: float = Field(allow_inf_nan=False)
    celular_emergencia: str
    correo_emergencia: str
    alergias: str = "Ninguna"

    @field_validator("curp", "rfc", "ine")
    @classmethod
    def _mayusculas(cls, valor: str) -> str:
        return valor.upper()

    @field_validator("alergias")
    @classmethod
    def _sin_alergias(cls, valor: str) -> str:
        return valor or "Ninguna"


class AltaOut(BaseModel):
    numero_control: str
    correo_institucional: str
    nombre_completo: str
    turno: str
    grupo: str
    aviso_turno: str | None = None
    documentos: int
