"""Normalizacion de telefonos colombianos y deteccion de WhatsApp probable.

Reglas del plan de numeracion vigente en Colombia (desde 2022):
  * Movil  : 10 digitos que empiezan por 3            -> 3XXXXXXXXX
  * Fijo   : 10 digitos que empiezan por 60 + indicativo (Bogota = 1)
             -> 601XXXXXXX
  * Fijo antiguo de Bogota: 7 digitos -> se migra a 601 + los 7 digitos
  * Indicativo pais: 57
"""
from __future__ import annotations

import re

# Separadores frecuentes cuando un tag de OSM trae varios numeros.
_SEPARADORES = re.compile(r"[;,/|]| o | y |\bext\b|\bExt\b", re.IGNORECASE)
_NO_DIGITOS = re.compile(r"\D+")

# Indicativos de fijo validos en Colombia: 60 + [1..8]
_INDICATIVOS_FIJOS = {"601", "602", "604", "605", "606", "607", "608"}

WHATSAPP_NOTA = "WhatsApp probable - validar"


def _solo_digitos(texto: str) -> str:
    return _NO_DIGITOS.sub("", texto or "")


def normalizar_numero(crudo: str) -> tuple[str, str] | None:
    """Normaliza un unico numero.

    Devuelve ``(e164_sin_mas, tipo)`` donde tipo es ``"movil"`` o ``"fijo"``,
    o ``None`` si el numero no es utilizable.
    """
    if not crudo:
        return None

    d = _solo_digitos(str(crudo))
    if not d:
        return None

    # Lineas gratuitas 018000: se conservan como fijo, no son celulares.
    if d.startswith("018000") and len(d) in (11, 12):
        return d, "fijo"

    # Quita el indicativo de pais en sus formas comunes (57, 0057, +57).
    if d.startswith("0057"):
        d = d[4:]
    elif len(d) > 10 and d.startswith("57"):
        d = d[2:]
    # Quita el prefijo de larga distancia nacional "03" / "09".
    if len(d) > 10 and d[0] == "0":
        d = d.lstrip("0")

    # Movil: 3XXXXXXXXX
    if len(d) == 10 and d.startswith("3"):
        return f"57{d}", "movil"

    # Fijo nuevo: 60X XXXXXXX
    if len(d) == 10 and d[:3] in _INDICATIVOS_FIJOS:
        return f"57{d}", "fijo"

    # Fijo antiguo de Bogota (7 digitos) -> anteponer 601
    if len(d) == 7 and d[0] in "23456789":
        return f"57601{d}", "fijo"

    # Fijo antiguo con indicativo de 1 digito (ej. 1 234 5678 = Bogota)
    if len(d) == 8 and d[0] == "1":
        return f"57601{d[1:]}", "fijo"

    return None


def extraer_numeros(*valores: str) -> tuple[list[str], list[str]]:
    """Extrae y clasifica todos los numeros presentes en los valores dados.

    Devuelve ``(moviles, fijos)`` en formato ``57XXXXXXXXXX``, sin duplicados y
    preservando el orden de aparicion.

    Los tags de OSM en Colombia vienen escritos de todas las formas
    imaginables: ``3201234567``, ``320 123 4567 - 310 987 6543``,
    ``Tel 601 2345678 Cel 320 1234567``... Por eso, cuando un fragmento no
    encaja como un unico numero, se rastrea como texto libre en vez de
    descartarlo: de otro modo un guion entre dos celulares hace perder ambos.
    """
    moviles: list[str] = []
    fijos: list[str] = []

    def agregar(numero: str, tipo: str) -> None:
        destino = moviles if tipo == "movil" else fijos
        if numero not in destino:
            destino.append(numero)

    for valor in valores:
        if not valor:
            continue
        for parte in _SEPARADORES.split(str(valor)):
            parte = parte.strip()
            if not parte:
                continue

            resultado = normalizar_numero(parte)
            if resultado is not None:
                agregar(*resultado)
                continue

            # El fragmento no es un numero suelto: puede traer varios juntos,
            # o texto mezclado ("Tel ... Cel ...").
            for numero in buscar_numeros_en_texto(parte)[0]:
                agregar(numero, "movil")
            for numero in buscar_numeros_en_texto(parte)[1]:
                agregar(numero, "fijo")

    return moviles, fijos


def buscar_numeros_en_texto(texto: str, limite: int = 12) -> tuple[list[str], list[str]]:
    """Busca telefonos colombianos dentro de texto libre (HTML de un sitio web).

    Es deliberadamente conservador: solo acepta secuencias que, tras limpiar
    separadores, encajan en el plan de numeracion nacional.
    """
    if not texto:
        return [], []

    candidatos = re.findall(
        r"(?:\+?57[\s\-.]?)?(?:\(?\d{1,3}\)?[\s\-.]?)?\d{3}[\s\-.]?\d{2,4}[\s\-.]?\d{2,4}",
        texto,
    )

    moviles: list[str] = []
    fijos: list[str] = []
    for candidato in candidatos:
        resultado = normalizar_numero(candidato)
        if resultado is None:
            continue
        numero, tipo = resultado
        destino = moviles if tipo == "movil" else fijos
        if numero not in destino and len(destino) < limite:
            destino.append(numero)

    return moviles, fijos


def es_movil(numero_e164: str) -> bool:
    """True si el numero ya normalizado (57XXXXXXXXXX) es celular colombiano."""
    d = _solo_digitos(numero_e164)
    return len(d) == 12 and d.startswith("573")


def link_whatsapp(numero_e164: str) -> str:
    """Construye el enlace wa.me para un movil normalizado."""
    d = _solo_digitos(numero_e164)
    return f"https://wa.me/{d}" if d else ""


def formato_legible(numero_e164: str) -> str:
    """Formatea 573001234567 como +57 300 123 4567 (mas comodo para llamar)."""
    d = _solo_digitos(numero_e164)
    if len(d) == 12 and d.startswith("57"):
        n = d[2:]
        if n.startswith("3"):
            return f"+57 {n[:3]} {n[3:6]} {n[6:]}"
        return f"+57 {n[:3]} {n[3:]}"
    return numero_e164
