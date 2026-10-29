"""Lógica de negocio de Altas (Algoritmo 3 del documento de contexto).

Flujo de `registrar_alta`, bajo un candado global de MySQL para que dos altas
simultáneas no generen el mismo número de control:
  1. ficha y CURP no repetidas
  2. turno sugerido a partir del promedio
  3. número de control = año(2) + tecnológico(2) + carrera(2) + secuencia(2)
  4. copia de los PDF al servidor
  5. INSERT del alumno y rutas del expediente; Secretaría asigna el paquete después
Si algo falla después del paso 4 se borran los PDF copiados y se hace rollback.
"""
import logging
import json
import re
import shutil
import unicodedata
import uuid
from datetime import date, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import bindparam, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from ambar_common import validators as v

from .config import engine, settings
from .catalogo_horarios import CATALOGO_1ISC, PERIODO_1ISC
from .constantes import (
    DOCUMENTOS,
    DOCUMENTOS_MODIFICABLES,
    ROL_DOCENTE,
    ROL_SECRETARIA,
    SEMESTRE_INGRESO,
    TURNOS,
)
from .esquemas import AltaIn, DocenteCreate, SecretariaCreate
from .seguridad import hashear

log = logging.getLogger("sige")
NOMBRE_CANDADO = "sige_altas"
ERRNO_CHECK_VIOLADO = (3819, 4025)      # MySQL / MariaDB
# Constancia fiscal existe en el ENUM de la BD, aunque Altas todavía no la solicita.
TIPOS_EXPEDIENTE = [
    DOCUMENTOS["doc_acta_nacimiento"],
    DOCUMENTOS["doc_curp"],
    DOCUMENTOS["doc_comprobante_domicilio"],
    DOCUMENTOS["doc_ine"],
    ("Constancia de situación fiscal", "Constancia Situacion Fiscal"),
    DOCUMENTOS["doc_certificado_preparatoria"],
    DOCUMENTOS["doc_certificado_medico"],
]


class NoEncontrado(Exception):
    pass


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


SEMANAS_EVALUACION = {
    "Semana 5": 5,
    "Semana 9": 9,
    "Semana 13": 13,
    "Final": 17,
}


def _semana_del_periodo(fecha_inicio: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return max(0, (hoy - fecha_inicio).days // 7 + 1)


def _slug(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return "_".join(normalizado.lower().split())


def guardar_pdfs(numero_control: str, archivos: dict[str, str], base: Path) -> dict[str, str]:
    """Copia los PDF a base/<numero_control>/<documento>.pdf."""
    destino = Path(base) / numero_control
    destino.mkdir(parents=True, exist_ok=False)
    guardados: dict[str, str] = {}
    try:
        for doc, origen in archivos.items():
            if not origen:
                raise OSError(f"No se pudo leer «{doc}»")
            ruta = destino / f"{_slug(doc)}.pdf"
            shutil.copyfile(origen, ruta)
            guardados[doc] = str(ruta)
    except Exception:
        shutil.rmtree(destino, ignore_errors=True)
        raise
    return guardados


# --------------------------------------------------------------------------
# Validación (mismas reglas que la app, que no es de fiar por sí sola)
# --------------------------------------------------------------------------
def validar_alta(d: AltaIn, exigir_identificacion_adulto: bool = True) -> dict[str, str]:
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
    revisar(
        "curp",
        v.validar_curp(d.curp, ref, d.ap_paterno, d.ap_materno, d.genero),
    )
    mayor_de_18 = not err_fecha and v.es_mayor_de_18(d.fecha_nacimiento)
    if exigir_identificacion_adulto and mayor_de_18 and not d.rfc:
        revisar("rfc", "Campo obligatorio para mayores de edad")
    revisar("rfc", v.validar_rfc(d.rfc, ref))
    revisar("nss", v.validar_nss(d.nss))
    if exigir_identificacion_adulto and mayor_de_18 and not d.ine:
        revisar("ine", "Campo obligatorio para mayores de edad")
    if d.ine:
        revisar("ine", v.validar_ine(d.ine))
    revisar("genero", v.validar_genero(d.genero))
    revisar("celular", v.validar_celular(d.celular))
    revisar("correo", v.validar_correo_con_dominio(d.correo, maximo=100))
    if not re.fullmatch(r"\d{5}", d.codigo_postal):
        revisar("codigo_postal", "El código postal debe contener 5 dígitos")
    revisar("calle", v.validar_calle(d.calle))
    revisar("numero_exterior", v.validar_numero_exterior(d.numero_exterior))
    revisar("preparatoria", v.validar_preparatoria(d.preparatoria))
    revisar("promedio", v.validar_promedio(str(d.promedio)))
    revisar("celular_emergencia", v.validar_celular_emergencia(d.celular_emergencia, d.celular))
    revisar(
        "correo_emergencia",
        v.validar_correo_emergencia(d.correo_emergencia, d.correo, maximo=100),
    )
    revisar("tipo_sangre", v.validar_tipo_sangre(d.tipo_sangre))
    revisar("alergias", v.validar_alergias(d.alergias))
    return errores


def _domicilio_catalogo_valido(conn, d: AltaIn) -> bool:
    return conn.execute(
        text("""SELECT 1 FROM catalogo_codigos_postales
                WHERE codigo_postal = :codigo_postal
                  AND estado = :estado AND municipio = :municipio AND colonia = :colonia
                LIMIT 1"""),
        {
            "codigo_postal": d.codigo_postal,
            "estado": d.estado,
            "municipio": d.municipio,
            "colonia": d.colonia,
        },
    ).first() is not None


def _formatear_domicilio(domicilio: dict | None) -> str:
    if not domicilio:
        return "—"
    partes = [
        " ".join(p for p in (domicilio["calle"], domicilio["numero_exterior"]) if p),
        domicilio["colonia"],
        domicilio["municipio"],
        domicilio["estado"],
    ]
    completo = ", ".join(p for p in partes if p)
    if domicilio["codigo_postal"]:
        completo += f", C.P. {domicilio['codigo_postal']}"
    return completo or "—"


def validar_domicilio_catalogo(
    d: AltaIn,
    permitir_cp_sin_catalogo: bool = False,
) -> dict[str, str]:
    """Comprueba que la selección del formulario coincida con el catálogo local."""
    if permitir_cp_sin_catalogo and not opciones_domicilio(d.codigo_postal)["estados"]:
        return {}
    with engine.connect() as conn:
        valido = _domicilio_catalogo_valido(conn, d)
    return {} if valido else {
        "colonia": "La colonia no corresponde al código postal seleccionado",
    }


def opciones_domicilio(codigo_postal: str) -> dict:
    """Devuelve opciones locales del catálogo, sin consultas de red."""
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT estado, municipio, colonia
                    FROM catalogo_codigos_postales
                    WHERE codigo_postal = :codigo_postal
                    ORDER BY estado, municipio, colonia"""),
            {"codigo_postal": codigo_postal},
        ).mappings().all()
    estados: dict[str, dict[str, list[str]]] = {}
    for fila in filas:
        estados.setdefault(fila["estado"], {}).setdefault(fila["municipio"], []).append(
            fila["colonia"],
        )
    return {
        "codigo_postal": codigo_postal,
        "estados": [
            {
                "estado": estado,
                "municipios": [
                    {"municipio": municipio, "colonias": colonias}
                    for municipio, colonias in municipios.items()
                ],
            }
            for estado, municipios in estados.items()
        ],
    }


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
def duplicados(
    conn,
    ficha: str,
    curp: str,
    nss: str = "",
    rfc: str = "",
    ine: str = "",
    correo: str = "",
    excluir_numero_control: str | None = None,
) -> dict[str, bool]:
    valores = {
        "ficha": ficha.strip(),
        "curp": curp.strip().upper(),
        "nss": nss.strip(),
        "rfc": rfc.strip().upper(),
        "ine": v.normalizar_ine(ine).upper(),
        "correo": correo.strip().lower(),
    }
    condiciones = []
    parametros = {}
    condiciones_por_campo = {
        "ficha": "numero_ficha = :ficha",
        "curp": "UPPER(curp) = :curp",
        "nss": "nss = :nss",
        "rfc": "UPPER(rfc) = :rfc",
        "ine": "REPLACE(UPPER(ine), ' ', '') = :ine",
        "correo": "LOWER(TRIM(correo_personal)) = :correo",
    }
    for campo, condicion in condiciones_por_campo.items():
        if valores[campo]:
            condiciones.append(condicion)
            parametros[campo] = valores[campo]
    if not condiciones:
        return {campo: False for campo in condiciones_por_campo}

    consulta = (
        "SELECT numero_ficha, curp, nss, rfc, ine, correo_personal FROM alumnos "
        f"WHERE ({' OR '.join(condiciones)})"
    )
    if excluir_numero_control is not None:
        consulta += " AND numero_control != :excluir_numero_control"
        parametros["excluir_numero_control"] = excluir_numero_control
    filas = conn.execute(text(consulta), parametros).mappings().all()
    return {
        "ficha": bool(valores["ficha"]) and any(f["numero_ficha"] == valores["ficha"] for f in filas),
        "curp": bool(valores["curp"]) and any(f["curp"].upper() == valores["curp"] for f in filas),
        "nss": bool(valores["nss"]) and any(f["nss"] == valores["nss"] for f in filas),
        "rfc": bool(valores["rfc"]) and any(f["rfc"] and f["rfc"].upper() == valores["rfc"] for f in filas),
        "ine": bool(valores["ine"]) and any(
            f["ine"] and v.normalizar_ine(f["ine"]).upper() == valores["ine"] for f in filas
        ),
        "correo": bool(valores["correo"]) and any(
            f["correo_personal"].strip().lower() == valores["correo"] for f in filas
        ),
    }


def verificar_duplicados(
    ficha: str = "",
    curp: str = "",
    nss: str = "",
    rfc: str = "",
    ine: str = "",
    correo: str = "",
) -> dict[str, bool]:
    with engine.connect() as conn:
        return duplicados(conn, ficha, curp, nss, rfc, ine, correo)


def _ultimo_sufijo_control(conn, prefijo: str) -> int | None:
    """Lee carrera+secuencia más altas del año y tecnológico actuales."""
    ultimo = conn.execute(
        text("""SELECT MAX(CAST(SUBSTRING(numero_control, 5, 4) AS UNSIGNED))
                FROM alumnos
                WHERE numero_control LIKE :patron AND CHAR_LENGTH(numero_control) = 8"""),
        {"patron": prefijo + "%"},
    ).scalar_one()
    return int(ultimo) if ultimo is not None else None


def _check_violado(exc: DBAPIError) -> bool:
    args = getattr(exc.orig, "args", ())
    return bool(args) and args[0] in ERRNO_CHECK_VIOLADO


def buscar_expediente(q: str, incluir_bajas: bool = False) -> dict:
    """Busca por número de control o CURP (exactos)."""
    q = q.strip()
    with engine.connect() as conn:
        a = conn.execute(
            text("""SELECT * FROM alumnos
                    WHERE (numero_control = :q OR curp = :cu)
                      AND (:incluir_bajas OR eliminado = FALSE)
                    LIMIT 1"""),
            {"q": q, "cu": q.upper(), "incluir_bajas": incluir_bajas},
        ).mappings().first()
        if a is None:
            raise NoEncontrado()

        docs = {
            f["tipo_documento"]: f["id_documento"]
            for f in conn.execute(
                text("SELECT id_documento, tipo_documento FROM expedientes_digitales WHERE numero_control = :n"),
                {"n": a["numero_control"]},
            ).mappings()
        }
        grupo = conn.execute(
            text("""SELECT p.nombre_paquete AS grupo, g.periodo_escolar AS periodo
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE i.numero_control = :n
                    ORDER BY i.id_inscripcion DESC LIMIT 1"""),
            {"n": a["numero_control"]},
        ).mappings().first()
        domicilio = conn.execute(
            text("""SELECT codigo_postal, estado, municipio, colonia, calle, numero_exterior
                    FROM domicilios WHERE numero_control = :n"""),
            {"n": a["numero_control"]},
        ).mappings().first()

    nombre = " ".join(p for p in (a["nombres"], a["apellido_paterno"], a["apellido_materno"]) if p)
    return {
        "numero_control": a["numero_control"],
        "nombre_completo": nombre,
        "semestre_actual": a["semestre_actual"],
        "estatus": a["estatus"],
        "eliminado": bool(a["eliminado"]),
        "personales": {
            "nombres": a["nombres"],
            "apellido_paterno": a["apellido_paterno"],
            "apellido_materno": a["apellido_materno"],
            "fecha_nacimiento": a["fecha_nacimiento"].strftime("%d/%m/%Y"),
            "genero": v.GENEROS.get(a["genero"], a["genero"] or "—"),
            "curp": a["curp"],
            "rfc": a["rfc"] or "—",
            "ine": a["ine"] or "—",
            "nss": a["nss"] or "—",
        },
        "contacto": {
            "domicilio": _formatear_domicilio(dict(domicilio) if domicilio else None),
            "codigo_postal": domicilio["codigo_postal"] if domicilio else None,
            "estado": domicilio["estado"] if domicilio else None,
            "municipio": domicilio["municipio"] if domicilio else None,
            "colonia": domicilio["colonia"] if domicilio else None,
            "calle": domicilio["calle"] if domicilio else None,
            "numero_exterior": domicilio["numero_exterior"] if domicilio else None,
            "celular": a["celular"],
            "correo_personal": a["correo_personal"],
            "correo_institucional": a["correo_institucional"] or "—",
            "celular_emergencia": a["celular_emergencia"],
            "correo_emergencia": a["correo_emergencia"] or "—",
            "tipo_sangre": a["tipo_sangre"] or "—",
            "alergias": a["alergias"] or "Ninguna",
        },
        "academicos": {
            "numero_ficha": a["numero_ficha"],
            "preparatoria": a["preparatoria_procedencia"],
            "promedio": f"{a['promedio_preparatoria']:.2f}",
            "turno": a["turno"],
            "semestre": str(a["semestre_actual"]),
            "grupo": grupo["grupo"] if grupo else "Sin horario asignado",
            "periodo": grupo["periodo"] if grupo else "—",
            "estatus": a["estatus"],
            **({"motivo_baja": a["motivo_baja"]} if a["motivo_baja"] else {}),
        },
        "documentos": [
            {
                "documento": visible,
                "id_documento": docs.get(tipo_bd),
                "estado": "Recibido" if tipo_bd in docs else "Pendiente",
            }
            for visible, tipo_bd in TIPOS_EXPEDIENTE
        ],
    }


def ruta_documento(id_documento: int, incluir_bajas: bool = False) -> tuple[Path, str]:
    """Devuelve la ruta absoluta del PDF y el nombre sugerido para descargarlo."""
    with engine.connect() as conn:
        fila = conn.execute(
            text("""SELECT e.numero_control, e.tipo_documento, e.ruta_archivo
                    FROM expedientes_digitales e
                    JOIN alumnos a ON a.numero_control = e.numero_control
                    WHERE e.id_documento = :i
                      AND (:incluir_bajas OR a.eliminado = FALSE)"""),
            {"i": id_documento, "incluir_bajas": incluir_bajas},
        ).mappings().first()
    if fila is None:
        raise NoEncontrado()
    base = settings.storage_dir
    ruta = (base / fila["ruta_archivo"]).resolve()
    if not ruta.is_relative_to(base) or not ruta.is_file():
        raise NoEncontrado()
    return ruta, f"{fila['numero_control']}_{ruta.name}"


def _guardar_historial(
    conn,
    numero_control: str,
    accion: str,
    anterior: dict,
    nuevo: dict | None,
    id_usuario: int,
) -> None:
    conn.execute(
        text("""INSERT INTO historial_alumnos
                    (numero_control, accion, datos_anteriores, datos_nuevos, id_usuario)
                VALUES (:numero, :accion, :anterior, :nuevo, :usuario)"""),
        {
            "numero": numero_control,
            "accion": accion,
            "anterior": json.dumps(anterior, ensure_ascii=False, default=str),
            "nuevo": json.dumps(nuevo, ensure_ascii=False, default=str) if nuevo is not None else None,
            "usuario": id_usuario,
        },
    )


def actualizar_alumno(numero_control: str, datos: AltaIn, id_usuario: int) -> None:
    errores = validar_alta(datos)
    if errores:
        raise Conflicto("Revisa los datos capturados", errores)

    try:
        with engine.begin() as conn:
            anterior = conn.execute(
                text("SELECT * FROM alumnos WHERE numero_control = :numero FOR UPDATE"),
                {"numero": numero_control},
            ).mappings().first()
            if anterior is None or anterior["eliminado"]:
                raise NoEncontrado()
            domicilio_anterior = conn.execute(
                text("""SELECT codigo_postal, estado, municipio, colonia, calle, numero_exterior
                        FROM domicilios WHERE numero_control = :numero"""),
                {"numero": numero_control},
            ).mappings().first()
            if not _domicilio_catalogo_valido(conn, datos):
                raise Conflicto(
                    "La colonia no corresponde al código postal seleccionado",
                    {"colonia": "Selecciona una colonia del catálogo para ese código postal"},
                )

            duplicados_alumno = duplicados(
                conn, datos.ficha, datos.curp, datos.nss, datos.rfc or "", datos.ine or "",
                datos.correo, excluir_numero_control=numero_control,
            )
            errores_duplicados = {
                "ficha": "Esta ficha ya está registrada",
                "curp": "Esta CURP ya está registrada",
                "nss": "Este NSS ya está registrado",
                "rfc": "Este RFC ya está registrado",
                "ine": "Este IDMEX ya está registrado",
                "correo": "Este correo personal ya está registrado",
            }
            errores_duplicados = {
                campo: mensaje for campo, mensaje in errores_duplicados.items()
                if duplicados_alumno[campo]
            }
            if errores_duplicados:
                raise Conflicto("Los datos ya están registrados para otro alumno", errores_duplicados)

            conn.execute(
                text("""UPDATE alumnos SET
                            numero_ficha = :ficha, nombres = :nombre,
                            apellido_paterno = :ap_paterno, apellido_materno = :ap_materno,
                            fecha_nacimiento = :fecha, genero = :genero, curp = :curp,
                            rfc = :rfc, ine = :ine, nss = :nss,
                            celular = :celular, celular_emergencia = :celular_emergencia,
                            correo_personal = :correo, correo_emergencia = :correo_emergencia,
                            tipo_sangre = :tipo_sangre, alergias = :alergias,
                            preparatoria_procedencia = :preparatoria,
                            promedio_preparatoria = :promedio
                        WHERE numero_control = :numero"""),
                {
                    "numero": numero_control, "ficha": datos.ficha, "nombre": datos.nombre,
                    "ap_paterno": datos.ap_paterno, "ap_materno": datos.ap_materno,
                    "fecha": datos.fecha_nacimiento, "genero": datos.genero, "curp": datos.curp,
                    "rfc": datos.rfc, "ine": v.normalizar_ine(datos.ine), "nss": datos.nss,
                    "celular": re.sub(r"[\s-]", "", datos.celular),
                    "celular_emergencia": re.sub(r"[\s-]", "", datos.celular_emergencia),
                    "correo": datos.correo, "correo_emergencia": datos.correo_emergencia,
                    "tipo_sangre": datos.tipo_sangre, "alergias": datos.alergias,
                    "preparatoria": datos.preparatoria,
                    "promedio": datos.promedio,
                },
            )
            conn.execute(
                text("""INSERT INTO domicilios
                            (numero_control, codigo_postal, estado, municipio, colonia, calle, numero_exterior)
                        VALUES
                            (:numero, :codigo_postal, :estado, :municipio, :colonia, :calle, :numero_exterior)
                        ON DUPLICATE KEY UPDATE
                            codigo_postal = VALUES(codigo_postal),
                            estado = VALUES(estado),
                            municipio = VALUES(municipio),
                            colonia = VALUES(colonia),
                            calle = VALUES(calle),
                            numero_exterior = VALUES(numero_exterior)"""),
                {
                    "numero": numero_control,
                    "codigo_postal": datos.codigo_postal,
                    "estado": datos.estado,
                    "municipio": datos.municipio,
                    "colonia": datos.colonia,
                    "calle": datos.calle,
                    "numero_exterior": datos.numero_exterior,
                },
            )
            nuevo = conn.execute(
                text("SELECT * FROM alumnos WHERE numero_control = :numero"),
                {"numero": numero_control},
            ).mappings().one()
            domicilio_nuevo = conn.execute(
                text("""SELECT codigo_postal, estado, municipio, colonia, calle, numero_exterior
                        FROM domicilios WHERE numero_control = :numero"""),
                {"numero": numero_control},
            ).mappings().one()
            anterior = dict(anterior)
            anterior["domicilio"] = _formatear_domicilio(
                dict(domicilio_anterior) if domicilio_anterior else None,
            )
            nuevo = dict(nuevo)
            nuevo["domicilio"] = _formatear_domicilio(dict(domicilio_nuevo))
            _guardar_historial(
                conn, numero_control, "MODIFICACION", anterior, nuevo, id_usuario,
            )
    except IntegrityError as exc:
        raise Conflicto("Uno o más datos identificadores ya están registrados.") from exc


def actualizar_documentos(numero_control: str, pdfs: dict[str, str]) -> None:
    """Agrega o reemplaza documentos sin modificar los demás archivos del expediente."""
    tipos = {visible: tipo_bd for visible, tipo_bd in DOCUMENTOS_MODIFICABLES.values()}
    if any(documento not in tipos for documento in pdfs):
        raise ValueError("Tipo de documento no válido")

    base = settings.storage_dir
    carpeta = base / numero_control
    rutas_nuevas: list[Path] = []
    rutas_anteriores: list[Path] = []
    try:
        with engine.begin() as conn:
            alumno = conn.execute(
                text("""SELECT numero_control FROM alumnos
                        WHERE numero_control = :numero AND eliminado = FALSE
                        FOR UPDATE"""),
                {"numero": numero_control},
            ).first()
            if alumno is None:
                raise NoEncontrado()

            carpeta.mkdir(parents=True, exist_ok=True)
            for documento, origen in pdfs.items():
                ruta = carpeta / f"{_slug(documento)}_{uuid.uuid4().hex}.pdf"
                shutil.copyfile(origen, ruta)
                rutas_nuevas.append(ruta)
                ruta_relativa = ruta.relative_to(base).as_posix()
                anterior = conn.execute(
                    text("""SELECT id_documento, ruta_archivo
                            FROM expedientes_digitales
                            WHERE numero_control = :numero AND tipo_documento = :tipo
                            FOR UPDATE"""),
                    {"numero": numero_control, "tipo": tipos[documento]},
                ).mappings().first()
                if anterior:
                    conn.execute(
                        text("""UPDATE expedientes_digitales SET ruta_archivo = :ruta
                                WHERE id_documento = :id"""),
                        {"ruta": ruta_relativa, "id": anterior["id_documento"]},
                    )
                    rutas_anteriores.append(base / anterior["ruta_archivo"])
                else:
                    conn.execute(
                        text("""INSERT INTO expedientes_digitales
                                    (numero_control, tipo_documento, ruta_archivo)
                                VALUES (:numero, :tipo, :ruta)"""),
                        {
                            "numero": numero_control,
                            "tipo": tipos[documento],
                            "ruta": ruta_relativa,
                        },
                    )
    except Exception:
        for ruta in rutas_nuevas:
            ruta.unlink(missing_ok=True)
        raise

    for ruta in rutas_anteriores:
        try:
            ruta_resuelta = ruta.resolve()
            if ruta_resuelta.is_relative_to(base.resolve()) and ruta_resuelta.is_file():
                ruta_resuelta.unlink()
        except OSError:
            log.warning("No se pudo eliminar el documento reemplazado: %s", ruta)


def eliminar_alumno(numero_control: str, id_usuario: int) -> None:
    with engine.begin() as conn:
        anterior = conn.execute(
            text("SELECT * FROM alumnos WHERE numero_control = :numero FOR UPDATE"),
            {"numero": numero_control},
        ).mappings().first()
        if anterior is None or anterior["eliminado"]:
            raise NoEncontrado()
        conn.execute(
            text("UPDATE alumnos SET eliminado = TRUE WHERE numero_control = :numero"),
            {"numero": numero_control},
        )
        nuevo = dict(anterior) | {"eliminado": True}
        _guardar_historial(
            conn, numero_control, "BAJA", dict(anterior), nuevo, id_usuario,
        )


def historial_alumno(numero_control: str) -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT h.id_historial, h.numero_control, h.accion,
                           h.datos_anteriores, h.datos_nuevos, h.fecha,
                           u.correo AS usuario
                    FROM historial_alumnos h
                    JOIN usuarios u ON u.id_usuario = h.id_usuario
                    WHERE h.numero_control = :numero
                    ORDER BY h.fecha DESC, h.id_historial DESC"""),
            {"numero": numero_control},
        ).mappings().all()
    return [
        {
            "id_historial": fila["id_historial"],
            "numero_control": fila["numero_control"],
            "accion": fila["accion"],
            "datos_anteriores": json.loads(fila["datos_anteriores"]),
            "datos_nuevos": json.loads(fila["datos_nuevos"]) if fila["datos_nuevos"] else None,
            "fecha": fila["fecha"].isoformat(sep=" ", timespec="seconds"),
            "usuario": fila["usuario"],
        }
        for fila in filas
    ]


def listar_secretarias() -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT u.id_usuario, u.correo, u.estatus, ps.nombres, ps.apellidos
                    FROM usuarios u
                    JOIN roles r ON r.id_rol = u.id_rol
                    JOIN personal_secretaria ps ON ps.id_usuario = u.id_usuario
                    WHERE r.nombre_rol = :rol
                    ORDER BY ps.apellidos, ps.nombres, u.correo"""),
            {"rol": ROL_SECRETARIA},
        ).mappings().all()
    return [dict(fila) for fila in filas]


def crear_secretaria(datos: SecretariaCreate) -> dict:
    try:
        with engine.begin() as conn:
            id_rol = conn.execute(
                text("SELECT id_rol FROM roles WHERE nombre_rol = :rol"),
                {"rol": ROL_SECRETARIA},
            ).scalar_one_or_none()
            if id_rol is None:
                raise Conflicto("No está configurado el rol Secretaría en la base de datos.")
            id_usuario = conn.execute(
                text("""INSERT INTO usuarios (correo, password, id_rol, estatus)
                        VALUES (:correo, :password, :rol, 'Activo')"""),
                {
                    "correo": datos.correo,
                    "password": hashear(datos.password),
                    "rol": id_rol,
                },
            ).lastrowid
            conn.execute(
                text("""INSERT INTO personal_secretaria (id_usuario, nombres, apellidos)
                        VALUES (:usuario, :nombres, :apellidos)"""),
                {
                    "usuario": id_usuario,
                    "nombres": datos.nombres,
                    "apellidos": datos.apellidos,
                },
            )
    except IntegrityError as exc:
        raise Conflicto("Ya existe una cuenta con ese correo.") from exc
    return {
        "id_usuario": id_usuario,
        "correo": datos.correo,
        "estatus": "Activo",
        "nombres": datos.nombres,
        "apellidos": datos.apellidos,
    }


def crear_docente(datos: DocenteCreate) -> dict:
    try:
        with engine.begin() as conn:
            id_rol = conn.execute(
                text("SELECT id_rol FROM roles WHERE nombre_rol = :rol"),
                {"rol": ROL_DOCENTE},
            ).scalar_one_or_none()
            if id_rol is None:
                raise Conflicto("No está configurado el rol Docente en la base de datos.")
            id_usuario = conn.execute(
                text("""INSERT INTO usuarios (correo, password, id_rol, estatus)
                        VALUES (:correo, :password, :rol, 'Activo')"""),
                {
                    "correo": datos.correo,
                    "password": hashear(datos.password),
                    "rol": id_rol,
                },
            ).lastrowid
            conn.execute(
                text("""INSERT INTO empleados_docentes (id_usuario, nombres, apellidos)
                        VALUES (:usuario, :nombres, :apellidos)"""),
                {
                    "usuario": id_usuario,
                    "nombres": datos.nombres,
                    "apellidos": datos.apellidos,
                },
            )
    except IntegrityError as exc:
        raise Conflicto("Ya existe una cuenta con ese correo.") from exc
    return {
        "id_usuario": id_usuario,
        "correo": datos.correo,
        "estatus": "Activo",
        "nombres": datos.nombres,
        "apellidos": datos.apellidos,
    }


def listar_docentes() -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT u.id_usuario, u.correo, u.estatus, d.nombres, d.apellidos
                    FROM usuarios u
                    JOIN roles r ON r.id_rol = u.id_rol
                    JOIN empleados_docentes d ON d.id_usuario = u.id_usuario
                    WHERE r.nombre_rol = :rol
                    ORDER BY d.apellidos, d.nombres, u.correo"""),
            {"rol": ROL_DOCENTE},
        ).mappings().all()
    return [dict(fila) for fila in filas]


def cargar_catalogo_1isc(conn) -> None:
    turnos = {
        nombre: "Matutino" if int(nombre[-1]) % 2 else "Vespertino"
        for nombre in CATALOGO_1ISC
    }
    for nombre_paquete, materias in CATALOGO_1ISC.items():
        id_paquete = conn.execute(
            text("""SELECT id_paquete FROM paquetes_horario
                    WHERE nombre_paquete = :nombre AND semestre = 1
                    ORDER BY id_paquete LIMIT 1"""),
            {"nombre": nombre_paquete},
        ).scalar_one_or_none()
        if id_paquete is None:
            id_paquete = conn.execute(
                text("""INSERT INTO paquetes_horario (nombre_paquete, semestre)
                        VALUES (:nombre, 1)"""),
                {"nombre": nombre_paquete},
            ).lastrowid

        for nombre_materia, aula, creditos, docente, dias in materias:
            id_materia = conn.execute(
                text("""SELECT id_materia FROM materias
                        WHERE nombre_materia = :nombre AND semestre = 1
                        ORDER BY id_materia LIMIT 1"""),
                {"nombre": nombre_materia},
            ).scalar_one_or_none()
            if id_materia is None:
                id_materia = conn.execute(
                    text("""INSERT INTO materias (nombre_materia, semestre)
                            VALUES (:nombre, 1)"""),
                    {"nombre": nombre_materia},
                ).lastrowid

            id_grupo = conn.execute(
                text("""SELECT id_grupo FROM grupos
                        WHERE id_paquete = :paquete AND id_materia = :materia
                          AND periodo_escolar = :periodo
                        ORDER BY id_grupo LIMIT 1"""),
                {
                    "paquete": id_paquete,
                    "materia": id_materia,
                    "periodo": PERIODO_1ISC,
                },
            ).scalar_one_or_none()
            if id_grupo is None:
                id_grupo = conn.execute(
                    text("""INSERT INTO grupos (
                                id_paquete, id_materia, id_docente, docente_programado,
                                aula, creditos, periodo_escolar, turno,
                                cupo_maximo, cupo_disponible
                            ) VALUES (
                                :paquete, :materia, NULL, :docente, :aula, :creditos,
                                :periodo, :turno, 25, 25
                            )"""),
                    {
                        "paquete": id_paquete,
                        "materia": id_materia,
                        "docente": docente,
                        "aula": aula,
                        "creditos": creditos,
                        "periodo": PERIODO_1ISC,
                        "turno": turnos[nombre_paquete],
                    },
                ).lastrowid
            else:
                conn.execute(
                    text("""UPDATE grupos SET docente_programado = :docente,
                                aula = :aula, creditos = :creditos, turno = :turno
                            WHERE id_grupo = :grupo"""),
                    {
                        "grupo": id_grupo,
                        "docente": docente,
                        "aula": aula,
                        "creditos": creditos,
                        "turno": turnos[nombre_paquete],
                    },
                )

            conn.execute(
                text("DELETE FROM horarios_grupo WHERE id_grupo = :grupo"),
                {"grupo": id_grupo},
            )
            for dia_semana, horario in enumerate(dias, 1):
                if horario is None:
                    continue
                inicio, fin = horario.split("-")
                conn.execute(
                    text("""INSERT INTO horarios_grupo
                                (id_grupo, dia_semana, hora_inicio, hora_fin)
                            VALUES (:grupo, :dia, :inicio, :fin)"""),
                    {
                        "grupo": id_grupo,
                        "dia": dia_semana,
                        "inicio": inicio,
                        "fin": fin,
                    },
                )


def _resumen_paquetes_horario(
    conn,
    periodo: str,
    semestre: int | None = None,
    solo_catalogo: bool = True,
) -> list[dict]:
    filas = conn.execute(
        text("""SELECT p.id_paquete, p.nombre_paquete AS nombre, p.semestre,
                       g.periodo_escolar AS periodo,
                       COUNT(DISTINCT g.id_grupo) AS total_materias,
                       COUNT(DISTINCT CASE
                           WHEN a.estatus = 'Activo' AND a.eliminado = FALSE
                           THEN a.numero_control END) AS alumnos,
                       MIN(g.turno) AS turno,
                       MIN(g.cupo_maximo) AS cupo_maximo,
                       MIN(g.cupo_disponible) AS lugares
                FROM paquetes_horario p
                JOIN grupos g ON g.id_paquete = p.id_paquete
                LEFT JOIN inscripciones_grupos i ON i.id_grupo = g.id_grupo
                LEFT JOIN alumnos a ON a.numero_control = i.numero_control
                WHERE g.periodo_escolar = :periodo
                  AND (:solo_catalogo = 0 OR p.nombre_paquete LIKE '1ISC%')
                  AND (:semestre IS NULL OR p.semestre = :semestre)
                GROUP BY p.id_paquete, p.nombre_paquete, p.semestre, g.periodo_escolar
                ORDER BY p.nombre_paquete"""),
        {"periodo": periodo, "semestre": semestre, "solo_catalogo": solo_catalogo},
    ).mappings().all()
    return [dict(fila) for fila in filas]


def listar_paquetes_horario(semestre: int) -> list[dict]:
    with engine.connect() as conn:
        return _resumen_paquetes_horario(conn, PERIODO_1ISC, semestre)


def _datos_paquete_horario(
    conn,
    id_paquete: int,
    periodo: str,
    solo_catalogo: bool = True,
) -> tuple[dict, list[dict]]:
    resumen = next(
        (fila for fila in _resumen_paquetes_horario(
            conn, periodo, solo_catalogo=solo_catalogo,
        )
         if fila["id_paquete"] == id_paquete),
        None,
    )
    if resumen is None:
        raise NoEncontrado()

    filas = conn.execute(
        text("""SELECT g.id_grupo, m.nombre_materia, g.aula, g.creditos,
                       g.id_docente, g.docente_programado,
                       CONCAT_WS(' ', d.nombres, d.apellidos) AS docente_asignado,
                       h.dia_semana, h.hora_inicio, h.hora_fin
                FROM grupos g
                JOIN materias m ON m.id_materia = g.id_materia
                LEFT JOIN empleados_docentes d ON d.id_docente = g.id_docente
                LEFT JOIN horarios_grupo h ON h.id_grupo = g.id_grupo
                WHERE g.id_paquete = :paquete AND g.periodo_escolar = :periodo
                ORDER BY m.nombre_materia, h.dia_semana"""),
        {"paquete": id_paquete, "periodo": periodo},
    ).mappings().all()

    materias: dict[int, dict] = {}
    dias = ("", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes")
    for fila in filas:
        materia = materias.setdefault(fila["id_grupo"], {
            "id_grupo": fila["id_grupo"],
            "nombre_materia": fila["nombre_materia"],
            "aula": fila["aula"],
            "creditos": fila["creditos"],
            "id_docente": fila["id_docente"],
            "docente_asignado": fila["docente_asignado"],
            "docente_programado": fila["docente_programado"],
            "docente": fila["docente_asignado"] or fila["docente_programado"] or "Por asignar",
            "horarios": [],
        })
        if fila["dia_semana"] is not None:
            inicio = fila["hora_inicio"]
            fin = fila["hora_fin"]
            materia["horarios"].append({
                "dia_semana": fila["dia_semana"],
                "dia": dias[fila["dia_semana"]],
                "inicio": inicio[:5] if isinstance(inicio, str) else _formatear_hora(inicio)[:5],
                "fin": fin[:5] if isinstance(fin, str) else _formatear_hora(fin)[:5],
            })
    return resumen, list(materias.values())


def detalle_paquete_horario(id_paquete: int) -> dict:
    with engine.connect() as conn:
        paquete, materias = _datos_paquete_horario(conn, id_paquete, PERIODO_1ISC)
    return {"paquete": paquete, "materias": materias}


def estado_horario_alumno(numero_control: str) -> dict:
    with engine.connect() as conn:
        alumno = conn.execute(
            text("""SELECT numero_control, nombres, apellido_paterno, apellido_materno,
                           semestre_actual, estatus, eliminado
                    FROM alumnos WHERE numero_control = :numero"""),
            {"numero": numero_control},
        ).mappings().first()
        if alumno is None or alumno["eliminado"] or alumno["estatus"] != "Activo":
            raise NoEncontrado()

        paquetes = conn.execute(
            text("""SELECT DISTINCT p.id_paquete
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE i.numero_control = :numero AND g.periodo_escolar = :periodo"""),
            {"numero": numero_control, "periodo": PERIODO_1ISC},
        ).scalars().all()
        if len(paquetes) > 1:
            raise Conflicto("El alumno aparece inscrito en más de un paquete del periodo actual.")
        if not paquetes:
            return {
                "numero_control": numero_control,
                "nombre_completo": " ".join(
                    parte for parte in (
                        alumno["nombres"], alumno["apellido_paterno"], alumno["apellido_materno"],
                    ) if parte
                ),
                "semestre": alumno["semestre_actual"],
                "periodo": PERIODO_1ISC,
                "asignado": False,
                "paquete": None,
                "materias": [],
            }

        paquete, materias = _datos_paquete_horario(
            conn, paquetes[0], PERIODO_1ISC, solo_catalogo=False,
        )
        return {
            "numero_control": numero_control,
            "nombre_completo": " ".join(
                parte for parte in (
                    alumno["nombres"], alumno["apellido_paterno"], alumno["apellido_materno"],
                ) if parte
            ),
            "semestre": alumno["semestre_actual"],
            "periodo": PERIODO_1ISC,
            "asignado": True,
            "paquete": paquete,
            "materias": materias,
        }


def estado_reinscripcion_alumno(consulta: str) -> dict:
    consulta = consulta.strip().upper()
    with engine.connect() as conn:
        alumno = conn.execute(
            text("""SELECT numero_control, nombres, apellido_paterno, apellido_materno,
                           semestre_actual, estatus, eliminado
                    FROM alumnos
                    WHERE numero_control = :consulta OR UPPER(TRIM(curp)) = :consulta"""),
            {"consulta": consulta},
        ).mappings().first()
        if alumno is None or alumno["eliminado"] or alumno["estatus"] != "Activo":
            raise NoEncontrado()

        semestre = alumno["semestre_actual"]
        if semestre is None or not 2 <= semestre <= 10:
            raise Conflicto(
                "La reinscripción está disponible únicamente para alumnos de semestres 2 a 10."
            )

        paquetes = _resumen_paquetes_horario(
            conn, settings.periodo, semestre, solo_catalogo=False,
        )
        existentes = conn.execute(
            text("""SELECT DISTINCT p.id_paquete
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE i.numero_control = :numero AND g.periodo_escolar = :periodo"""),
            {"numero": alumno["numero_control"], "periodo": settings.periodo},
        ).scalars().all()
        if len(existentes) > 1:
            raise Conflicto(
                "El alumno aparece inscrito en más de un paquete del periodo activo."
            )

        paquete_actual = None
        materias = []
        if existentes:
            paquete_actual, materias = _datos_paquete_horario(
                conn, existentes[0], settings.periodo, solo_catalogo=False,
            )

        return {
            "numero_control": alumno["numero_control"],
            "nombre_completo": " ".join(
                parte for parte in (
                    alumno["nombres"], alumno["apellido_paterno"],
                    alumno["apellido_materno"],
                ) if parte
            ),
            "semestre": semestre,
            "periodo": settings.periodo,
            "asignado": bool(existentes),
            "paquete": paquete_actual,
            "materias": materias,
            "paquetes": paquetes,
        }


def asignar_paquete_reinscripcion(numero_control: str, id_paquete: int) -> dict:
    with engine.begin() as conn:
        alumno = conn.execute(
            text("""SELECT semestre_actual, estatus, eliminado
                    FROM alumnos WHERE numero_control = :numero FOR UPDATE"""),
            {"numero": numero_control},
        ).mappings().first()
        if alumno is None or alumno["eliminado"] or alumno["estatus"] != "Activo":
            raise NoEncontrado()

        semestre = alumno["semestre_actual"]
        if semestre is None or not 2 <= semestre <= 10:
            raise Conflicto(
                "La reinscripción está disponible únicamente para alumnos de semestres 2 a 10."
            )

        paquete = conn.execute(
            text("""SELECT id_paquete FROM paquetes_horario
                    WHERE id_paquete = :paquete AND semestre = :semestre"""),
            {"paquete": id_paquete, "semestre": semestre},
        ).mappings().first()
        if paquete is None:
            raise Conflicto("El paquete seleccionado no corresponde al semestre del alumno.")

        existentes = conn.execute(
            text("""SELECT DISTINCT p.nombre_paquete
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE i.numero_control = :numero AND g.periodo_escolar = :periodo"""),
            {"numero": numero_control, "periodo": settings.periodo},
        ).scalars().all()
        if existentes:
            raise Conflicto(
                f"El alumno ya tiene un paquete asignado en {settings.periodo}: "
                f"{', '.join(existentes)}."
            )

        grupos = conn.execute(
            text("""SELECT id_grupo, turno, cupo_disponible
                    FROM grupos
                    WHERE id_paquete = :paquete AND periodo_escolar = :periodo
                    ORDER BY id_grupo FOR UPDATE"""),
            {"paquete": id_paquete, "periodo": settings.periodo},
        ).mappings().all()
        if not grupos:
            raise NoEncontrado()
        if any(fila["cupo_disponible"] <= 0 for fila in grupos):
            raise CupoLleno("El paquete seleccionado ya no tiene cupo disponible.")

        conn.execute(
            text("""INSERT INTO inscripciones_grupos (numero_control, id_grupo)
                    VALUES (:numero, :grupo)"""),
            [{"numero": numero_control, "grupo": fila["id_grupo"]} for fila in grupos],
        )
        conn.execute(
            text("UPDATE alumnos SET turno = :turno WHERE numero_control = :numero"),
            {"turno": grupos[0]["turno"], "numero": numero_control},
        )

    return estado_reinscripcion_alumno(numero_control)


def asignar_paquete_horario(numero_control: str, id_paquete: int) -> dict:
    with engine.begin() as conn:
        alumno = conn.execute(
            text("""SELECT semestre_actual, estatus, eliminado
                    FROM alumnos WHERE numero_control = :numero FOR UPDATE"""),
            {"numero": numero_control},
        ).mappings().first()
        if alumno is None or alumno["eliminado"] or alumno["estatus"] != "Activo":
            raise NoEncontrado()

        paquete = conn.execute(
            text("""SELECT id_paquete, nombre_paquete, semestre
                    FROM paquetes_horario
                    WHERE id_paquete = :paquete AND semestre = :semestre"""),
            {"paquete": id_paquete, "semestre": alumno["semestre_actual"]},
        ).mappings().first()
        if paquete is None or paquete["nombre_paquete"] not in CATALOGO_1ISC:
            raise Conflicto(
                "El paquete seleccionado no corresponde al semestre o periodo escolar habilitado."
            )

        existentes = conn.execute(
            text("""SELECT DISTINCT p.nombre_paquete
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE i.numero_control = :numero AND g.periodo_escolar = :periodo"""),
            {"numero": numero_control, "periodo": PERIODO_1ISC},
        ).scalars().all()
        if existentes:
            raise Conflicto(
                f"El alumno ya tiene un grupo asignado en {PERIODO_1ISC}: {', '.join(existentes)}."
            )

        grupos = conn.execute(
            text("""SELECT id_grupo, turno, cupo_disponible
                    FROM grupos
                    WHERE id_paquete = :paquete AND periodo_escolar = :periodo
                    ORDER BY id_grupo FOR UPDATE"""),
            {"paquete": id_paquete, "periodo": PERIODO_1ISC},
        ).mappings().all()
        if not grupos:
            raise NoEncontrado()
        if len(grupos) != 6:
            raise Conflicto("El paquete está incompleto y no puede asignarse.")
        if any(fila["cupo_disponible"] <= 0 for fila in grupos):
            raise CupoLleno("El paquete seleccionado ya no tiene cupo disponible.")

        conn.execute(
            text("""INSERT INTO inscripciones_grupos (numero_control, id_grupo)
                    VALUES (:numero, :grupo)"""),
            [{"numero": numero_control, "grupo": fila["id_grupo"]} for fila in grupos],
        )
        conn.execute(
            text("UPDATE alumnos SET turno = :turno WHERE numero_control = :numero"),
            {"turno": grupos[0]["turno"], "numero": numero_control},
        )

    return estado_horario_alumno(numero_control)


def lista_alumnos_paquete(id_paquete: int) -> dict:
    with engine.connect() as conn:
        paquete = next(
            (fila for fila in _resumen_paquetes_horario(conn, PERIODO_1ISC)
             if fila["id_paquete"] == id_paquete),
            None,
        )
        if paquete is None:
            raise NoEncontrado()
        alumnos = conn.execute(
            text("""SELECT DISTINCT a.numero_control, a.nombres, a.apellido_paterno,
                           a.apellido_materno, a.correo_institucional
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN alumnos a ON a.numero_control = i.numero_control
                    WHERE g.id_paquete = :paquete AND g.periodo_escolar = :periodo
                      AND a.estatus = 'Activo' AND a.eliminado = FALSE
                    ORDER BY a.apellido_paterno, a.apellido_materno, a.nombres,
                             a.numero_control"""),
            {"paquete": id_paquete, "periodo": PERIODO_1ISC},
        ).mappings().all()
    return {"paquete": paquete, "alumnos": [dict(fila) for fila in alumnos]}


def listar_docentes_activos() -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT d.id_docente, d.nombres, d.apellidos, u.correo
                    FROM empleados_docentes d
                    JOIN usuarios u ON u.id_usuario = d.id_usuario
                    JOIN roles r ON r.id_rol = u.id_rol
                    WHERE r.nombre_rol = :rol AND u.estatus = 'Activo'
                    ORDER BY d.apellidos, d.nombres, u.correo"""),
            {"rol": ROL_DOCENTE},
        ).mappings().all()
    return [dict(fila) for fila in filas]


def listar_periodos_escolares() -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT periodo, fecha_inicio, actualizado_en
                    FROM periodos_escolares
                    ORDER BY fecha_inicio DESC, periodo DESC""")
        ).mappings().all()
    return [dict(fila) for fila in filas]


def guardar_periodo_escolar(
    periodo: str,
    fecha_inicio: date,
    id_usuario: int,
    periodo_anterior: str | None = None,
) -> dict:
    origen = periodo_anterior or periodo
    with engine.begin() as conn:
        existente = conn.execute(
            text("SELECT fecha_inicio FROM periodos_escolares WHERE periodo = :periodo FOR UPDATE"),
            {"periodo": origen},
        ).mappings().first()
        if periodo_anterior and not existente:
            raise Conflicto("El periodo seleccionado ya no existe. Actualiza la lista e inténtalo de nuevo.")

        if origen != periodo:
            duplicado = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM periodos_escolares WHERE periodo = :periodo)"),
                {"periodo": periodo},
            ).scalar_one()
            if duplicado:
                raise Conflicto("Ya existe un periodo con ese nombre.")
            grupos_destino = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM grupos WHERE periodo_escolar = :periodo)"),
                {"periodo": periodo},
            ).scalar_one()
            if grupos_destino:
                raise Conflicto(
                    "Ya hay grupos asociados al periodo de destino; no se pueden combinar automáticamente."
                )
            conn.execute(
                text("UPDATE grupos SET periodo_escolar = :nuevo WHERE periodo_escolar = :anterior"),
                {"nuevo": periodo, "anterior": origen},
            )
            conn.execute(
                text("""UPDATE periodos_escolares
                        SET periodo = :nuevo, fecha_inicio = :fecha_inicio, actualizado_por = :usuario
                        WHERE periodo = :anterior"""),
                {
                    "nuevo": periodo,
                    "anterior": origen,
                    "fecha_inicio": fecha_inicio,
                    "usuario": id_usuario,
                },
            )
        elif existente:
            conn.execute(
                text("""UPDATE periodos_escolares
                        SET fecha_inicio = :fecha_inicio, actualizado_por = :usuario
                        WHERE periodo = :periodo"""),
                {"periodo": periodo, "fecha_inicio": fecha_inicio, "usuario": id_usuario},
            )
        else:
            conn.execute(
                text("""INSERT INTO periodos_escolares (periodo, fecha_inicio, actualizado_por)
                        VALUES (:periodo, :fecha_inicio, :usuario)"""),
                {"periodo": periodo, "fecha_inicio": fecha_inicio, "usuario": id_usuario},
            )
        fila = conn.execute(
            text("""SELECT periodo, fecha_inicio, actualizado_en
                    FROM periodos_escolares WHERE periodo = :periodo"""),
            {"periodo": periodo},
        ).mappings().one()
    if origen != periodo and settings.periodo == origen:
        settings.periodo_escolar = periodo
    return dict(fila)


def listar_grupos_docente(id_usuario: int) -> list[dict]:
    """Devuelve solo los grupos asignados al docente, con su horario y calificaciones."""
    dias = ("", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes")
    with engine.connect() as conn:
        fecha_inicio = conn.execute(
            text("SELECT fecha_inicio FROM periodos_escolares WHERE periodo = :periodo"),
            {"periodo": settings.periodo},
        ).scalar_one_or_none()
        filas = conn.execute(
            text("""SELECT g.id_grupo, p.id_paquete, p.nombre_paquete AS grupo,
                           m.nombre_materia, g.aula, g.creditos, g.turno,
                           g.periodo_escolar, d.nombres AS docente_nombres,
                           d.apellidos AS docente_apellidos,
                           h.dia_semana, h.hora_inicio, h.hora_fin
                    FROM empleados_docentes d
                    JOIN grupos g ON g.id_docente = d.id_docente
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    JOIN materias m ON m.id_materia = g.id_materia
                    LEFT JOIN horarios_grupo h ON h.id_grupo = g.id_grupo
                    WHERE d.id_usuario = :usuario AND g.periodo_escolar = :periodo
                    ORDER BY p.nombre_paquete, m.nombre_materia, h.dia_semana"""),
            {"usuario": id_usuario, "periodo": settings.periodo},
        ).mappings().all()

        grupos: dict[int, dict] = {}
        for fila in filas:
            grupo = grupos.setdefault(fila["id_grupo"], {
                "id_grupo": fila["id_grupo"],
                "id_paquete": fila["id_paquete"],
                "grupo": fila["grupo"],
                "nombre_materia": fila["nombre_materia"],
                "aula": fila["aula"],
                "creditos": fila["creditos"],
                "turno": fila["turno"],
                "periodo": fila["periodo_escolar"],
                "docente": " ".join(filter(None, (
                    fila["docente_nombres"], fila["docente_apellidos"],
                ))),
                "horarios": [],
                "alumnos": [],
            })
            if fila["dia_semana"] is not None:
                inicio = fila["hora_inicio"]
                fin = fila["hora_fin"]
                grupo["horarios"].append({
                    "dia": dias[fila["dia_semana"]],
                    "inicio": inicio[:5] if isinstance(inicio, str) else _formatear_hora(inicio)[:5],
                    "fin": fin[:5] if isinstance(fin, str) else _formatear_hora(fin)[:5],
                })

        if not grupos:
            return []

        semana_actual = _semana_del_periodo(fecha_inicio) if fecha_inicio else None
        evaluaciones_disponibles = [
            periodo for periodo, semana in SEMANAS_EVALUACION.items()
            if semana_actual is not None and semana_actual >= semana
        ]
        inscripciones = conn.execute(
            text("""SELECT i.id_grupo, a.numero_control, a.nombres, a.apellido_paterno,
                           a.apellido_materno,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Semana 5' THEN c.valor END) AS semana_5,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Semana 9' THEN c.valor END) AS semana_9,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Semana 13' THEN c.valor END) AS semana_13,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Final' THEN c.valor END) AS final,
                           MAX(CASE WHEN c.periodo_evaluacion = 'Final'
                                    THEN c.confirmada ELSE FALSE END) AS final_confirmada
                    FROM inscripciones_grupos i
                    JOIN alumnos a ON a.numero_control = i.numero_control
                    LEFT JOIN calificaciones c ON c.id_inscripcion = i.id_inscripcion
                    WHERE i.id_grupo IN :grupos AND a.estatus = 'Activo' AND a.eliminado = FALSE
                    GROUP BY i.id_grupo, a.numero_control, a.nombres,
                             a.apellido_paterno, a.apellido_materno
                    ORDER BY i.id_grupo, a.apellido_paterno, a.apellido_materno,
                             a.nombres, a.numero_control""").bindparams(
                bindparam("grupos", expanding=True)
            ),
            {"grupos": list(grupos)},
        ).mappings().all()

    for fila in inscripciones:
        grupos[fila["id_grupo"]]["alumnos"].append({
            "numero_control": fila["numero_control"],
            "nombres": fila["nombres"],
            "apellido_paterno": fila["apellido_paterno"],
            "apellido_materno": fila["apellido_materno"],
            "nombre_completo": " ".join(filter(None, (
                fila["apellido_paterno"], fila["apellido_materno"], fila["nombres"],
            ))),
            "semana_5": fila["semana_5"],
            "semana_9": fila["semana_9"],
            "semana_13": fila["semana_13"],
            "final": fila["final"],
            "final_confirmada": bool(fila["final_confirmada"]),
        })
    for grupo in grupos.values():
        grupo["semana_actual"] = semana_actual
        grupo["evaluaciones_disponibles"] = evaluaciones_disponibles
        grupo["fecha_inicio_periodo"] = fecha_inicio
    return list(grupos.values())


def _inscripcion_docente_bloqueada(conn, id_usuario: int, id_grupo: int, numero_control: str):
    fila = conn.execute(
        text("""SELECT i.id_inscripcion
                FROM inscripciones_grupos i
                JOIN grupos g ON g.id_grupo = i.id_grupo
                JOIN empleados_docentes d ON d.id_docente = g.id_docente
                JOIN alumnos a ON a.numero_control = i.numero_control
                WHERE d.id_usuario = :usuario AND g.id_grupo = :grupo
                  AND g.periodo_escolar = :periodo
                  AND i.numero_control = :numero
                  AND a.estatus = 'Activo' AND a.eliminado = FALSE
                FOR UPDATE"""),
        {
            "usuario": id_usuario,
            "grupo": id_grupo,
            "periodo": settings.periodo,
            "numero": numero_control,
        },
    ).mappings().first()
    if fila is None:
        raise NoEncontrado
    return fila["id_inscripcion"]


def guardar_calificacion_docente(
    id_usuario: int,
    id_grupo: int,
    numero_control: str,
    periodo_evaluacion: str,
    valor: int,
) -> dict:
    if periodo_evaluacion not in ("Semana 5", "Semana 9", "Semana 13"):
        raise Conflicto("Selecciona un periodo de evaluación válido.")
    with engine.begin() as conn:
        inscripcion = _inscripcion_docente_bloqueada(
            conn, id_usuario, id_grupo, numero_control,
        )
        fecha_inicio = conn.execute(
            text("SELECT fecha_inicio FROM periodos_escolares WHERE periodo = :periodo"),
            {"periodo": settings.periodo},
        ).scalar_one_or_none()
        if fecha_inicio is None:
            raise Conflicto("El administrador aún no configuró la fecha de inicio de este periodo.")
        if _semana_del_periodo(fecha_inicio) < SEMANAS_EVALUACION[periodo_evaluacion]:
            raise Conflicto(f"La captura de {periodo_evaluacion} aún no está habilitada.")
        final_confirmada = conn.execute(
            text("""SELECT confirmada FROM calificaciones
                    WHERE id_inscripcion = :inscripcion AND periodo_evaluacion = 'Final'
                    FOR UPDATE"""),
            {"inscripcion": inscripcion},
        ).scalar_one_or_none()
        if final_confirmada:
            raise Conflicto(
                "No se pueden modificar los periodos después de confirmar la calificación final."
            )

        conn.execute(
            text("""INSERT INTO calificaciones (id_inscripcion, periodo_evaluacion, valor)
                    VALUES (:inscripcion, :periodo, :valor)
                    ON DUPLICATE KEY UPDATE valor = VALUES(valor)"""),
            {"inscripcion": inscripcion, "periodo": periodo_evaluacion, "valor": valor},
        )
    return {"numero_control": numero_control, "periodo_evaluacion": periodo_evaluacion, "valor": valor}


def confirmar_calificacion_final_docente(
    id_usuario: int,
    id_grupo: int,
    numero_control: str,
) -> dict:
    with engine.begin() as conn:
        inscripcion = _inscripcion_docente_bloqueada(
            conn, id_usuario, id_grupo, numero_control,
        )
        fecha_inicio = conn.execute(
            text("SELECT fecha_inicio FROM periodos_escolares WHERE periodo = :periodo"),
            {"periodo": settings.periodo},
        ).scalar_one_or_none()
        if fecha_inicio is None:
            raise Conflicto("El administrador aún no configuró la fecha de inicio de este periodo.")
        if _semana_del_periodo(fecha_inicio) < SEMANAS_EVALUACION["Final"]:
            raise Conflicto("La calificación final solo se puede confirmar a partir de la semana 17.")

        final_existente = conn.execute(
            text("""SELECT confirmada FROM calificaciones
                    WHERE id_inscripcion = :inscripcion AND periodo_evaluacion = 'Final'
                    FOR UPDATE"""),
            {"inscripcion": inscripcion},
        ).scalar_one_or_none()
        if final_existente:
            raise Conflicto("La calificación final ya fue confirmada y no se puede modificar.")

        periodos = conn.execute(
            text("""SELECT periodo_evaluacion, valor FROM calificaciones
                    WHERE id_inscripcion = :inscripcion
                      AND periodo_evaluacion IN ('Semana 5', 'Semana 9', 'Semana 13')
                    FOR UPDATE"""),
            {"inscripcion": inscripcion},
        ).mappings().all()
        valores = {fila["periodo_evaluacion"]: Decimal(str(fila["valor"])) for fila in periodos}
        requeridos = ("Semana 5", "Semana 9", "Semana 13")
        faltantes = [periodo for periodo in requeridos if periodo not in valores]
        if faltantes:
            raise Conflicto(
                f"No se puede confirmar la final; faltan calificaciones: {', '.join(faltantes)}."
            )

        promedio_exacto = sum(valores.values()) / Decimal(3)
        promedio = promedio_exacto.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        final = promedio if promedio_exacto >= 70 else Decimal("0")
        if final_existente is None:
            conn.execute(
                text("""INSERT INTO calificaciones
                            (id_inscripcion, periodo_evaluacion, valor, confirmada)
                        VALUES (:inscripcion, 'Final', :valor, TRUE)"""),
                {"inscripcion": inscripcion, "valor": final},
            )
        else:
            conn.execute(
                text("""UPDATE calificaciones
                        SET valor = :valor, confirmada = TRUE
                        WHERE id_inscripcion = :inscripcion
                          AND periodo_evaluacion = 'Final' AND confirmada = FALSE"""),
                {"inscripcion": inscripcion, "valor": final},
            )
    return {
        "numero_control": numero_control,
        "periodo_evaluacion": "Final",
        "valor": final,
        "confirmada": True,
    }


def actualizar_docente_grupo(id_grupo: int, id_docente: int | None) -> dict:
    with engine.begin() as conn:
        grupo = conn.execute(
            text("""SELECT g.id_grupo FROM grupos g
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE g.id_grupo = :grupo AND g.periodo_escolar = :periodo
                      AND p.nombre_paquete LIKE '1ISC%'
                    FOR UPDATE"""),
            {"grupo": id_grupo, "periodo": PERIODO_1ISC},
        ).mappings().first()
        if grupo is None:
            raise NoEncontrado()
        id_paquete = conn.execute(
            text("SELECT id_paquete FROM grupos WHERE id_grupo = :grupo"),
            {"grupo": id_grupo},
        ).scalar_one()
        if id_docente is not None:
            docente = conn.execute(
                text("""SELECT d.id_docente FROM empleados_docentes d
                        JOIN usuarios u ON u.id_usuario = d.id_usuario
                        JOIN roles r ON r.id_rol = u.id_rol
                        WHERE d.id_docente = :docente AND u.estatus = 'Activo'
                          AND r.nombre_rol = :rol
                        FOR UPDATE"""),
                {"docente": id_docente, "rol": ROL_DOCENTE},
            ).first()
            if docente is None:
                raise Conflicto("Selecciona una cuenta de maestro activa.")
            traslape = conn.execute(
                text("""SELECT m.nombre_materia, h.dia_semana,
                               h.hora_inicio, h.hora_fin
                        FROM grupos g
                        JOIN materias m ON m.id_materia = g.id_materia
                        JOIN horarios_grupo h ON h.id_grupo = g.id_grupo
                        JOIN horarios_grupo nuevo
                          ON nuevo.id_grupo = :grupo
                         AND nuevo.dia_semana = h.dia_semana
                         AND h.hora_inicio < nuevo.hora_fin
                         AND nuevo.hora_inicio < h.hora_fin
                        WHERE g.id_docente = :docente
                          AND g.id_grupo != :grupo
                          AND g.periodo_escolar = :periodo
                        ORDER BY h.dia_semana, h.hora_inicio
                        LIMIT 1"""),
                {
                    "grupo": id_grupo,
                    "docente": id_docente,
                    "periodo": PERIODO_1ISC,
                },
            ).mappings().first()
            if traslape is not None:
                dia = ("", "lunes", "martes", "miércoles", "jueves", "viernes")[
                    traslape["dia_semana"]
                ]
                inicio = _formatear_hora(traslape["hora_inicio"])[:5]
                fin = _formatear_hora(traslape["hora_fin"])[:5]
                raise Conflicto(
                    f"El maestro ya tiene asignada la materia "
                    f"«{traslape['nombre_materia']}» el {dia} de {inicio} a {fin}."
                )
        conn.execute(
            text("UPDATE grupos SET id_docente = :docente WHERE id_grupo = :grupo"),
            {"docente": id_docente, "grupo": id_grupo},
        )
    return detalle_paquete_horario(id_paquete)


def dar_baja_docente(id_usuario: int) -> dict:
    with engine.begin() as conn:
        fila = conn.execute(
            text("""SELECT u.id_usuario, u.correo, u.estatus, d.nombres, d.apellidos
                    FROM usuarios u
                    JOIN roles r ON r.id_rol = u.id_rol
                    JOIN empleados_docentes d ON d.id_usuario = u.id_usuario
                    WHERE u.id_usuario = :usuario AND r.nombre_rol = :rol
                    FOR UPDATE"""),
            {"usuario": id_usuario, "rol": ROL_DOCENTE},
        ).mappings().first()
        if fila is None:
            raise NoEncontrado()
        if fila["estatus"] == "Activo":
            conn.execute(
                text("UPDATE usuarios SET estatus = 'Inactivo' WHERE id_usuario = :usuario"),
                {"usuario": id_usuario},
            )
    return dict(fila) | {"estatus": "Inactivo"}


def dar_baja_secretaria(id_usuario: int) -> dict:
    with engine.begin() as conn:
        fila = conn.execute(
            text("""SELECT u.id_usuario, u.correo, u.estatus, ps.nombres, ps.apellidos
                    FROM usuarios u
                    JOIN roles r ON r.id_rol = u.id_rol
                    JOIN personal_secretaria ps ON ps.id_usuario = u.id_usuario
                    WHERE u.id_usuario = :usuario AND r.nombre_rol = :rol
                    FOR UPDATE"""),
            {"usuario": id_usuario, "rol": ROL_SECRETARIA},
        ).mappings().first()
        if fila is None:
            raise NoEncontrado()
        if fila["estatus"] == "Activo":
            conn.execute(
                text("UPDATE usuarios SET estatus = 'Inactivo' WHERE id_usuario = :usuario"),
                {"usuario": id_usuario},
            )
    return dict(fila) | {"estatus": "Inactivo"}


def _formatear_hora(valor: time | timedelta | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, timedelta):
        segundos_totales = int(valor.total_seconds())
        signo = "-" if segundos_totales < 0 else ""
        horas, resto = divmod(abs(segundos_totales), 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{signo}{horas:02d}:{minutos:02d}:{segundos:02d}"
    return valor.strftime("%H:%M:%S")


def listar_bitacora_accesos(limite: int = 200) -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT b.id_bitacora, b.fecha, b.hora_entrada, b.hora_salida,
                           u.correo, r.nombre_rol AS rol,
                           COALESCE(
                               NULLIF(TRIM(CONCAT_WS(' ', ps.nombres, ps.apellidos)), ''),
                               NULLIF(TRIM(CONCAT_WS(' ', d.nombres, d.apellidos)), ''),
                               u.correo
                           ) AS nombre
                    FROM bitacora_accesos b
                    JOIN usuarios u ON u.id_usuario = b.id_usuario
                    JOIN roles r ON r.id_rol = u.id_rol
                    LEFT JOIN personal_secretaria ps ON ps.id_usuario = u.id_usuario
                    LEFT JOIN empleados_docentes d ON d.id_usuario = u.id_usuario
                    ORDER BY b.fecha DESC, b.hora_entrada DESC, b.id_bitacora DESC
                    LIMIT :limite"""),
            {"limite": limite},
        ).mappings().all()
    return [
        {
            "id_bitacora": fila["id_bitacora"],
            "fecha": fila["fecha"].strftime("%d/%m/%Y"),
            "hora_entrada": _formatear_hora(fila["hora_entrada"]),
            "hora_salida": _formatear_hora(fila["hora_salida"]),
            "correo": fila["correo"],
            "rol": fila["rol"],
            "nombre": fila["nombre"],
        }
        for fila in filas
    ]


# --------------------------------------------------------------------------
# Alta
# --------------------------------------------------------------------------
def registrar_alta(d: AltaIn, pdfs: dict[str, str], usuario: dict) -> dict:
    """`pdfs` mapea nombre visible del documento -> ruta temporal ya validada."""
    errores = validar_alta(d)
    if errores:
        raise Conflicto("Revisa los datos capturados", errores)
    base = settings.storage_dir

    # El candado vive en su propia conexión y se libera DESPUÉS del commit; si se
    # soltara antes, otra alta leería cupos y consecutivos sin ver esta inscripción.
    with engine.connect() as candado:
        if candado.execute(text("SELECT GET_LOCK(:n, 20)"), {"n": NOMBRE_CANDADO}).scalar() != 1:
            raise Ocupado()
        carpeta: Path | None = None
        try:
            with engine.begin() as conn:
                dup = duplicados(
                    conn, d.ficha, d.curp, d.nss, d.rfc or "", d.ine or "", d.correo,
                )
                errores = {}
                if dup["ficha"]:
                    errores["ficha"] = "Esta ficha ya está registrada"
                if dup["curp"]:
                    errores["curp"] = "Esta CURP ya está registrada"
                if dup["nss"]:
                    errores["nss"] = "Este NSS ya está registrado"
                if dup["rfc"]:
                    errores["rfc"] = "Este RFC ya está registrado"
                if dup["ine"]:
                    errores["ine"] = "Este IDMEX ya está registrado"
                if dup["correo"]:
                    errores["correo"] = "Este correo personal ya está registrado"
                if errores:
                    raise Conflicto("El alumno ya está registrado", errores)
                if not _domicilio_catalogo_valido(conn, d):
                    raise Conflicto(
                        "La colonia no corresponde al código postal seleccionado",
                        {"colonia": "Selecciona una colonia del catálogo para ese código postal"},
                    )

                turno = v.turno_por_promedio(d.promedio)

                hoy = date.today()
                prefijo = v.prefijo_control(hoy.year, settings.numero_tecnologico)
                ultimo_sufijo = _ultimo_sufijo_control(conn, prefijo)
                try:
                    carrera, consecutivo = v.siguiente_carrera_secuencia(
                        ultimo_sufijo,
                        settings.numero_carrera,
                    )
                except OverflowError as exc:
                    raise Conflicto(f"Se agotaron los números de control con el prefijo {prefijo}.") from exc
                numero = v.generar_numero_control(
                    hoy.year,
                    settings.numero_tecnologico,
                    carrera,
                    consecutivo,
                )
                correo_inst = v.correo_institucional(numero, settings.dominio_institucional)

                # Con el candado tomado, una carpeta con este número no pertenece a
                # ningún alumno registrado: es resto de una alta interrumpida.
                huerfana = base / numero
                if huerfana.exists():
                    log.warning("Se elimina carpeta huérfana de expediente: %s", huerfana)
                    shutil.rmtree(huerfana)

                rutas = guardar_pdfs(numero, pdfs, base)
                carpeta = base / numero

                conn.execute(text("""
                    INSERT INTO alumnos (
                        numero_control, numero_ficha, nombres, apellido_paterno, apellido_materno,
                        fecha_nacimiento, genero, curp, rfc, ine, nss, celular,
                        celular_emergencia, correo_personal,
                        correo_emergencia, correo_institucional, tipo_sangre, alergias,
                        preparatoria_procedencia, promedio_preparatoria, turno, semestre_actual,
                        estatus
                    ) VALUES (
                        :numero, :ficha, :nombres, :ap_p, :ap_m, :nacimiento, :genero, :curp, :rfc,
                        :ine, :nss, :celular, :cel_emerg, :correo,
                        :correo_emerg, :correo_inst, :tipo_sangre, :alergias, :prepa, :promedio, :turno, :sem,
                        'Activo'
                    )"""), {
                    "numero": numero, "ficha": d.ficha, "nombres": d.nombre,
                    "ap_p": d.ap_paterno, "ap_m": d.ap_materno, "nacimiento": d.fecha_nacimiento,
                    "genero": d.genero, "curp": d.curp, "rfc": d.rfc,
                    "ine": v.normalizar_ine(d.ine), "nss": d.nss,
                    "celular": re.sub(r"[\s-]", "", d.celular),
                    "cel_emerg": re.sub(r"[\s-]", "", d.celular_emergencia),
                    "correo": d.correo,
                    "correo_emerg": d.correo_emergencia, "correo_inst": correo_inst,
                    "tipo_sangre": d.tipo_sangre, "alergias": d.alergias,
                    "prepa": d.preparatoria, "promedio": d.promedio,
                    "turno": turno, "sem": SEMESTRE_INGRESO,
                })
                conn.execute(
                    text("""INSERT INTO domicilios
                                (numero_control, codigo_postal, estado, municipio, colonia, calle, numero_exterior)
                            VALUES
                                (:numero, :codigo_postal, :estado, :municipio, :colonia, :calle, :numero_exterior)"""),
                    {
                        "numero": numero,
                        "codigo_postal": d.codigo_postal,
                        "estado": d.estado,
                        "municipio": d.municipio,
                        "colonia": d.colonia,
                        "calle": d.calle,
                        "numero_exterior": d.numero_exterior,
                    },
                )

                # La BD guarda solo la ruta, relativa a STORAGE_DIR (portable entre servidores)
                tipos = {visible: tipo_bd for visible, tipo_bd in DOCUMENTOS.values()}
                if rutas:
                    conn.execute(
                        text("""INSERT INTO expedientes_digitales (numero_control, tipo_documento, ruta_archivo)
                                VALUES (:numero, :tipo, :ruta)"""),
                        [{"numero": numero, "tipo": tipos[doc], "ruta": f"{numero}/{Path(ruta).name}"}
                         for doc, ruta in rutas.items()],
                    )

            log.info("Alta %s registrada por usuario %s", numero, usuario["id_usuario"])
            return {
                "numero_control": numero,
                "correo_institucional": correo_inst,
                "nombre_completo": f"{d.nombre} {d.ap_paterno} {d.ap_materno}",
                "turno": turno,
                "grupo": None,
                "aviso_turno": "El paquete horario se asignará desde Consultas.",
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
