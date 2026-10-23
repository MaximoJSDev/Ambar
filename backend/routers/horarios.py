"""Asignación y consulta de paquetes de horario de Secretaría."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import reportes, servicios
from ..constantes import ROL_DOCENTE, ROL_SECRETARIA
from ..deps import requiere_roles
from ..esquemas import CalificacionIn

router = APIRouter(prefix="/horarios", tags=["Horarios y grupos"])
solo_secretaria = requiere_roles(ROL_SECRETARIA)
solo_docente = requiere_roles(ROL_DOCENTE)


class AsignarPaqueteIn(BaseModel):
    id_paquete: int = Field(gt=0)


class AsignarDocenteIn(BaseModel):
    id_docente: int | None = Field(default=None, gt=0)


def _not_found():
    raise HTTPException(404, {"mensaje": "No se encontró el alumno, paquete o grupo solicitado"})


@router.get("/paquetes")
def listar_paquetes(
    semestre: int = Query(..., ge=1, le=12),
    _: dict = Depends(solo_secretaria),
):
    return servicios.listar_paquetes_horario(semestre)


@router.get("/alumnos/{numero_control}")
def estado_horario(numero_control: str, _: dict = Depends(solo_secretaria)):
    try:
        return servicios.estado_horario_alumno(numero_control)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.post("/alumnos/{numero_control}/paquete", status_code=status.HTTP_201_CREATED)
def asignar_paquete(
    numero_control: str,
    datos: AsignarPaqueteIn,
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.asignar_paquete_horario(numero_control, datos.id_paquete)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.CupoLleno as ex:
        raise HTTPException(409, {"mensaje": str(ex)})
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.put("/alumnos/{numero_control}/paquete")
def migrar_paquete(
    numero_control: str,
    datos: AsignarPaqueteIn,
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.reasignar_paquete_horario(numero_control, datos.id_paquete)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.CupoLleno as ex:
        raise HTTPException(409, {"mensaje": str(ex)})
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.get("/alumnos/{numero_control}/pdf")
def descargar_horario_alumno(numero_control: str, _: dict = Depends(solo_secretaria)):
    try:
        horario = servicios.estado_horario_alumno(numero_control)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})
    if not horario["asignado"]:
        raise HTTPException(409, {"mensaje": "El alumno aún no tiene un paquete de horario asignado"})
    contenido = reportes.generar_horario_alumno_pdf({
        "alumno": {
            "numero_control": horario["numero_control"],
            "nombre_completo": horario["nombre_completo"],
            "semestre": horario["semestre"],
        },
        "paquete": horario["paquete"],
        "materias": horario["materias"],
    })
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="horario_{numero_control}.pdf"'},
    )


@router.get("/grupos")
def listar_grupos(_: dict = Depends(solo_secretaria)):
    return servicios.listar_paquetes_horario(1)


@router.get("/grupos/{id_paquete}")
def detalle_grupo(id_paquete: int, _: dict = Depends(solo_secretaria)):
    try:
        return servicios.detalle_paquete_horario(id_paquete)
    except servicios.NoEncontrado:
        _not_found()


@router.get("/grupos/{id_paquete}/alumnos")
def alumnos_grupo(id_paquete: int, _: dict = Depends(solo_secretaria)):
    try:
        return servicios.lista_alumnos_paquete(id_paquete)
    except servicios.NoEncontrado:
        _not_found()


@router.get("/grupos/{id_paquete}/alumnos/pdf")
def descargar_lista_grupo(id_paquete: int, _: dict = Depends(solo_secretaria)):
    try:
        datos = servicios.lista_alumnos_paquete(id_paquete)
    except servicios.NoEncontrado:
        _not_found()
    contenido = reportes.generar_lista_grupo_pdf(datos)
    nombre = datos["paquete"]["nombre"]
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="lista_{nombre}.pdf"'},
    )


@router.get("/docentes")
def listar_docentes(_: dict = Depends(solo_secretaria)):
    return servicios.listar_docentes_activos()


@router.get("/docente/grupos")
def grupos_del_docente(usuario: dict = Depends(solo_docente)):
    return servicios.listar_grupos_docente(usuario["id_usuario"])


def _grupo_docente(usuario: dict, id_grupo: int) -> dict:
    grupos = servicios.listar_grupos_docente(usuario["id_usuario"])
    grupo = next((item for item in grupos if item["id_grupo"] == id_grupo), None)
    if grupo is None:
        raise HTTPException(404, {"mensaje": "No se encontró el grupo asignado al docente"})
    return grupo


@router.get("/docente/grupos/pdf")
def descargar_grupos_docente(usuario: dict = Depends(solo_docente)):
    grupos = servicios.listar_grupos_docente(usuario["id_usuario"])
    if not grupos:
        raise HTTPException(409, {"mensaje": "No tienes grupos asignados en el periodo actual"})
    docente = grupos[0]["docente"]
    contenido = reportes.generar_grupos_docente_pdf({
        "docente": docente,
        "grupos": grupos,
    })
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="mis_grupos_horarios.pdf"'},
    )


@router.get("/docente/grupos/{id_grupo}/alumnos/pdf")
def descargar_lista_alumnos_docente(
    id_grupo: int,
    usuario: dict = Depends(solo_docente),
):
    grupo = _grupo_docente(usuario, id_grupo)
    contenido = reportes.generar_lista_docente_pdf(grupo)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="alumnos_{id_grupo}.pdf"',
        },
    )


@router.get("/docente/grupos/{id_grupo}/calificaciones/pdf")
def descargar_calificaciones_docente(
    id_grupo: int,
    usuario: dict = Depends(solo_docente),
):
    grupo = _grupo_docente(usuario, id_grupo)
    contenido = reportes.generar_lista_docente_pdf(grupo, incluir_calificaciones=True)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="calificaciones_{id_grupo}.pdf"',
        },
    )


@router.put("/docente/grupos/{id_grupo}/alumnos/{numero_control}/calificaciones/{periodo_evaluacion}")
def guardar_calificacion(
    id_grupo: int,
    numero_control: str,
    periodo_evaluacion: str,
    datos: CalificacionIn,
    usuario: dict = Depends(solo_docente),
):
    try:
        return servicios.guardar_calificacion_docente(
            usuario["id_usuario"], id_grupo, numero_control,
            periodo_evaluacion, datos.valor,
        )
    except servicios.NoEncontrado:
        _not_found()
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.post("/docente/grupos/{id_grupo}/alumnos/{numero_control}/calificaciones/final")
def confirmar_calificacion_final(
    id_grupo: int,
    numero_control: str,
    usuario: dict = Depends(solo_docente),
):
    try:
        return servicios.confirmar_calificacion_final_docente(
            usuario["id_usuario"], id_grupo, numero_control,
        )
    except servicios.NoEncontrado:
        _not_found()
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})


@router.put("/grupos/{id_grupo}/docente")
def asignar_docente(
    id_grupo: int,
    datos: AsignarDocenteIn,
    _: dict = Depends(solo_secretaria),
):
    try:
        return servicios.actualizar_docente_grupo(id_grupo, datos.id_docente)
    except servicios.NoEncontrado:
        _not_found()
    except servicios.Conflicto as ex:
        raise HTTPException(409, {"mensaje": ex.mensaje})
