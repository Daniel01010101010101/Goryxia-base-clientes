"""Servicios GoryxIA sugeridos y observaciones comerciales por registro."""
from __future__ import annotations

from .config import SERVICIOS_DEFECTO, SERVICIOS_POR_GRUPO
from .models import Negocio
from .scoring import PRESENCIA_ALTA, PRESENCIA_BAJA, PRESENCIA_MEDIA, es_cadena


def servicios_sugeridos(negocio: Negocio) -> str:
    """Paquete de servicios recomendado segun el giro del negocio."""
    base = list(SERVICIOS_POR_GRUPO.get(negocio.grupo, SERVICIOS_DEFECTO))

    # Ajustes finos segun lo que le falta al negocio.
    if not negocio.tiene_web and "Pagina web" not in base and "Landing page" not in base:
        base.append("Pagina web")
    if negocio.tiene_celular and "Chatbot IA" not in base and "Agente IA" not in base:
        base.append("Automatizacion WhatsApp")
    if negocio.grupo == "Comercio" and not negocio.tiene_redes:
        base.append("Gestion de redes")

    return " | ".join(dict.fromkeys(base))


def observaciones_comerciales(negocio: Negocio) -> str:
    """Frase corta y accionable para el comercial que va a hacer el contacto."""
    notas: list[str] = []

    if negocio.tiene_celular:
        notas.append("Contactar hoy por WhatsApp (celular verificado en fuente publica)")
    elif negocio.tiene_fijo:
        notas.append("Llamar a fijo y pedir el celular del propietario")
    elif negocio.tiene_correo:
        notas.append("Enviar propuesta por correo y hacer seguimiento")
    elif negocio.tiene_web:
        notas.append("Buscar celular en el sitio web o formulario de contacto")
    elif negocio.tiene_redes:
        notas.append("Escribir por mensaje directo en redes sociales")
    else:
        notas.append("Sin canal de contacto: requiere visita en campo o busqueda manual")

    if negocio.presencia_digital == PRESENCIA_BAJA:
        notas.append("sin presencia digital, oportunidad alta para paquete completo")
    elif negocio.presencia_digital == PRESENCIA_MEDIA:
        notas.append("presencia digital parcial, ofrecer lo que le falta")
    elif negocio.presencia_digital == PRESENCIA_ALTA:
        notas.append("ya tiene web y redes, entrar por automatizacion e IA")

    if not negocio.horario:
        notas.append("horario no publicado")

    if negocio.calificacion is not None and negocio.resenas:
        if negocio.calificacion < 4.0:
            notas.append(
                f"calificacion {negocio.calificacion} con {negocio.resenas} resenas: "
                "argumento de mejora de reputacion"
            )
        elif negocio.resenas >= 50:
            notas.append(f"negocio consolidado ({negocio.resenas} resenas)")

    if es_cadena(negocio.nombre):
        notas.append("posible cadena: la decision de compra suele ser centralizada")

    return "; ".join(notas).capitalize()


def enriquecer(negocio: Negocio) -> Negocio:
    negocio.servicios = servicios_sugeridos(negocio)
    negocio.observaciones = observaciones_comerciales(negocio)
    return negocio
