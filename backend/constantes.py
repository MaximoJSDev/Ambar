"""Constantes de negocio compartidas por routers y servicios."""

ROL_SECRETARIA = "Secretaría"
ROL_DOCENTE = "Docente"
TURNOS = ("Matutino", "Vespertino")
SEMESTRE_INGRESO = 1

# campo del formulario multipart -> (nombre visible, valor del ENUM tipo_documento en la BD)
# El nombre visible es el mismo que usa la app Flet y la clave que recibe storage.guardar_pdfs.
DOCUMENTOS = {
    "doc_acta_nacimiento": ("Acta de nacimiento", "Acta de Nacimiento"),
    "doc_curp": ("CURP", "CURP"),
    "doc_comprobante_domicilio": ("Comprobante de domicilio", "Comprobante de domicilio"),
    "doc_ine": ("INE", "INE"),
    "doc_certificado_preparatoria": ("Certificado de preparatoria", "Certificado Preparatoria"),
    "doc_certificado_medico": ("Certificado médico", "Certificado Medico"),
}
TIPOS_REQUERIDOS = [tipo_bd for _, tipo_bd in DOCUMENTOS.values()]
