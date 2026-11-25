"""Almacenamiento local o privado de expedientes en Cloudinary."""

from pathlib import Path
import shutil
import time
from typing import Iterator

import cloudinary
from cloudinary import api, uploader
from cloudinary.exceptions import NotFound
from cloudinary.utils import private_download_url
import httpx

from ambar_common.validators import (
    MAX_CLOUDINARY_FREE_PDF_BYTES,
    MAX_CLOUDINARY_FREE_PDF_MB,
)

from .config import settings

PREFIJO_CLOUDINARY = "cloudinary:"


def _configurar_cloudinary() -> None:
    if not settings.cloudinary_configurado:
        raise RuntimeError("Cloudinary no está configurado")
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


def es_archivo_cloudinary(locator: str) -> bool:
    return locator.startswith(PREFIJO_CLOUDINARY)


def guardar_archivo(origen: Path, clave: str) -> str:
    """Guarda un archivo y devuelve la referencia que se almacena en MySQL."""
    if not settings.cloudinary_configurado:
        destino = settings.storage_dir / Path(clave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, destino)
        return Path(clave).as_posix()

    if origen.stat().st_size > MAX_CLOUDINARY_FREE_PDF_BYTES:
        raise ValueError(
            f"El plan gratuito de Cloudinary permite PDF de hasta {MAX_CLOUDINARY_FREE_PDF_MB} MB",
        )

    _configurar_cloudinary()
    resultado = uploader.upload_large(
        str(origen),
        public_id=Path(clave).as_posix(),
        resource_type="raw",
        type="private",
        overwrite=False,
        unique_filename=False,
        use_filename=False,
        headers="X-Robots-Tag: noindex",
    )
    public_id = resultado.get("public_id")
    if not public_id:
        raise RuntimeError("Cloudinary no devolvió el identificador del archivo")
    return f"{PREFIJO_CLOUDINARY}{public_id}"


def existe_archivo(locator: str) -> bool:
    if es_archivo_cloudinary(locator):
        _configurar_cloudinary()
        try:
            api.resource(
                locator.removeprefix(PREFIJO_CLOUDINARY),
                resource_type="raw",
                type="private",
            )
        except NotFound:
            return False
        return True

    base = settings.storage_dir.resolve()
    ruta = (base / locator).resolve()
    return ruta.is_relative_to(base) and ruta.is_file()


def eliminar_archivo(locator: str) -> None:
    if es_archivo_cloudinary(locator):
        _configurar_cloudinary()
        resultado = uploader.destroy(
            locator.removeprefix(PREFIJO_CLOUDINARY),
            resource_type="raw",
            type="private",
            invalidate=True,
        )
        if resultado.get("result") not in {"ok", "not found"}:
            raise RuntimeError("Cloudinary no pudo eliminar el archivo")
        return

    base = settings.storage_dir.resolve()
    ruta = (base / locator).resolve()
    if ruta.is_relative_to(base):
        ruta.unlink(missing_ok=True)


def transmitir_archivo(locator: str) -> Iterator[bytes]:
    """Transmite el PDF sin exponer su enlace privado ni cargarlo completo en memoria."""
    if es_archivo_cloudinary(locator):
        _configurar_cloudinary()
        url = private_download_url(
            locator.removeprefix(PREFIJO_CLOUDINARY),
            "pdf",
            resource_type="raw",
            type="private",
            secure=True,
            expires_at=int(time.time()) + 60,
        )
        timeout = httpx.Timeout(30.0, read=900.0)
        with httpx.stream("GET", url, timeout=timeout) as response:
            response.raise_for_status()
            yield from response.iter_bytes(1024 * 1024)
        return

    base = settings.storage_dir.resolve()
    ruta = (base / locator).resolve()
    if not ruta.is_relative_to(base):
        raise FileNotFoundError("La ruta del documento no es válida")
    with ruta.open("rb") as archivo:
        while bloque := archivo.read(1024 * 1024):
            yield bloque
