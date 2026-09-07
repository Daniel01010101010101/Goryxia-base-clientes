"""Deduplicacion de negocios en tres pasadas, de mas fuerte a mas debil.

1. ``place_id``  - identidad exacta de la fuente.
2. Telefono      - dos registros que comparten un numero son el mismo negocio.
3. Nombre normalizado + distancia menor a 50 metros.

Los duplicados no se descartan: se FUSIONAN, de modo que si un registro traia
el celular y otro el sitio web, el resultado conserva ambos. Eso es lo que
maximiza la contactabilidad de la base.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from .geo import haversine_km
from .models import Negocio

log = logging.getLogger(__name__)

DISTANCIA_MAXIMA_KM = 0.050  # 50 metros
# Tamano de celda de la rejilla espacial: ~55 m en latitud.
CELDA_GRADOS = 0.0005


def _celda(lat: float, lon: float) -> tuple[int, int]:
    return (int(lat / CELDA_GRADOS), int(lon / CELDA_GRADOS))


def _celdas_vecinas(lat: float, lon: float):
    cy, cx = _celda(lat, lon)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            yield (cy + dy, cx + dx)


def deduplicar(negocios: list[Negocio]) -> tuple[list[Negocio], dict[str, int]]:
    """Devuelve la lista deduplicada y un conteo de duplicados por regla."""
    conteo = {"place_id": 0, "telefono": 0, "nombre_distancia": 0}

    # ------------------------------------------------------------------
    # Pasada 1: place_id
    # ------------------------------------------------------------------
    por_place_id: dict[str, Negocio] = {}
    sin_place_id: list[Negocio] = []
    for negocio in negocios:
        if not negocio.place_id:
            sin_place_id.append(negocio)
            continue
        existente = por_place_id.get(negocio.place_id)
        if existente is None:
            por_place_id[negocio.place_id] = negocio
        else:
            existente.fusionar(negocio)
            conteo["place_id"] += 1

    candidatos = list(por_place_id.values()) + sin_place_id

    # ------------------------------------------------------------------
    # Pasada 2: telefono compartido
    # ------------------------------------------------------------------
    por_telefono: dict[str, Negocio] = {}
    resultado_fase2: list[Negocio] = []
    for negocio in candidatos:
        numeros = negocio.moviles + negocio.fijos
        maestro = next((por_telefono[n] for n in numeros if n in por_telefono), None)
        if maestro is not None and maestro is not negocio:
            maestro.fusionar(negocio)
            conteo["telefono"] += 1
            # El maestro pudo ganar numeros nuevos: se reindexan.
            for numero in maestro.moviles + maestro.fijos:
                por_telefono.setdefault(numero, maestro)
            continue
        for numero in numeros:
            por_telefono.setdefault(numero, negocio)
        resultado_fase2.append(negocio)

    # ------------------------------------------------------------------
    # Pasada 3: mismo nombre normalizado a menos de 50 m
    # ------------------------------------------------------------------
    rejilla: dict[tuple[int, int], list[Negocio]] = defaultdict(list)
    resultado: list[Negocio] = []

    for negocio in resultado_fase2:
        if negocio.lat is None or negocio.lon is None or not negocio.clave_nombre:
            resultado.append(negocio)
            continue

        clave = negocio.clave_nombre
        duplicado = None
        for celda in _celdas_vecinas(negocio.lat, negocio.lon):
            for otro in rejilla.get(celda, ()):
                if otro.clave_nombre != clave:
                    continue
                distancia = haversine_km(negocio.lat, negocio.lon, otro.lat, otro.lon)
                if distancia <= DISTANCIA_MAXIMA_KM:
                    duplicado = otro
                    break
            if duplicado:
                break

        if duplicado is not None:
            duplicado.fusionar(negocio)
            conteo["nombre_distancia"] += 1
            continue

        rejilla[_celda(negocio.lat, negocio.lon)].append(negocio)
        resultado.append(negocio)

    total_duplicados = sum(conteo.values())
    log.info("Deduplicacion: %s -> %s registros (%s duplicados: %s)",
             len(negocios), len(resultado), total_duplicados, conteo)
    return resultado, conteo
