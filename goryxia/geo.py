"""Utilidades geoespaciales sin dependencias pesadas.

Implementa haversine y point-in-polygon (ray casting) en Python puro para no
obligar a instalar GEOS/shapely en la maquina del comercial.
"""
from __future__ import annotations

import json
import math
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence

from .config import CIUDAD, LOCALIDAD_BBOXES, LOCALIDADES_BOGOTA, REFERENCE_POINT

RADIO_TIERRA_KM = 6371.0088


def quitar_tildes(texto: str) -> str:
    """Normaliza a ASCII para comparar nombres ('Engativá' == 'Engativa')."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en kilometros entre dos coordenadas."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(math.sqrt(a))


def distancia_a_referencia(lat: float, lon: float) -> float:
    """Distancia en km desde el punto de referencia comercial configurado."""
    ref_lat, ref_lon = REFERENCE_POINT
    return round(haversine_km(ref_lat, ref_lon, lat, lon), 2)


def punto_en_anillo(lat: float, lon: float, anillo: Sequence[Sequence[float]]) -> bool:
    """Ray casting sobre un anillo GeoJSON (lista de pares [lon, lat])."""
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > lat) != (yj > lat):
            interseccion = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lon < interseccion:
                dentro = not dentro
        j = i
    return dentro


def punto_en_poligono(lat: float, lon: float, coordenadas: Sequence) -> bool:
    """Evalua un Polygon GeoJSON (anillo exterior menos huecos)."""
    if not coordenadas:
        return False
    if not punto_en_anillo(lat, lon, coordenadas[0]):
        return False
    for hueco in coordenadas[1:]:
        if punto_en_anillo(lat, lon, hueco):
            return False
    return True


def punto_en_geometria(lat: float, lon: float, geometria: dict) -> bool:
    """Soporta Polygon y MultiPolygon de GeoJSON."""
    tipo = geometria.get("type")
    coords = geometria.get("coordinates") or []
    if tipo == "Polygon":
        return punto_en_poligono(lat, lon, coords)
    if tipo == "MultiPolygon":
        return any(punto_en_poligono(lat, lon, poly) for poly in coords)
    return False


def bbox_de_geometria(geometria: dict) -> tuple[float, float, float, float] | None:
    """Calcula (sur, oeste, norte, este) para prefiltrar antes del ray casting."""
    lats: list[float] = []
    lons: list[float] = []

    def recorrer(nodo):
        if isinstance(nodo, (list, tuple)):
            if len(nodo) == 2 and all(isinstance(v, (int, float)) for v in nodo):
                lons.append(float(nodo[0]))
                lats.append(float(nodo[1]))
            else:
                for hijo in nodo:
                    recorrer(hijo)

    recorrer(geometria.get("coordinates") or [])
    if not lats:
        return None
    return (min(lats), min(lons), max(lats), max(lons))


class LocalizadorLocalidades:
    """Asigna localidad a un punto usando poligonos reales de OSM.

    Si no hay poligonos disponibles (por ejemplo sin red), cae a los bounding
    boxes aproximados de ``config.LOCALIDAD_BBOXES``, marcando el resultado como
    aproximado para que quede claro en la base final.
    """

    def __init__(self, geojson: dict | None = None):
        self.poligonos: list[tuple[str, dict, tuple[float, float, float, float]]] = []
        self.exacto = False
        if geojson:
            self._cargar(geojson)

    @classmethod
    def desde_archivo(cls, ruta: Path) -> "LocalizadorLocalidades":
        if ruta.exists():
            try:
                return cls(json.loads(ruta.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        return cls()

    def _cargar(self, geojson: dict) -> None:
        canonicos = {quitar_tildes(n).lower(): n for n in LOCALIDADES_BOGOTA}
        for feature in geojson.get("features", []):
            props = feature.get("properties") or {}
            nombre_crudo = props.get("name") or props.get("nombre") or ""
            clave = quitar_tildes(nombre_crudo).lower().replace("localidad de ", "").strip()
            nombre = canonicos.get(clave)
            if not nombre:
                # Coincidencia laxa: "Ciudad Bolivar (Localidad 19)"
                for canon_clave, canon_nombre in canonicos.items():
                    if canon_clave and canon_clave in clave:
                        nombre = canon_nombre
                        break
            if not nombre:
                continue
            geometria = feature.get("geometry") or {}
            bbox = bbox_de_geometria(geometria)
            if bbox:
                self.poligonos.append((nombre, geometria, bbox))
        self.exacto = len(self.poligonos) >= 10

    def localidad(self, lat: float, lon: float) -> str:
        if lat is None or lon is None:
            return ""
        for nombre, geometria, (sur, oeste, norte, este) in self.poligonos:
            if sur <= lat <= norte and oeste <= lon <= este:
                if punto_en_geometria(lat, lon, geometria):
                    return nombre
        return self._por_bbox(lat, lon)

    @staticmethod
    def _por_bbox(lat: float, lon: float) -> str:
        """Respaldo aproximado: la localidad cuyo centro este mas cerca."""
        mejor, mejor_dist = "", float("inf")
        for nombre, (sur, oeste, norte, este) in LOCALIDAD_BBOXES.items():
            if sur <= lat <= norte and oeste <= lon <= este:
                centro_lat = (sur + norte) / 2
                centro_lon = (oeste + este) / 2
                dist = haversine_km(lat, lon, centro_lat, centro_lon)
                if dist < mejor_dist:
                    mejor, mejor_dist = nombre, dist
        return mejor


class LocalizadorBarrios:
    """Asigna el barrio mas cercano a partir de nodos place=* de OSM."""

    def __init__(self, puntos: Iterable[tuple[str, float, float]] = ()):
        self.puntos = [(n, la, lo) for n, la, lo in puntos if n]

    @classmethod
    def desde_archivo(cls, ruta: Path) -> "LocalizadorBarrios":
        if not ruta.exists():
            return cls()
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        puntos = [
            (p.get("nombre", ""), float(p["lat"]), float(p["lon"]))
            for p in datos
            if p.get("nombre") and p.get("lat") is not None and p.get("lon") is not None
        ]
        return cls(puntos)

    def barrio(self, lat: float, lon: float, radio_km: float = 1.2) -> str:
        if lat is None or lon is None or not self.puntos:
            return ""
        mejor, mejor_dist = "", radio_km
        # Prefiltro barato por grados antes del haversine.
        margen = radio_km / 100.0
        for nombre, plat, plon in self.puntos:
            if abs(plat - lat) > margen or abs(plon - lon) > margen:
                continue
            dist = haversine_km(lat, lon, plat, plon)
            if dist < mejor_dist:
                mejor, mejor_dist = nombre, dist
        return mejor


def ciudad_por_defecto() -> str:
    return CIUDAD
