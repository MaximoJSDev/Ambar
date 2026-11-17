"""Fachada temporal de los servicios organizados por dominio."""

import logging

from .catalogo_horarios import CATALOGO_HORARIOS, PERIODO_1ISC
from .config import engine, settings
from .constantes import DOCUMENTOS, DOCUMENTOS_MODIFICABLES, SEMESTRE_INGRESO, TURNOS
from .esquemas import AltaIn, DocenteCreate, SecretariaCreate
from .services.alumnos import (
    MENSAJES_DUPLICADOS_ALUMNO,
    TIPOS_EXPEDIENTE,
    _CLAVES_PARAMETROS_ALTA,
    _CLAVES_PARAMETROS_MODIFICACION,
    _SQL_DOMICILIO_EXPEDIENTE,
    _SQL_DOMICILIO_MODIFICACION,
    _consulta_domicilio,
    _domicilio_catalogo_valido,
    _errores_duplicados,
    _formatear_domicilio,
    _guardar_historial,
    _limpiar_celular,
    _lugares_por_paquete,
    _parametros_alumno,
    _parametros_domicilio,
    _ultimo_sufijo_control,
    actualizar_alumno,
    actualizar_documentos,
    buscar_expediente,
    cupo_ingreso,
    duplicados,
    elegir_paquete,
    eliminar_alumno,
    guardar_pdfs,
    historial_alumno,
    lugares_por_turno,
    opciones_domicilio,
    registrar_alta,
    ruta_documento,
    validar_alta,
    validar_domicilio_catalogo,
    verificar_duplicados,
)
from .services.bitacora import listar_bitacora_accesos
from .services.common import (
    Conflicto,
    CupoLleno,
    NOMBRE_CANDADO,
    NoEncontrado,
    NumeroControlDuplicado,
    Ocupado,
    SinGrupos,
    _administrar_candado_mysql_altas,
    _formatear_hora,
    _obtener_fecha_inicio_periodo,
    _semana_del_periodo,
)
from .services.docentes import (
    SEMANAS_EVALUACION,
    _inscripcion_docente_bloqueada,
    confirmar_calificacion_final_docente,
    guardar_calificacion_docente,
    listar_grupos_docente,
)
from .services.horarios import (
    _datos_paquete_horario,
    _resumen_paquetes_horario,
    actualizar_docente_grupo,
    asignar_paquete_horario,
    cargar_catalogo_horarios,
    detalle_paquete_horario,
    estado_horario_alumno,
    lista_alumnos_paquete,
    listar_docentes_activos,
    listar_paquetes_horario,
)
from .services.periodos import (
    _SQL_FECHA_INICIO,
    _SQL_FECHA_INICIO_BLOQUEADA,
    _SQL_FECHA_INICIO_BLOQUEADA_AVANCE,
    avanzar_semestre_si_corresponde,
    guardar_periodo_escolar,
    listar_periodos_escolares,
    preparar_avances_semestre,
)
from .services.personal import (
    _crear_cuenta_personal,
    _dar_baja_personal,
    _listar_personal,
    crear_docente,
    crear_secretaria,
    dar_baja_docente,
    dar_baja_secretaria,
    listar_docentes,
    listar_secretarias,
)
from .services.reinscripciones import (
    _grupos_paquete_reinscripcion,
    _liberar_cupos_inscripciones,
    asignar_paquete_reinscripcion,
    eliminar_reinscripcion,
    estado_reinscripcion_alumno,
    modificar_reinscripcion,
    obtener_reinscripcion,
    registrar_reinscripcion,
    validar_reinscripcion,
)

log = logging.getLogger("sige")
