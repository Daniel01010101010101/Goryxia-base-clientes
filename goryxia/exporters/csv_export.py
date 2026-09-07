"""Exportacion a CSV (UTF-8 con BOM para que Excel en Windows lo abra bien)."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from ..config import COLUMNAS, CSV_PATH
from ..models import Negocio

log = logging.getLogger(__name__)


def exportar_csv(negocios: list[Negocio], ruta: Path = CSV_PATH) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS, extrasaction="ignore")
        escritor.writeheader()
        for negocio in negocios:
            escritor.writerow(negocio.a_fila())
    log.info("CSV escrito: %s (%s filas)", ruta, len(negocios))
    return ruta
