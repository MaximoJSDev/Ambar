"""Altas y consulta de alumnos (datos en JSON + 6 PDF en multipart)."""
import logging
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from ambar_common import validators as v

from .. import reportes, servicios
from ..config import settings
from ..constantes import DOCUMENTOS, DOCUMENTOS_MODIFICABLES, ROL_ADMINISTRADOR, ROL_SECRETARIA
from ..deps import requiere_roles, usuario_actual
from ..esquemas import AltaIn, AltaOut

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])
solo_secretaria = requiere_roles(ROL_SECRETARIA)
solo_administrador = requiere_roles(ROL_ADMINISTRADOR)
secretaria_o_administrador = requiere_roles(ROL_SECRETARIA, ROL_ADMINISTRADOR)
log = logging.getLogger("sige")


@router.get("/cupo-ingreso")
def cupo_ingreso(_: dict = Depends(solo_secretaria)):
    """Lugares disponibles por turno en primer semestre del periodo actual."""
    return servicios.cupo_ingreso()


@router.get("/verificar")
def verificar(
    ficha: str = Query(""),
    curp: str = Query(""),
    nss: str = Query(""),
    rfc: str = Query(""),
    ine: str = Query(""),
    correo: str = Query(""),
    _: dict = Depends(solo_secretaria),
):
    """Indica si algún dato único ya está registrado (para avisar antes del alta)."""
    return servicios.verificar_duplicados(
        ficha, curp, nss, rfc, v.normalizar_ine(ine), correo,
    )


@router.get("/domicilios/{codigo_postal}")
def consultar_domicilio(codigo_postal: str, _: dict = Depends(usuario_actual)):
    """Opciones de estado, municipio y colonia del catálogo postal local."""
    if not re.fullmatch(r"\d{5}", codigo_postal):
        raise HTTPException(422, {"mensaje": "El código postal debe contener 5 dígitos"})
    return servicios.opciones_domicilio(codigo_postal)


# --- Consultas -------------------------------------------------------------
@router.get("/expediente")
def expediente(
    q: str = Query(..., min_length=1, max_length=40),
    usuario: dict = Depends(usuario_actual),
    incluir_bajas: bool = Query(False),
):
    """Expediente completo por número de control o CURP."""
    if incluir_bajas and usuario["rol"] != ROL_ADMINISTRADOR:
        raise HTTPException(403, {"mensaje": "Solo Administración puede consultar expedientes dados de baja"})
    try:
        return servicios.buscar_expediente(q, incluir_bajas)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró ningún alumno con ese número de control o CURP"})


@router.get("/expediente/pdf")
def descargar_expediente_pdf(
    q: str = Query(..., min_length=1, max_length=40),
    usuario: dict = Depends(usuario_actual),
    incluir_bajas: bool = Query(False),
):
    """Descarga una ficha PDF con membrete institucional y el estado del expediente."""
    if incluir_bajas and usuario["rol"] != ROL_ADMINISTRADOR:
        raise HTTPException(403, {"mensaje": "Solo Administración puede consultar expedientes dados de baja"})
    try:
        datos = servicios.buscar_expediente(q, incluir_bajas)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró ningún alumno con ese número de control o CURP"})

    contenido = reportes.generar_expediente_pdf(datos)
    numero = re.sub(r"[^A-Za-z0-9_-]", "_", datos["numero_control"])
    nombre = f"expediente_{numero}.pdf"
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/documentos/{id_documento}")
def descargar_documento(
    id_documento: int,
    usuario: dict = Depends(usuario_actual),
    incluir_bajas: bool = Query(False),
):
    """Sirve el PDF guardado en el servidor."""
    if incluir_bajas and usuario["rol"] != ROL_ADMINISTRADOR:
        raise HTTPException(403, {"mensaje": "Solo Administración puede consultar expedientes dados de baja"})
    try:
        ruta, nombre = servicios.ruta_documento(id_documento, incluir_bajas)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "El documento no existe en el servidor"})
    return FileResponse(ruta, media_type="application/pdf", filename=nombre,
                        content_disposition_type="inline")


@router.put("/{numero_control}")
def actualizar_alumno(
    numero_control: str,
    datos: AltaIn,
    usuario: dict = Depends(secretaria_o_administrador),
):
    """Modifica datos personales y de contacto sin cambiar el historial académico."""
    errores = servicios.validar_alta(datos, exigir_identificacion_adulto=False)
    if not errores:
        errores.update(servicios.validar_domicilio_catalogo(datos))
    if errores:
        raise HTTPException(422, {"mensaje": "Revisa los datos capturados", "errores": errores})
    try:
        servicios.actualizar_alumno(numero_control, datos, usuario["id_usuario"])
        return {"mensaje": "Datos del alumno actualizados"}
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró el alumno"})
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje, "errores": ex.errores})


@router.put("/{numero_control}/documentos")
def actualizar_documentos(
    numero_control: str,
    doc_acta_nacimiento: UploadFile | None = File(None),
    doc_curp: UploadFile | None = File(None),
    doc_comprobante_domicilio: UploadFile | None = File(None),
    doc_ine: UploadFile | None = File(None),
    doc_certificado_preparatoria: UploadFile | None = File(None),
    doc_certificado_medico: UploadFile | None = File(None),
    doc_constancia_situacion_fiscal: UploadFile | None = File(None),
    usuario: dict = Depends(secretaria_o_administrador),
):
    """Agrega o reemplaza uno o más PDF del expediente."""
    subidos = {
        "doc_acta_nacimiento": doc_acta_nacimiento,
        "doc_curp": doc_curp,
        "doc_comprobante_domicilio": doc_comprobante_domicilio,
        "doc_ine": doc_ine,
        "doc_certificado_preparatoria": doc_certificado_preparatoria,
        "doc_certificado_medico": doc_certificado_medico,
        "doc_constancia_situacion_fiscal": doc_constancia_situacion_fiscal,
    }
    with tempfile.TemporaryDirectory(prefix="sige_") as tmp:
        pdfs, errores_pdf = _preparar_pdfs(Path(tmp), subidos)
        if errores_pdf:
            raise HTTPException(
                422,
                {"mensaje": "Revisa los documentos", "errores": {"documentos": "; ".join(errores_pdf)}},
            )
        if not pdfs:
            raise HTTPException(422, {"mensaje": "Selecciona al menos un documento PDF"})
        try:
            servicios.actualizar_documentos(numero_control, pdfs)
            return {"mensaje": "Documentos del expediente actualizados"}
        except servicios.NoEncontrado:
            raise HTTPException(404, {"mensaje": "No se encontró el alumno"})
        except OSError:
            log.exception("Error al actualizar los PDF del expediente %s", numero_control)
            raise HTTPException(500, {"mensaje": "No se pudieron guardar los archivos PDF en el servidor"})


@router.delete("/{numero_control}")
def eliminar_alumno(
    numero_control: str,
    usuario: dict = Depends(secretaria_o_administrador),
):
    """Da de baja el expediente y conserva su historial administrativo."""
    try:
        servicios.eliminar_alumno(numero_control, usuario["id_usuario"])
        return {"mensaje": "Expediente dado de baja; el historial se conserva"}
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró el alumno"})


@router.get("/{numero_control}/historial", dependencies=[Depends(solo_administrador)])
def historial_alumno(numero_control: str):
    """Historial de modificaciones y bajas, disponible solo para Administración."""
    try:
        servicios.buscar_expediente(numero_control, incluir_bajas=True)
    except servicios.NoEncontrado:
        raise HTTPException(404, {"mensaje": "No se encontró el alumno"})
    return servicios.historial_alumno(numero_control)


# --- Altas -----------------------------------------------------------------
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
        visible = DOCUMENTOS_MODIFICABLES[campo][0]
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
    if not errores:
        errores.update(servicios.validar_domicilio_catalogo(alta))
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
            raise HTTPException(
                503,
                {"mensaje": f"{ex} Ejecuta python -m backend.seed o configura los grupos."},
            )
        except servicios.Ocupado:
            raise HTTPException(503, {"mensaje": "El servidor está procesando otra alta. Intenta de nuevo."})
        except OSError:
            log.exception("Error al guardar los PDF del expediente")
            raise HTTPException(500, {"mensaje": "No se pudieron guardar los archivos PDF en el servidor"})
