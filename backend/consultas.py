"""Consulta del expediente de un alumno (datos, estado de documentos y descarga de PDF)."""
from pathlib import Path

from sqlalchemy import text

from ambar_common import validators as v

from .config import settings
from .constantes import DOCUMENTOS
from .db import engine

# Documentos que muestra el expediente: los 6 que se cargan en Altas + la constancia fiscal
# (existe en el ENUM de la BD, pero Altas todavía no la pide).
# (nombre visible, valor del ENUM tipo_documento)
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


def buscar_expediente(q: str) -> dict:
    """Busca por número de control o CURP (exactos)."""
    q = q.strip()
    with engine.connect() as conn:
        a = conn.execute(
            text("SELECT * FROM alumnos WHERE numero_control = :q OR curp = :cu LIMIT 1"),
            {"q": q, "cu": q.upper()},
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
        # Grupo vigente = el de la inscripción más reciente
        grupo = conn.execute(
            text("""SELECT p.nombre_paquete AS grupo, g.periodo_escolar AS periodo
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE i.numero_control = :n
                    ORDER BY i.id_inscripcion DESC LIMIT 1"""),
            {"n": a["numero_control"]},
        ).mappings().first()

    nombre = " ".join(p for p in (a["nombres"], a["apellido_paterno"], a["apellido_materno"]) if p)
    return {
        "numero_control": a["numero_control"],
        "nombre_completo": nombre,
        "semestre_actual": a["semestre_actual"],
        "estatus": a["estatus"],
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
            "domicilio": a["domicilio"],
            "celular": a["celular"],
            "correo_personal": a["correo_personal"],
            "correo_institucional": a["correo_institucional"] or "—",
            "celular_emergencia": a["celular_emergencia"],
            "correo_emergencia": a["correo_emergencia"] or "—",
            "alergias": a["alergias"] or "Ninguna",
        },
        "academicos": {
            "numero_ficha": a["numero_ficha"],
            "preparatoria": a["preparatoria_procedencia"],
            "promedio": f"{a['promedio_preparatoria']:.2f}",
            "turno": a["turno"],
            "semestre": str(a["semestre_actual"]),
            "grupo": grupo["grupo"] if grupo else "Sin grupo",
            "periodo": grupo["periodo"] if grupo else "—",
            "estatus": a["estatus"],
            **({"motivo_baja": a["motivo_baja"]} if a["motivo_baja"] else {}),
        },
        "documentos": [
            {"documento": visible, "id_documento": docs.get(tipo_bd),
             "estado": "Recibido" if tipo_bd in docs else "Pendiente"}
            for visible, tipo_bd in TIPOS_EXPEDIENTE
        ],
    }


def ruta_documento(id_documento: int) -> tuple[Path, str]:
    """(ruta absoluta del PDF, nombre sugerido). La BD guarda la ruta relativa a STORAGE_DIR."""
    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT numero_control, tipo_documento, ruta_archivo FROM expedientes_digitales WHERE id_documento = :i"),
            {"i": id_documento},
        ).mappings().first()
    if fila is None:
        raise NoEncontrado()
    base = settings.storage_dir
    ruta = (base / fila["ruta_archivo"]).resolve()
    # Evita salir de la carpeta de expedientes aunque la BD contenga una ruta manipulada
    if not ruta.is_relative_to(base) or not ruta.is_file():
        raise NoEncontrado()
    return ruta, f"{fila['numero_control']}_{ruta.name}"
