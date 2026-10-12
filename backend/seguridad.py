"""Hash de contraseñas (argon2) y tokens de sesión (JWT)."""
import datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import settings

_ph = PasswordHasher()
# Se verifica contra este hash cuando el correo no existe, para que la respuesta
# tarde lo mismo y no revele qué cuentas existen.
_HASH_FALSO = _ph.hash("contraseña-inexistente")


def hashear(password: str) -> str:
    return _ph.hash(password)


def verificar(hash_guardado: str | None, password: str) -> bool:
    try:
        coincide = _ph.verify(hash_guardado or _HASH_FALSO, password)
    except (VerificationError, InvalidHashError):
        return False
    return coincide and hash_guardado is not None


def crear_token(id_usuario: int, id_bitacora: int) -> str:
    ahora = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(id_usuario),
        "bid": id_bitacora,
        "iat": ahora,
        "exp": ahora + datetime.timedelta(hours=settings.jwt_horas),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decodificar(token: str) -> dict:
    """Lanza jwt.PyJWTError si el token es inválido o expiró."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
