"""Administra las cuentas iniciales de Secretaría y Administración.

    python -m backend.seed --correo secretaria@acapulco.tecnm.mx --nombres "María" --apellidos "López Pérez"
    python -m backend.seed --admin-correo administrador@acapulco.tecnm.mx

Es idempotente. Si el usuario ya existe, actualiza su nombre (personal_secretaria)
y contraseña (sirve para restablecerla). Carga los horarios publicados; los
docentes se vinculan a sus cuentas después.
"""
import argparse
import getpass
import sys

from sqlalchemy import text

from .config import engine
from .migraciones import aplicar_migraciones
from .constantes import (
    ROL_ADMINISTRADOR,
    ROL_SECRETARIA,
)
from .seguridad import hashear
from . import servicios

ROLES = [ROL_SECRETARIA, ROL_ADMINISTRADOR, "Docente", "Alumno"]

def pedir_password(usuario: str = "Secretaría") -> str:
    while True:
        p1 = getpass.getpass(f"Contraseña de {usuario} (mín. 10 caracteres): ")
        if len(p1) < 10:
            print("Demasiado corta.")
        elif p1 != getpass.getpass("Repítela: "):
            print("No coinciden.")
        else:
            return p1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--correo", help="correo para crear o actualizar Secretaría")
    ap.add_argument("--nombres", help="nombre(s) de Secretaría")
    ap.add_argument("--apellidos", help="apellidos de Secretaría")
    ap.add_argument("--password", help="si se omite, se pide por teclado")
    ap.add_argument("--admin-correo", help="crear o actualizar una cuenta Administrador independiente")
    ap.add_argument("--admin-password", help="si se omite, se pide por teclado")
    args = ap.parse_args()
    secretaria_datos = (args.correo, args.nombres, args.apellidos)
    if any(secretaria_datos) and not all(secretaria_datos):
        ap.error("--correo, --nombres y --apellidos deben indicarse juntos")
    if not args.correo and not args.admin_correo:
        ap.error("indica los datos de Secretaría o --admin-correo")
    password = None
    if args.correo:
        password = args.password or pedir_password()
        if len(password) < 10:
            sys.exit("La contraseña de Secretaría debe tener al menos 10 caracteres.")
    admin_password = None
    if args.admin_correo:
        admin_password = args.admin_password or pedir_password("Administración")
        if len(admin_password) < 10:
            sys.exit("La contraseña de Administración debe tener al menos 10 caracteres.")

    with engine.begin() as conn:
        aplicar_migraciones(conn)
        for rol in ROLES:
            conn.execute(text("INSERT IGNORE INTO roles (nombre_rol) VALUES (:r)"), {"r": rol})
        id_rol = {
            rol: conn.execute(
                text("SELECT id_rol FROM roles WHERE nombre_rol = :r"),
                {"r": rol},
            ).scalar_one()
            for rol in ROLES
        }

        id_secretaria_usuario = None
        if args.correo:
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
            if conn.execute(text("SELECT 1 FROM personal_secretaria WHERE id_usuario = :u"),
                            {"u": id_secretaria_usuario}).scalar():
                conn.execute(text("UPDATE personal_secretaria SET nombres = :n, apellidos = :a WHERE id_usuario = :u"),
                             {"n": args.nombres, "a": args.apellidos, "u": id_secretaria_usuario})
            else:
                conn.execute(text("INSERT INTO personal_secretaria (id_usuario, nombres, apellidos) VALUES (:u, :n, :a)"),
                             {"u": id_secretaria_usuario, "n": args.nombres, "a": args.apellidos})

        if args.admin_correo:
            admin_correo = args.admin_correo.strip().lower()
            admin_existente = conn.execute(
                text("SELECT id_usuario, id_rol FROM usuarios WHERE correo = :c"),
                {"c": admin_correo},
            ).mappings().first()
            if admin_existente and admin_existente["id_rol"] != id_rol[ROL_ADMINISTRADOR]:
                raise SystemExit(f"{admin_correo} ya existe con otro rol; no se cambió la cuenta.")
            if admin_existente:
                conn.execute(
                    text("UPDATE usuarios SET password = :p, estatus = 'Activo' WHERE id_usuario = :i"),
                    {"p": hashear(admin_password), "i": admin_existente["id_usuario"]},
                )
                print(f"Administrador actualizado: {admin_correo}")
            else:
                conn.execute(
                    text("INSERT INTO usuarios (correo, password, id_rol) VALUES (:c, :p, :r)"),
                    {"c": admin_correo, "p": hashear(admin_password), "r": id_rol[ROL_ADMINISTRADOR]},
                )
                print(f"Administrador creado: {admin_correo}")

        servicios.cargar_catalogo_horarios(conn)

if __name__ == "__main__":
    main()
