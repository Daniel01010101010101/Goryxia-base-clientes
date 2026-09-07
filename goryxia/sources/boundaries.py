"""Poligonos de localidades y nodos de barrio, descargados de OpenStreetMap.

Permite asignar Localidad y Barrio con datos reales en vez de aproximaciones.
Ambos resultados se cachean en disco porque cambian muy poco con el tiempo.
"""
from __future__ import annotations

import json
import logging

from ..config import BOGOTA_BBOX, CACHE_DIR, OVERPASS_TIMEOUT
from ..geo import LocalizadorBarrios, LocalizadorLocalidades
from .overpass import ClienteOverpass

log = logging.getLogger(__name__)

RUTA_LOCALIDADES = CACHE_DIR / "localidades.geojson"
RUTA_BARRIOS = CACHE_DIR / "barrios.json"

# En OSM las localidades de Bogota estan mapeadas como limites administrativos
# de nivel 8 (y algunas fuentes usan 9). Se piden ambos y se filtra por nombre.
CONSULTA_LOCALIDADES = f"""
[out:json][timeout:{OVERPASS_TIMEOUT}];
area["name"="Bogota"]["admin_level"="4"]->.bogota;
(
  relation(area.bogota)["boundary"="administrative"]["admin_level"="8"];
  relation(area.bogota)["boundary"="administrative"]["admin_level"="9"];
);
out geom;
"""



def _relacion_a_geojson(elemento: dict) -> dict | None:
    """Convierte una relacion Overpass con ``out geom`` en un Feature GeoJSON.

    Une los tramos (``ways``) con rol ``outer`` en anillos cerrados. Es una
    reconstruccion tolerante: si un anillo no cierra perfectamente se conserva
    igual, porque para point-in-polygon un desfase de metros es irrelevante.
    """
    tags = elemento.get("tags") or {}
    nombre = tags.get("name")
    if not nombre:
        return None

    tramos: list[list[list[float]]] = []
    for miembro in elemento.get("members", []):
        if miembro.get("type") != "way" or miembro.get("role") not in ("outer", "", None):
            continue
        geometria = miembro.get("geometry") or []
        puntos = [[p["lon"], p["lat"]] for p in geometria if "lon" in p and "lat" in p]
        if len(puntos) >= 2:
            tramos.append(puntos)

    if not tramos:
        return None

    anillos: list[list[list[float]]] = []
    pendientes = list(tramos)
    actual = pendientes.pop(0)

    while pendientes:
        extremo = actual[-1]
        for indice, tramo in enumerate(pendientes):
            if tramo[0] == extremo:
                actual.extend(tramo[1:])
                pendientes.pop(indice)
                break
            if tramo[-1] == extremo:
                actual.extend(list(reversed(tramo))[1:])
                pendientes.pop(indice)
                break
        else:
            # No hay continuidad: se cierra el anillo actual y se abre otro.
            if len(actual) >= 4:
                if actual[0] != actual[-1]:
                    actual.append(actual[0])
                anillos.append(actual)
            actual = pendientes.pop(0)

    if len(actual) >= 4:
        if actual[0] != actual[-1]:
            actual.append(actual[0])
        anillos.append(actual)

    if not anillos:
        return None

    anillos.sort(key=len, reverse=True)
    geometria = (
        {"type": "Polygon", "coordinates": [anillos[0]]}
        if len(anillos) == 1
        else {"type": "MultiPolygon", "coordinates": [[a] for a in anillos]}
    )
    return {
        "type": "Feature",
        "properties": {"name": nombre, "admin_level": tags.get("admin_level", "")},
        "geometry": geometria,
    }


def obtener_localidades(cliente: ClienteOverpass | None = None,
                        forzar: bool = False) -> LocalizadorLocalidades:
    """Devuelve el localizador de localidades, descargando poligonos si hace falta."""
    if not forzar and RUTA_LOCALIDADES.exists():
        localizador = LocalizadorLocalidades.desde_archivo(RUTA_LOCALIDADES)
        if localizador.poligonos:
            log.info("Localidades desde cache: %s poligonos", len(localizador.poligonos))
            return localizador

    cliente = cliente or ClienteOverpass()
    datos = cliente.ejecutar(CONSULTA_LOCALIDADES)
    if not datos:
        log.warning("No se pudieron descargar los limites de localidades; "
                    "se usara aproximacion por bounding box")
        return LocalizadorLocalidades()

    features = []
    for elemento in datos.get("elements", []):
        feature = _relacion_a_geojson(elemento)
        if feature:
            features.append(feature)

    coleccion = {"type": "FeatureCollection", "features": features}
    RUTA_LOCALIDADES.parent.mkdir(parents=True, exist_ok=True)
    RUTA_LOCALIDADES.write_text(json.dumps(coleccion), encoding="utf-8")
    log.info("Localidades descargadas: %s poligonos", len(features))
    return LocalizadorLocalidades(coleccion)


def obtener_barrios(cliente: ClienteOverpass | None = None,
                    forzar: bool = False) -> LocalizadorBarrios:
    """Devuelve el localizador de barrios (nodos place=* de OSM)."""
    if not forzar and RUTA_BARRIOS.exists():
        localizador = LocalizadorBarrios.desde_archivo(RUTA_BARRIOS)
        if localizador.puntos:
            log.info("Barrios desde cache: %s puntos", len(localizador.puntos))
            return localizador

    cliente = cliente or ClienteOverpass()
    sur, oeste, norte, este = BOGOTA_BBOX
    consulta = (
        f"[out:json][timeout:{OVERPASS_TIMEOUT}];\n"
        f'node["place"~"^(suburb|neighbourhood|quarter|borough)$"]'
        f"({sur},{oeste},{norte},{este});\n"
        "out tags center;"
    )
    datos = cliente.ejecutar(consulta)
    if not datos:
        log.warning("No se pudieron descargar los barrios")
        return LocalizadorBarrios()

    puntos = []
    for elemento in datos.get("elements", []):
        tags = elemento.get("tags") or {}
        nombre = tags.get("name")
        lat = elemento.get("lat") or (elemento.get("center") or {}).get("lat")
        lon = elemento.get("lon") or (elemento.get("center") or {}).get("lon")
        if nombre and lat is not None and lon is not None:
            puntos.append({"nombre": nombre, "lat": float(lat), "lon": float(lon)})

    RUTA_BARRIOS.parent.mkdir(parents=True, exist_ok=True)
    RUTA_BARRIOS.write_text(json.dumps(puntos, ensure_ascii=False), encoding="utf-8")
    log.info("Barrios descargados: %s puntos", len(puntos))
    return LocalizadorBarrios([(p["nombre"], p["lat"], p["lon"]) for p in puntos])
