"""Modelos de entrada/salida de la API."""
import datetime

from ambar_common import validators as v
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class LoginIn(BaseModel):
    correo: str = Field(max_length=150)
    password: str = Field(min_length=1, max_length=200)


class UsuarioOut(BaseModel):
    id_usuario: int
    correo: str
    nombre: str
    rol: str


class SecretariaCreate(BaseModel):
    nombres: str = Field(min_length=1, max_length=50)
    apellidos: str = Field(min_length=1, max_length=100)
    correo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=10, max_length=200)

    @field_validator("nombres", "apellidos")
    @classmethod
    def _nombre_no_vacio(cls, valor: str, info: ValidationInfo) -> str:
        valor = valor.strip()
        maximo = 50 if info.field_name == "nombres" else 100
        mensaje = v.validar_nombre_personal(valor, info.field_name, maximo)
        if mensaje:
            raise ValueError(mensaje)
        return valor

    @field_validator("correo")
    @classmethod
    def _correo_valido(cls, valor: str) -> str:
        valor = valor.strip().lower()
        if v.validar_correo(valor):
            raise ValueError("Escribe un correo válido")
        return valor

    @field_validator("password")
    @classmethod
    def _password_no_vacio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("La contraseña no puede estar vacía")
        return valor


class DocenteCreate(SecretariaCreate):
    pass


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
    rfc: str | None = None
    nss: str
    ine: str | None = None
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
    def _mayusculas(cls, valor: str | None) -> str | None:
        return valor.upper() if valor else None

    @field_validator("alergias")
    @classmethod
    def _sin_alergias(cls, valor: str) -> str:
        return valor or "Ninguna"


class AltaOut(BaseModel):
    numero_control: str
    correo_institucional: str
    nombre_completo: str
    turno: str
    grupo: str | None = None
    aviso_turno: str | None = None
    documentos: int
