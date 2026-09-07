"""Fuente PRIORIDAD 2: Google Places API (opcional y configurable).

Desactivada por defecto: requiere ``GOOGLE_PLACES_API_KEY`` y es de pago.
Aporta lo que OSM casi nunca tiene: calificacion, numero de resenas, horario
verificado y un telefono de contacto confirmado por el propio negocio.

Coste: cada Place Details con campos de contacto se factura aparte. El modulo
consulta Details SOLO para los lugares que no vinieron con telefono, y respeta
``max_detalles`` para acotar el gasto.
"""
from __future__ import annotations

import logging
import time

import requests

from .. import phones
from ..config import (
    GOOGLE_PLACES_API_KEY,
    LOCALIDAD_BBOXES,
    USER_AGENT,
    Ajustes,
    Categoria,
)
from ..models import Negocio, limpiar, normalizar_url

log = logging.getLogger(__name__)

URL_NEARBY = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
URL_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

CAMPOS_DETALLE = ",".join([
    "formatted_phone_number",
    "international_phone_number",
    "website",
    "opening_hours",
    "rating",
    "user_ratings_total",
    "formatted_address",
    "url",
])

# Radio de busqueda por punto de rejilla, en metros.
RADIO_METROS = 1200
PASO_REJILLA = 0.02  # ~2.2 km


def _centros(bbox: tuple[float, float, float, float], paso: float = PASO_REJILLA):
    sur, oeste, norte, este = bbox
    lat = sur + paso / 2
    while lat < norte:
        lon = oeste + paso / 2
        while lon < este:
            yield round(lat, 5), round(lon, 5)
            lon += paso
        lat += paso


class ClienteGooglePlaces:
    """Cliente minimo de Places con paginacion y control de gasto."""

    def __init__(self, api_key: str = GOOGLE_PLACES_API_KEY, max_detalles: int = 1500):
        if not api_key:
            raise ValueError("Falta GOOGLE_PLACES_API_KEY")
        self.api_key = api_key
        self.max_detalles = max_detalles
        self.detalles_pedidos = 0
        self.sesion = requests.Session()
        self.sesion.headers.update({"User-Agent": USER_AGENT})

    def buscar_cerca(self, lat: float, lon: float, tipo: str) -> list[dict]:
        resultados: list[dict] = []
        parametros = {
            "location": f"{lat},{lon}",
            "radius": RADIO_METROS,
            "type": tipo,
            "language": "es",
            "key": self.api_key,
        }
        for pagina in range(3):  # Places devuelve maximo 3 paginas (60 lugares)
            try:
                respuesta = self.sesion.get(URL_NEARBY, params=parametros, timeout=30)
                respuesta.raise_for_status()
                datos = respuesta.json()
            except (requests.RequestException, ValueError) as exc:
                log.warning("Google Places nearby fallo: %s", exc)
                break

            estado = datos.get("status")
            if estado == "OVER_QUERY_LIMIT":
                log.error("Google Places: cuota agotada")
                break
            if estado not in ("OK", "ZERO_RESULTS"):
                log.warning("Google Places status=%s: %s", estado,
                            datos.get("error_message", ""))
                break

            resultados.extend(datos.get("results", []))
            token = datos.get("next_page_token")
            if not token:
                break
            time.sleep(2)  # el token tarda unos segundos en activarse
            parametros = {"pagetoken": token, "key": self.api_key}

        return resultados

    def detalles(self, place_id: str) -> dict:
        if self.detalles_pedidos >= self.max_detalles:
            return {}
        try:
            self.detalles_pedidos += 1
            respuesta = self.sesion.get(
                URL_DETAILS,
                params={"place_id": place_id, "fields": CAMPOS_DETALLE,
                        "language": "es", "key": self.api_key},
                timeout=30,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
            if datos.get("status") == "OK":
                return datos.get("result", {})
        except (requests.RequestException, ValueError) as exc:
            log.warning("Google Places details fallo: %s", exc)
        return {}


def _a_negocio(lugar: dict, detalle: dict, categoria: Categoria) -> Negocio | None:
    nombre = limpiar(lugar.get("name"))
    geometria = (lugar.get("geometry") or {}).get("location") or {}
    lat, lon = geometria.get("lat"), geometria.get("lng")
    if not nombre or lat is None or lon is None:
        return None

    moviles, fijos = phones.extraer_numeros(
        detalle.get("international_phone_number", ""),
        detalle.get("formatted_phone_number", ""),
    )

    horario = ""
    horas = (detalle.get("opening_hours") or {}).get("weekday_text") or []
    if horas:
        horario = "; ".join(horas)

    return Negocio(
        nombre=nombre,
        categoria=categoria.nombre,
        grupo=categoria.grupo,
        direccion=limpiar(detalle.get("formatted_address") or lugar.get("vicinity")),
        moviles=moviles,
        fijos=fijos,
        sitio_web=normalizar_url(detalle.get("website", "")),
        horario=horario,
        calificacion=lugar.get("rating") or detalle.get("rating"),
        resenas=lugar.get("user_ratings_total") or detalle.get("user_ratings_total"),
        fuente="Google Places",
        place_id=f"google:{lugar.get('place_id', '')}",
        lat=float(lat),
        lon=float(lon),
    )


def recolectar(ajustes: Ajustes, max_detalles: int = 1500, progreso=None) -> list[Negocio]:
    """Recorre las localidades pedidas usando los tipos de Google de cada categoria."""
    if not GOOGLE_PLACES_API_KEY:
        log.info("Google Places desactivado (sin GOOGLE_PLACES_API_KEY)")
        return []

    cliente = ClienteGooglePlaces(max_detalles=max_detalles)
    categorias = [c for c in ajustes.categorias_activas if c.google_types]

    negocios: list[Negocio] = []
    vistos: set[str] = set()
    puntos = [
        (localidad, punto)
        for localidad in ajustes.localidades
        if LOCALIDAD_BBOXES.get(localidad)
        for punto in _centros(LOCALIDAD_BBOXES[localidad])
    ]

    total = len(puntos) * len(categorias)
    hecho = 0
    for localidad, (lat, lon) in puntos:
        for categoria in categorias:
            for tipo in categoria.google_types:
                for lugar in cliente.buscar_cerca(lat, lon, tipo):
                    place_id = lugar.get("place_id", "")
                    if not place_id or place_id in vistos:
                        continue
                    vistos.add(place_id)
                    detalle = cliente.detalles(place_id)
                    negocio = _a_negocio(lugar, detalle, categoria)
                    if negocio is None:
                        continue
                    negocio.localidad = negocio.localidad or localidad
                    negocios.append(negocio)
            hecho += 1
            if progreso:
                progreso(hecho, total, localidad, len(negocios))

        if ajustes.limite and len(negocios) >= ajustes.limite:
            break

    log.info("Google Places: %s negocios (%s Place Details facturados)",
             len(negocios), cliente.detalles_pedidos)
    return negocios
