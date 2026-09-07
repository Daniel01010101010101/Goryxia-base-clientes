"""Exportacion a GeoJSON para mapas (QGIS, Google My Maps, Leaflet, Kepler)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import GEOJSON_PATH
from ..models import Negocio

log = logging.getLogger(__name__)

# Campos que viajan al mapa. Se omiten los textos largos para que el archivo
# siga siendo manejable al abrirlo en herramientas web.
PROPIEDADES = [
    "ID", "Nombre del negocio", "Categoria", "Grupo", "Direccion", "Barrio",
    "Localidad", "Telefono", "WhatsApp", "Link WhatsApp", "Correo electronico",
    "Sitio web", "Instagram", "Facebook", "Presencia digital", "Score Contacto",
    "Prioridad", "Fuente", "Distancia aprox. (km)",
]


def exportar_geojson(negocios: list[Negocio], ruta: Path = GEOJSON_PATH) -> Path:
    features = []
    omitidos = 0
    for negocio in negocios:
        if negocio.lat is None or negocio.lon is None:
            omitidos += 1
            continue
        fila = negocio.a_fila()
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [negocio.lon, negocio.lat]},
            "properties": {clave: fila.get(clave) for clave in PROPIEDADES},
        })

    coleccion = {
        "type": "FeatureCollection",
        "name": "Base_Clientes_GoryxIA",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }

    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(coleccion, ensure_ascii=False), encoding="utf-8")
    log.info("GeoJSON escrito: %s (%s puntos, %s sin coordenadas)",
             ruta, len(features), omitidos)
    return ruta
