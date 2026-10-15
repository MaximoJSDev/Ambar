"""Generación de reportes PDF de expedientes escolares."""
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
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
        ("Identificación electoral", personales.get("ine")),
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
