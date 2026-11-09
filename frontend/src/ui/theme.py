"""Shared palette and document policy used across screens."""

NAVY = "#17345C"
GOLD = "#D99A2B"
BG = "#F3F5F9"
WHITE = "#FFFFFF"
TEXT = "#1B2A41"
MUTED = "#6B7A90"
BORDER = "#E3E7EF"
SOFT_BLUE = "#E8F0FB"
OK_BG, OK_FG = "#DFF1E8", "#13734A"
WARN_BG, WARN_FG = "#FFEFD2", "#9A5B00"

DOCUMENTOS = [
    "Acta de nacimiento",
    "CURP",
    "Comprobante de domicilio",
    "INE",
    "Certificado de preparatoria",
    "Certificado médico",
]
DOCUMENTOS_MODIFICABLES = (*DOCUMENTOS, "Constancia de situación fiscal")
REQUIERE_TODOS_LOS_DOCUMENTOS = True
