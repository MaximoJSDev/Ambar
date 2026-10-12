"""Inicio y cierre de sesión. Cada sesión queda en bitacora_accesos."""
import datetime
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .. import seguridad
from ..config import settings
from ..db import engine
from ..deps import usuario_actual
from ..esquemas import LoginIn, LoginOut, UsuarioOut
from ..login_guard import LoginGuard
from ..usuarios import SELECT_USUARIO

router = APIRouter(prefix="/auth", tags=["Sesión"])

# Estado en memoria: con varios procesos (uvicorn --workers N) cada uno llevaría su
# propio contador; para un despliegue de un solo proceso es suficiente.
guard = LoginGuard(settings.login_max_intentos, settings.login_segundos_bloqueo)
_candado = threading.Lock()     # LoginGuard no es seguro entre hilos


def _bloqueado(segundos: int) -> HTTPException:
    return HTTPException(
        423,
        {"mensaje": "Cuenta bloqueada por demasiados intentos", "segundos": segundos},
        headers={"Retry-After": str(segundos)},
    )


@router.post("/login", response_model=LoginOut)
def login(datos: LoginIn):
    correo = datos.correo.strip().lower()
    with _candado:
        segundos = guard.segundos_restantes(correo)
    if segundos > 0:
        raise _bloqueado(segundos)

    with engine.connect() as conn:
        fila = conn.execute(
            text(SELECT_USUARIO + " WHERE u.correo = :c"),
            {"c": correo},
        ).mappings().first()

    # Se verifica siempre (aunque no exista el correo) para no filtrar cuentas por tiempo
    password_ok = seguridad.verificar(fila["password"] if fila else None, datos.password)
    if not (fila and password_ok and fila["estatus"] == "Activo"):
        with _candado:
            restantes = guard.registrar_fallo(correo)
            segundos = guard.segundos_restantes(correo)
        if restantes == 0:
            raise _bloqueado(segundos)
        # Mensaje genérico: no revela si el correo existe
        raise HTTPException(401, {"mensaje": "Credenciales incorrectas", "intentos_restantes": restantes})

    with _candado:
        guard.registrar_exito(correo)

    ahora = datetime.datetime.now()
    with engine.begin() as conn:
        id_bitacora = conn.execute(
            text("INSERT INTO bitacora_accesos (id_usuario, fecha, hora_entrada) VALUES (:u, :f, :h)"),
            {"u": fila["id_usuario"], "f": ahora.date(), "h": ahora.time().replace(microsecond=0)},
        ).lastrowid

    return LoginOut(
        token=seguridad.crear_token(fila["id_usuario"], id_bitacora),
        usuario=UsuarioOut(
            id_usuario=fila["id_usuario"], correo=fila["correo"],
            nombre=fila["nombre"] or fila["correo"], rol=fila["rol"],
        ),
    )


@router.post("/logout", status_code=204)
def logout(usuario: dict = Depends(usuario_actual)):
    if usuario.get("bid"):
        with engine.begin() as conn:
            conn.execute(
                text("""UPDATE bitacora_accesos SET hora_salida = :h
                        WHERE id_bitacora = :b AND id_usuario = :u AND hora_salida IS NULL"""),
                {"h": datetime.datetime.now().time().replace(microsecond=0),
                 "b": usuario["bid"], "u": usuario["id_usuario"]},
            )


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: dict = Depends(usuario_actual)):
    return UsuarioOut(id_usuario=usuario["id_usuario"], correo=usuario["correo"],
                      nombre=usuario["nombre"], rol=usuario["rol"])
