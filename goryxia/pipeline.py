"""Orquestacion completa: recoleccion -> deduplicacion -> enriquecimiento -> exportacion."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import scoring, services
from .config import (
    CSV_PATH,
    GEOJSON_PATH,
    PDF_PATH,
    XLSX_PATH,
    Ajustes,
)
from .dedupe import deduplicar
from .exporters import exportar_csv, exportar_excel, exportar_geojson, exportar_pdf
from .geo import LocalizadorBarrios, LocalizadorLocalidades, distancia_a_referencia
from .models import Negocio
from .resumen import Resumen, construir
from .sources import datos_abiertos, google_places, overpass

log = logging.getLogger(__name__)


@dataclass
class ResultadoCorrida:
    """Todo lo que produjo una ejecucion del pipeline."""

    negocios: list[Negocio] = field(default_factory=list)
    resumen: Resumen | None = None
    archivos: dict[str, Path] = field(default_factory=dict)
    duplicados: dict[str, int] = field(default_factory=dict)
    ganancia_web: dict[str, int] = field(default_factory=dict)
    crudos_por_fuente: dict[str, int] = field(default_factory=dict)
    segundos: float = 0.0


def _progreso_overpass(indice: int, total: int, localidad: str, acumulado: int) -> None:
    if indice % 5 == 0 or indice == total:
        log.info("  Overpass %s/%s mosaicos (%s) - %s negocios",
                 indice, total, localidad, acumulado)


def _progreso_web(indice: int, total: int, nuevos: int) -> None:
    if indice % 100 == 0 or indice == total:
        log.info("  Webs %s/%s - +%s celulares nuevos", indice, total, nuevos)


def recolectar(ajustes: Ajustes) -> tuple[list[Negocio], dict[str, int]]:
    """Ejecuta las fuentes en el orden de prioridad definido por el negocio."""
    negocios: list[Negocio] = []
    conteo: dict[str, int] = {}

    if ajustes.usar_overpass:
        log.info("[1/3] OpenStreetMap (Overpass API)")
        encontrados = overpass.recolectar(ajustes, progreso=_progreso_overpass)
        conteo["OpenStreetMap"] = len(encontrados)
        negocios.extend(encontrados)

    if ajustes.usar_google:
        log.info("[2/3] Google Places API")
        encontrados = google_places.recolectar(ajustes)
        conteo["Google Places"] = len(encontrados)
        negocios.extend(encontrados)

    if ajustes.usar_datos_abiertos:
        log.info("[3/3] Datos Abiertos Bogota")
        encontrados = datos_abiertos.recolectar(ajustes)
        conteo["Datos Abiertos"] = len(encontrados)
        negocios.extend(encontrados)

    log.info("Recoleccion cruda: %s registros %s", len(negocios), conteo)
    return negocios, conteo


def enriquecer_geografia(negocios: list[Negocio],
                         localizador_localidades: LocalizadorLocalidades,
                         localizador_barrios: LocalizadorBarrios) -> None:
    """Completa localidad, barrio y distancia a la referencia comercial."""
    for negocio in negocios:
        if negocio.lat is None or negocio.lon is None:
            continue
        if not negocio.localidad:
            negocio.localidad = localizador_localidades.localidad(negocio.lat, negocio.lon)
        if not negocio.barrio:
            negocio.barrio = localizador_barrios.barrio(negocio.lat, negocio.lon)
        negocio.distancia_km = distancia_a_referencia(negocio.lat, negocio.lon)


def enriquecer_comercial(negocios: list[Negocio]) -> None:
    """Calcula presencia digital, score, prioridad, servicios y observaciones."""
    for negocio in negocios:
        scoring.enriquecer(negocio)
        services.enriquecer(negocio)
        if not negocio.id:
            negocio.asignar_id()


def ordenar(negocios: list[Negocio]) -> list[Negocio]:
    """Orden final de la base: celular > WhatsApp > correo > web > sin contacto."""
    return sorted(negocios, key=scoring.clave_orden)


def exportar_todo(negocios: list[Negocio], resumen: Resumen) -> dict[str, Path]:
    return {
        "xlsx": exportar_excel(negocios, XLSX_PATH, resumen),
        "csv": exportar_csv(negocios, CSV_PATH),
        "pdf": exportar_pdf(negocios, PDF_PATH, resumen),
        "geojson": exportar_geojson(negocios, GEOJSON_PATH),
    }


def ejecutar(ajustes: Ajustes,
             negocios_precargados: list[Negocio] | None = None,
             exportar: bool = True) -> ResultadoCorrida:
    """Corre el pipeline completo y devuelve el resultado.

    ``negocios_precargados`` permite reprocesar una recoleccion previa (o una
    fixture de pruebas) sin volver a salir a la red.
    """
    inicio = time.time()
    resultado = ResultadoCorrida()

    # 1. Recoleccion --------------------------------------------------------
    if negocios_precargados is not None:
        negocios = list(negocios_precargados)
        resultado.crudos_por_fuente = {"precargado": len(negocios)}
    else:
        negocios, resultado.crudos_por_fuente = recolectar(ajustes)

    if not negocios:
        log.warning("No se recolecto ningun negocio. Revisa la conectividad "
                    "con Overpass o los filtros de la corrida.")
        resultado.resumen = construir([])
        resultado.segundos = time.time() - inicio
        return resultado

    # 2. Deduplicacion ------------------------------------------------------
    log.info("Deduplicando %s registros", len(negocios))
    negocios, resultado.duplicados = deduplicar(negocios)

    # 3. Geografia ----------------------------------------------------------
    log.info("Asignando localidad, barrio y distancia")
    if ajustes.usar_overpass and negocios_precargados is None:
        from .sources import boundaries
        localizador_localidades = boundaries.obtener_localidades()
        localizador_barrios = boundaries.obtener_barrios()
    else:
        from .sources.boundaries import RUTA_BARRIOS, RUTA_LOCALIDADES
        localizador_localidades = LocalizadorLocalidades.desde_archivo(RUTA_LOCALIDADES)
        localizador_barrios = LocalizadorBarrios.desde_archivo(RUTA_BARRIOS)
    enriquecer_geografia(negocios, localizador_localidades, localizador_barrios)

    # 4. Sitios web: la fase que mas celulares aporta ------------------------
    if ajustes.scrapear_webs:
        from .sources import websites
        log.info("Enriqueciendo desde sitios web oficiales")
        resultado.ganancia_web = websites.enriquecer_negocios(
            negocios, max_sitios=ajustes.max_webs,
            usar_cache=ajustes.usar_cache,
            presupuesto_minutos=ajustes.minutos_web,
            progreso=_progreso_web)

    # 5. Scoring comercial ---------------------------------------------------
    log.info("Calculando score, prioridad y servicios sugeridos")
    enriquecer_comercial(negocios)

    # 6. Orden final ---------------------------------------------------------
    negocios = ordenar(negocios)
    if ajustes.limite:
        negocios = negocios[:ajustes.limite]

    resultado.negocios = negocios
    resultado.resumen = construir(negocios)

    # 7. Exportacion ---------------------------------------------------------
    if exportar:
        log.info("Exportando archivos finales")
        resultado.archivos = exportar_todo(negocios, resultado.resumen)

    resultado.segundos = time.time() - inicio
    log.info("Corrida completa en %.1f s: %s negocios, %s con celular (%.1f%%)",
             resultado.segundos, resultado.resumen.total,
             resultado.resumen.con_celular, resultado.resumen.pct_celular)
    return resultado
