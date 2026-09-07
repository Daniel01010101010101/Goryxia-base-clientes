"""Fuente PRIORIDAD 1: OpenStreetMap via Overpass API.

Estrategia para maximizar negocios contactables:
  * Se recorre Bogota por mosaicos (tiles) derivados de los bounding boxes de
    cada localidad, empezando por las localidades priorizadas.
  * Cada consulta pide TODAS las categorias objetivo de una vez agrupadas por
    llave OSM, lo que reduce a ~1 peticion por mosaico en lugar de una por
    categoria.
  * Se leen todas las variantes de tags de contacto que usa la comunidad OSM
    (``phone``, ``contact:mobile``, ``contact:whatsapp``, etc.), porque ahi es
    donde aparecen los celulares que son el objetivo del proyecto.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from pathlib import Path
from typing import Iterable, Iterator

import requests

from .. import phones
from ..config import (
    CACHE_DIR,
    CATEGORIA_POR_OSM,
    LOCALIDAD_BBOXES,
    OVERPASS_ENDPOINTS,
    OVERPASS_PAUSA_SEG,
    OVERPASS_REINTENTOS,
    OVERPASS_TIMEOUT,
    USER_AGENT,
    Ajustes,
    Categoria,
)
from ..models import Negocio, limpiar, normalizar_red, normalizar_url

log = logging.getLogger(__name__)

CACHE_OVERPASS = CACHE_DIR / "overpass"

# Tamano de mosaico en grados (~3.3 km). Mosaicos pequenos evitan los
# "timeout" y "too many requests" del servidor publico.
TILE_GRADOS = 0.03

# Zonas rurales o de muy baja densidad comercial: mosaicos grandes, porque
# gastar 240 peticiones en Sumapaz no aporta leads contactables.
TILE_GRADOS_POR_LOCALIDAD = {
    "Sumapaz": 0.20,
    "Usme": 0.05,
    "Ciudad Bolivar": 0.04,
}

# ---------------------------------------------------------------------------
# Lectura de tags OSM
# ---------------------------------------------------------------------------
TAGS_TELEFONO = (
    "phone", "contact:phone", "telephone", "phone:CO", "contact:phone:CO",
)
TAGS_MOVIL = (
    "contact:mobile", "mobile", "phone:mobile", "contact:phone:mobile",
    "contact:cell", "cell",
)
TAGS_WHATSAPP = ("contact:whatsapp", "whatsapp", "contact:whats_app")
TAGS_EMAIL = ("email", "contact:email", "contact:e-mail")
TAGS_WEB = ("website", "contact:website", "url", "contact:url", "website:official")
TAGS_FACEBOOK = ("contact:facebook", "facebook", "contact:fb")
TAGS_INSTAGRAM = ("contact:instagram", "instagram")
TAGS_LINKEDIN = ("contact:linkedin", "linkedin")
TAGS_NOMBRE = ("name", "official_name", "alt_name", "brand", "operator")


def _primer_tag(tags: dict, llaves: Iterable[str]) -> str:
    for llave in llaves:
        valor = limpiar(tags.get(llave))
        if valor:
            return valor
    return ""


def _todos_los_tags(tags: dict, llaves: Iterable[str]) -> list[str]:
    return [limpiar(tags[k]) for k in llaves if limpiar(tags.get(k))]


# ---------------------------------------------------------------------------
# Construccion de consultas
# ---------------------------------------------------------------------------
def construir_consulta(bbox: tuple[float, float, float, float],
                       categorias: list[Categoria]) -> str:
    """Consulta Overpass QL que trae todas las categorias del mosaico."""
    por_llave: dict[str, set[str]] = {}
    for categoria in categorias:
        for llave, valor in categoria.osm:
            por_llave.setdefault(llave, set()).add(valor)

    sur, oeste, norte, este = bbox
    caja = f"({sur:.5f},{oeste:.5f},{norte:.5f},{este:.5f})"

    partes = []
    for llave, valores in sorted(por_llave.items()):
        alternativas = "|".join(sorted(valores))
        partes.append(f'  nwr["{llave}"~"^({alternativas})$"]{caja};')

    cuerpo = "\n".join(partes)
    return (
        f"[out:json][timeout:{OVERPASS_TIMEOUT}];\n"
        f"(\n{cuerpo}\n);\n"
        "out center tags;"
    )


def mosaicos(bbox: tuple[float, float, float, float],
             paso: float = TILE_GRADOS) -> Iterator[tuple[float, float, float, float]]:
    """Trocea un bounding box en mosaicos de ``paso`` grados."""
    sur, oeste, norte, este = bbox
    lat = sur
    while lat < norte:
        lat_fin = min(lat + paso, norte)
        lon = oeste
        while lon < este:
            lon_fin = min(lon + paso, este)
            yield (round(lat, 5), round(lon, 5), round(lat_fin, 5), round(lon_fin, 5))
            lon = lon_fin
        lat = lat_fin


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------
class ClienteOverpass:
    """Cliente con rotacion de mirrors, reintentos exponenciales y cache en disco."""

    def __init__(self, usar_cache: bool = True, cache_dir: Path = CACHE_OVERPASS):
        self.usar_cache = usar_cache
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sesion = requests.Session()
        self.sesion.headers.update({"User-Agent": USER_AGENT})
        self.endpoints = list(OVERPASS_ENDPOINTS)
        self.peticiones = 0
        self.aciertos_cache = 0
        self.fallos = 0

    def _ruta_cache(self, consulta: str) -> Path:
        clave = hashlib.sha1(consulta.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{clave}.json"

    def ejecutar(self, consulta: str) -> dict | None:
        """Ejecuta una consulta Overpass QL. Devuelve el JSON o None si fallo."""
        ruta = self._ruta_cache(consulta)
        if self.usar_cache and ruta.exists():
            try:
                self.aciertos_cache += 1
                return json.loads(ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("Cache corrupta, se vuelve a consultar: %s", ruta.name)

        espera = OVERPASS_PAUSA_SEG
        for intento in range(1, OVERPASS_REINTENTOS + 1):
            endpoint = self.endpoints[(self.peticiones + intento) % len(self.endpoints)]
            try:
                self.peticiones += 1
                respuesta = self.sesion.post(
                    endpoint,
                    data={"data": consulta},
                    timeout=OVERPASS_TIMEOUT + 30,
                )
                if respuesta.status_code in (429, 504):
                    log.info("Overpass %s ocupado (%s), reintento %s/%s",
                             endpoint, respuesta.status_code, intento, OVERPASS_REINTENTOS)
                    time.sleep(espera + random.uniform(0, 2))
                    espera *= 2
                    continue
                respuesta.raise_for_status()
                datos = respuesta.json()
                if self.usar_cache:
                    ruta.write_text(json.dumps(datos), encoding="utf-8")
                time.sleep(OVERPASS_PAUSA_SEG)
                return datos
            except (requests.RequestException, json.JSONDecodeError) as exc:
                log.warning("Fallo Overpass (%s) intento %s/%s: %s",
                            endpoint, intento, OVERPASS_REINTENTOS, exc)
                time.sleep(espera + random.uniform(0, 2))
                espera *= 2

        self.fallos += 1
        log.error("Consulta Overpass agotada tras %s intentos", OVERPASS_REINTENTOS)
        return None


# ---------------------------------------------------------------------------
# Conversion de elementos OSM a Negocio
# ---------------------------------------------------------------------------
def _categoria_de(tags: dict) -> Categoria | None:
    """Encuentra la categoria objetivo a la que pertenece un elemento OSM."""
    for llave, valor in tags.items():
        categoria = CATEGORIA_POR_OSM.get((llave, valor))
        if categoria:
            return categoria
    # Valores compuestos: shop=hairdresser;beauty
    for llave, valor in tags.items():
        if ";" in str(valor):
            for parte in str(valor).split(";"):
                categoria = CATEGORIA_POR_OSM.get((llave, parte.strip()))
                if categoria:
                    return categoria
    return None


def _direccion_de(tags: dict) -> str:
    completa = limpiar(tags.get("addr:full"))
    if completa:
        return completa
    calle = limpiar(tags.get("addr:street"))
    numero = limpiar(tags.get("addr:housenumber"))
    if calle and numero:
        return f"{calle} #{numero}"
    return calle or numero or ""


def elemento_a_negocio(elemento: dict) -> Negocio | None:
    """Convierte un elemento Overpass en un Negocio; None si no es objetivo."""
    tags = elemento.get("tags") or {}
    if not tags:
        return None

    categoria = _categoria_de(tags)
    if categoria is None:
        return None

    nombre = _primer_tag(tags, TAGS_NOMBRE)
    if not nombre:
        # Sin nombre no hay forma de presentarse en la llamada comercial.
        return None

    lat = elemento.get("lat")
    lon = elemento.get("lon")
    if lat is None or lon is None:
        centro = elemento.get("center") or {}
        lat, lon = centro.get("lat"), centro.get("lon")
    if lat is None or lon is None:
        return None

    # --- Telefonos -------------------------------------------------------
    valores_movil = _todos_los_tags(tags, TAGS_MOVIL + TAGS_WHATSAPP)
    valores_generico = _todos_los_tags(tags, TAGS_TELEFONO)

    moviles_directos, fijos_directos = phones.extraer_numeros(*valores_movil)
    moviles_generico, fijos_generico = phones.extraer_numeros(*valores_generico)

    # Un numero etiquetado como "mobile" que no cumple el plan movil colombiano
    # se conserva como fijo: sigue siendo un canal de contacto.
    moviles = list(dict.fromkeys(moviles_directos + moviles_generico))
    fijos = list(dict.fromkeys(fijos_directos + fijos_generico))

    correos = [c.lower() for c in _todos_los_tags(tags, TAGS_EMAIL) if "@" in c]

    tipo = elemento.get("type", "node")
    osm_id = elemento.get("id", "")

    negocio = Negocio(
        nombre=nombre,
        categoria=categoria.nombre,
        grupo=categoria.grupo,
        direccion=_direccion_de(tags),
        barrio=_primer_tag(tags, ("addr:suburb", "addr:neighbourhood", "addr:quarter")),
        localidad=_primer_tag(tags, ("addr:district",)),
        moviles=moviles,
        fijos=fijos,
        correos=list(dict.fromkeys(correos)),
        sitio_web=normalizar_url(_primer_tag(tags, TAGS_WEB)),
        facebook=normalizar_red(_primer_tag(tags, TAGS_FACEBOOK), "facebook.com"),
        instagram=normalizar_red(_primer_tag(tags, TAGS_INSTAGRAM), "instagram.com"),
        linkedin=normalizar_red(_primer_tag(tags, TAGS_LINKEDIN), "linkedin.com/company"),
        horario=limpiar(tags.get("opening_hours")),
        propietario=limpiar(tags.get("operator") or tags.get("brand")),
        fuente="OpenStreetMap",
        place_id=f"osm:{tipo}/{osm_id}",
        lat=float(lat),
        lon=float(lon),
    )
    return negocio


# ---------------------------------------------------------------------------
# Recoleccion
# ---------------------------------------------------------------------------
def recolectar(ajustes: Ajustes,
               cliente: ClienteOverpass | None = None,
               progreso=None) -> list[Negocio]:
    """Recorre las localidades solicitadas y devuelve los negocios encontrados."""
    cliente = cliente or ClienteOverpass(usar_cache=ajustes.usar_cache)
    categorias = ajustes.categorias_activas

    tiles: list[tuple[str, tuple[float, float, float, float]]] = []
    for localidad in ajustes.localidades:
        bbox = LOCALIDAD_BBOXES.get(localidad)
        if not bbox:
            log.warning("Sin bounding box para la localidad %s", localidad)
            continue
        paso = TILE_GRADOS_POR_LOCALIDAD.get(localidad, TILE_GRADOS)
        for tile in mosaicos(bbox, paso):
            tiles.append((localidad, tile))

    log.info("Overpass: %s mosaicos sobre %s localidades",
             len(tiles), len(ajustes.localidades))

    negocios: list[Negocio] = []
    vistos: set[str] = set()

    for indice, (localidad, tile) in enumerate(tiles, start=1):
        consulta = construir_consulta(tile, categorias)
        datos = cliente.ejecutar(consulta)
        if progreso:
            progreso(indice, len(tiles), localidad, len(negocios))
        if not datos:
            continue

        for elemento in datos.get("elements", []):
            negocio = elemento_a_negocio(elemento)
            if negocio is None or negocio.place_id in vistos:
                continue
            vistos.add(negocio.place_id)
            if not negocio.localidad:
                negocio.localidad = localidad
            negocios.append(negocio)

        if ajustes.limite and len(negocios) >= ajustes.limite:
            log.info("Limite de %s registros alcanzado", ajustes.limite)
            break

    log.info("Overpass: %s negocios (%s peticiones, %s desde cache, %s fallos)",
             len(negocios), cliente.peticiones, cliente.aciertos_cache, cliente.fallos)
    return negocios
