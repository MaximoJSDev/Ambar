"""Paleta compartida y políticas de documentos usadas en las pantallas."""

from ambar_common.documents import DOCUMENTOS as MAPA_DOCUMENTOS, DOCUMENTOS_MODIFICABLES as MAPA_DOCUMENTOS_MODIFICABLES

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

DOCUMENTOS = [nombre for nombre, _ in MAPA_DOCUMENTOS.values()]
DOCUMENTOS_MODIFICABLES = tuple(nombre for nombre, _ in MAPA_DOCUMENTOS_MODIFICABLES.values())
REQUIERE_TODOS_LOS_DOCUMENTOS = True
