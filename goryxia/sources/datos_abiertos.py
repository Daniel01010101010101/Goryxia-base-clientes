"""Fuente PRIORIDAD 3: Datos Abiertos Bogota / datos.gov.co (portales Socrata).

Los identificadores de dataset cambian con el tiempo y no todos los conjuntos
publican telefono, asi que este modulo es deliberadamente generico: se le pasan
datasets por configuracion (``GORYXIA_SOCRATA_DATASETS``) con la forma
``dominio:dataset_id`` y el mapeo de columnas se resuelve por heuristica sobre
los nombres de campo que devuelve el propio portal.

Ejemplo:
    export GORYXIA_SOCRATA_DATASETS="www.datos.gov.co:abcd-1234,datosabiertos.bogota.gov.co:wxyz-5678"
"""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

from .. import phones
from ..config import (
    CATEGORIAS,
    DATOS_ABIERTOS_DATASETS,
    SOCRATA_APP_TOKEN,
    USER_AGENT,
    Ajustes,
)
from ..geo import quitar_tildes
from ..models import Negocio, limpiar, normalizar_url

log = logging.getLogger(__name__)

TAMANO_PAGINA = 1000
MAX_PAGINAS = 50

# Heuristica de mapeo: fragmento en el nombre de columna -> campo destino.
PISTAS = {
    "nombre": ("razon_social", "nombre_comercial", "nombre_establecimiento",
               "nombre", "establecimiento", "empresa"),
    "direccion": ("direccion", "direccion_comercial", "dir_comercial", "domicilio"),
    "telefono": ("telefono", "celular", "movil", "contacto_telefono", "tel"),
    "correo": ("correo", "email", "e_mail", "correo_electronico"),
    "web": ("web", "sitio_web", "pagina_web", "url"),
    "localidad": ("localidad", "nom_localidad", "localidad_nombre"),
    "barrio": ("barrio", "nom_barrio", "barrio_nombre"),
    "actividad": ("actividad", "ciiu", "descripcion_actividad", "objeto_social",
                  "actividad_economica"),
    "lat": ("latitud", "lat", "y", "coord_y"),
    "lon": ("longitud", "lon", "lng", "x", "coord_x"),
}


def _detectar_columnas(fila: dict[str, Any]) -> dict[str, str]:
    """Asocia cada campo destino con la primera columna del dataset que encaje."""
    mapeo: dict[str, str] = {}
    columnas = list(fila.keys())
    for destino, pistas in PISTAS.items():
        for pista in pistas:
            for columna in columnas:
                normalizada = quitar_tildes(columna).lower()
                if normalizada == pista or normalizada.endswith("_" + pista) \
                        or normalizada.startswith(pista):
                    mapeo[destino] = columna
                    break
            if destino in mapeo:
                break
    return mapeo


def _clasificar(actividad: str, nombre: str) -> tuple[str, str]:
    """Asigna categoria y grupo por palabras clave del objeto social o el nombre."""
    texto = quitar_tildes(f"{actividad} {nombre}").lower()
    for categoria in CATEGORIAS:
        for palabra in categoria.keywords:
            if quitar_tildes(palabra).lower() in texto:
                return categoria.nombre, categoria.grupo
    return "Otro comercio", "Comercio"


def _fila_a_negocio(fila: dict, mapeo: dict[str, str], dominio: str) -> Negocio | None:
    nombre = limpiar(fila.get(mapeo.get("nombre", ""), ""))
    if not nombre:
        return None

    moviles, fijos = phones.extraer_numeros(
        str(fila.get(mapeo.get("telefono", ""), "") or "")
    )

    correo = limpiar(fila.get(mapeo.get("correo", ""), "")).lower()
    actividad = limpiar(fila.get(mapeo.get("actividad", ""), ""))
    categoria, grupo = _clasificar(actividad, nombre)

    def _num(clave: str) -> float | None:
        crudo = fila.get(mapeo.get(clave, ""), None)
        try:
            valor = float(str(crudo).replace(",", "."))
        except (TypeError, ValueError):
            return None
        return valor if valor != 0 else None

    lat, lon = _num("lat"), _num("lon")
    # Algunos datasets traen la geometria en un campo "the_geom" o "ubicacion".
    if lat is None or lon is None:
        for clave in ("the_geom", "ubicacion", "location", "georeferencia"):
            geo = fila.get(clave)
            if isinstance(geo, dict) and geo.get("coordinates"):
                lon, lat = geo["coordinates"][0], geo["coordinates"][1]
                break

    identificador = re.sub(r"\W+", "", nombre.lower())[:40]
    return Negocio(
        nombre=nombre,
        categoria=categoria,
        grupo=grupo,
        direccion=limpiar(fila.get(mapeo.get("direccion", ""), "")),
        barrio=limpiar(fila.get(mapeo.get("barrio", ""), "")),
        localidad=limpiar(fila.get(mapeo.get("localidad", ""), "")).title(),
        moviles=moviles,
        fijos=fijos,
        correos=[correo] if "@" in correo else [],
        sitio_web=normalizar_url(limpiar(fila.get(mapeo.get("web", ""), ""))),
        fuente=f"Datos Abiertos ({dominio})",
        place_id=f"socrata:{dominio}:{identificador}",
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
    )


def descargar_dataset(dominio: str, dataset_id: str) -> list[Negocio]:
    """Descarga un dataset Socrata completo, paginando."""
    url = f"https://{dominio}/resource/{dataset_id}.json"
    cabeceras = {"User-Agent": USER_AGENT}
    if SOCRATA_APP_TOKEN:
        cabeceras["X-App-Token"] = SOCRATA_APP_TOKEN

    negocios: list[Negocio] = []
    mapeo: dict[str, str] = {}

    for pagina in range(MAX_PAGINAS):
        parametros = {"$limit": TAMANO_PAGINA, "$offset": pagina * TAMANO_PAGINA}
        try:
            respuesta = requests.get(url, params=parametros, headers=cabeceras, timeout=60)
            respuesta.raise_for_status()
            filas = respuesta.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("Datos Abiertos %s/%s fallo: %s", dominio, dataset_id, exc)
            break

        if not filas:
            break
        if not mapeo:
            mapeo = _detectar_columnas(filas[0])
            log.info("Dataset %s: columnas detectadas %s", dataset_id, mapeo)
            if "nombre" not in mapeo:
                log.warning("Dataset %s sin columna de nombre reconocible; se omite",
                            dataset_id)
                break

        for fila in filas:
            negocio = _fila_a_negocio(fila, mapeo, dominio)
            if negocio:
                negocios.append(negocio)

        if len(filas) < TAMANO_PAGINA:
            break

    log.info("Datos Abiertos %s/%s: %s registros", dominio, dataset_id, len(negocios))
    return negocios


def recolectar(ajustes: Ajustes) -> list[Negocio]:
    """Descarga todos los datasets configurados."""
    if not DATOS_ABIERTOS_DATASETS:
        log.info("Datos Abiertos desactivado (define GORYXIA_SOCRATA_DATASETS)")
        return []

    negocios: list[Negocio] = []
    for entrada in DATOS_ABIERTOS_DATASETS:
        if ":" not in entrada:
            log.warning("Entrada Socrata invalida (usa dominio:dataset_id): %s", entrada)
            continue
        dominio, dataset_id = entrada.split(":", 1)
        negocios.extend(descargar_dataset(dominio.strip(), dataset_id.strip()))

    return negocios
