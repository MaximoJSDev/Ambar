"""Carga inicial de cuentas docentes y asignaciones del horario publicado."""
import csv
import logging
import os
from pathlib import Path
import re
import secrets
import unicodedata
from collections import Counter, defaultdict

from sqlalchemy import bindparam, text

from .catalogo_horarios import CATALOGO_HORARIOS, PERIODO_1ISC
from .config import engine, settings
from .constantes import ROL_DOCENTE
from .esquemas import DocenteCreate
from .seguridad import hashear

log = logging.getLogger("sige")

_VERSION = "2026_11_04_docentes_horario"
_SIN_ASIGNACION = {
    ("7ISC1", "Carolina Astudillo Hernández", "Gestión de Proyectos de Software"),
}
_DIAS = ("", "lunes", "martes", "miércoles", "jueves", "viernes")


def _normalizar_nombre(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto.casefold()).split())


def _identidades_horario() -> dict[str, str]:
    return {
        _normalizar_nombre(fila[3]): fila[3]
        for materias in CATALOGO_HORARIOS.values()
        for fila in materias
        if fila[3] and fila[3].strip()
    }


def _datos_cuenta(nombre_completo: str) -> DocenteCreate:
    partes = nombre_completo.split()
    if len(partes) < 2:
        raise RuntimeError(f"No se puede separar el nombre del docente: {nombre_completo}")
    nombres = partes[0]
    apellidos = " ".join(partes[1:]).replace(".", "")
    base = ".".join(_normalizar_nombre(nombre_completo).split())
    dominio = settings.dominio_institucional
    correo = f"{base}@{dominio}"
    password = secrets.token_urlsafe(24)
    return DocenteCreate(
        nombres=nombres,
        apellidos=apellidos,
        correo=correo,
        password=password,
    )


def _crear_archivo_credenciales(cuentas: list[tuple[DocenteCreate, str]]) -> Path:
    directorio = Path.home() / ".ambar" / "credenciales"
    directorio.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directorio.chmod(0o700)

    ruta = directorio / f"maestros-{secrets.token_hex(8)}.csv"
    try:
        with ruta.open("x", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(("Nombres", "Apellidos", "Correo de acceso", "Contraseña inicial"))
            for datos, password in cuentas:
                escritor.writerow((datos.nombres, datos.apellidos, datos.correo, password))
            archivo.flush()
            os.fsync(archivo.fileno())
        if os.name != "nt":
            ruta.chmod(0o600)
        return ruta
    except Exception:
        ruta.unlink(missing_ok=True)
        raise


def _planificar_asignaciones(
    grupos: list[dict],
    docente_por_nombre: dict[str, int],
) -> dict[int, int | None]:
    sin_asignacion = {
        (paquete, _normalizar_nombre(docente), _normalizar_nombre(materia))
        for paquete, docente, materia in _SIN_ASIGNACION
    }
    resultado = {}
    for grupo in grupos:
        nombre = (grupo["docente_programado"] or "").strip()
        if not nombre:
            resultado[grupo["id_grupo"]] = None
            continue
        clave = _normalizar_nombre(nombre)
        materia = _normalizar_nombre(grupo["nombre_materia"])
        if (grupo["nombre_paquete"], clave, materia) in sin_asignacion:
            resultado[grupo["id_grupo"]] = None
            continue
        if clave not in docente_por_nombre:
            raise RuntimeError(f"No hay cuenta activa para el docente programado {nombre}.")
        resultado[grupo["id_grupo"]] = docente_por_nombre[clave]
    return resultado


def _validar_traslapes(grupos: list[dict], asignaciones: dict[int, int | None]) -> None:
    horarios: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for grupo in grupos:
        id_docente = asignaciones.get(grupo["id_grupo"], grupo["id_docente"])
        if id_docente is None or grupo["dia_semana"] is None:
            continue
        inicio = str(grupo["hora_inicio"])[:5]
        fin = str(grupo["hora_fin"])[:5]
        for existente in horarios[(id_docente, grupo["dia_semana"])]:
            if inicio < existente["fin"] and existente["inicio"] < fin:
                dia = _DIAS[grupo["dia_semana"]]
                raise RuntimeError(
                    f"El horario asignaría al mismo docente dos materias traslapadas "
                    f"el {dia}: «{existente['materia']}» y «{grupo['nombre_materia']}»."
                )
        horarios[(id_docente, grupo["dia_semana"])].append({
            "inicio": inicio,
            "fin": fin,
            "materia": grupo["nombre_materia"],
        })


def sincronizar_docentes_horario() -> None:
    """Crea las cuentas faltantes y asigna el horario publicado solo una vez."""
    identidades = _identidades_horario()
    ruta_credenciales = None
    try:
        with engine.begin() as conn:
            if conn.execute(
                text("SELECT version FROM ambar_schema_migrations WHERE version = :version"),
                {"version": _VERSION},
            ).scalar_one_or_none() is not None:
                return

            conn.execute(
                text("INSERT IGNORE INTO roles (nombre_rol) VALUES (:rol)"),
                {"rol": ROL_DOCENTE},
            )
            id_rol = conn.execute(
                text("SELECT id_rol FROM roles WHERE nombre_rol = :rol"),
                {"rol": ROL_DOCENTE},
            ).scalar_one_or_none()
            if id_rol is None:
                raise RuntimeError("No está configurado el rol Docente.")

            existentes = conn.execute(text("""SELECT d.id_docente, d.nombres, d.apellidos,
                    u.correo, u.estatus
                FROM empleados_docentes d
                JOIN usuarios u ON u.id_usuario = d.id_usuario
                JOIN roles r ON r.id_rol = u.id_rol
                WHERE r.nombre_rol = :rol
                FOR UPDATE"""), {"rol": ROL_DOCENTE}).mappings().all()
            por_nombre: dict[str, list[dict]] = defaultdict(list)
            for docente in existentes:
                por_nombre[_normalizar_nombre(
                    f"{docente['nombres']} {docente['apellidos']}"
                )].append(dict(docente))
            correos = {
                correo.casefold()
                for correo in conn.execute(text("SELECT correo FROM usuarios")).scalars()
            }

            docente_por_nombre: dict[str, int] = {}
            cuentas_nuevas: list[tuple[str, DocenteCreate, str]] = []
            for clave, nombre in identidades.items():
                coincidencias = por_nombre.get(clave, [])
                activas = [fila for fila in coincidencias if fila["estatus"] == "Activo"]
                if len(activas) > 1:
                    raise RuntimeError(
                        f"Hay varias cuentas activas para {nombre}; no se sincronizó el horario."
                    )
                if activas:
                    docente_por_nombre[clave] = activas[0]["id_docente"]
                    continue
                if coincidencias:
                    raise RuntimeError(
                        f"Solo hay cuentas inactivas para {nombre}; "
                        "reactívalas o corrige el registro antes de sincronizar."
                    )

                datos = _datos_cuenta(nombre)
                base, dominio = datos.correo.rsplit("@", 1)
                correo = datos.correo
                sufijo = 2
                while correo.casefold() in correos:
                    correo = f"{base}.{sufijo}@{dominio}"
                    sufijo += 1
                if correo != datos.correo:
                    datos = datos.model_copy(update={"correo": correo})
                correos.add(correo.casefold())
                cuentas_nuevas.append((clave, datos, datos.password))

            grupos = conn.execute(text("""SELECT g.id_grupo, g.id_docente,
                    g.docente_programado, p.nombre_paquete, m.nombre_materia
                FROM grupos g
                JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                JOIN materias m ON m.id_materia = g.id_materia
                WHERE g.periodo_escolar = :periodo
                  AND p.nombre_paquete IN :paquetes
                ORDER BY p.semestre, p.nombre_paquete, g.id_grupo
                FOR UPDATE""").bindparams(bindparam("paquetes", expanding=True)), {
                    "periodo": PERIODO_1ISC,
                    "paquetes": tuple(CATALOGO_HORARIOS),
                }).mappings().all()
            grupos = [dict(grupo) for grupo in grupos]
            por_grupo = {grupo["id_grupo"]: grupo for grupo in grupos}
            esperados = Counter(
                (paquete, fila[0], _normalizar_nombre(fila[3]))
                for paquete, filas in CATALOGO_HORARIOS.items()
                for fila in filas
            )
            actuales = Counter(
                (grupo["nombre_paquete"], grupo["nombre_materia"],
                 _normalizar_nombre(grupo["docente_programado"]))
                for grupo in por_grupo.values()
            )
            if len(por_grupo) != sum(map(len, CATALOGO_HORARIOS.values())) or esperados != actuales:
                raise RuntimeError(
                    "Los paquetes del horario publicado no están completos en la base de datos."
                )

            for clave, datos, password in cuentas_nuevas:
                id_usuario = conn.execute(
                    text("""INSERT INTO usuarios (correo, password, id_rol, estatus)
                            VALUES (:correo, :password, :rol, 'Activo')"""),
                    {
                        "correo": datos.correo,
                        "password": hashear(password),
                        "rol": id_rol,
                    },
                ).lastrowid
                id_docente = conn.execute(
                    text("""INSERT INTO empleados_docentes (id_usuario, nombres, apellidos)
                            VALUES (:usuario, :nombres, :apellidos)"""),
                    {
                        "usuario": id_usuario,
                        "nombres": datos.nombres,
                        "apellidos": datos.apellidos,
                    },
                ).lastrowid
                docente_por_nombre[clave] = id_docente

            asignaciones = _planificar_asignaciones(grupos, docente_por_nombre)
            grupos_con_horario = conn.execute(text("""SELECT g.id_grupo, g.id_docente,
                    CAST(h.hora_inicio AS CHAR) AS hora_inicio,
                    CAST(h.hora_fin AS CHAR) AS hora_fin,
                    h.dia_semana, m.nombre_materia
                FROM grupos g
                JOIN materias m ON m.id_materia = g.id_materia
                LEFT JOIN horarios_grupo h ON h.id_grupo = g.id_grupo
                WHERE g.periodo_escolar = :periodo
                FOR UPDATE"""), {"periodo": PERIODO_1ISC}).mappings().all()
            _validar_traslapes([dict(fila) for fila in grupos_con_horario], asignaciones)

            nuevas = [(datos, password) for _, datos, password in cuentas_nuevas]
            if nuevas:
                ruta_credenciales = _crear_archivo_credenciales(nuevas)

            for id_grupo, id_docente in asignaciones.items():
                if por_grupo[id_grupo]["id_docente"] != id_docente:
                    resultado = conn.execute(
                        text("UPDATE grupos SET id_docente = :docente WHERE id_grupo = :grupo"),
                        {"docente": id_docente, "grupo": id_grupo},
                    )
                    if resultado.rowcount != 1:
                        raise RuntimeError(f"No se pudo actualizar la asignación del grupo {id_grupo}.")

            conn.execute(
                text("INSERT INTO ambar_schema_migrations (version) VALUES (:version)"),
                {"version": _VERSION},
            )
    except Exception:
        if ruta_credenciales is not None:
            ruta_credenciales.unlink(missing_ok=True)
        raise

    log.info(
        "Sincronización inicial de horarios aplicada: %s docentes; %s cuentas nuevas.",
        len(identidades),
        len(cuentas_nuevas),
    )
    if ruta_credenciales is not None:
        log.warning("Contraseñas iniciales de docentes guardadas en %s", ruta_credenciales)
