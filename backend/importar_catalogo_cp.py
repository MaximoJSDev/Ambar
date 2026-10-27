"""Importa un catálogo TXT de SEPOMEX a las tablas locales de Ambar."""
import argparse
import csv
import io
from itertools import chain
from pathlib import Path

INDICES_SEPOMEX = (0, 1, 3, 4)
ALIAS_CAMPOS = {
    "codigo_postal": {"d_codigo", "codigo_postal", "cp"},
    "colonia": {"d_asenta", "colonia", "asentamiento"},
    "municipio": {"d_mnpio", "municipio", "delegacion_municipio"},
    "estado": {"d_estado", "estado", "entidad"},
}


def _indice_columnas(fila: list[str]) -> dict[str, int] | None:
    encabezados = {valor.strip().lstrip("\ufeff").casefold(): indice
                   for indice, valor in enumerate(fila)}
    indices = {
        campo: next((encabezados[nombre] for nombre in alias if nombre in encabezados), None)
        for campo, alias in ALIAS_CAMPOS.items()
    }
    return indices if all(indice is not None for indice in indices.values()) else None


def leer_registros(contenido: str) -> list[dict[str, str]]:
    """Lee TXT SEPOMEX con encabezados o con el orden estándar de 15 columnas."""
    lector = csv.reader(io.StringIO(contenido, newline=""), delimiter="|", quotechar='"')
    primera = next(lector, None)
    if primera is None:
        raise ValueError("El archivo está vacío")

    indices = _indice_columnas(primera)
    filas = lector if indices else chain((primera,), lector)
    if indices is None:
        indices = dict(zip(ALIAS_CAMPOS, INDICES_SEPOMEX))

    registros: set[tuple[str, str, str, str]] = set()
    for fila in filas:
        if len(fila) <= max(indices.values()):
            continue
        codigo = fila[indices["codigo_postal"]].strip()
        if not codigo.isdigit() or len(codigo) > 5:
            continue
        codigo = codigo.zfill(5)
        colonia = fila[indices["colonia"]].strip()
        municipio = fila[indices["municipio"]].strip()
        estado = fila[indices["estado"]].strip()
        if not all((colonia, municipio, estado)):
            continue
        registros.add((codigo, estado, municipio, colonia))

    if not registros:
        raise ValueError("No se encontraron registros postales válidos en el archivo")
    return [
        {"codigo_postal": cp, "estado": estado, "municipio": municipio, "colonia": colonia}
        for cp, estado, municipio, colonia in sorted(registros)
    ]


def importar(archivo: Path) -> int:
    from sqlalchemy import text

    from .config import engine

    contenido_bytes = archivo.read_bytes()
    try:
        contenido = contenido_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        contenido = contenido_bytes.decode("cp1252")
    registros = leer_registros(contenido)

    consulta = text("""INSERT INTO catalogo_codigos_postales
                           (codigo_postal, estado, municipio, colonia)
                       VALUES
                           (:codigo_postal, :estado, :municipio, :colonia)
                       ON DUPLICATE KEY UPDATE colonia = VALUES(colonia)""")
    with engine.begin() as conn:
        for inicio in range(0, len(registros), 2000):
            conn.execute(consulta, registros[inicio:inicio + 2000])
    return len(registros)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa el TXT de códigos postales de SEPOMEX al catálogo local de Ambar.",
    )
    parser.add_argument("archivo", type=Path, help="Ruta al archivo TXT descargado previamente")
    args = parser.parse_args()
    if not args.archivo.is_file():
        parser.error(f"No existe el archivo: {args.archivo}")
    cantidad = importar(args.archivo)
    print(f"Catálogo postal local actualizado: {cantidad:,} combinaciones.")


if __name__ == "__main__":
    main()
