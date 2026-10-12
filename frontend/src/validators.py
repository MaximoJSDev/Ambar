"""Validaciones puras (sin dependencia de Flet) para el sistema SIGE.

Cada validador recibe el texto del campo y devuelve un mensaje de error
(str) o None si el valor es válido. Así se pueden probar sin abrir la app.
"""
import datetime
import os
import re
import time
import unicodedata

PATRON_EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PATRON_CELULAR = re.compile(r"(744|781)\d{7}")
PATRON_FICHA = re.compile(r"\d{10}|\d{4}-\d{5}")
PATRON_NOMBRE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[ '\-][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*")
PATRON_CURP = re.compile(
    r"[A-Z]{4}\d{6}[HMX](?:AS|BC|BS|CC|CL|CM|CS|CH|DF|DG|GT|GR|HG|JC|MC|MN|MS|NT|NL|OC|PL|QT|QR|SP|SL|SR|TC|TS|TL|VZ|YN|ZS|NE)"
    r"[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d"
)
PATRON_RFC = re.compile(r"[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}")
PATRON_NSS = re.compile(r"\d{11}")
PATRON_INE = re.compile(r"[A-Z]{6}\d{8}[HM]\d{3}")

EDAD_MINIMA = 16
EDAD_MAXIMA = 70
NOMBRE_MIN, NOMBRE_MAX = 3, 20      # longitud de nombre y apellidos (diagrama de Altas)
MAX_PDF_MB = 500                    # límite por archivo (Algoritmo 3, paso 3)
MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
TURNO_MATUTINO_MIN = 9              # promedio >= 9 -> Matutino, si no Vespertino

GENEROS = {
    "hombre": "Hombre",
    "mujer": "Mujer",
    "no_binario": "No binario",
    "no_especifica": "Prefiero no especificar",
}


def hace_anios(n: int, hoy: datetime.date | None = None) -> datetime.date:
    """Fecha de hace n años (maneja el 29 de febrero)."""
    hoy = hoy or datetime.date.today()
    try:
        return hoy.replace(year=hoy.year - n)
    except ValueError:
        return hoy.replace(year=hoy.year - n, day=28)


# --------------------------------------------------------------------------
# Campos de texto
# --------------------------------------------------------------------------
def validar_correo_login(valor: str) -> str | None:
    if not PATRON_EMAIL.fullmatch(valor.strip()):
        return "Formato de correo electrónico inválido"
    return None


def validar_ficha(valor: str) -> str | None:
    if not PATRON_FICHA.fullmatch(valor.strip()):
        return "Ficha inválida: 10 dígitos o formato AAAA-NNNNN"
    return None


def validar_nombre(valor: str, tipo: str = "Nombre") -> str | None:
    v = valor.strip()
    if not NOMBRE_MIN <= len(v) <= NOMBRE_MAX:
        return f"{tipo}: de {NOMBRE_MIN} a {NOMBRE_MAX} caracteres"
    if not PATRON_NOMBRE.fullmatch(v):
        return f"{tipo}: solo letras y espacios"
    return None


def validar_apellido(valor: str) -> str | None:
    return validar_nombre(valor, "Apellido")


def validar_fecha_nacimiento(valor: datetime.date | None,
                             hoy: datetime.date | None = None) -> str | None:
    if valor is None:
        return "Selecciona una fecha válida"
    if valor < hace_anios(EDAD_MAXIMA, hoy) or valor > hace_anios(EDAD_MINIMA, hoy):
        return f"La edad debe estar entre {EDAD_MINIMA} y {EDAD_MAXIMA} años"
    return None


def _yymmdd(fecha: datetime.date) -> str:
    return fecha.strftime("%y%m%d")


def validar_curp(valor: str, fecha: datetime.date | None = None) -> str | None:
    v = valor.strip().upper()
    if len(v) != 18:
        return "La CURP debe tener 18 caracteres"
    if not PATRON_CURP.fullmatch(v):
        return "Formato de CURP inválido"
    if fecha is not None and v[4:10] != _yymmdd(fecha):
        return "La fecha de la CURP no coincide con la fecha de nacimiento"
    return None


def validar_rfc(valor: str, fecha: datetime.date | None = None) -> str | None:
    v = valor.strip().upper()
    if len(v) != 13:
        return "El RFC debe tener 13 caracteres"
    if not PATRON_RFC.fullmatch(v):
        return "Formato de RFC inválido"
    if fecha is not None and v[4:10] != _yymmdd(fecha):
        return "La fecha del RFC no coincide con la fecha de nacimiento"
    return None


def validar_nss(valor: str) -> str | None:
    if not PATRON_NSS.fullmatch(valor.strip()):
        return "El número de seguro social debe tener 11 dígitos"
    return None


def validar_celular(valor: str) -> str | None:
    v = re.sub(r"[\s-]", "", valor)
    if not PATRON_CELULAR.fullmatch(v):
        return "Teléfono inválido: 10 dígitos con lada 744 o 781"
    return None


def validar_correo(valor: str) -> str | None:
    if not PATRON_EMAIL.fullmatch(valor.strip()):
        return "Formato de correo electrónico inválido"
    return None


def validar_domicilio(valor: str) -> str | None:
    if len(valor.strip()) < 10:
        return "Escribe calle, número, colonia, ciudad y estado"
    return None


def validar_preparatoria(valor: str) -> str | None:
    if not 3 <= len(valor.strip()) <= 80:
        return "Nombre de la preparatoria: de 3 a 80 caracteres"
    return None


def validar_promedio(valor: str) -> str | None:
    try:
        promedio = float(valor.strip().replace(",", "."))
    except ValueError:
        return "Promedio inválido"
    if not 1 <= promedio <= 10:
        return "Ingresa un promedio del 1 al 10"
    return None


def validar_ine(valor: str, fecha: datetime.date | None = None) -> str | None:
    """Clave de elector: 6 letras + AAMMDD + entidad (2) + H/M + 3 dígitos = 18."""
    v = valor.strip().upper()
    if len(v) != 18:
        return "La clave de elector debe tener 18 caracteres"
    if not PATRON_INE.fullmatch(v):
        return "Formato de clave de elector inválido"
    if fecha is not None and v[6:12] != _yymmdd(fecha):
        return "La fecha de la INE no coincide con la fecha de nacimiento"
    return None


def validar_genero(valor: str | None) -> str | None:
    if valor not in GENEROS:
        return "Selecciona un género"
    return None


def validar_celular_emergencia(valor: str, celular_alumno: str = "") -> str | None:
    err = validar_celular(valor)
    if err:
        return err
    limpio = lambda t: re.sub(r"[\s-]", "", t)
    if celular_alumno and limpio(valor) == limpio(celular_alumno):
        return "Debe ser distinto al celular del alumno"
    return None


def validar_correo_emergencia(valor: str, correo_alumno: str = "") -> str | None:
    err = validar_correo(valor)
    if err:
        return err
    if correo_alumno and valor.strip().lower() == correo_alumno.strip().lower():
        return "Debe ser distinto al correo personal del alumno"
    return None


def validar_alergias(valor: str) -> str | None:
    """Opcional; vacío equivale a «Ninguna»."""
    if len(valor.strip()) > 200:
        return "Máximo 200 caracteres"
    return None


# --------------------------------------------------------------------------
# Reglas de negocio de Altas
# --------------------------------------------------------------------------
def turno_por_promedio(promedio: float) -> str:
    return "Matutino" if promedio >= TURNO_MATUTINO_MIN else "Vespertino"


def indice_letra(apellido: str) -> int:
    """A=1 ... Z=26 (acentos y Ñ se reducen a su letra base)."""
    base = unicodedata.normalize("NFD", apellido.strip().upper())
    for ch in base:
        if "A" <= ch <= "Z":
            return ord(ch) - 64
    raise ValueError("El apellido no contiene letras")


def prefijo_control(anio: int, plantel: int, apellido: str) -> str:
    return f"{anio}{plantel:02d}{indice_letra(apellido):02d}"


def generar_numero_control(anio: int, plantel: int, apellido: str, consecutivo: int) -> str:
    """AAAA + plantel(2) + letra del apellido(2) + consecutivo en esa letra(3)."""
    return f"{prefijo_control(anio, plantel, apellido)}{consecutivo:03d}"


def correo_institucional(numero_control: str, dominio: str = "acapulco.tecnm.mx") -> str:
    return f"al{numero_control}@{dominio}"


def validar_pdf(nombre: str, tamano: int | None, ruta: str | None = None,
                max_bytes: int = MAX_PDF_BYTES) -> str | None:
    if not nombre.lower().endswith(".pdf"):
        return "El archivo debe ser PDF"
    if ruta:
        try:
            tamano = os.path.getsize(ruta)
        except OSError:
            return "No se pudo leer el archivo"
    if not tamano:
        return "El archivo está vacío"
    if tamano > max_bytes:
        return f"El archivo excede {max_bytes // (1024 * 1024)} MB"
    if ruta:
        try:
            with open(ruta, "rb") as f:
                if f.read(5) != b"%PDF-":
                    return "El archivo no es un PDF válido"
        except OSError:
            return "No se pudo leer el archivo"
    return None


# --------------------------------------------------------------------------
# Bloqueo de inicio de sesión
# --------------------------------------------------------------------------
class LoginGuard:
    """Cuenta intentos fallidos por correo y bloquea tras `max_intentos`.

    El estado vive en este objeto (no en la vista), por lo que recargar la
    pantalla de login no reinicia el contador. El bloqueo expira tras
    `segundos_bloqueo` (0 = permanente hasta reiniciar la aplicación).
    """

    def __init__(self, max_intentos: int = 3, segundos_bloqueo: int = 300, reloj=time.monotonic):
        self.max_intentos = max_intentos
        self.segundos_bloqueo = segundos_bloqueo
        self._reloj = reloj
        self._fallos: dict[str, int] = {}
        self._bloqueado_hasta: dict[str, float] = {}

    @staticmethod
    def _clave(correo: str) -> str:
        return correo.strip().lower()

    def segundos_restantes(self, correo: str) -> int:
        """Segundos de bloqueo pendientes (0 si no está bloqueado)."""
        k = self._clave(correo)
        hasta = self._bloqueado_hasta.get(k)
        if hasta is None:
            return 0
        if self.segundos_bloqueo and self._reloj() >= hasta:
            del self._bloqueado_hasta[k]
            self._fallos.pop(k, None)
            return 0
        return max(1, int(hasta - self._reloj() + 0.999)) if self.segundos_bloqueo else 10**9

    def bloqueado(self, correo: str) -> bool:
        return self.segundos_restantes(correo) > 0

    def intentos_restantes(self, correo: str) -> int:
        return max(0, self.max_intentos - self._fallos.get(self._clave(correo), 0))

    def registrar_fallo(self, correo: str) -> int:
        """Registra un fallo y devuelve los intentos que quedan."""
        k = self._clave(correo)
        self._fallos[k] = self._fallos.get(k, 0) + 1
        if self._fallos[k] >= self.max_intentos:
            self._bloqueado_hasta[k] = self._reloj() + self.segundos_bloqueo
        return self.intentos_restantes(correo)

    def registrar_exito(self, correo: str) -> None:
        k = self._clave(correo)
        self._fallos.pop(k, None)
        self._bloqueado_hasta.pop(k, None)