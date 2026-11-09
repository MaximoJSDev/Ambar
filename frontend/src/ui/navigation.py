"""Route catalogs shared by the shell and access-control checks."""

import flet as ft


NAV = [
    ("/secretaria", "Inicio", ft.Icons.HOME_OUTLINED),
    ("/altas", "Altas", ft.Icons.ADD),
    ("/altas-maestros", "Alta de maestros", ft.Icons.PERSON_ADD_ALT_1),
    ("/consulta-maestros", "Consulta de maestros", ft.Icons.GROUP_OUTLINED),
    ("/consultas", "Consultas", ft.Icons.LIST_ALT),
    ("/grupos-horarios", "Grupos y horarios", ft.Icons.GROUP_OUTLINED),
    ("/modificacion", "Modificación", ft.Icons.EDIT_OUTLINED),
    ("/bajas", "Bajas", ft.Icons.REMOVE),
    ("/reinscripcion", "Reinscripción", ft.Icons.REPLAY),
    ("/estadisticas", "Estadísticas", ft.Icons.BAR_CHART),
]
ADMIN_NAV = [
    ("/consultas", "Historial de alumnos", ft.Icons.HISTORY),
    ("/modificacion", "Modificación", ft.Icons.EDIT_OUTLINED),
    ("/administracion/periodos", "Periodos escolares", ft.Icons.CALENDAR_MONTH),
    ("/administracion/secretarias/alta", "Alta de secretaria", ft.Icons.PERSON_ADD_ALT_1),
    ("/administracion/secretarias", "Consulta de secretarias", ft.Icons.LIST_ALT),
    ("/bitacora", "Bitácora", ft.Icons.FORMAT_LIST_BULLETED),
]
DOCENTE_NAV = [
    ("/docente", "Mis grupos", ft.Icons.GROUP_OUTLINED),
]
RUTAS_ADMIN = {
    "/consultas",
    "/modificacion",
    "/administracion/periodos",
    "/administracion/secretarias/alta",
    "/administracion/secretarias",
    "/bitacora",
}
IMPLEMENTADAS = {
    "/secretaria", "/altas", "/altas-maestros", "/consulta-maestros",
    "/grupos-horarios", "/modificacion", "/bajas", "/reinscripcion", "/docente",
    *RUTAS_ADMIN,
}
