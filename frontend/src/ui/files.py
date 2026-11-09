"""Desktop helpers for opening downloaded documents."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
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
