"""Hash de contraseñas (argon2) y tokens de sesión (JWT)."""
import datetime
import time

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


class LoginGuard:
    """Cuenta fallos por correo y aplica un bloqueo temporal tras varios intentos."""

    def __init__(self, max_intentos: int = 3, segundos_bloqueo: int = 300, reloj=time.monotonic):
        self.max_intentos = max_intentos
        self.segundos_bloqueo = segundos_bloqueo
        self._reloj = reloj
        self._fallos: dict[str, int] = {}
        self._bloqueado_hasta: dict[str, float] = {}

    @staticmethod
    def _clave(correo: str) -> str:
        return correo.strip().lower()

    def segundos_restantes(self, correo: str) -> int:
        """Segundos de bloqueo pendientes (0 si no está bloqueado)."""
        k = self._clave(correo)
        hasta = self._bloqueado_hasta.get(k)
        if hasta is None:
            return 0
        if self.segundos_bloqueo and self._reloj() >= hasta:
            del self._bloqueado_hasta[k]
            self._fallos.pop(k, None)
            return 0
        return max(1, int(hasta - self._reloj() + 0.999)) if self.segundos_bloqueo else 10**9

    def bloqueado(self, correo: str) -> bool:
        return self.segundos_restantes(correo) > 0

    def intentos_restantes(self, correo: str) -> int:
        return max(0, self.max_intentos - self._fallos.get(self._clave(correo), 0))

    def registrar_fallo(self, correo: str) -> int:
        """Registra un fallo y devuelve los intentos que quedan."""
        k = self._clave(correo)
        self._fallos[k] = self._fallos.get(k, 0) + 1
        if self._fallos[k] >= self.max_intentos:
            self._bloqueado_hasta[k] = self._reloj() + self.segundos_bloqueo
        return self.intentos_restantes(correo)

    def registrar_exito(self, correo: str) -> None:
        k = self._clave(correo)
        self._fallos.pop(k, None)
        self._bloqueado_hasta.pop(k, None)
