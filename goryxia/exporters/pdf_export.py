"""Exportacion a PDF: informe ejecutivo + lista priorizada de llamadas.

El PDF no pretende replicar la base completa (para eso estan el Excel y el
CSV): es el documento que el comercial imprime o abre en el celular para
empezar a marcar, con los mejores leads primero.
"""
from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..config import PDF_PATH
from ..models import Negocio
from ..resumen import Resumen, construir, kpis

log = logging.getLogger(__name__)

AZUL = colors.HexColor("#1F3864")
VERDE = colors.HexColor("#C6EFCE")
GRIS = colors.HexColor("#F2F2F2")

MAX_LEADS_PDF = 600


def _estilos():
    hojas = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=hojas["Title"], textColor=AZUL,
                                 fontSize=20, spaceAfter=4),
        "subtitulo": ParagraphStyle("subtitulo", parent=hojas["Heading2"],
                                    textColor=AZUL, fontSize=13, spaceBefore=10,
                                    spaceAfter=6),
        "normal": ParagraphStyle("cuerpo", parent=hojas["Normal"], fontSize=9,
                                 leading=12, alignment=TA_LEFT),
        "pie": ParagraphStyle("pie", parent=hojas["Normal"], fontSize=8,
                              textColor=colors.grey),
        "celda": ParagraphStyle("celda", parent=hojas["Normal"], fontSize=7.2,
                                leading=8.6),
    }


def _estilo_tabla(cabecera_repetida: bool = True) -> TableStyle:
    ordenes = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, -1), 7.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BFBFBF")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    return TableStyle(ordenes)


def _pie_de_pagina(canvas, documento):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    ancho, _ = documento.pagesize
    canvas.drawString(15 * mm, 10 * mm,
                      "Base de Clientes GoryxIA - Bogota D.C. | Datos de fuentes publicas")
    canvas.drawRightString(ancho - 15 * mm, 10 * mm, f"Pagina {canvas.getPageNumber()}")
    canvas.restoreState()


def _tabla_resumen(resumen: Resumen, estilos) -> list:
    elementos = []

    filas = [["Indicador", "Valor", "%", "Lectura comercial"]]
    for etiqueta, valor, comentario in kpis(resumen):
        porcentaje = f"{round(100 * valor / resumen.total, 1)}%" if resumen.total else "-"
        filas.append([etiqueta, f"{valor:,}".replace(",", "."), porcentaje,
                      Paragraph(comentario, estilos["celda"])])

    tabla = Table(filas, colWidths=[62 * mm, 24 * mm, 20 * mm, 145 * mm], repeatRows=1)
    tabla.setStyle(_estilo_tabla())
    elementos.append(tabla)

    if resumen.por_localidad:
        elementos.append(Paragraph("Cobertura por localidad", estilos["subtitulo"]))
        filas = [["Localidad", "Negocios", "Con celular", "% con celular"]]
        for localidad, total, celulares in resumen.por_localidad:
            pct = f"{round(100 * celulares / total, 1)}%" if total else "-"
            filas.append([localidad, str(total), str(celulares), pct])
        tabla = Table(filas, colWidths=[70 * mm, 35 * mm, 35 * mm, 35 * mm], repeatRows=1)
        tabla.setStyle(_estilo_tabla())
        elementos.append(tabla)

    if resumen.por_categoria:
        elementos.append(Paragraph("Cobertura por categoria", estilos["subtitulo"]))
        filas = [["Categoria", "Negocios", "Con celular", "% con celular"]]
        for categoria, total, celulares in resumen.por_categoria:
            pct = f"{round(100 * celulares / total, 1)}%" if total else "-"
            filas.append([categoria, str(total), str(celulares), pct])
        tabla = Table(filas, colWidths=[70 * mm, 35 * mm, 35 * mm, 35 * mm], repeatRows=1)
        tabla.setStyle(_estilo_tabla())
        elementos.append(tabla)

    return elementos


def _tabla_leads(negocios: list[Negocio], estilos, maximo: int) -> list:
    seleccion = negocios[:maximo]
    filas = [["#", "Negocio", "Categoria", "Localidad", "Telefono / WhatsApp",
              "Correo y web", "Pri.", "Que ofrecerle"]]

    for indice, negocio in enumerate(seleccion, start=1):
        contacto = negocio.telefono_principal or "-"
        if negocio.whatsapp:
            contacto += "\nWhatsApp: si"
        digital = negocio.correo or ""
        if negocio.sitio_web:
            digital = f"{digital}\n{negocio.sitio_web}" if digital else negocio.sitio_web
        filas.append([
            str(indice),
            Paragraph(negocio.nombre[:70], estilos["celda"]),
            Paragraph(negocio.categoria, estilos["celda"]),
            Paragraph(negocio.localidad or "-", estilos["celda"]),
            Paragraph(contacto.replace("\n", "<br/>"), estilos["celda"]),
            Paragraph((digital or "-")[:70].replace("\n", "<br/>"), estilos["celda"]),
            negocio.prioridad[:1] or "-",
            Paragraph(negocio.servicios, estilos["celda"]),
        ])

    tabla = Table(
        filas,
        colWidths=[10 * mm, 52 * mm, 24 * mm, 24 * mm, 34 * mm, 46 * mm, 10 * mm, 55 * mm],
        repeatRows=1,
    )
    estilo = _estilo_tabla()
    # Resalta en verde los leads con WhatsApp: son los de accion inmediata.
    for numero, negocio in enumerate(seleccion, start=1):
        if negocio.tiene_celular:
            estilo.add("BACKGROUND", (4, numero), (4, numero), VERDE)
    tabla.setStyle(estilo)
    return [tabla]


def exportar_pdf(negocios: list[Negocio], ruta: Path = PDF_PATH,
                 resumen: Resumen | None = None,
                 max_leads: int = MAX_LEADS_PDF) -> Path:
    """Genera el informe PDF ejecutivo con la lista priorizada de contacto."""
    resumen = resumen or construir(negocios)
    estilos = _estilos()

    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento = SimpleDocTemplate(
        str(ruta),
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title="Base de Clientes GoryxIA - Bogota D.C.",
        author="GoryxIA",
    )

    elementos: list = [
        Paragraph("Base de Clientes GoryxIA", estilos["titulo"]),
        Paragraph(
            f"Prospeccion comercial de PYMEs en Bogota D.C. &nbsp;|&nbsp; "
            f"Generada el {resumen.generado} &nbsp;|&nbsp; "
            f"Distancias medidas desde {resumen.referencia}",
            estilos["pie"]),
        Spacer(1, 6 * mm),
        Paragraph("Resumen ejecutivo", estilos["subtitulo"]),
        Paragraph(
            f"La base contiene <b>{resumen.total:,}</b> negocios unicos de Bogota "
            f"obtenidos de fuentes publicas. De ellos, <b>{resumen.con_celular:,}</b> "
            f"({resumen.pct_celular}%) tienen celular y por tanto WhatsApp probable, "
            f"y <b>{resumen.contactables:,}</b> ({resumen.pct_contactables}%) se pueden "
            "contactar hoy mismo por telefono o correo. La lista de llamadas de las "
            "paginas siguientes esta ordenada por contactabilidad: primero celular, "
            "luego correo, luego web."
            .replace(",", "."),
            estilos["normal"]),
        Spacer(1, 4 * mm),
    ]
    elementos.extend(_tabla_resumen(resumen, estilos))
    elementos.append(PageBreak())

    total_mostrados = min(len(negocios), max_leads)
    elementos.append(Paragraph(
        f"Lista priorizada de contacto (primeros {total_mostrados} de "
        f"{resumen.total:,} registros)".replace(",", "."), estilos["subtitulo"]))
    elementos.append(Paragraph(
        "Resaltado en verde: negocios con celular, listos para escribir por WhatsApp. "
        "Columna Pri.: A = alta, M = media, B = baja. "
        "La base completa esta en el Excel y el CSV.", estilos["pie"]))
    elementos.append(Spacer(1, 3 * mm))
    elementos.extend(_tabla_leads(negocios, estilos, max_leads))

    documento.build(elementos, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    log.info("PDF escrito: %s (%s leads listados)", ruta, total_mostrados)
    return ruta
