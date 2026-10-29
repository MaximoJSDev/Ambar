"""Generación de reportes PDF de expedientes escolares."""
from datetime import date
from io import BytesIO
from pathlib import Path
import unicodedata
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#17345C")
GOLD = colors.HexColor("#C99435")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#D8DEE8")
GREEN = colors.HexColor("#16805A")
ORANGE = colors.HexColor("#A76412")
MEMBRETE = Path(__file__).resolve().parent / "assets" / "membrete_institucional.png"


def _texto(valor: object) -> str:
    texto = "—" if valor is None or str(valor).strip() == "" else str(valor)
    return escape(texto).replace("\n", "<br/>")


def _clave_orden_alumno(alumno: dict) -> tuple[str, str, str, str]:
    def normalizar(valor: object) -> str:
        texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
        return "".join(caracter for caracter in texto if not unicodedata.combining(caracter))

    nombre = alumno.get("nombre_completo", "")
    return (
        normalizar(alumno.get("apellido_paterno") or nombre),
        normalizar(alumno.get("apellido_materno")),
        normalizar(alumno.get("nombres")),
        normalizar(alumno.get("numero_control")),
    )


def _nombre_alumno(alumno: dict) -> str:
    apellidos_y_nombres = (
        alumno.get("apellido_paterno"),
        alumno.get("apellido_materno"),
        alumno.get("nombres"),
    )
    return " ".join(filter(None, apellidos_y_nombres)) or alumno.get("nombre_completo", "")


def _crear_estilos():
    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(
        name="ReportTitle",
        parent=estilos["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=NAVY,
        spaceAfter=2 * mm,
    ))
    estilos.add(ParagraphStyle(
        name="ReportName",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=NAVY,
        alignment=TA_LEFT,
    ))
    estilos.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=MUTED,
    ))
    estilos.add(ParagraphStyle(
        name="ReportDate",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=MUTED,
        alignment=TA_RIGHT,
    ))
    estilos.add(ParagraphStyle(
        name="ReportSection",
        parent=estilos["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=NAVY,
        spaceBefore=4 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    ))
    estilos.add(ParagraphStyle(
        name="ReportField",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1B2A41"),
        wordWrap="CJK",
    ))
    estilos.add(ParagraphStyle(
        name="ReportDocument",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1B2A41"),
        wordWrap="CJK",
    ))
    estilos.add(ParagraphStyle(
        name="ReportSmall",
        parent=estilos["BodyText"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=MUTED,
    ))
    return estilos


def _campo(etiqueta: str, valor: object, estilo: ParagraphStyle) -> Paragraph:
    return Paragraph(
        f'<font size="7" color="#64748B">{_texto(etiqueta)}</font><br/>'
        f"<b>{_texto(valor)}</b>",
        estilo,
    )


def _seccion(
    titulo: str,
    campos: list[tuple[str, object]],
    ancho: float,
    estilos,
) -> list:
    titulo_parrafo = Paragraph(titulo, estilos["ReportSection"])
    celdas = [
        _campo(etiqueta, valor, estilos["ReportField"])
        for etiqueta, valor in campos
    ]
    if len(celdas) % 2:
        celdas.append(Paragraph("", estilos["ReportField"]))

    filas = [
        [celdas[indice], "", celdas[indice + 1]]
        for indice in range(0, len(celdas), 2)
    ]
    tabla = Table(
        filas,
        colWidths=[(ancho - 8 * mm) / 2, 8 * mm, (ancho - 8 * mm) / 2],
        hAlign="LEFT",
    )
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [KeepTogether([titulo_parrafo, tabla])]


def generar_expediente_pdf(datos: dict) -> bytes:
    """Genera un expediente imprimible con membrete institucional y datos agrupados."""
    if not MEMBRETE.is_file():
        raise FileNotFoundError(f"No se encontró la imagen del membrete: {MEMBRETE}")

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=41 * mm,
        bottomMargin=19 * mm,
        title=f"Expediente escolar {datos['numero_control']}",
        author="Sistema Integral de Gestión Escolar",
    )
    estilos = _crear_estilos()
    ancho_contenido = letter[0] - documento.leftMargin - documento.rightMargin

    academicos = datos.get("academicos", {})
    elementos = [
        Paragraph("EXPEDIENTE DEL ESTUDIANTE", estilos["ReportTitle"]),
    ]
    identidad = Table(
        [[
            [
                Paragraph(_texto(datos.get("nombre_completo")), estilos["ReportName"]),
                Spacer(1, 1.5 * mm),
                Paragraph(
                    f"Número de control: <b>{_texto(datos.get('numero_control'))}</b>",
                    estilos["ReportSubtitle"],
                ),
            ],
            Paragraph(
                f"Generado el<br/><b>{date.today().strftime('%d/%m/%Y')}</b>",
                estilos["ReportDate"],
            ),
        ]],
        colWidths=[ancho_contenido - 35 * mm, 35 * mm],
        hAlign="LEFT",
    )
    identidad.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, GOLD),
    ]))
    elementos.extend([identidad, Spacer(1, 1 * mm)])

    personales = datos.get("personales", {})
    elementos.extend(_seccion("Datos personales", [
        ("Fecha de nacimiento", personales.get("fecha_nacimiento")),
        ("Género", personales.get("genero")),
        ("CURP", personales.get("curp")),
        ("RFC", personales.get("rfc")),
        ("IDMEX", personales.get("ine")),
        ("Número de seguro social", personales.get("nss")),
    ], ancho_contenido, estilos))

    contacto = datos.get("contacto", {})
    elementos.extend(_seccion("Contacto y salud", [
        ("Domicilio", contacto.get("domicilio")),
        ("Teléfono celular", contacto.get("celular")),
        ("Correo personal", contacto.get("correo_personal")),
        ("Correo institucional", contacto.get("correo_institucional")),
        ("Teléfono de emergencia", contacto.get("celular_emergencia")),
        ("Correo de emergencia", contacto.get("correo_emergencia")),
        ("Tipo de sangre", contacto.get("tipo_sangre")),
        ("Alergias o información de salud", contacto.get("alergias")),
    ], ancho_contenido, estilos))

    elementos.extend(_seccion("Trayectoria académica", [
        ("Número de ficha", academicos.get("numero_ficha")),
        ("Escuela de procedencia", academicos.get("preparatoria")),
        ("Promedio de bachillerato", academicos.get("promedio")),
        ("Turno", academicos.get("turno")),
        ("Semestre actual", academicos.get("semestre")),
        ("Grupo", academicos.get("grupo")),
        ("Periodo escolar", academicos.get("periodo")),
        ("Situación escolar", academicos.get("estatus", datos.get("estatus"))),
        ("Motivo de baja", academicos.get("motivo_baja")),
    ], ancho_contenido, estilos))

    documentos = datos.get("documentos", [])
    elementos.append(Paragraph("Documentación del expediente", estilos["ReportSection"]))
    if documentos:
        celdas_documentos = []
        for doc in documentos:
            recibido = doc.get("estado") == "Recibido"
            estado = "Integrado al expediente" if recibido else "Pendiente de integrar"
            color_estado = GREEN.hexval() if recibido else ORANGE.hexval()
            celdas_documentos.append(Paragraph(
                f"<b>{_texto(doc.get('documento'))}</b><br/>"
                f'<font size="7" color="{color_estado}">{estado}</font>',
                estilos["ReportDocument"],
            ))
        if len(celdas_documentos) % 2:
            celdas_documentos.append(Paragraph("", estilos["ReportDocument"]))
        filas_documentos = [
            [celdas_documentos[indice], "", celdas_documentos[indice + 1]]
            for indice in range(0, len(celdas_documentos), 2)
        ]
        lista_documentos = Table(
            filas_documentos,
            colWidths=[
                (ancho_contenido - 8 * mm) / 2,
                8 * mm,
                (ancho_contenido - 8 * mm) / 2,
            ],
            hAlign="LEFT",
        )
        lista_documentos.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elementos.append(lista_documentos)
    else:
        elementos.append(Paragraph(
            "No hay documentos asociados a este expediente.",
            estilos["ReportSmall"],
        ))

    def dibujar_membrete(canvas, doc):
        canvas.saveState()
        ancho, alto = letter
        imagen = ImageReader(str(MEMBRETE))
        imagen_ancho, imagen_alto = imagen.getSize()
        membrete_alto = ancho * imagen_alto / imagen_ancho
        canvas.drawImage(
            imagen,
            0,
            alto - membrete_alto,
            width=ancho,
            height=membrete_alto,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 15 * mm, ancho - doc.rightMargin, 15 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(doc.leftMargin, 10.5 * mm, "Este documento no tiene validez oficial.")
        canvas.drawRightString(ancho - doc.rightMargin, 10.5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    documento.build(
        elementos,
        onFirstPage=dibujar_membrete,
        onLaterPages=dibujar_membrete,
    )
    return buffer.getvalue()


def _dibujar_membrete(canvas, documento):
    canvas.saveState()
    ancho, alto = documento.pagesize
    imagen = ImageReader(str(MEMBRETE))
    imagen_ancho, imagen_alto = imagen.getSize()
    membrete_alto = ancho * imagen_alto / imagen_ancho
    canvas.drawImage(
        imagen,
        0,
        alto - membrete_alto,
        width=ancho,
        height=membrete_alto,
        preserveAspectRatio=True,
        mask="auto",
    )
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(documento.leftMargin, 15 * mm, ancho - documento.rightMargin, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(documento.leftMargin, 10.5 * mm, "Este documento no tiene validez oficial.")
    canvas.drawRightString(ancho - documento.rightMargin, 10.5 * mm, f"Página {documento.page}")
    canvas.restoreState()


def _documento_horario(buffer: BytesIO, titulo: str, autor: str) -> SimpleDocTemplate:
    if not MEMBRETE.is_file():
        raise FileNotFoundError(f"No se encontró la imagen del membrete: {MEMBRETE}")
    return SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=39 * mm,
        bottomMargin=19 * mm,
        title=titulo,
        author=autor,
    )


def _estilo_tabla_horario() -> ParagraphStyle:
    return ParagraphStyle(
        name="HorarioTable",
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#1B2A41"),
        wordWrap="CJK",
    )


def generar_horario_alumno_pdf(datos: dict) -> bytes:
    """Genera el horario individual del alumno con membrete institucional."""
    buffer = BytesIO()
    documento = _documento_horario(
        buffer,
        f"Horario {datos['alumno']['numero_control']}",
        "Sistema Integral de Gestión Escolar",
    )
    estilos = _crear_estilos()
    estilo_tabla = _estilo_tabla_horario()
    alumno = datos["alumno"]
    paquete = datos["paquete"]
    encabezados = ["Asignatura", "Horario semanal", "Aula", "Docente", "Créditos"]
    filas = [[
        Paragraph(f'<font color="#FFFFFF"><b>{texto}</b></font>', estilo_tabla)
        for texto in encabezados
    ]]
    for materia in datos["materias"]:
        horarios = "<br/>".join(
            f"{_texto(horario['dia'])}: {_texto(horario['inicio'])}–{_texto(horario['fin'])}"
            for horario in materia["horarios"]
        ) or "Sin horario"
        filas.append([
            Paragraph(_texto(materia["nombre_materia"]), estilo_tabla),
            Paragraph(horarios, estilo_tabla),
            Paragraph(_texto(materia["aula"]), estilo_tabla),
            Paragraph(_texto(materia["docente"]), estilo_tabla),
            Paragraph(_texto(materia["creditos"]), estilo_tabla),
        ])

    tabla = Table(
        filas,
        colWidths=[53 * mm, 78 * mm, 22 * mm, 76 * mm, 19 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos = [
        Paragraph("HORARIO DEL ESTUDIANTE", estilos["ReportTitle"]),
        Paragraph(
            f"<b>{_texto(alumno['nombre_completo'])}</b> · "
            f"Número de control: <b>{_texto(alumno['numero_control'])}</b>",
            estilos["ReportSubtitle"],
        ),
        Paragraph(
            f"Semestre: <b>{_texto(alumno['semestre'])}</b> · "
            f"Grupo: <b>{_texto(paquete['nombre'])}</b> · "
            f"Periodo: <b>{_texto(paquete['periodo'])}</b>",
            estilos["ReportSubtitle"],
        ),
        Spacer(1, 4 * mm),
        tabla,
    ]
    documento.build(elementos, onFirstPage=_dibujar_membrete, onLaterPages=_dibujar_membrete)
    return buffer.getvalue()


def generar_lista_grupo_pdf(datos: dict) -> bytes:
    """Genera la lista de alumnos inscritos en una sección con membrete."""
    buffer = BytesIO()
    paquete = datos["paquete"]
    documento = _documento_horario(
        buffer,
        f"Lista {paquete['nombre']}",
        "Sistema Integral de Gestión Escolar",
    )
    estilos = _crear_estilos()
    estilo_tabla = _estilo_tabla_horario()
    filas = [[
        Paragraph('<font color="#FFFFFF"><b>No.</b></font>', estilo_tabla),
        Paragraph('<font color="#FFFFFF"><b>Número de control</b></font>', estilo_tabla),
        Paragraph('<font color="#FFFFFF"><b>Apellidos y nombre(s)</b></font>', estilo_tabla),
        Paragraph('<font color="#FFFFFF"><b>Correo institucional</b></font>', estilo_tabla),
    ]]
    alumnos = sorted(datos["alumnos"], key=_clave_orden_alumno)
    for indice, alumno in enumerate(alumnos, 1):
        nombre = " ".join(
            parte for parte in (
                alumno["apellido_paterno"], alumno["apellido_materno"], alumno["nombres"],
            ) if parte
        )
        filas.append([
            Paragraph(str(indice), estilo_tabla),
            Paragraph(_texto(alumno["numero_control"]), estilo_tabla),
            Paragraph(_texto(nombre), estilo_tabla),
            Paragraph(_texto(alumno["correo_institucional"]), estilo_tabla),
        ])

    tabla = Table(
        filas,
        colWidths=[15 * mm, 43 * mm, 110 * mm, 80 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos = [
        Paragraph("LISTA DE ALUMNOS POR GRUPO", estilos["ReportTitle"]),
        Paragraph(
            f"Grupo: <b>{_texto(paquete['nombre'])}</b> · "
            f"Semestre: <b>{_texto(paquete['semestre'])}</b> · "
            f"Periodo: <b>{_texto(paquete['periodo'])}</b>",
            estilos["ReportSubtitle"],
        ),
        Paragraph(
            f"Alumnos inscritos: <b>{len(datos['alumnos'])}</b>",
            estilos["ReportSubtitle"],
        ),
        Spacer(1, 4 * mm),
        tabla,
    ]
    documento.build(elementos, onFirstPage=_dibujar_membrete, onLaterPages=_dibujar_membrete)
    return buffer.getvalue()


def generar_grupos_docente_pdf(datos: dict) -> bytes:
    """Genera el horario de los grupos asignados a un docente."""
    buffer = BytesIO()
    docente = datos["docente"]
    documento = _documento_horario(
        buffer,
        f"Grupos y horarios {docente}",
        "Sistema Integral de Gestión Escolar",
    )
    estilos = _crear_estilos()
    estilo = _estilo_tabla_horario()
    filas = [[
        Paragraph(f'<font color="#FFFFFF"><b>{_texto(titulo)}</b></font>', estilo)
        for titulo in ("Grupo", "Materia", "Horario", "Aula", "Turno", "Periodo")
    ]]
    for grupo in datos["grupos"]:
        horarios = "<br/>".join(
            f"{_texto(item['dia'])}: {_texto(item['inicio'])}–{_texto(item['fin'])}"
            for item in grupo["horarios"]
        ) or "Sin horario publicado"
        filas.append([
            Paragraph(_texto(grupo["grupo"]), estilo),
            Paragraph(_texto(grupo["nombre_materia"]), estilo),
            Paragraph(horarios, estilo),
            Paragraph(_texto(grupo["aula"]), estilo),
            Paragraph(_texto(grupo["turno"]), estilo),
            Paragraph(_texto(grupo["periodo"]), estilo),
        ])

    tabla = Table(
        filas,
        colWidths=[26 * mm, 65 * mm, 75 * mm, 25 * mm, 28 * mm, 34 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos = [
        Paragraph("GRUPOS Y HORARIOS DEL DOCENTE", estilos["ReportTitle"]),
        Paragraph(
            f"Docente: <b>{_texto(docente)}</b> · "
            f"Grupos asignados: <b>{len(datos['grupos'])}</b>",
            estilos["ReportSubtitle"],
        ),
        Spacer(1, 4 * mm),
        tabla,
    ]
    documento.build(elementos, onFirstPage=_dibujar_membrete, onLaterPages=_dibujar_membrete)
    return buffer.getvalue()


def generar_lista_docente_pdf(datos: dict, incluir_calificaciones: bool = False) -> bytes:
    """Genera una lista membretada de alumnos o de calificaciones de un grupo docente."""
    buffer = BytesIO()
    grupo = datos
    docente = grupo["docente"]
    documento = _documento_horario(
        buffer,
        f"Lista {grupo['grupo']} {grupo['nombre_materia']}",
        "Sistema Integral de Gestión Escolar",
    )
    estilos = _crear_estilos()
    estilo = _estilo_tabla_horario()
    encabezados = ["No.", "Número de control", "Alumno"]
    anchos = [15 * mm, 40 * mm, 105 * mm]
    if incluir_calificaciones:
        encabezados.extend(("Sem. 5", "Sem. 9", "Sem. 13", "Final"))
        anchos.extend([23 * mm] * 4)
    filas = [[
        Paragraph(f'<font color="#FFFFFF"><b>{_texto(titulo)}</b></font>', estilo)
        for titulo in encabezados
    ]]
    alumnos = sorted(grupo["alumnos"], key=_clave_orden_alumno)
    for indice, alumno in enumerate(alumnos, 1):
        fila = [
            Paragraph(str(indice), estilo),
            Paragraph(_texto(alumno["numero_control"]), estilo),
            Paragraph(_texto(_nombre_alumno(alumno)), estilo),
        ]
        if incluir_calificaciones:
            fila.extend(
                Paragraph(
                    "—" if alumno[campo] is None else _texto(int(alumno[campo])),
                    estilo,
                )
                for campo in ("semana_5", "semana_9", "semana_13", "final")
            )
        filas.append(fila)

    tabla = Table(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos = [
        Paragraph(
            "LISTA DE CALIFICACIONES" if incluir_calificaciones else "LISTA DE ALUMNOS",
            estilos["ReportTitle"],
        ),
        Paragraph(
            f"Docente: <b>{_texto(docente)}</b> · Grupo: <b>{_texto(grupo['grupo'])}</b> · "
            f"Materia: <b>{_texto(grupo['nombre_materia'])}</b>",
            estilos["ReportSubtitle"],
        ),
        Paragraph(
            f"Periodo: <b>{_texto(grupo['periodo'])}</b> · "
            f"Alumnos: <b>{len(alumnos)}</b>",
            estilos["ReportSubtitle"],
        ),
        Spacer(1, 4 * mm),
        tabla,
    ]
    documento.build(elementos, onFirstPage=_dibujar_membrete, onLaterPages=_dibujar_membrete)
    return buffer.getvalue()
