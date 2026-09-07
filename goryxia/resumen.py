"""Estadisticas de la base, compartidas por el Dashboard de Excel y el PDF."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .config import LOCALIDADES_PRIORITARIAS, REFERENCE_NAME
from .geo import quitar_tildes
from .models import Negocio


@dataclass
class Resumen:
    """Fotografia de la base generada, en terminos comerciales."""

    total: int = 0
    con_celular: int = 0
    con_whatsapp: int = 0
    con_correo: int = 0
    con_web: int = 0
    con_redes: int = 0
    con_fijo: int = 0
    sin_contacto: int = 0
    contactables: int = 0

    por_localidad: list[tuple[str, int, int]] = field(default_factory=list)
    por_categoria: list[tuple[str, int, int]] = field(default_factory=list)
    por_prioridad: list[tuple[str, int]] = field(default_factory=list)
    por_presencia: list[tuple[str, int]] = field(default_factory=list)
    por_score: list[tuple[str, int]] = field(default_factory=list)
    por_fuente: list[tuple[str, int]] = field(default_factory=list)

    generado: str = ""
    referencia: str = REFERENCE_NAME

    @property
    def pct_celular(self) -> float:
        return round(100 * self.con_celular / self.total, 1) if self.total else 0.0

    @property
    def pct_contactables(self) -> float:
        return round(100 * self.contactables / self.total, 1) if self.total else 0.0


def _pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1) if total else 0.0


def construir(negocios: list[Negocio]) -> Resumen:
    """Calcula todas las metricas de la base en una sola pasada."""
    resumen = Resumen(total=len(negocios))
    resumen.generado = datetime.now().strftime("%Y-%m-%d %H:%M")

    localidad_total: Counter[str] = Counter()
    localidad_celular: Counter[str] = Counter()
    categoria_total: Counter[str] = Counter()
    categoria_celular: Counter[str] = Counter()
    prioridad: Counter[str] = Counter()
    presencia: Counter[str] = Counter()
    score: Counter[str] = Counter()
    fuente: Counter[str] = Counter()

    for negocio in negocios:
        tiene_celular = negocio.tiene_celular
        resumen.con_celular += tiene_celular
        resumen.con_whatsapp += tiene_celular  # celular colombiano = WhatsApp probable
        resumen.con_correo += negocio.tiene_correo
        resumen.con_web += negocio.tiene_web
        resumen.con_redes += negocio.tiene_redes
        resumen.con_fijo += negocio.tiene_fijo

        contactable = tiene_celular or negocio.tiene_fijo or negocio.tiene_correo
        resumen.contactables += contactable
        if not (contactable or negocio.tiene_web or negocio.tiene_redes):
            resumen.sin_contacto += 1

        loc = negocio.localidad or "Sin localidad"
        localidad_total[loc] += 1
        localidad_celular[loc] += tiene_celular

        cat = negocio.categoria or "Sin categoria"
        categoria_total[cat] += 1
        categoria_celular[cat] += tiene_celular

        prioridad[negocio.prioridad or "Sin prioridad"] += 1
        presencia[negocio.presencia_digital or "Sin dato"] += 1
        score[str(negocio.score)] += 1
        for f in (negocio.fuente or "Sin fuente").split(","):
            fuente[f.strip()] += 1

    # Localidades: primero las priorizadas por la operacion, luego por volumen.
    prioritarias = {quitar_tildes(l).lower() for l in LOCALIDADES_PRIORITARIAS}
    resumen.por_localidad = sorted(
        ((loc, total, localidad_celular[loc]) for loc, total in localidad_total.items()),
        key=lambda fila: (quitar_tildes(fila[0]).lower() not in prioritarias, -fila[2], -fila[1]),
    )
    resumen.por_categoria = sorted(
        ((cat, total, categoria_celular[cat]) for cat, total in categoria_total.items()),
        key=lambda fila: (-fila[2], -fila[1]),
    )
    resumen.por_prioridad = [(k, prioridad[k]) for k in ("ALTA", "MEDIA", "BAJA")
                             if prioridad.get(k)]
    resumen.por_presencia = [(k, presencia[k]) for k in ("ALTA", "MEDIA", "BAJA")
                             if presencia.get(k)]
    resumen.por_score = sorted(score.items(), key=lambda kv: -int(kv[0]))
    resumen.por_fuente = sorted(fuente.items(), key=lambda kv: -kv[1])
    return resumen


def kpis(resumen: Resumen) -> list[tuple[str, object, str]]:
    """KPIs listos para pintar: (etiqueta, valor, comentario)."""
    total = resumen.total
    return [
        ("Total de negocios", total, "Registros unicos tras deduplicacion"),
        ("Con celular / WhatsApp", resumen.con_celular,
         f"{_pct(resumen.con_celular, total)}% - contactables hoy mismo"),
        ("Con correo electronico", resumen.con_correo,
         f"{_pct(resumen.con_correo, total)}% - campanas de correo"),
        ("Con telefono fijo", resumen.con_fijo, f"{_pct(resumen.con_fijo, total)}%"),
        ("Con sitio web", resumen.con_web, f"{_pct(resumen.con_web, total)}%"),
        ("Con redes sociales", resumen.con_redes, f"{_pct(resumen.con_redes, total)}%"),
        ("Contactables (cel/fijo/correo)", resumen.contactables,
         f"{resumen.pct_contactables}% de la base"),
        ("Sin ningun contacto", resumen.sin_contacto,
         f"{_pct(resumen.sin_contacto, total)}% - requieren trabajo de campo"),
    ]
