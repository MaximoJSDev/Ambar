"""Datos iniciales: roles, usuario de Secretaría y catálogo de primer semestre.

    python -m backend.seed --correo secretaria@acapulco.tecnm.mx --nombres "María" --apellidos "López Pérez"
    python -m backend.seed --admin-correo administrador@acapulco.tecnm.mx
    python -m backend.seed --correo secretaria2@acapulco.tecnm.mx --nombres "Anna" --apellidos "Herrera Escobar"
    python -m backend.seed --correo secretaria3@acapulco.tecnm.mx --nombres "Emmanuel" --apellidos "Garnica Saida"

Es idempotente. Si el usuario ya existe, actualiza su nombre (personal_secretaria)
y contraseña (sirve para restablecerla). Carga el horario publicado de 1ISC1 a
1ISC7 para agosto-diciembre de 2026; los docentes se vinculan a sus cuentas después.
"""
import argparse
import datetime
import getpass
import sys
import unicodedata

from sqlalchemy import text

from ambar_common import validators as v

from .config import engine, settings
from .constantes import (
    ROL_ADMINISTRADOR,
    ROL_SECRETARIA,
)
from .esquemas import AltaIn
from .seguridad import hashear
from . import servicios

ROLES = [ROL_SECRETARIA, ROL_ADMINISTRADOR, "Docente", "Alumno"]

ALUMNOS_DEMO = [
    ("Ana Sofia", "Gonzalez", "Ramirez"),
    ("Diego", "Lopez", "Sanchez"),
    ("Valeria", "Martinez", "Cruz"),
    ("Mateo", "Hernandez", "Flores"),
    ("Camila", "Perez", "Reyes"),
    ("Santiago", "Garcia", "Morales"),
    ("Regina", "Torres", "Vargas"),
    ("Sebastian", "Diaz", "Castillo"),
    ("Ximena", "Romero", "Ortega"),
    ("Emiliano", "Mendoza", "Rojas"),
]


def _ascii(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().upper()


def _datos_alumno_demo(indice: int) -> AltaIn:
    nombre, paterno, materno = ALUMNOS_DEMO[(indice - 1) % len(ALUMNOS_DEMO)]
    hoy = datetime.date.today()
    fecha = datetime.date(hoy.year - 18, (indice - 1) % 12 + 1, (indice - 1) % 28 + 1)
    yymmdd = fecha.strftime("%y%m%d")

    iniciales = v.prefijo_curp_apellidos(paterno, materno) + _ascii(nombre)[:1]
    consonantes = "".join(letra for letra in _ascii(paterno + materno + nombre) if letra not in "AEIOU")[:3]
    consonantes = (consonantes + "XXX")[:3]
    alfanumerico = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[(indice - 1) % 36]
    genero = "mujer" if indice % 2 else "hombre"
    sexo = "M" if genero == "mujer" else "H"
    ficha = f"9999-{indice:05d}"
    curp = f"{iniciales}{yymmdd}{sexo}AS{consonantes}{alfanumerico}{indice % 10}"
    ine = f"{(_ascii(paterno + materno + nombre) + 'XXXXXX')[:6]}{yymmdd}12{sexo}{indice % 1000:03d}"

    return AltaIn(
        ficha=ficha,
        nombre=nombre,
        ap_paterno=paterno,
        ap_materno=materno,
        fecha_nacimiento=fecha,
        curp=curp,
        rfc=f"{iniciales}{yymmdd}A{indice % 100:02d}",
        nss=f"{10000000000 + indice:011d}",
        ine=ine,
        genero=genero,
        celular=f"744{indice:07d}",
        correo=f"alumno.demo{indice:05d}@example.test",
        domicilio=f"Calle Demo {indice}, Colonia Centro, Acapulco, Guerrero",
        preparatoria="Preparatoria Demo",
        promedio=9.2 if indice % 2 else 8.4,
        celular_emergencia=f"781{indice:07d}",
        correo_emergencia=f"contacto.demo{indice:05d}@example.test",
        alergias="Ninguna",
    )


def crear_alumnos_demo(cantidad: int, id_usuario: int) -> None:
    creados = 0
    for indice in range(1, cantidad + 1):
        datos = _datos_alumno_demo(indice)
        existentes = servicios.verificar_duplicados(datos.ficha, datos.curp)
        if existentes["ficha"] or existentes["curp"]:
            print(f"Alumno demo ya registrado; se omite ficha {datos.ficha}.")
            continue
        resultado = servicios.registrar_alta(datos, {}, {"id_usuario": id_usuario})
        print(f"Alumno demo creado: {resultado['numero_control']} - {resultado['nombre_completo']}")
        creados += 1
    print(f"Periodo {settings.periodo}: {creados} alumnos demo nuevos.")


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
    ap.add_argument(
        "--alumnos-demo",
        type=int,
        default=0,
        metavar="CANTIDAD",
        help="crear alumnos ficticios pendientes de asignar a un paquete (sin PDFs)",
    )
    args = ap.parse_args()
    secretaria_datos = (args.correo, args.nombres, args.apellidos)
    if any(secretaria_datos) and not all(secretaria_datos):
        ap.error("--correo, --nombres y --apellidos deben indicarse juntos")
    if not args.correo and not args.admin_correo:
        ap.error("indica los datos de Secretaría o --admin-correo")
    if args.alumnos_demo and not args.correo:
        ap.error("--alumnos-demo requiere una cuenta de Secretaría")
    if args.alumnos_demo < 0:
        ap.error("--alumnos-demo debe ser cero o mayor")
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
        servicios.migrar_docente_sin_asignar(conn)
        for rol in ROLES:
            conn.execute(text("INSERT IGNORE INTO roles (nombre_rol) VALUES (:r)"), {"r": rol})
            # MySQL's accent-insensitive unique collation can ignore an accented
            # spelling when an older unaccented role already exists.
            conn.execute(text("UPDATE roles SET nombre_rol = :r WHERE nombre_rol = :r"), {"r": rol})
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

        servicios.migrar_horarios(conn)
        servicios.cargar_catalogo_1isc(conn)

    if args.alumnos_demo:
        crear_alumnos_demo(args.alumnos_demo, id_secretaria_usuario)


if __name__ == "__main__":
    main()
