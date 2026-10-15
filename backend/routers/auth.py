"""Inicio y cierre de sesión. Cada sesión queda en bitacora_accesos."""
import datetime
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .. import seguridad
from ..config import engine, settings
from ..deps import SELECT_USUARIO, usuario_actual
from ..esquemas import LoginIn, LoginOut, UsuarioOut
from ..seguridad import LoginGuard

router = APIRouter(prefix="/auth", tags=["Sesión"])
log = logging.getLogger("sige")

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
    started = time.perf_counter()
    log.info("Login started")
    correo = datos.correo.strip().lower()
    with _candado:
        segundos = guard.segundos_restantes(correo)
    if segundos > 0:
        log.info("Login rejected: account is temporarily blocked")
        raise _bloqueado(segundos)

    stage_started = time.perf_counter()
    log.info("Login user lookup started")
    try:
        with engine.connect() as conn:
            fila = conn.execute(
                text(SELECT_USUARIO + " WHERE u.correo = :c"),
                {"c": correo},
            ).mappings().first()
    except Exception:
        log.exception("Login user lookup failed")
        raise
    log.info("Login user lookup completed elapsed_ms=%.1f",
             (time.perf_counter() - stage_started) * 1000)

    # Se verifica siempre (aunque no exista el correo) para no filtrar cuentas por tiempo
    stage_started = time.perf_counter()
    log.info("Login password verification started")
    try:
        password_ok = seguridad.verificar(fila["password"] if fila else None, datos.password)
    except Exception:
        log.exception("Login password verification failed")
        raise
    log.info("Login password verification completed elapsed_ms=%.1f",
             (time.perf_counter() - stage_started) * 1000)
    if not (fila and password_ok and fila["estatus"] == "Activo"):
        with _candado:
            restantes = guard.registrar_fallo(correo)
            segundos = guard.segundos_restantes(correo)
        log.info("Login rejected: invalid credentials")
        if restantes == 0:
            raise _bloqueado(segundos)
        # Mensaje genérico: no revela si el correo existe
        raise HTTPException(401, {"mensaje": "Credenciales incorrectas", "intentos_restantes": restantes})

    with _candado:
        guard.registrar_exito(correo)

    ahora = datetime.datetime.now()
    stage_started = time.perf_counter()
    log.info("Login access log insert started")
    try:
        with engine.begin() as conn:
            id_bitacora = conn.execute(
                text("INSERT INTO bitacora_accesos (id_usuario, fecha, hora_entrada) VALUES (:u, :f, :h)"),
                {"u": fila["id_usuario"], "f": ahora.date(), "h": ahora.time().replace(microsecond=0)},
            ).lastrowid
    except Exception:
        log.exception("Login access log insert failed")
        raise
    log.info("Login access log insert completed elapsed_ms=%.1f",
             (time.perf_counter() - stage_started) * 1000)

    resultado = LoginOut(
        token=seguridad.crear_token(fila["id_usuario"], id_bitacora),
        usuario=UsuarioOut(
            id_usuario=fila["id_usuario"], correo=fila["correo"],
            nombre=fila["nombre"] or fila["correo"], rol=fila["rol"],
        ),
    )
    log.info("Login completed elapsed_ms=%.1f", (time.perf_counter() - started) * 1000)
    return resultado


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
