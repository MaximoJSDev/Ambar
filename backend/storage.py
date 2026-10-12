"""Almacenamiento de los PDF de expedientes digitales en el servidor."""
import shutil
import unicodedata
from pathlib import Path


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
