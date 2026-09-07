"""Score de contactabilidad, presencia digital y prioridad comercial."""
from __future__ import annotations

from .config import (
    CADENAS_NACIONALES,
    LOCALIDADES_PRIORITARIAS,
    SCORE_CELULAR,
    SCORE_FIJO_WEB,
    SCORE_REDES,
    SCORE_SIN_CONTACTO,
    SCORE_WEB,
)
from .geo import quitar_tildes
from .models import Negocio

PRESENCIA_ALTA = "ALTA"
PRESENCIA_MEDIA = "MEDIA"
PRESENCIA_BAJA = "BAJA"


def calcular_score(negocio: Negocio) -> int:
    """Score de contactabilidad segun las reglas comerciales de GoryxIA.

    100 = celular / WhatsApp, 80 = fijo + web, 60 = web, 40 = redes, 0 = nada.
    """
    if negocio.tiene_celular:
        return SCORE_CELULAR
    if negocio.tiene_fijo and negocio.tiene_web:
        return SCORE_FIJO_WEB
    if negocio.tiene_web:
        return SCORE_WEB
    if negocio.tiene_redes:
        return SCORE_REDES
    if negocio.tiene_fijo or negocio.tiene_correo:
        # Un fijo sin web sigue siendo contactable: vale mas que nada pero
        # menos que una red social, donde si hay canal digital de venta.
        return 30
    return SCORE_SIN_CONTACTO


def calcular_presencia_digital(negocio: Negocio) -> str:
    """ALTA = web + Facebook + Instagram; MEDIA = web o una red; BAJA = nada."""
    tiene_fb = bool(negocio.facebook)
    tiene_ig = bool(negocio.instagram)
    if negocio.tiene_web and tiene_fb and tiene_ig:
        return PRESENCIA_ALTA
    if negocio.tiene_web or tiene_fb or tiene_ig or negocio.linkedin:
        return PRESENCIA_MEDIA
    return PRESENCIA_BAJA


def es_cadena(nombre: str) -> bool:
    """Detecta cadenas nacionales o multinacionales (no son PYMEs objetivo)."""
    limpio = quitar_tildes(nombre or "").lower()
    return any(marca in limpio for marca in CADENAS_NACIONALES)


def calcular_prioridad(negocio: Negocio) -> str:
    """Prioridad comercial: ALTA / MEDIA / BAJA.

    ALTA  = celular o WhatsApp + presencia digital baja + servicios vendibles.
            Es el perfil ideal: se le puede escribir hoy y necesita lo que
            vendemos porque hoy no tiene presencia.
    MEDIA = hay telefono fijo o pagina web.
    BAJA  = cadenas grandes (decision de compra centralizada) o sin contacto.
    """
    if es_cadena(negocio.nombre):
        return "BAJA"

    presencia = negocio.presencia_digital or calcular_presencia_digital(negocio)

    if negocio.tiene_celular and presencia in (PRESENCIA_BAJA, PRESENCIA_MEDIA):
        return "ALTA"
    if negocio.tiene_celular and presencia == PRESENCIA_ALTA:
        # Contactable de inmediato, pero ya tiene canal digital montado.
        return "MEDIA"
    if negocio.tiene_fijo or negocio.tiene_web:
        return "MEDIA"
    return "BAJA"


def bonus_localidad(localidad: str) -> int:
    """Desempate a favor de las localidades priorizadas por la operacion."""
    if not localidad:
        return 0
    limpio = quitar_tildes(localidad).lower()
    prioritarias = {quitar_tildes(l).lower() for l in LOCALIDADES_PRIORITARIAS}
    return 1 if limpio in prioritarias else 0


def enriquecer(negocio: Negocio) -> Negocio:
    """Calcula presencia, score y prioridad en el orden correcto de dependencia."""
    negocio.presencia_digital = calcular_presencia_digital(negocio)
    negocio.score = calcular_score(negocio)
    negocio.prioridad = calcular_prioridad(negocio)
    return negocio


def clave_orden(negocio: Negocio) -> tuple:
    """Clave de ordenamiento final de la base.

    Orden exigido por la operacion comercial:
      1. Negocios con celular
      2. Negocios con WhatsApp probable
      3. Negocios con correo
      4. Negocios con web
      5. Negocios sin contacto
    Dentro de cada nivel se ordena por score, prioridad, localidad priorizada,
    presencia digital baja (mas necesidad de nuestros servicios) y resenas.
    """
    escalon = 5
    if negocio.tiene_celular:
        escalon = 1               # celular == WhatsApp probable en Colombia
    elif negocio.tiene_correo:
        escalon = 3
    elif negocio.tiene_web:
        escalon = 4

    orden_prioridad = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}.get(negocio.prioridad, 3)
    necesidad = {PRESENCIA_BAJA: 0, PRESENCIA_MEDIA: 1, PRESENCIA_ALTA: 2}.get(
        negocio.presencia_digital, 3
    )
    return (
        escalon,
        -negocio.score,
        orden_prioridad,
        -bonus_localidad(negocio.localidad),
        necesidad,
        -(negocio.resenas or 0),
        negocio.nombre.lower(),
    )
