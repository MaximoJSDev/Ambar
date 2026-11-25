"""Servicios de paquetes, grupos y horarios."""

from sqlalchemy import bindparam, text

from ..catalogo_horarios import CATALOGO_HORARIOS, PERIODO_1ISC
from ..config import engine
from ..constantes import ROL_DOCENTE
from .common import Conflicto, CupoLleno, NoEncontrado, _formatear_hora, _inscribir_en_grupos

def cargar_catalogo_horarios(conn) -> None:
    turnos = {
        nombre: "Matutino" if int(nombre[-1]) % 2 else "Vespertino"
        for nombre in CATALOGO_HORARIOS
    }
    for nombre_paquete, materias in CATALOGO_HORARIOS.items():
        semestre = int(nombre_paquete[0])
        id_paquete = conn.execute(
            text("""SELECT id_paquete FROM paquetes_horario
                    WHERE nombre_paquete = :nombre AND semestre = :semestre
                    ORDER BY id_paquete LIMIT 1"""),
            {"nombre": nombre_paquete, "semestre": semestre},
        ).scalar_one_or_none()
        if id_paquete is None:
            id_paquete = conn.execute(
                text("""INSERT INTO paquetes_horario (nombre_paquete, semestre)
                        VALUES (:nombre, :semestre)"""),
                {"nombre": nombre_paquete, "semestre": semestre},
            ).lastrowid

        grupos_por_materia: dict[int, list[int]] = {}
        grupos_existentes = conn.execute(
            text("""SELECT id_grupo, id_materia FROM grupos
                    WHERE id_paquete = :paquete AND periodo_escolar = :periodo
                    ORDER BY id_grupo"""),
            {"paquete": id_paquete, "periodo": PERIODO_1ISC},
        ).mappings().all()
        for grupo in grupos_existentes:
            grupos_por_materia.setdefault(grupo["id_materia"], []).append(
                grupo["id_grupo"]
            )
        ocurrencias_por_materia: dict[int, int] = {}

        for nombre_materia, aula, creditos, docente, dias in materias:
            id_materia = conn.execute(
                text("""SELECT id_materia FROM materias
                        WHERE nombre_materia = :nombre AND semestre = :semestre
                        ORDER BY id_materia LIMIT 1"""),
                {"nombre": nombre_materia, "semestre": semestre},
            ).scalar_one_or_none()
            if id_materia is None:
                id_materia = conn.execute(
                    text("""INSERT INTO materias (nombre_materia, semestre)
                            VALUES (:nombre, :semestre)"""),
                    {"nombre": nombre_materia, "semestre": semestre},
                ).lastrowid

            ocurrencia = ocurrencias_por_materia.get(id_materia, 0)
            ocurrencias_por_materia[id_materia] = ocurrencia + 1
            grupos_materia = grupos_por_materia.setdefault(id_materia, [])
            if ocurrencia < len(grupos_materia):
                id_grupo = grupos_materia[ocurrencia]
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
            else:
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
                grupos_materia.append(id_grupo)

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
                           WHEN (a.numero_control IS NOT NULL
                                 AND a.estatus = 'Activo' AND a.eliminado = FALSE)
                             OR (r.numero_control IS NOT NULL AND r.eliminado = FALSE)
                           THEN i.numero_control END) AS alumnos,
                       MIN(g.turno) AS turno,
                       MIN(g.cupo_maximo) AS cupo_maximo,
                       MIN(g.cupo_disponible) AS lugares
                FROM paquetes_horario p
                JOIN grupos g ON g.id_paquete = p.id_paquete
                LEFT JOIN inscripciones_grupos i ON i.id_grupo = g.id_grupo
                LEFT JOIN alumnos a ON a.numero_control = i.numero_control
                LEFT JOIN reinscripciones r ON r.numero_control = i.numero_control
                WHERE g.periodo_escolar = :periodo
                  AND (:solo_catalogo = 0 OR p.nombre_paquete IN :nombres_catalogo)
                  AND (:semestre IS NULL OR p.semestre = :semestre)
                GROUP BY p.id_paquete, p.nombre_paquete, p.semestre, g.periodo_escolar
                ORDER BY p.nombre_paquete""").bindparams(
            bindparam("nombres_catalogo", expanding=True)
        ),
        {
            "periodo": periodo,
            "semestre": semestre,
            "solo_catalogo": solo_catalogo,
            "nombres_catalogo": tuple(CATALOGO_HORARIOS),
        },
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
                    FROM alumnos WHERE numero_control = :numero
                    UNION ALL
                    SELECT numero_control, nombre AS nombres, apellido_paterno,
                           apellido_materno, semestre AS semestre_actual,
                           'Activo' AS estatus, eliminado
                    FROM reinscripciones
                    WHERE numero_control = :numero AND eliminado = FALSE
                    LIMIT 1"""),
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
        if paquete is None or paquete["nombre_paquete"] not in CATALOGO_HORARIOS:
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
        if len(grupos) != len(CATALOGO_HORARIOS[paquete["nombre_paquete"]]):
            raise Conflicto("El paquete está incompleto y no puede asignarse.")
        if any(fila["cupo_disponible"] <= 0 for fila in grupos):
            raise CupoLleno("El paquete seleccionado ya no tiene cupo disponible.")

        _inscribir_en_grupos(conn, numero_control, (fila["id_grupo"] for fila in grupos))
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
            text("""SELECT DISTINCT i.numero_control,
                           COALESCE(a.nombres, r.nombre) AS nombres,
                           COALESCE(a.apellido_paterno, r.apellido_paterno) AS apellido_paterno,
                           COALESCE(a.apellido_materno, r.apellido_materno) AS apellido_materno,
                           a.correo_institucional
                    FROM inscripciones_grupos i
                    JOIN grupos g ON g.id_grupo = i.id_grupo
                    LEFT JOIN alumnos a ON a.numero_control = i.numero_control
                    LEFT JOIN reinscripciones r ON r.numero_control = i.numero_control
                    WHERE g.id_paquete = :paquete AND g.periodo_escolar = :periodo
                      AND ((a.numero_control IS NOT NULL AND a.estatus = 'Activo'
                            AND a.eliminado = FALSE)
                           OR (r.numero_control IS NOT NULL AND r.eliminado = FALSE))
                    ORDER BY apellido_paterno, apellido_materno, nombres,
                             i.numero_control"""),
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


def actualizar_docente_grupo(id_grupo: int, id_docente: int | None) -> dict:
    with engine.begin() as conn:
        grupo = conn.execute(
            text("""SELECT g.id_grupo, g.id_docente FROM grupos g
                    JOIN paquetes_horario p ON p.id_paquete = g.id_paquete
                    WHERE g.id_grupo = :grupo AND g.periodo_escolar = :periodo
                      AND p.nombre_paquete IN :nombres_catalogo
                    FOR UPDATE""").bindparams(
                bindparam("nombres_catalogo", expanding=True)
            ),
            {
                "grupo": id_grupo,
                "periodo": PERIODO_1ISC,
                "nombres_catalogo": tuple(CATALOGO_HORARIOS),
            },
        ).mappings().first()
        if grupo is None:
            raise NoEncontrado()
        if grupo["id_docente"] is not None and grupo["id_docente"] != id_docente:
            raise Conflicto("El maestro de esta materia ya está asignado y no se puede cambiar.")
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
