"""Datos iniciales: roles, usuario de Secretaría y grupos de primer semestre.

    python seed.py --correo secretaria@acapulco.tecnm.mx --nombres "María" --apellidos "López Pérez"

Es idempotente. Si el usuario ya existe, actualiza su nombre (personal_secretaria) y contraseña (sirve
para restablecerla). Las materias y los docentes son DE EJEMPLO: reemplázalos por
los reales; los grupos se crean para el periodo actual (o PERIODO_ESCOLAR).
"""
import argparse
import getpass
import sys

from sqlalchemy import text

from config import settings
from constantes import ROL_SECRETARIA, SEMESTRE_INGRESO, TURNOS
from db import engine
from seguridad import hashear

ROLES = [ROL_SECRETARIA, "Docente", "Alumno"]
MATERIAS_PRIMER_SEMESTRE = [        # EJEMPLO
    "Cálculo Diferencial", "Fundamentos de Programación", "Química",
    "Fundamentos de Investigación", "Taller de Ética",
]
PAQUETES = [("1A", TURNOS[0]), ("1B", TURNOS[1])]       # (nombre del grupo, turno)
CUPO = 25


def pedir_password() -> str:
    while True:
        p1 = getpass.getpass("Contraseña de Secretaría (mín. 10 caracteres): ")
        if len(p1) < 10:
            print("Demasiado corta.")
        elif p1 != getpass.getpass("Repítela: "):
            print("No coinciden.")
        else:
            return p1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--correo", required=True)
    ap.add_argument("--nombres", required=True)
    ap.add_argument("--apellidos", required=True)
    ap.add_argument("--password", help="si se omite, se pide por teclado")
    args = ap.parse_args()
    password = args.password or pedir_password()
    if len(password) < 10:
        sys.exit("La contraseña debe tener al menos 10 caracteres.")

    with engine.begin() as conn:
        for rol in ROLES:
            conn.execute(text("INSERT IGNORE INTO roles (nombre_rol) VALUES (:r)"), {"r": rol})
        id_rol = {r: i for i, r in conn.execute(text("SELECT id_rol, nombre_rol FROM roles")).all()}

        correo = args.correo.strip().lower()
        existente = conn.execute(text("SELECT id_usuario FROM usuarios WHERE correo = :c"), {"c": correo}).scalar()
        if existente:
            conn.execute(text("UPDATE usuarios SET password = :p, estatus = 'Activo' WHERE id_usuario = :i"),
                         {"p": hashear(password), "i": existente})
            id_secretaria_usuario = existente
            print(f"Usuario actualizado: {correo}")
        else:
            id_secretaria_usuario = conn.execute(
                text("INSERT INTO usuarios (correo, password, id_rol) VALUES (:c, :p, :r)"),
                {"c": correo, "p": hashear(password), "r": id_rol[ROL_SECRETARIA]}).lastrowid
            print(f"Usuario creado: {correo}")
        # El nombre que muestra la app sale de personal_secretaria
        if conn.execute(text("SELECT 1 FROM personal_secretaria WHERE id_usuario = :u"),
                        {"u": id_secretaria_usuario}).scalar():
            conn.execute(text("UPDATE personal_secretaria SET nombres = :n, apellidos = :a WHERE id_usuario = :u"),
                         {"n": args.nombres, "a": args.apellidos, "u": id_secretaria_usuario})
        else:
            conn.execute(text("INSERT INTO personal_secretaria (id_usuario, nombres, apellidos) VALUES (:u, :n, :a)"),
                         {"u": id_secretaria_usuario, "n": args.nombres, "a": args.apellidos})

        id_materias = []
        for nombre in MATERIAS_PRIMER_SEMESTRE:
            id_m = conn.execute(text("SELECT id_materia FROM materias WHERE nombre_materia = :n AND semestre = :s"),
                                {"n": nombre, "s": SEMESTRE_INGRESO}).scalar()
            if id_m is None:
                id_m = conn.execute(text("INSERT INTO materias (nombre_materia, semestre) VALUES (:n, :s)"),
                                    {"n": nombre, "s": SEMESTRE_INGRESO}).lastrowid
            id_materias.append(id_m)

        creados = 0
        for nombre_paquete, turno in PAQUETES:
            id_p = conn.execute(text("SELECT id_paquete FROM paquetes_horario WHERE nombre_paquete = :n AND semestre = :s"),
                                {"n": nombre_paquete, "s": SEMESTRE_INGRESO}).scalar()
            if id_p is None:
                id_p = conn.execute(text("INSERT INTO paquetes_horario (nombre_paquete, semestre) VALUES (:n, :s)"),
                                    {"n": nombre_paquete, "s": SEMESTRE_INGRESO}).lastrowid
            for id_m in id_materias:
                ya = conn.execute(
                    text("SELECT 1 FROM grupos WHERE id_paquete = :p AND id_materia = :m AND periodo_escolar = :per"),
                    {"p": id_p, "m": id_m, "per": settings.periodo}).scalar()
                if not ya:
                    conn.execute(
                        text("""INSERT INTO grupos (id_paquete, id_materia, id_docente, periodo_escolar, turno,
                                                    cupo_maximo, cupo_disponible)
                                VALUES (:p, :m, :d, :per, :t, :c, :c)"""),
                        {"p": id_p, "m": id_m, "d": None, "per": settings.periodo, "t": turno, "c": CUPO})
                    creados += 1
        print(f"Periodo {settings.periodo}: {creados} grupos nuevos de primer semestre.")


if __name__ == "__main__":
    main()
