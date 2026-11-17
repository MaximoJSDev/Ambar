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
from datetime import date
from pathlib import Path

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.result import MappingResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import TextClause

from ambar_common import validators as v

from .config import engine, settings
from .catalogo_horarios import CATALOGO_HORARIOS, PERIODO_1ISC
from .services.common import (
    Conflicto,
    CupoLleno,
    NoEncontrado,
    NumeroControlDuplicado,
    Ocupado,
    SinGrupos,
    _administrar_candado_mysql_altas,
    _obtener_fecha_inicio_periodo,
    _semana_del_periodo,
)
from .services.bitacora import listar_bitacora_accesos
from .services.periodos import (
    _SQL_FECHA_INICIO,
    _SQL_FECHA_INICIO_BLOQUEADA,
    _SQL_FECHA_INICIO_BLOQUEADA_AVANCE,
    avanzar_semestre_si_corresponde,
    guardar_periodo_escolar,
    listar_periodos_escolares,
    preparar_avances_semestre,
)
from .services.personal import (
    _crear_cuenta_personal,
    _dar_baja_personal,
    _listar_personal,
    crear_docente,
    crear_secretaria,
    dar_baja_docente,
    dar_baja_secretaria,
    listar_docentes,
    listar_secretarias,
)
from .constantes import (
    DOCUMENTOS,
    DOCUMENTOS_MODIFICABLES,
    SEMESTRE_INGRESO,
    TURNOS,
)
from .esquemas import AltaIn

log = logging.getLogger("sige")
_SQL_DOMICILIO_EXPEDIENTE = text(
    """SELECT codigo_postal, estado, municipio, colonia, calle, numero_exterior
                    FROM domicilios WHERE numero_control = :n""",
)
_SQL_DOMICILIO_MODIFICACION = text(
    """SELECT codigo_postal, estado, municipio, colonia, calle, numero_exterior
                        FROM domicilios WHERE numero_control = :numero""",
)
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


MENSAJES_DUPLICADOS_ALUMNO = {
    "ficha": "Esta ficha ya está registrada",
    "curp": "Esta CURP ya está registrada",
    "nss": "Este NSS ya está registrado",
    "rfc": "Este RFC ya está registrado",
    "ine": "Este IDMEX ya está registrado",
    "correo": "Este correo personal ya está registrado",
}
_CLAVES_PARAMETROS_ALTA = ("nombres", "ap_p", "ap_m", "nacimiento", "cel_emerg", "correo_emerg", "prepa")
_CLAVES_PARAMETROS_MODIFICACION = ("nombre", "ap_paterno", "ap_materno", "fecha", "celular_emergencia", "correo_emergencia", "preparatoria")


def _errores_duplicados(duplicados_alumno: dict[str, bool]) -> dict[str, str]:
    """Construye los errores visibles para los identificadores duplicados."""
    return {
        campo: mensaje
        for campo, mensaje in MENSAJES_DUPLICADOS_ALUMNO.items()
        if duplicados_alumno[campo]
    }


def _limpiar_celular(celular: str) -> str:
    """Elimina espacios y guiones del número celular."""
    return re.sub(r"[\s-]", "", celular)


def _parametros_alumno(
    datos: AltaIn,
    numero_control: str,
    claves: tuple[str, str, str, str, str, str, str],
    adicionales: dict[str, object] | None = None,
) -> dict[str, object]:
    """Arma parámetros conservando los nombres de bind de cada consulta."""
    parametros = {
        "numero": numero_control, "ficha": datos.ficha,
        "genero": datos.genero, "curp": datos.curp, "rfc": datos.rfc,
        "ine": v.normalizar_ine(datos.ine), "nss": datos.nss,
        "celular": _limpiar_celular(datos.celular), "correo": datos.correo,
        "tipo_sangre": datos.tipo_sangre, "alergias": datos.alergias,
        "promedio": datos.promedio,
    }
    parametros.update(
        zip(
            claves,
            (
                datos.nombre, datos.ap_paterno, datos.ap_materno, datos.fecha_nacimiento,
                _limpiar_celular(datos.celular_emergencia), datos.correo_emergencia,
                datos.preparatoria,
            ),
        )
    )
    return parametros | (adicionales or {})


def _parametros_domicilio(datos: AltaIn, numero_control: str) -> dict[str, object]:
    """Arma los parámetros del domicilio del alumno."""
    return {
        "numero": numero_control, "codigo_postal": datos.codigo_postal,
        "estado": datos.estado, "municipio": datos.municipio,
        "colonia": datos.colonia, "calle": datos.calle,
        "numero_exterior": datos.numero_exterior,
    }


def _consulta_domicilio(
    conn: Connection, numero_control: str, consulta: TextClause, clave_numero: str,
) -> MappingResult:
    """Ejecuta la consulta del domicilio con el bind requerido."""
    return conn.execute(consulta, {clave_numero: numero_control}).mappings()


















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
    """Lee el sufijo más alto entre alumnos y reinscripciones."""
    ultimo = conn.execute(
        text("""SELECT MAX(CAST(SUBSTRING(numero_control, 5, 4) AS UNSIGNED))
                FROM (
                    SELECT numero_control FROM alumnos
                    UNION ALL
                    SELECT numero_control FROM reinscripciones
                ) controles
                WHERE numero_control LIKE :patron AND CHAR_LENGTH(numero_control) = 8"""),
        {"patron": prefijo + "%"},
    ).scalar_one()
    return int(ultimo) if ultimo is not None else None


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
        domicilio = _consulta_domicilio(conn, a["numero_control"], _SQL_DOMICILIO_EXPEDIENTE, "n").first()

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
    try:
        with engine.begin() as conn:
            anterior = conn.execute(
                text("SELECT * FROM alumnos WHERE numero_control = :numero FOR UPDATE"),
                {"numero": numero_control},
            ).mappings().first()
            if anterior is None or anterior["eliminado"]:
                raise NoEncontrado()
            domicilio_anterior = _consulta_domicilio(
                conn, numero_control, _SQL_DOMICILIO_MODIFICACION, "numero",
            ).first()
            if not _domicilio_catalogo_valido(conn, datos):
                raise Conflicto(
                    "La colonia no corresponde al código postal seleccionado",
                    {"colonia": "Selecciona una colonia del catálogo para ese código postal"},
                )

            duplicados_alumno = duplicados(
                conn, datos.ficha, datos.curp, datos.nss, datos.rfc or "", datos.ine or "",
                datos.correo, excluir_numero_control=numero_control,
            )
            errores_duplicados = _errores_duplicados(duplicados_alumno)
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
                _parametros_alumno(datos, numero_control, _CLAVES_PARAMETROS_MODIFICACION),
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
                _parametros_domicilio(datos, numero_control),
            )
            nuevo = conn.execute(
                text("SELECT * FROM alumnos WHERE numero_control = :numero"),
                {"numero": numero_control},
            ).mappings().one()
            domicilio_nuevo = _consulta_domicilio(
                conn, numero_control, _SQL_DOMICILIO_MODIFICACION, "numero",
            ).one()
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
        _liberar_cupos_inscripciones(conn, numero_control)
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
    with _administrar_candado_mysql_altas():
        carpeta: Path | None = None
        try:
            with engine.begin() as conn:
                dup = duplicados(
                    conn, d.ficha, d.curp, d.nss, d.rfc or "", d.ine or "", d.correo,
                )
                errores = _errores_duplicados(dup)
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
                    )"""),
                    _parametros_alumno(
                        d, numero, _CLAVES_PARAMETROS_ALTA,
                        {"correo_inst": correo_inst, "turno": turno, "sem": SEMESTRE_INGRESO},
                    ),
                )
                conn.execute(
                    text("""INSERT INTO domicilios
                                (numero_control, codigo_postal, estado, municipio, colonia, calle, numero_exterior)
                            VALUES
                                (:numero, :codigo_postal, :estado, :municipio, :colonia, :calle, :numero_exterior)"""),
                    _parametros_domicilio(d, numero),
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

from .services.docentes import (
    SEMANAS_EVALUACION,
    _inscripcion_docente_bloqueada,
    confirmar_calificacion_final_docente,
    guardar_calificacion_docente,
    listar_grupos_docente,
)

from .services.horarios import (
    _datos_paquete_horario,
    _resumen_paquetes_horario,
    actualizar_docente_grupo,
    asignar_paquete_horario,
    cargar_catalogo_horarios,
    detalle_paquete_horario,
    estado_horario_alumno,
    lista_alumnos_paquete,
    listar_docentes_activos,
    listar_paquetes_horario,
)

from .services.reinscripciones import (
    _grupos_paquete_reinscripcion,
    _liberar_cupos_inscripciones,
    asignar_paquete_reinscripcion,
    eliminar_reinscripcion,
    estado_reinscripcion_alumno,
    modificar_reinscripcion,
    obtener_reinscripcion,
    registrar_reinscripcion,
    validar_reinscripcion,
)
