"""Almacenamiento de los PDF del expediente digital."""
import shutil
import unicodedata
from pathlib import Path


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return "_".join(t.lower().split())


def guardar_pdfs(numero_control: str, archivos: dict[str, str], base: Path) -> dict[str, str]:
    """Copia cada PDF a base/<numero_control>/<documento>.pdf.

    `archivos` mapea nombre de documento -> ruta de origen. Si algo falla, se
    elimina lo copiado para no dejar expedientes a medias y se propaga el error.
    """
    destino = Path(base) / numero_control
    destino.mkdir(parents=True, exist_ok=False)
    guardados: dict[str, str] = {}
    try:
        for doc, origen in archivos.items():
            if not origen:
                raise OSError(f"No se pudo leer «{doc}»")
            ruta = destino / f"{slug(doc)}.pdf"
            shutil.copyfile(origen, ruta)
            guardados[doc] = str(ruta)
    except Exception:
        shutil.rmtree(destino, ignore_errors=True)
        raise
    return guardados