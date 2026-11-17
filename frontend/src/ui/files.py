"""Ayudantes de escritorio para abrir documentos descargados."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path


_pdf_directory: str | None = None


def carpeta_pdf_temporal() -> Path:
    global _pdf_directory
    if _pdf_directory is None:
        _pdf_directory = tempfile.mkdtemp(prefix="sige_pdf_")
        atexit.register(shutil.rmtree, _pdf_directory, ignore_errors=True)
    return Path(_pdf_directory)


def abrir_archivo(ruta: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(ruta)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(ruta)])
    else:
        subprocess.Popen(["xdg-open", str(ruta)])


def descargar_pdf_y_abrir(
    nombre: str, descargar: Callable[[Path], bytes | Path | None],
) -> None:
    destino = carpeta_pdf_temporal() / nombre
    resultado = descargar(destino)
    if isinstance(resultado, bytes):
        destino.write_bytes(resultado)
    elif isinstance(resultado, Path):
        destino = resultado
    abrir_archivo(destino)
