"""Genera una salida de ejemplo a partir de la fixture sintetica.

Sirve para revisar el FORMATO de los entregables (Excel con Dashboard, CSV,
PDF y GeoJSON) sin consumir la red ni la cuota de ninguna API.

Los negocios son INVENTADOS. Para generar la base real de Bogota se usa:
    python -m goryxia
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from goryxia.config import Ajustes  # noqa: E402
from goryxia.exporters import (  # noqa: E402
    exportar_csv,
    exportar_excel,
    exportar_geojson,
    exportar_pdf,
)
from goryxia.pipeline import ejecutar  # noqa: E402
from goryxia.sources.overpass import elemento_a_negocio  # noqa: E402

FIXTURE = RAIZ / "tests" / "fixtures" / "overpass_demo.json"
SALIDA = RAIZ / "data" / "demo"

AVISO = """\
Los archivos de esta carpeta son una MUESTRA DE FORMATO generada a partir de
datos sinteticos (tests/fixtures/overpass_demo.json). Los negocios NO existen:
todos los nombres empiezan por "DEMO" y los telefonos usan el rango de pruebas
300 000 XXXX.

Para generar la base real de PYMEs de Bogota, con datos de OpenStreetMap:

    python -m goryxia

Eso escribe los archivos definitivos en data/ (sin el prefijo DEMO_).
"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    negocios = [n for n in (elemento_a_negocio(e) for e in datos["elements"]) if n]
    print(f"Fixture: {len(negocios)} negocios sinteticos")

    ajustes = Ajustes(scrapear_webs=False, usar_datos_abiertos=False, usar_google=False)
    resultado = ejecutar(ajustes, negocios_precargados=negocios, exportar=False)

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "LEEME.txt").write_text(AVISO, encoding="utf-8")

    exportar_excel(resultado.negocios, SALIDA / "DEMO_Base_Clientes_GoryxIA.xlsx",
                   resultado.resumen)
    exportar_csv(resultado.negocios, SALIDA / "DEMO_Base_Clientes_GoryxIA.csv")
    exportar_pdf(resultado.negocios, SALIDA / "DEMO_Base_Clientes_GoryxIA.pdf",
                 resultado.resumen, max_leads=120)
    exportar_geojson(resultado.negocios, SALIDA / "DEMO_clientes.geojson")

    r = resultado.resumen
    print(f"\nDemo generada en {SALIDA}")
    print(f"  {r.total} registros | {r.con_celular} con celular ({r.pct_celular}%) "
          f"| {r.contactables} contactables ({r.pct_contactables}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
