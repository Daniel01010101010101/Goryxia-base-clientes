"""Exportacion a Excel con dos hojas: Clientes y Dashboard.

La hoja Clientes esta pensada para que un comercial trabaje directamente sobre
ella: filtros activos, panel congelado, enlaces de WhatsApp clicables y las
filas de mayor prioridad resaltadas.
"""
from __future__ import annotations

import logging
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ..config import COLUMNAS, XLSX_PATH
from ..models import Negocio
from ..resumen import Resumen, construir, kpis

log = logging.getLogger(__name__)

# Paleta corporativa sobria: azul profundo + acentos legibles en pantalla.
AZUL = "FF1F3864"
VERDE = "FFC6EFCE"
AMARILLO = "FFFFEB9C"
BLANCO = "FFFFFFFF"

FUENTE_TITULO = Font(name="Calibri", size=16, bold=True, color=AZUL)
FUENTE_CABECERA = Font(name="Calibri", size=11, bold=True, color=BLANCO)
FUENTE_SUBTITULO = Font(name="Calibri", size=12, bold=True, color=AZUL)
RELLENO_CABECERA = PatternFill("solid", fgColor=AZUL)
RELLENO_ALTA = PatternFill("solid", fgColor=VERDE)
RELLENO_MEDIA = PatternFill("solid", fgColor=AMARILLO)
BORDE_FINO = Border(*[Side(style="thin", color="FFBFBFBF")] * 4)

ANCHOS = {
    "ID": 14, "Nombre del negocio": 38, "Categoria": 18, "Grupo": 20,
    "Direccion": 30, "Barrio": 20, "Localidad": 18, "Ciudad": 14,
    "Distancia aprox. (km)": 12, "Telefono": 32, "WhatsApp": 18,
    "Link WhatsApp": 30, "Correo electronico": 30, "Sitio web": 32,
    "Facebook": 28, "Instagram": 28, "LinkedIn": 28,
    "Horario de atencion": 26, "Calificacion Google": 10, "N Resenas": 10,
    "Propietario / Gerente": 24, "Persona de contacto": 22,
    "Presencia digital": 14, "Score Contacto": 12,
    "Servicios sugeridos": 46, "Observaciones comerciales": 60,
    "Prioridad": 12, "Fuente": 26, "place_id": 22, "lat": 12, "lon": 12,
}

MAX_HIPERVINCULOS = 60000  # Excel se degrada con demasiados enlaces por hoja


def _hoja_clientes(libro: Workbook, negocios: list[Negocio]) -> Worksheet:
    hoja = libro.create_sheet("Clientes")

    hoja.append(COLUMNAS)
    for indice, columna in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=indice)
        celda.font = FUENTE_CABECERA
        celda.fill = RELLENO_CABECERA
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        hoja.column_dimensions[get_column_letter(indice)].width = ANCHOS.get(columna, 18)
    hoja.row_dimensions[1].height = 30

    col_link = COLUMNAS.index("Link WhatsApp") + 1
    col_web = COLUMNAS.index("Sitio web") + 1
    col_prioridad = COLUMNAS.index("Prioridad") + 1
    enlaces = 0

    for negocio in negocios:
        fila = negocio.a_fila()
        hoja.append([fila.get(columna) for columna in COLUMNAS])
        n = hoja.max_row

        # Resalta por prioridad comercial: verde = llamar ya.
        if fila.get("Prioridad") == "ALTA":
            relleno = RELLENO_ALTA
        elif fila.get("Prioridad") == "MEDIA":
            relleno = RELLENO_MEDIA
        else:
            relleno = None
        if relleno:
            hoja.cell(row=n, column=col_prioridad).fill = relleno

        if enlaces < MAX_HIPERVINCULOS:
            link = fila.get("Link WhatsApp")
            if link:
                celda = hoja.cell(row=n, column=col_link)
                celda.hyperlink = link
                celda.style = "Hyperlink"
                enlaces += 1
            web = fila.get("Sitio web")
            if web:
                celda = hoja.cell(row=n, column=col_web)
                celda.hyperlink = web
                celda.style = "Hyperlink"
                enlaces += 1

    hoja.freeze_panes = "C2"
    if hoja.max_row > 1:
        hoja.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS))}{hoja.max_row}"
    return hoja


def _escribir_tabla(hoja: Worksheet, fila_inicio: int, titulo: str,
                    cabeceras: list[str], filas: list[tuple]) -> int:
    """Pinta una tabla con titulo y devuelve la siguiente fila libre."""
    celda = hoja.cell(row=fila_inicio, column=1, value=titulo)
    celda.font = FUENTE_SUBTITULO
    fila = fila_inicio + 1

    for indice, cabecera in enumerate(cabeceras, start=1):
        celda = hoja.cell(row=fila, column=indice, value=cabecera)
        celda.font = FUENTE_CABECERA
        celda.fill = RELLENO_CABECERA
        celda.alignment = Alignment(horizontal="center")
    fila += 1

    for valores in filas:
        for indice, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=indice, value=valor)
            celda.border = BORDE_FINO
            if indice > 1:
                celda.alignment = Alignment(horizontal="center")
        fila += 1

    return fila + 1


def _hoja_dashboard(libro: Workbook, resumen: Resumen) -> Worksheet:
    hoja = libro.create_sheet("Dashboard", 0)
    hoja.sheet_view.showGridLines = False

    hoja["A1"] = "Base de Clientes GoryxIA - Bogota D.C."
    hoja["A1"].font = FUENTE_TITULO
    hoja["A2"] = (f"Generada el {resumen.generado} | Fuentes publicas | "
                  f"Distancias medidas desde: {resumen.referencia}")
    hoja["A2"].font = Font(size=10, italic=True, color="FF595959")

    for ancho, columna in zip((38, 16, 16, 46), "ABCD"):
        hoja.column_dimensions[columna].width = ancho

    # --- KPIs ------------------------------------------------------------
    fila = 4
    hoja.cell(row=fila, column=1, value="Indicadores clave").font = FUENTE_SUBTITULO
    fila += 1
    for etiqueta, cabecera in zip(("Indicador", "Valor", "%", "Lectura comercial"), "ABCD"):
        celda = hoja[f"{cabecera}{fila}"]
        celda.value = etiqueta
        celda.font = FUENTE_CABECERA
        celda.fill = RELLENO_CABECERA
    fila += 1

    for etiqueta, valor, comentario in kpis(resumen):
        hoja.cell(row=fila, column=1, value=etiqueta).border = BORDE_FINO
        celda_valor = hoja.cell(row=fila, column=2, value=valor)
        celda_valor.font = Font(bold=True, size=12, color=AZUL)
        celda_valor.alignment = Alignment(horizontal="center")
        celda_valor.border = BORDE_FINO
        porcentaje = round(100 * valor / resumen.total, 1) if resumen.total else 0
        celda_pct = hoja.cell(row=fila, column=3, value=porcentaje / 100)
        celda_pct.number_format = "0.0%"
        celda_pct.alignment = Alignment(horizontal="center")
        celda_pct.border = BORDE_FINO
        hoja.cell(row=fila, column=4, value=comentario).border = BORDE_FINO
        fila += 1

    fila += 1
    fila_localidades = fila + 1
    fila = _escribir_tabla(
        hoja, fila, "Cobertura por localidad (ordenada por celulares obtenidos)",
        ["Localidad", "Negocios", "Con celular"], resumen.por_localidad)

    fila_categorias = fila + 1
    fila = _escribir_tabla(
        hoja, fila, "Cobertura por categoria",
        ["Categoria", "Negocios", "Con celular"], resumen.por_categoria)

    fila_prioridad = fila + 1
    fila = _escribir_tabla(
        hoja, fila, "Prioridad comercial",
        ["Prioridad", "Negocios"], resumen.por_prioridad)

    fila = _escribir_tabla(
        hoja, fila, "Presencia digital",
        ["Presencia", "Negocios"], resumen.por_presencia)

    fila = _escribir_tabla(
        hoja, fila, "Distribucion del score de contacto",
        ["Score", "Negocios"], resumen.por_score)

    fila = _escribir_tabla(
        hoja, fila, "Origen de los datos",
        ["Fuente", "Registros"], resumen.por_fuente)

    # --- Graficas --------------------------------------------------------
    if resumen.por_localidad:
        grafico = BarChart()
        grafico.type = "bar"
        grafico.title = "Negocios con celular por localidad"
        grafico.height, grafico.width = 11, 18
        n = len(resumen.por_localidad)
        datos = Reference(hoja, min_col=3, min_row=fila_localidades,
                          max_row=fila_localidades + n)
        categorias = Reference(hoja, min_col=1, min_row=fila_localidades + 1,
                               max_row=fila_localidades + n)
        grafico.add_data(datos, titles_from_data=True)
        grafico.set_categories(categorias)
        hoja.add_chart(grafico, "F4")

    if resumen.por_categoria:
        grafico = BarChart()
        grafico.type = "col"
        grafico.title = "Negocios por categoria"
        grafico.height, grafico.width = 11, 18
        n = len(resumen.por_categoria)
        datos = Reference(hoja, min_col=2, min_row=fila_categorias,
                          max_row=fila_categorias + n)
        categorias = Reference(hoja, min_col=1, min_row=fila_categorias + 1,
                               max_row=fila_categorias + n)
        grafico.add_data(datos, titles_from_data=True)
        grafico.set_categories(categorias)
        hoja.add_chart(grafico, "F27")

    if resumen.por_prioridad:
        grafico = PieChart()
        grafico.title = "Prioridad comercial"
        grafico.height, grafico.width = 9, 12
        n = len(resumen.por_prioridad)
        datos = Reference(hoja, min_col=2, min_row=fila_prioridad,
                          max_row=fila_prioridad + n)
        categorias = Reference(hoja, min_col=1, min_row=fila_prioridad + 1,
                               max_row=fila_prioridad + n)
        grafico.add_data(datos, titles_from_data=True)
        grafico.set_categories(categorias)
        hoja.add_chart(grafico, "F50")

    return hoja


def exportar_excel(negocios: list[Negocio], ruta: Path = XLSX_PATH,
                   resumen: Resumen | None = None) -> Path:
    """Escribe el libro con las hojas Dashboard y Clientes."""
    resumen = resumen or construir(negocios)

    libro = Workbook()
    libro.remove(libro.active)  # quita la hoja vacia por defecto
    _hoja_clientes(libro, negocios)
    _hoja_dashboard(libro, resumen)
    libro.active = 0

    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
    log.info("Excel escrito: %s (%s filas)", ruta, len(negocios))
    return ruta
