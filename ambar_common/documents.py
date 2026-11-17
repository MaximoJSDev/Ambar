"""Mapa común de documentos del expediente."""

DOCUMENTOS = {
    "doc_acta_nacimiento": ("Acta de nacimiento", "Acta de Nacimiento"),
    "doc_curp": ("CURP", "CURP"),
    "doc_comprobante_domicilio": ("Comprobante de domicilio", "Comprobante de domicilio"),
    "doc_ine": ("INE", "INE"),
    "doc_certificado_preparatoria": ("Certificado de preparatoria", "Certificado Preparatoria"),
    "doc_certificado_medico": ("Certificado médico", "Certificado Medico"),
}
DOCUMENTOS_MODIFICABLES = DOCUMENTOS | {
    "doc_constancia_situacion_fiscal": (
        "Constancia de situación fiscal",
        "Constancia Situacion Fiscal",
    ),
}
