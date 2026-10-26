"""Validaciones compartidas (sin dependencia de Flet) para el sistema SIGE.

Cada validador recibe el texto del campo y devuelve un mensaje de error
(str) o None si el valor es válido.
"""
import datetime
import os
import re
import unicodedata

PATRON_EMAIL = re.compile(
    r"^[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
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
PATRON_PROMEDIO = re.compile(r"\d{1,3}(?:[.,]\d{1,2})?")
PUNTUACION_DESCRIPTIVA = " .,#°ºª'’()/&-;:+"

EDAD_MINIMA = 12
EDAD_MAXIMA = 80
DOMINIO_CORREO_INSTITUCIONAL = "@acapulco.tecnm.mx"
DOMINIOS_CORREO_PUBLICOS = frozenset({
    "gmail.com", "googlemail.com",
    "hotmail.com", "hotmail.com.mx", "hotmail.es",
    "outlook.com", "outlook.com.mx", "outlook.es",
    "live.com", "live.com.mx", "msn.com",
    "yahoo.com", "yahoo.com.mx", "yahoo.es", "ymail.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "pm.me",
    "gmx.com", "gmx.net", "zoho.com", "yandex.com",
})
TIPOS_SANGRE = ("O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-")
NOMBRE_MIN, NOMBRE_MAX = 3, 50
PROMEDIO_MIN, PROMEDIO_MAX = 6, 10
MAX_PDF_MB = 500                    # límite por archivo (Algoritmo 3, paso 3)
MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
TURNO_MATUTINO_MIN = 9              # promedio >= 9 -> Matutino, si no Vespertino

GENEROS = {
    "hombre": "Hombre",
    "mujer": "Mujer",
    "no_binario": "No binario",
}

SEXO_CURP_POR_GENERO = {
    "hombre": "H",
    "mujer": "M",
    "no_binario": "X",
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


def validar_nombre_personal(
    valor: str,
    tipo: str = "Nombre",
    maximo: int = 50,
) -> str | None:
    v = valor.strip()
    if len(v) < 2:
        return f"{tipo}: mínimo 2 caracteres"
    if len(v) > maximo:
        return f"{tipo}: máximo {maximo} caracteres"
    if not PATRON_NOMBRE.fullmatch(v):
        return f"{tipo}: usa solo letras, espacios, guiones o apóstrofes"
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


def es_mayor_de_18(fecha: datetime.date, hoy: datetime.date | None = None) -> bool:
    """Indica si la persona ya cumplió 18 años."""
    hoy = hoy or datetime.date.today()
    edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
    return edad >= 18


def _yymmdd(fecha: datetime.date) -> str:
    return fecha.strftime("%y%m%d")


_PARTICULAS_APELLIDO = {"DE", "DEL", "LA", "LAS", "LOS", "Y"}


def _normalizar_apellido_curp(valor: str) -> str:
    texto = valor.strip().upper().replace("Ñ", "X")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Mn")
    palabras = re.findall(r"[A-Z]+", texto)
    apellido = next(
        (palabra for palabra in palabras if palabra not in _PARTICULAS_APELLIDO),
        palabras[-1] if palabras else "",
    )
    return apellido


def prefijo_curp_apellidos(apellido_paterno: str, apellido_materno: str) -> str:
    paterno = _normalizar_apellido_curp(apellido_paterno)
    materno = _normalizar_apellido_curp(apellido_materno)
    inicial_paterno = paterno[:1] or "X"
    vocal_interna = next((letra for letra in paterno[1:] if letra in "AEIOU"), "X")
    inicial_materno = materno[:1] or "X"
    return inicial_paterno + vocal_interna + inicial_materno


def validar_curp(
    valor: str,
    fecha: datetime.date | None = None,
    apellido_paterno: str | None = None,
    apellido_materno: str | None = None,
    genero: str | None = None,
) -> str | None:
    v = valor.strip().upper()
    if len(v) != 18:
        return "La CURP debe tener 18 caracteres"
    if not PATRON_CURP.fullmatch(v):
        return "Formato de CURP inválido"
    if fecha is not None and v[4:10] != _yymmdd(fecha):
        return "La fecha de la CURP no coincide con la fecha de nacimiento"
    if apellido_paterno and apellido_materno:
        prefijo_esperado = prefijo_curp_apellidos(apellido_paterno, apellido_materno)
        if v[:3] != prefijo_esperado:
            return "La CURP no coincide con los apellidos ingresados"
    sexo_esperado = SEXO_CURP_POR_GENERO.get(genero)
    if sexo_esperado and v[10] != sexo_esperado:
        return "El género no coincide con el carácter de sexo de la CURP"
    return None


def validar_rfc(valor: str | None, fecha: datetime.date | None = None) -> str | None:
    if not valor or not valor.strip():
        return None
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


def validar_correo(valor: str, maximo: int = 150) -> str | None:
    v = valor.strip()
    if len(v) > maximo:
        return f"El correo no puede exceder {maximo} caracteres"
    if not PATRON_EMAIL.fullmatch(v):
        return "Formato de correo electrónico inválido"
    return None


def validar_correo_con_dominio(valor: str, maximo: int = 150) -> str | None:
    error = validar_correo(valor, maximo)
    if error:
        return error
    dominio = valor.strip().rsplit("@", 1)[1].lower()
    if dominio not in DOMINIOS_CORREO_PUBLICOS:
        # Los dominios personalizados se aceptan por formato, sin comprobarlos.
        return None
    # Los proveedores públicos de esta lista se consideran conocidos sin red.
    return None


def validar_correo_institucional(valor: str) -> str | None:
    error = validar_correo(valor)
    if error:
        return error
    if not valor.strip().lower().endswith(DOMINIO_CORREO_INSTITUCIONAL):
        return f"El correo debe terminar en {DOMINIO_CORREO_INSTITUCIONAL}"
    return None


def _texto_descriptivo_valido(valor: str) -> bool:
    return any(caracter.isalpha() for caracter in valor) and all(
        caracter.isalnum() or caracter in PUNTUACION_DESCRIPTIVA
        for caracter in valor
    )


def validar_domicilio(valor: str) -> str | None:
    v = valor.strip()
    if len(v) < 10:
        return "Escribe calle, número, colonia, ciudad y estado"
    if len(v) > 255:
        return "El domicilio no puede exceder 255 caracteres"
    if not _texto_descriptivo_valido(v):
        return "El domicilio debe contener texto"
    return None


def validar_preparatoria(valor: str) -> str | None:
    v = valor.strip()
    if not 3 <= len(v) <= 100:
        return "Nombre de la preparatoria: de 3 a 100 caracteres"
    if not _texto_descriptivo_valido(v):
        return "El nombre de la preparatoria debe contener texto"
    return None


def validar_promedio(valor: str) -> str | None:
    texto = valor.strip().replace(",", ".")
    if not PATRON_PROMEDIO.fullmatch(texto):
        return "Promedio inválido"
    try:
        promedio = float(texto)
    except ValueError:
        return "Promedio inválido"
    if not PROMEDIO_MIN <= promedio <= PROMEDIO_MAX:
        return f"Ingresa un promedio del {PROMEDIO_MIN} al {PROMEDIO_MAX}"
    return None


def validar_ine(valor: str | None, fecha: datetime.date | None = None) -> str | None:
    """Clave de elector: 6 letras + AAMMDD + entidad (2) + H/M + 3 dígitos = 18."""
    if not valor or not valor.strip():
        return None
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


def validar_tipo_sangre(valor: str | None) -> str | None:
    if valor not in TIPOS_SANGRE:
        return "Selecciona un tipo de sangre válido"
    return None


def validar_celular_emergencia(valor: str, celular_alumno: str = "") -> str | None:
    err = validar_celular(valor)
    if err:
        return err
    limpio = lambda t: re.sub(r"[\s-]", "", t)
    if celular_alumno and limpio(valor) == limpio(celular_alumno):
        return "Debe ser distinto al celular del alumno"
    return None


def validar_correo_emergencia(
    valor: str,
    correo_alumno: str = "",
    maximo: int = 150,
) -> str | None:
    err = validar_correo_con_dominio(valor, maximo)
    if err:
        return err
    if correo_alumno and valor.strip().lower() == correo_alumno.strip().lower():
        return "Debe ser distinto al correo personal del alumno"
    return None


def validar_alergias(valor: str) -> str | None:
    """Opcional; vacío equivale a «Ninguna»."""
    v = valor.strip()
    if len(v) > 200:
        return "Máximo 200 caracteres"
    if v and not _texto_descriptivo_valido(v):
        return "Describe la alergia con texto o escribe «Ninguna»"
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


def prefijo_control(anio: int, numero_tecnologico: int) -> str:
    """Prefijo de cuatro dígitos: año de dos dígitos y tecnológico de dos."""
    if not 0 <= numero_tecnologico <= 99:
        raise ValueError("El número de tecnológico debe tener dos dígitos")
    return f"{anio % 100:02d}{numero_tecnologico:02d}"


def siguiente_carrera_secuencia(
    ultimo_sufijo: int | None,
    numero_carrera_inicial: int,
) -> tuple[int, int]:
    """Avanza carrera(2)+secuencia(2), empezando en la carrera indicada y 00."""
    if not 0 <= numero_carrera_inicial <= 99:
        raise ValueError("El número de carrera debe tener dos dígitos")
    inicial = numero_carrera_inicial * 100
    siguiente = max(inicial, (ultimo_sufijo + 1) if ultimo_sufijo is not None else inicial)
    if siguiente > 9999:
        raise OverflowError("Se agotaron los números de control disponibles")
    return divmod(siguiente, 100)


def generar_numero_control(
    anio: int,
    numero_tecnologico: int,
    numero_carrera: int,
    consecutivo: int,
) -> str:
    """Genera YY + tecnológico(2) + carrera(2) + consecutivo(2)."""
    if not 0 <= numero_carrera <= 99:
        raise ValueError("El número de carrera debe tener dos dígitos")
    if not 0 <= consecutivo <= 99:
        raise ValueError("El consecutivo debe tener dos dígitos")
    return (
        f"{prefijo_control(anio, numero_tecnologico)}"
        f"{numero_carrera:02d}{consecutivo:02d}"
    )


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
