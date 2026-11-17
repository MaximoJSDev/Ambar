"""Operaciones del ciclo de reinscripción."""

import re

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from ambar_common import validators as v

from ..catalogo_horarios import CATALOGO_HORARIOS, PERIODO_1ISC
from ..config import engine, settings
from .common import (
    Conflicto,
    CupoLleno,
    NoEncontrado,
    NumeroControlDuplicado,
    _administrar_candado_mysql_altas,
)
from .horarios import _datos_paquete_horario, _resumen_paquetes_horario

def validar_reinscripcion(datos: dict) -> dict[str, str]:
    errores: dict[str, str] = {}
    numero = datos["numero_control"]
    nombre = datos["nombre"]
    apellido_paterno = datos["apellido_paterno"]
    apellido_materno = datos["apellido_materno"]
    semestre = datos["semestre"]

    if not re.fullmatch(r"\d{8}", numero):
        errores["numero_control"] = "Debe contener exactamente 8 dígitos"
    if error := v.validar_nombre_personal(nombre, "Nombre", maximo=50):
        errores["nombre"] = error
    if error := v.validar_nombre_personal(
        apellido_paterno, "Apellido paterno", maximo=50,
    ):
        errores["apellido_paterno"] = error
    if error := v.validar_nombre_personal(
        apellido_materno, "Apellido materno", maximo=50,
    ):
        errores["apellido_materno"] = error
    if semestre not in (2, 3):
        errores["semestre"] = "Selecciona segundo o tercer semestre"
    elif "numero_control" not in errores and re.fullmatch(r"\d{8}", numero):
        anio_esperado = "26" if semestre == 2 else "25"
        if not numero.startswith(anio_esperado):
            anio = "2026" if semestre == 2 else "2025"
            errores["numero_control"] = (
                f"Para {semestre}° semestre, el número de control debe corresponder al año {anio}"
            )
        elif error := v.validar_periodo_numero_control(numero, semestre):
            errores["numero_control"] = error
    return errores


def registrar_reinscripcion(datos: dict) -> dict:
    datos = {**datos, "numero_control": datos["numero_control"].strip()}
    errores = validar_reinscripcion(datos)
    if type(datos.get("id_paquete")) is not int or datos["id_paquete"] <= 0:
        errores["id_paquete"] = "Selecciona un paquete con lugares disponibles"
    if errores:
        raise Conflicto("Revisa los datos capturados", errores)

    with _administrar_candado_mysql_altas():
        try:
            with engine.begin() as conn:
                alumno = conn.execute(
                    text("SELECT 1 FROM alumnos WHERE numero_control = :numero"),
                    {"numero": datos["numero_control"]},
                ).scalar_one_or_none()
                reinscripcion = conn.execute(
                    text("SELECT 1 FROM reinscripciones WHERE numero_control = :numero"),
                    {"numero": datos["numero_control"]},
                ).scalar_one_or_none()
                if alumno is not None or reinscripcion is not None:
                    raise NumeroControlDuplicado(
                        "El número de control ya existe",
                        {"numero_control": "El número de control ya existe"},
                    )
                grupos_paquete = _grupos_paquete_reinscripcion(
                    conn, datos["semestre"], datos["id_paquete"],
                )
                conn.execute(
                    text("""INSERT INTO reinscripciones
                                (numero_control, nombre, apellido_paterno,
                                 apellido_materno, semestre)
                            VALUES (:numero_control, :nombre, :apellido_paterno,
                                    :apellido_materno, :semestre)"""),
                    {
                        "numero_control": datos["numero_control"],
                        "nombre": datos["nombre"],
                        "apellido_paterno": datos["apellido_paterno"],
                        "apellido_materno": datos["apellido_materno"],
                        "semestre": datos["semestre"],
                    },
                )
                conn.execute(
                    text("""INSERT INTO inscripciones_grupos (numero_control, id_grupo)
                            VALUES (:numero, :grupo)"""),
                    [
                        {"numero": datos["numero_control"], "grupo": grupo["id_grupo"]}
                        for grupo in grupos_paquete
                    ],
                )
        except IntegrityError as ex:
            raise NumeroControlDuplicado(
                "El número de control ya existe",
                {"numero_control": "El número de control ya existe"},
            ) from ex

    return datos | {"paquete": grupos_paquete[0]["nombre_paquete"]}


def _grupos_paquete_reinscripcion(
    conn, semestre: int, id_paquete: int | None = None,
) -> list[dict]:
    filas = conn.execute(
        text("""SELECT p.nombre_paquete, g.id_grupo, g.cupo_disponible
                FROM paquetes_horario p
                JOIN grupos g ON g.id_paquete = p.id_paquete
                WHERE p.semestre = :semestre
                  AND p.nombre_paquete IN :nombres_catalogo
                  AND g.periodo_escolar = :periodo
                  AND (:id_paquete IS NULL OR p.id_paquete = :id_paquete)
                ORDER BY p.nombre_paquete, g.id_grupo
                FOR UPDATE""").bindparams(bindparam("nombres_catalogo", expanding=True)),
        {
            "semestre": semestre,
            "id_paquete": id_paquete,
            "nombres_catalogo": tuple(CATALOGO_HORARIOS),
            "periodo": PERIODO_1ISC,
        },
    ).mappings().all()
    paquetes: dict[str, list[dict]] = {}
    for fila in filas:
        paquetes.setdefault(fila["nombre_paquete"], []).append(dict(fila))

    for nombre in sorted(paquetes):
        grupos = paquetes[nombre]
        if (
            len(grupos) == len(CATALOGO_HORARIOS[nombre])
            and all(grupo["cupo_disponible"] > 0 for grupo in grupos)
        ):
            return grupos
    if id_paquete is not None:
        raise Conflicto(
            "El paquete seleccionado no está disponible o no tiene cupo en todas sus materias.",
            {"id_paquete": "Selecciona un paquete completo con lugares disponibles"},
        )
    raise CupoLleno(
        f"No hay un paquete completo con cupo disponible para {semestre}° semestre."
    )


def obtener_reinscripcion(numero_control: str) -> dict:
    with engine.connect() as conn:
        fila = conn.execute(
            text("""SELECT DISTINCT r.numero_control, r.nombre, r.apellido_paterno,
                           r.apellido_materno, r.semestre,
                           r.eliminado, r.baja_en, r.baja_id_usuario,
                           p.id_paquete, p.nombre_paquete AS paquete
                    FROM reinscripciones r
                    LEFT JOIN inscripciones_grupos i ON i.numero_control = r.numero_control
                    LEFT JOIN grupos g ON g.id_grupo = i.id_grupo
                    LEFT JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE r.numero_control = :numero"""),
            {"numero": numero_control.strip()},
        ).mappings().first()
    if fila is None:
        raise NoEncontrado()
    return dict(fila)


def _liberar_cupos_inscripciones(conn, numero_control: str) -> None:
    grupos = conn.execute(
        text("""SELECT id_grupo FROM inscripciones_grupos
                WHERE numero_control = :numero
                ORDER BY id_grupo FOR UPDATE"""),
        {"numero": numero_control},
    ).mappings().all()
    for grupo in grupos:
        conn.execute(
            text("""UPDATE grupos
                    SET cupo_disponible = LEAST(cupo_maximo, cupo_disponible + 1)
                    WHERE id_grupo = :grupo"""),
            {"grupo": grupo["id_grupo"]},
        )


def eliminar_reinscripcion(numero_control: str, id_usuario: int) -> dict:
    with engine.begin() as conn:
        fila = conn.execute(
            text("""SELECT numero_control, eliminado FROM reinscripciones
                    WHERE numero_control = :numero FOR UPDATE"""),
            {"numero": numero_control.strip()},
        ).mappings().first()
        if fila is None:
            raise NoEncontrado()
        if fila["eliminado"]:
            raise Conflicto("La reinscripción ya se encuentra dada de baja.")
        conn.execute(
            text("""UPDATE reinscripciones
                    SET eliminado = TRUE, baja_en = CURRENT_TIMESTAMP,
                        baja_id_usuario = :usuario
                    WHERE numero_control = :numero"""),
            {"usuario": id_usuario, "numero": fila["numero_control"]},
        )
        _liberar_cupos_inscripciones(conn, fila["numero_control"])
    return {
        "numero_control": fila["numero_control"],
        "eliminado": True,
    }


def modificar_reinscripcion(numero_original: str, datos: dict) -> dict:
    numero_original = numero_original.strip()
    datos = {**datos, "numero_control": datos["numero_control"].strip()}
    errores = validar_reinscripcion(datos)
    if errores:
        raise Conflicto("Revisa los datos capturados", errores)

    with _administrar_candado_mysql_altas():
        try:
            with engine.begin() as conn:
                anterior = conn.execute(
                    text("""SELECT numero_control, semestre, eliminado FROM reinscripciones
                            WHERE numero_control = :numero FOR UPDATE"""),
                    {"numero": numero_original},
                ).mappings().first()
                if anterior is None:
                    raise NoEncontrado()
                if anterior["eliminado"]:
                    raise Conflicto("No se puede modificar una reinscripción dada de baja.")
                if numero_original != datos["numero_control"]:
                    raise Conflicto(
                        "No se puede modificar el número de control de una reinscripción.",
                        {"numero_control": "El número de control no se puede modificar"},
                    )
                duplicado = conn.execute(
                    text("""SELECT 1 FROM alumnos WHERE numero_control = :numero
                            UNION ALL
                            SELECT 1 FROM reinscripciones
                            WHERE numero_control = :numero AND numero_control != :original
                            LIMIT 1"""),
                    {"numero": datos["numero_control"], "original": numero_original},
                ).scalar_one_or_none()
                if duplicado is not None:
                    raise NumeroControlDuplicado(
                        "El número de control ya existe",
                        {"numero_control": "El número de control ya existe"},
                    )
                estado_horario = conn.execute(
                    text("""SELECT COUNT(DISTINCT i.id_inscripcion) AS inscripciones,
                                   COUNT(c.id_calificacion) AS calificaciones
                            FROM inscripciones_grupos i
                            LEFT JOIN calificaciones c ON c.id_inscripcion = i.id_inscripcion
                            WHERE i.numero_control = :numero"""),
                    {"numero": numero_original},
                ).mappings().one()
                id_paquete = datos.get("id_paquete")
                paquetes_actuales = []
                if id_paquete is not None:
                    paquetes_actuales = conn.execute(
                        text("""SELECT DISTINCT p.id_paquete
                                FROM inscripciones_grupos i
                                JOIN grupos g ON g.id_grupo = i.id_grupo
                                JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                                WHERE i.numero_control = :numero
                                  AND g.periodo_escolar = :periodo
                                FOR UPDATE"""),
                        {"numero": numero_original, "periodo": PERIODO_1ISC},
                    ).scalars().all()
                if len(paquetes_actuales) > 1:
                    raise Conflicto(
                        "La reinscripción aparece asignada a más de un paquete.",
                    )
                paquete_actual = paquetes_actuales[0] if paquetes_actuales else None
                cambio_semestre = anterior["semestre"] != datos["semestre"]
                cambio_paquete = (
                    id_paquete is not None and id_paquete != paquete_actual
                )
                cambio_asignacion = cambio_semestre or cambio_paquete
                if cambio_asignacion and estado_horario["calificaciones"]:
                    raise Conflicto(
                        "No se puede cambiar el semestre o el paquete porque ya tiene calificaciones registradas.",
                        {"id_paquete": "No se puede cambiar después de registrar calificaciones"},
                    )
                if cambio_asignacion:
                    grupos = _grupos_paquete_reinscripcion(
                        conn, datos["semestre"], id_paquete,
                    )
                    if estado_horario["inscripciones"]:
                        conn.execute(
                            text("DELETE FROM inscripciones_grupos WHERE numero_control = :numero"),
                            {"numero": numero_original},
                        )
                else:
                    grupos = []
                conn.execute(
                    text("""UPDATE reinscripciones
                            SET numero_control = :numero, nombre = :nombre,
                                apellido_paterno = :apellido_paterno,
                                apellido_materno = :apellido_materno,
                                semestre = :semestre
                            WHERE numero_control = :original"""),
                    {
                        "numero": datos["numero_control"],
                        "nombre": datos["nombre"],
                        "apellido_paterno": datos["apellido_paterno"],
                        "apellido_materno": datos["apellido_materno"],
                        "semestre": datos["semestre"],
                        "original": numero_original,
                    },
                )
                if grupos:
                    conn.execute(
                        text("""INSERT INTO inscripciones_grupos (numero_control, id_grupo)
                                VALUES (:numero, :grupo)"""),
                        [
                            {"numero": datos["numero_control"], "grupo": grupo["id_grupo"]}
                            for grupo in grupos
                        ],
                    )
        except IntegrityError as ex:
            raise NumeroControlDuplicado(
                "El número de control ya existe",
                {"numero_control": "El número de control ya existe"},
            ) from ex
    return datos


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
                "La reinscripciÃ³n estÃ¡ disponible Ãºnicamente para alumnos de semestres 2 a 10."
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
