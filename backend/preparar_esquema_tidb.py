"""Genera el esquema de TiDB a partir del esquema MySQL de Ámbar."""

import re
from pathlib import Path


def main() -> None:
    raiz = Path(__file__).resolve().parent.parent
    esquema = (raiz / "ambar-db.sql").read_text(encoding="utf-8")
    esquema, eliminados = re.subn(
        r"^-- Mantienen cupo_disponible[^\n]*\n"
        r"CREATE TRIGGER trg_inscripcion_alta\b[^;]*;\n\n"
        r"CREATE TRIGGER trg_inscripcion_baja\b[^;]*;\n\n",
        "",
        esquema,
        flags=re.MULTILINE,
    )
    if eliminados != 1 or re.search(r"^CREATE TRIGGER\b", esquema, re.MULTILINE):
        raise SystemExit("El esquema MySQL cambió. Revisa los triggers antes de generar el de TiDB.")
    esquema = esquema.replace(
        "cupo_disponible INT NOT NULL DEFAULT 25, -- lo mantienen los triggers de inscripciones",
        "cupo_disponible INT NOT NULL DEFAULT 25, -- lo mantiene FastAPI (DB_TIDB=true)",
    )
    esquema = re.sub(r"^CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", esquema, flags=re.MULTILINE)
    destino = raiz / "ambar-db-tidb.sql"
    destino.write_text(esquema, encoding="utf-8")
    print(destino)


if __name__ == "__main__":
    main()
