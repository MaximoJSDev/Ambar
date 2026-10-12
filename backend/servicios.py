"""Lógica de negocio de Altas (Algoritmo 3 del documento de contexto).

Flujo de `registrar_alta`, bajo un candado global de MySQL para que dos altas
simultáneas no se repartan el mismo cupo ni el mismo consecutivo:
  1. ficha y CURP no repetidas
  2. turno por promedio y grupo con lugar (si el turno está lleno, usa el otro)
  3. número de control = AAAA + plantel + letra del apellido + consecutivo
  4. copia de los PDF al servidor (storage.guardar_pdfs)
  5. INSERT del alumno, rutas del expediente e inscripción a todas las materias del grupo
Si algo falla después del paso 4 se borran los PDF copiados y se hace rollback.
"""
import logging
import re
import shutil
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

import storage
import validators as v

from .config import settings
from .constantes import DOCUMENTOS, SEMESTRE_INGRESO, TURNOS
from .db import engine
from .esquemas import AltaIn

log = logging.getLogger("sige")
NOMBRE_CANDADO = "sige_altas"
ERRNO_CHECK_VIOLADO = (3819, 4025)      # MySQL / MariaDB


class CupoLleno(Exception):
    """No hay lugar en ningún grupo de primer semestre."""


class SinGrupos(Exception):
    """El periodo no tiene grupos de primer semestre configurados."""


class Ocupado(Exception):
    """No se obtuvo el candado de altas a tiempo."""


class Conflicto(Exception):
    def __init__(self, mensaje: str, errores: dict[str, str] | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.errores = errores or {}


# --------------------------------------------------------------------------
# Validación (mismas reglas que la app, que no es de fiar por sí sola)
# --------------------------------------------------------------------------
def validar_alta(d: AltaIn) -> dict[str, str]:
    errores: dict[str, str] = {}

    def revisar(campo: str, err: str | None) -> None:
        if err:
            errores[campo] = err

    revisar("ficha", v.validar_ficha(d.ficha))
    revisar("nombre", v.validar_nombre(d.nombre))
    revisar("ap_paterno", v.validar_apellido(d.ap_paterno))
    revisar("ap_materno", v.validar_apellido(d.ap_materno))
    err_fecha = v.validar_fecha_nacimiento(d.fecha_nacimiento)
    revisar("fecha_nacimiento", err_fecha)
    ref = None if err_fecha else d.fecha_nacimiento
    revisar("curp", v.validar_curp(d.curp, ref))
    revisar("rfc", v.validar_rfc(d.rfc, ref))
    revisar("nss", v.validar_nss(d.nss))
    revisar("ine", v.validar_ine(d.ine, ref))
    revisar("genero", v.validar_genero(d.genero))
    revisar("celular", v.validar_celular(d.celular))
    revisar("correo", v.validar_correo(d.correo))
    revisar("domicilio", v.validar_domicilio(d.domicilio))
    revisar("preparatoria", v.validar_preparatoria(d.preparatoria))
    revisar("promedio", v.validar_promedio(str(d.promedio)))
    revisar("celular_emergencia", v.validar_celular_emergencia(d.celular_emergencia, d.celular))
    revisar("correo_emergencia", v.validar_correo_emergencia(d.correo_emergencia, d.correo))
    revisar("alergias", v.validar_alergias(d.alergias))
    return errores


# --------------------------------------------------------------------------
# Cupos y grupos
# --------------------------------------------------------------------------
def _lugares_por_paquete(conn, periodo: str) -> list[dict]:
    """Un grupo (paquete) tiene una fila de `grupos` por materia; su lugar real es
    el mínimo cupo_disponible de sus materias."""
    filas = conn.execute(
        text("""SELECT g.id_paquete, p.nombre_paquete AS nombre, g.turno,
                       MIN(g.cupo_disponible) AS lugares
                FROM grupos g
                JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                WHERE p.semestre = :sem AND g.periodo_escolar = :periodo
                GROUP BY g.id_paquete, p.nombre_paquete, g.turno
                ORDER BY g.id_paquete"""),
        {"sem": SEMESTRE_INGRESO, "periodo": periodo},
    ).mappings().all()
    return [dict(f) | {"lugares": int(f["lugares"])} for f in filas]


def lugares_por_turno(paquetes: list[dict]) -> dict[str, int]:
    lugares = {t: 0 for t in TURNOS}
    for p in paquetes:
        lugares[p["turno"]] += p["lugares"]
    return lugares


def elegir_paquete(paquetes: list[dict], preferido: str) -> tuple[dict, str, str | None]:
    """Devuelve (paquete, turno, aviso). Si el turno preferido está lleno usa el otro."""
    lugares = lugares_por_turno(paquetes)
    for turno in [preferido] + [t for t in TURNOS if t != preferido]:
        if lugares[turno] > 0:
            paquete = next(p for p in paquetes if p["turno"] == turno and p["lugares"] > 0)
            aviso = None if turno == preferido else (
                f"El grupo {preferido} está lleno; el alumno quedó en el grupo {turno}.")
            return paquete, turno, aviso
    raise CupoLleno("Los grupos de primer semestre ya tienen el cupo completo.")


def cupo_ingreso() -> dict:
    with engine.connect() as conn:
        paquetes = _lugares_por_paquete(conn, settings.periodo)
    turnos = lugares_por_turno(paquetes)
    return {"periodo": settings.periodo, "turnos": turnos, "total": sum(turnos.values())}


# --------------------------------------------------------------------------
# Consultas auxiliares
# --------------------------------------------------------------------------
def duplicados(conn, ficha: str, curp: str) -> dict[str, bool]:
    filas = conn.execute(
        text("SELECT numero_ficha, curp FROM alumnos WHERE numero_ficha = :f OR curp = :c"),
        {"f": ficha, "c": curp},
    ).mappings().all()
    return {
        "ficha": bool(ficha) and any(f["numero_ficha"] == ficha for f in filas),
        "curp": bool(curp) and any(f["curp"].upper() == curp for f in filas),
    }


def verificar_duplicados(ficha: str, curp: str) -> dict[str, bool]:
    with engine.connect() as conn:
        return duplicados(conn, ficha.strip(), curp.strip().upper())


def _siguiente_consecutivo(conn, prefijo: str) -> int:
    """Máximo + 1 (no cuenta filas: un hueco por una baja repetiría números)."""
    maximo = conn.execute(
        text("""SELECT COALESCE(MAX(CAST(SUBSTRING(numero_control, :ini) AS UNSIGNED)), 0)
                FROM alumnos WHERE numero_control LIKE :patron"""),
        {"ini": len(prefijo) + 1, "patron": prefijo + "%"},
    ).scalar_one()
    return int(maximo) + 1


def _check_violado(exc: DBAPIError) -> bool:
    args = getattr(exc.orig, "args", ())
    return bool(args) and args[0] in ERRNO_CHECK_VIOLADO


# --------------------------------------------------------------------------
# Alta
# --------------------------------------------------------------------------
def registrar_alta(d: AltaIn, pdfs: dict[str, str], usuario: dict) -> dict:
    """`pdfs` mapea nombre visible del documento -> ruta temporal ya validada."""
    periodo = settings.periodo
    base = settings.storage_dir

    # El candado vive en su propia conexión y se libera DESPUÉS del commit; si se
    # soltara antes, otra alta leería cupos y consecutivos sin ver esta inscripción.
    with engine.connect() as candado:
        if candado.execute(text("SELECT GET_LOCK(:n, 20)"), {"n": NOMBRE_CANDADO}).scalar() != 1:
            raise Ocupado()
        carpeta: Path | None = None
        try:
            with engine.begin() as conn:
                dup = duplicados(conn, d.ficha, d.curp)
                errores = {}
                if dup["ficha"]:
                    errores["ficha"] = "Esta ficha ya está registrada"
                if dup["curp"]:
                    errores["curp"] = "Esta CURP ya está registrada"
                if errores:
                    raise Conflicto("El alumno ya está registrado", errores)

                paquetes = _lugares_por_paquete(conn, periodo)
                if not paquetes:
                    raise SinGrupos(f"No hay grupos de primer semestre para el periodo {periodo}.")
                paquete, turno, aviso = elegir_paquete(paquetes, v.turno_por_promedio(d.promedio))

                hoy = date.today()
                prefijo = v.prefijo_control(hoy.year, settings.plantel, d.ap_paterno)
                consecutivo = _siguiente_consecutivo(conn, prefijo)
                if consecutivo > 999:
                    raise Conflicto(f"Se agotaron los números de control con el prefijo {prefijo}.")
                numero = v.generar_numero_control(hoy.year, settings.plantel, d.ap_paterno, consecutivo)
                correo_inst = v.correo_institucional(numero, settings.dominio_institucional)

                # Con el candado tomado, una carpeta con este número no pertenece a
                # ningún alumno registrado: es resto de una alta interrumpida.
                huerfana = base / numero
                if huerfana.exists():
                    log.warning("Se elimina carpeta huérfana de expediente: %s", huerfana)
                    shutil.rmtree(huerfana)

                rutas = storage.guardar_pdfs(numero, pdfs, base)
                carpeta = base / numero

                conn.execute(text("""
                    INSERT INTO alumnos (
                        numero_control, numero_ficha, nombres, apellido_paterno, apellido_materno,
                        fecha_nacimiento, genero, curp, rfc, ine, nss, domicilio, celular,
                        celular_emergencia, correo_personal,
                        correo_emergencia, correo_institucional, alergias,
                        preparatoria_procedencia, promedio_preparatoria, turno, semestre_actual,
                        estatus
                    ) VALUES (
                        :numero, :ficha, :nombres, :ap_p, :ap_m, :nacimiento, :genero, :curp, :rfc,
                        :ine, :nss, :domicilio, :celular, :cel_emerg, :correo,
                        :correo_emerg, :correo_inst, :alergias, :prepa, :promedio, :turno, :sem,
                        'Activo'
                    )"""), {
                    "numero": numero, "ficha": d.ficha, "nombres": d.nombre,
                    "ap_p": d.ap_paterno, "ap_m": d.ap_materno, "nacimiento": d.fecha_nacimiento,
                    "genero": d.genero, "curp": d.curp, "rfc": d.rfc, "ine": d.ine, "nss": d.nss,
                    "domicilio": d.domicilio, "celular": re.sub(r"[\s-]", "", d.celular),
                    "cel_emerg": re.sub(r"[\s-]", "", d.celular_emergencia),
                    "correo": d.correo,
                    "correo_emerg": d.correo_emergencia, "correo_inst": correo_inst,
                    "alergias": d.alergias, "prepa": d.preparatoria, "promedio": d.promedio,
                    "turno": turno, "sem": SEMESTRE_INGRESO,
                })

                # La BD guarda solo la ruta, relativa a STORAGE_DIR (portable entre servidores)
                tipos = {visible: tipo_bd for visible, tipo_bd in DOCUMENTOS.values()}
                conn.execute(
                    text("""INSERT INTO expedientes_digitales (numero_control, tipo_documento, ruta_archivo)
                            VALUES (:numero, :tipo, :ruta)"""),
                    [{"numero": numero, "tipo": tipos[doc], "ruta": f"{numero}/{Path(ruta).name}"}
                     for doc, ruta in rutas.items()],
                )

                id_grupos = conn.execute(
                    text("SELECT id_grupo FROM grupos WHERE id_paquete = :p AND periodo_escolar = :per"),
                    {"p": paquete["id_paquete"], "per": periodo},
                ).scalars().all()
                try:
                    # Los triggers descuentan cupo_disponible; el CHECK rechaza si no hay lugar
                    conn.execute(
                        text("INSERT INTO inscripciones_grupos (numero_control, id_grupo) VALUES (:n, :g)"),
                        [{"n": numero, "g": g} for g in id_grupos],
                    )
                except DBAPIError as exc:
                    if _check_violado(exc):
                        raise CupoLleno("El cupo se agotó mientras se registraba al alumno.") from exc
                    raise

            log.info("Alta %s registrada por usuario %s", numero, usuario["id_usuario"])
            return {
                "numero_control": numero,
                "correo_institucional": correo_inst,
                "nombre_completo": f"{d.nombre} {d.ap_paterno} {d.ap_materno}",
                "turno": turno,
                "grupo": paquete["nombre"],
                "aviso_turno": aviso,
                "documentos": len(rutas),
            }
        except IntegrityError as exc:
            if carpeta is not None:
                shutil.rmtree(carpeta, ignore_errors=True)
                carpeta = None
            raise Conflicto("El alumno ya está registrado (ficha, CURP o correo repetido).") from exc
        except Exception:
            if carpeta is not None:
                shutil.rmtree(carpeta, ignore_errors=True)
            raise
        finally:
            candado.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": NOMBRE_CANDADO})
