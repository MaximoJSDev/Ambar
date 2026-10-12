"""Altas de alumnos de nuevo ingreso (datos en JSON + 6 PDF en multipart)."""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

import validators as v

from .. import servicios
from ..config import settings
from ..constantes import DOCUMENTOS, ROL_SECRETARIA
from ..deps import requiere_roles
from ..esquemas import AltaIn, AltaOut

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])
solo_secretaria = requiere_roles(ROL_SECRETARIA)
log = logging.getLogger("sige")


@router.get("/cupo-ingreso")
def cupo_ingreso(_: dict = Depends(solo_secretaria)):
    """Lugares disponibles por turno en primer semestre del periodo actual."""
    return servicios.cupo_ingreso()


@router.get("/verificar")
def verificar(ficha: str = Query(""), curp: str = Query(""), _: dict = Depends(solo_secretaria)):
    """Indica si la ficha o la CURP ya están registradas (para avisar antes del alta)."""
    return servicios.verificar_duplicados(ficha, curp)


def _copiar_por_bloques(archivo: UploadFile, destino: Path) -> int:
    """Copia el PDF a disco sin cargarlo en memoria; corta si pasa del máximo."""
    total = 0
    with destino.open("wb") as salida:
        while bloque := archivo.file.read(1024 * 1024):
            total += len(bloque)
            if total > v.MAX_PDF_BYTES:
                break
            salida.write(bloque)
    return total


def _preparar_pdfs(tmp: Path, subidos: dict[str, UploadFile | None]) -> tuple[dict[str, str], list[str]]:
    rutas: dict[str, str] = {}
    errores: list[str] = []
    for campo, archivo in subidos.items():
        if archivo is None or not archivo.filename:
            continue
        visible = DOCUMENTOS[campo][0]
        ruta = tmp / f"{campo}.pdf"
        tamano = _copiar_por_bloques(archivo, ruta)
        if tamano > v.MAX_PDF_BYTES:
            err = f"El archivo excede {v.MAX_PDF_MB} MB"
        else:
            err = v.validar_pdf(archivo.filename, tamano, str(ruta))   # extensión, tamaño y cabecera %PDF-
        if err:
            errores.append(f"{visible}: {err}")
        else:
            rutas[visible] = str(ruta)
    return rutas, errores


@router.post("", response_model=AltaOut, status_code=201)
def registrar_alta(
    datos: str = Form(..., description="JSON con los datos del alumno (esquema AltaIn)"),
    doc_acta_nacimiento: UploadFile | None = File(None),
    doc_curp: UploadFile | None = File(None),
    doc_comprobante_domicilio: UploadFile | None = File(None),
    doc_ine: UploadFile | None = File(None),
    doc_certificado_preparatoria: UploadFile | None = File(None),
    doc_certificado_medico: UploadFile | None = File(None),
    usuario: dict = Depends(solo_secretaria),
):
    try:
        alta = AltaIn.model_validate_json(datos)
    except ValidationError as ex:
        errores = {".".join(str(p) for p in e["loc"]): e["msg"] for e in ex.errors()}
        raise HTTPException(422, {"mensaje": "Datos incompletos o con formato incorrecto", "errores": errores})

    errores = servicios.validar_alta(alta)
    subidos = {
        "doc_acta_nacimiento": doc_acta_nacimiento,
        "doc_curp": doc_curp,
        "doc_comprobante_domicilio": doc_comprobante_domicilio,
        "doc_ine": doc_ine,
        "doc_certificado_preparatoria": doc_certificado_preparatoria,
        "doc_certificado_medico": doc_certificado_medico,
    }

    with tempfile.TemporaryDirectory(prefix="sige_") as tmp:
        pdfs, errores_pdf = _preparar_pdfs(Path(tmp), subidos)
        if errores_pdf:
            errores["documentos"] = "; ".join(errores_pdf)
        elif settings.requiere_todos_los_documentos:
            faltan = [visible for visible, _ in DOCUMENTOS.values() if visible not in pdfs]
            if faltan:
                errores["documentos"] = "Falta cargar: " + ", ".join(faltan)
        if errores:
            raise HTTPException(422, {"mensaje": "Revisa los datos capturados", "errores": errores})

        try:
            return servicios.registrar_alta(alta, pdfs, usuario)
        except servicios.Conflicto as ex:
            raise HTTPException(409, {"mensaje": ex.mensaje, "errores": ex.errores})
        except servicios.CupoLleno as ex:
            raise HTTPException(409, {"mensaje": str(ex), "codigo": "cupo_lleno"})
        except servicios.SinGrupos as ex:
            raise HTTPException(503, {"mensaje": f"{ex} Ejecuta seed.py o configura los grupos."})
        except servicios.Ocupado:
            raise HTTPException(503, {"mensaje": "El servidor está procesando otra alta. Intenta de nuevo."})
        except OSError:
            log.exception("Error al guardar los PDF del expediente")
            raise HTTPException(500, {"mensaje": "No se pudieron guardar los archivos PDF en el servidor"})
