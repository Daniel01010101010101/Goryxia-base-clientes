"""Fuente PRIORIDAD 4: sitios web oficiales publicos de los negocios.

Es el modulo de mayor rendimiento comercial del proyecto: convierte registros
que solo tenian pagina web (60 puntos) en registros con celular y WhatsApp
(100 puntos). Muchas PYMEs de Bogota publican su celular y un boton de
WhatsApp en el home o en /contacto aunque no lo hayan mapeado en OSM.

Buenas practicas aplicadas:
  * Se respeta robots.txt.
  * Un unico hilo por dominio, maximo de paginas por sitio y tope de bytes.
  * Timeouts cortos y User-Agent identificable con correo de contacto.
"""
from __future__ import annotations

import concurrent.futures
import html
import json
import logging
import re
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .. import phones
from ..config import (
    CACHE_DIR,
    USER_AGENT,
    WEB_SCRAPE_MAX_BYTES,
    WEB_SCRAPE_TIMEOUT,
    WEB_SCRAPE_WORKERS,
)
from ..models import Negocio, normalizar_red

log = logging.getLogger(__name__)

RUTA_CACHE_WEB = CACHE_DIR / "webs.json"

# Rutas donde las PYMEs colombianas suelen publicar el celular.
RUTAS_CONTACTO = ("", "/contacto", "/contactenos", "/contact", "/nosotros",
                  "/quienes-somos", "/index.php/contacto")
MAX_PAGINAS_POR_SITIO = 3

_RE_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
_RE_WA = re.compile(
    r"(?:wa\.me|api\.whatsapp\.com/send|web\.whatsapp\.com/send|whatsapp://send)"
    r"[/?][^\"'\s<>]*?(\d{10,13})",
    re.IGNORECASE,
)
_RE_TEL = re.compile(r"tel:\+?([\d\s\-().]{7,20})", re.IGNORECASE)
_RE_FACEBOOK = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/([^\"'\s<>?&]+)", re.I)
_RE_INSTAGRAM = re.compile(r"https?://(?:www\.)?instagram\.com/([^\"'\s<>?&/]+)", re.I)
_RE_LINKEDIN = re.compile(r"https?://(?:www\.)?linkedin\.com/(company/[^\"'\s<>?&/]+|in/[^\"'\s<>?&/]+)", re.I)
_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_TAGS = re.compile(r"<[^>]+>")

# Handles genericos de las propias redes que no son del negocio.
_HANDLES_IGNORADOS = {
    "sharer", "share", "sharer.php", "dialog", "plugins", "tr", "profile.php",
    "pages", "people", "explore", "accounts", "p", "reel", "help", "login",
    "privacy", "policies", "legal", "home", "hashtag", "groups", "watch",
}
_EMAILS_IGNORADOS = re.compile(
    r"(sentry|wixpress|example|yourdomain|dominio|email\.com|@2x|\.png|\.jpg|\.webp)",
    re.IGNORECASE,
)


@dataclass
class ResultadoWeb:
    """Lo que se logro extraer de un sitio web."""

    url: str
    moviles: list[str] = field(default_factory=list)
    fijos: list[str] = field(default_factory=list)
    correos: list[str] = field(default_factory=list)
    facebook: str = ""
    instagram: str = ""
    linkedin: str = ""
    whatsapp_confirmado: bool = False
    error: str = ""

    def aporta_algo(self) -> bool:
        return bool(self.moviles or self.fijos or self.correos
                    or self.facebook or self.instagram or self.linkedin)


def _texto_plano(html_crudo: str) -> str:
    sin_scripts = _RE_SCRIPT.sub(" ", html_crudo)
    sin_tags = _RE_TAGS.sub(" ", sin_scripts)
    return html.unescape(sin_tags)


def _primer_handle(patron: re.Pattern, contenido: str, dominio: str) -> str:
    for coincidencia in patron.finditer(contenido):
        handle = coincidencia.group(1).strip("/")
        if not handle:
            continue
        # LinkedIn llega como "company/x" o "in/x"; el resto es un handle plano.
        if handle.startswith(("company/", "in/")):
            return f"https://linkedin.com/{handle}"
        # Se descartan rutas de la propia red social (sharer, plugins, login...)
        primer_segmento = handle.split("/")[0].lower()
        if primer_segmento in _HANDLES_IGNORADOS or "." in primer_segmento:
            continue
        return normalizar_red(primer_segmento, dominio)
    return ""


def extraer_de_html(html_crudo: str, url: str) -> ResultadoWeb:
    """Extrae contactos de una pagina. Funcion pura: facil de testear."""
    resultado = ResultadoWeb(url=url)

    # 1) Enlaces de WhatsApp: son la senal mas fuerte y ya vienen normalizados.
    for coincidencia in _RE_WA.finditer(html_crudo):
        crudo = coincidencia.group(1)
        normalizado = phones.normalizar_numero(crudo)
        if normalizado and normalizado[1] == "movil":
            if normalizado[0] not in resultado.moviles:
                resultado.moviles.append(normalizado[0])
                resultado.whatsapp_confirmado = True

    # 2) Enlaces tel:
    for coincidencia in _RE_TEL.finditer(html_crudo):
        normalizado = phones.normalizar_numero(coincidencia.group(1))
        if not normalizado:
            continue
        numero, tipo = normalizado
        destino = resultado.moviles if tipo == "movil" else resultado.fijos
        if numero not in destino:
            destino.append(numero)

    # 3) Texto visible (celulares escritos "3XX XXX XXXX").
    texto = _texto_plano(html_crudo)
    moviles_texto, fijos_texto = phones.buscar_numeros_en_texto(texto)
    for numero in moviles_texto:
        if numero not in resultado.moviles:
            resultado.moviles.append(numero)
    for numero in fijos_texto:
        if numero not in resultado.fijos:
            resultado.fijos.append(numero)

    # 4) Correos.
    for correo in _RE_EMAIL.findall(html_crudo):
        correo = correo.lower().strip(".")
        if _EMAILS_IGNORADOS.search(correo):
            continue
        if correo not in resultado.correos and len(resultado.correos) < 4:
            resultado.correos.append(correo)

    # 5) Redes sociales.
    resultado.facebook = _primer_handle(_RE_FACEBOOK, html_crudo, "facebook.com")
    resultado.instagram = _primer_handle(_RE_INSTAGRAM, html_crudo, "instagram.com")
    resultado.linkedin = _primer_handle(_RE_LINKEDIN, html_crudo, "linkedin.com")

    return resultado


class RaspadorWeb:
    """Descarga y analiza sitios web de negocios, en paralelo y con cache."""

    def __init__(self, usar_cache: bool = True, ruta_cache: Path = RUTA_CACHE_WEB):
        self.usar_cache = usar_cache
        self.ruta_cache = ruta_cache
        self.cache: dict[str, dict] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.exitos = 0
        self.errores = 0
        if usar_cache and ruta_cache.exists():
            try:
                self.cache = json.loads(ruta_cache.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.cache = {}

    # ------------------------------------------------------------------
    def _permitido(self, sesion: requests.Session, url: str) -> bool:
        """Consulta robots.txt una vez por dominio; ante la duda, permite."""
        partes = urllib.parse.urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        if base not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                respuesta = sesion.get(f"{base}/robots.txt", timeout=WEB_SCRAPE_TIMEOUT)
                if respuesta.status_code == 200:
                    parser.parse(respuesta.text.splitlines())
                else:
                    parser = None
            except requests.RequestException:
                parser = None
            self.robots[base] = parser
        parser = self.robots.get(base)
        if parser is None:
            return True
        try:
            return parser.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def _descargar(self, sesion: requests.Session, url: str) -> str:
        respuesta = sesion.get(url, timeout=WEB_SCRAPE_TIMEOUT, stream=True,
                               allow_redirects=True)
        respuesta.raise_for_status()
        tipo = respuesta.headers.get("Content-Type", "")
        if "html" not in tipo and "text" not in tipo:
            return ""
        contenido = respuesta.raw.read(WEB_SCRAPE_MAX_BYTES, decode_content=True) or b""
        codificacion = respuesta.encoding or "utf-8"
        return contenido.decode(codificacion, errors="ignore")

    def analizar(self, url: str) -> ResultadoWeb:
        """Analiza un sitio: home y, si hace falta, sus paginas de contacto."""
        if self.usar_cache and url in self.cache:
            return ResultadoWeb(**self.cache[url])

        resultado = ResultadoWeb(url=url)
        sesion = requests.Session()
        sesion.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-CO,es;q=0.9",
        })

        base = url.rstrip("/")
        paginas_leidas = 0
        for ruta in RUTAS_CONTACTO:
            if paginas_leidas >= MAX_PAGINAS_POR_SITIO:
                break
            destino = base + ruta if ruta else base
            try:
                if not self._permitido(sesion, destino):
                    continue
                contenido = self._descargar(sesion, destino)
            except requests.RequestException as exc:
                if not ruta:  # el home fallo: el sitio no responde
                    resultado.error = type(exc).__name__
                continue
            if not contenido:
                continue

            paginas_leidas += 1
            parcial = extraer_de_html(contenido, destino)
            for numero in parcial.moviles:
                if numero not in resultado.moviles:
                    resultado.moviles.append(numero)
            for numero in parcial.fijos:
                if numero not in resultado.fijos:
                    resultado.fijos.append(numero)
            for correo in parcial.correos:
                if correo not in resultado.correos:
                    resultado.correos.append(correo)
            resultado.facebook = resultado.facebook or parcial.facebook
            resultado.instagram = resultado.instagram or parcial.instagram
            resultado.linkedin = resultado.linkedin or parcial.linkedin
            resultado.whatsapp_confirmado |= parcial.whatsapp_confirmado

            # Ya tenemos lo mas valioso: no hace falta seguir pidiendo paginas.
            if resultado.moviles and resultado.correos:
                break

        sesion.close()
        if resultado.error:
            self.errores += 1
        else:
            self.exitos += 1
        if self.usar_cache:
            self.cache[url] = {
                "url": resultado.url,
                "moviles": resultado.moviles,
                "fijos": resultado.fijos,
                "correos": resultado.correos,
                "facebook": resultado.facebook,
                "instagram": resultado.instagram,
                "linkedin": resultado.linkedin,
                "whatsapp_confirmado": resultado.whatsapp_confirmado,
                "error": resultado.error,
            }
        return resultado

    def guardar_cache(self) -> None:
        if not self.usar_cache:
            return
        self.ruta_cache.parent.mkdir(parents=True, exist_ok=True)
        self.ruta_cache.write_text(json.dumps(self.cache, ensure_ascii=False),
                                   encoding="utf-8")


def enriquecer_negocios(negocios: list[Negocio],
                        max_sitios: int = 4000,
                        usar_cache: bool = True,
                        progreso=None) -> dict[str, int]:
    """Enriquece en paralelo los negocios que tienen sitio web.

    Prioriza los que aun NO tienen celular: son los que mas suben de score.
    Devuelve un resumen de cuanto mejoro la base.
    """
    candidatos = [n for n in negocios if n.sitio_web]
    # Primero los que no tienen celular (mayor ganancia por peticion).
    candidatos.sort(key=lambda n: (n.tiene_celular, not n.tiene_correo))
    candidatos = candidatos[:max_sitios]

    if not candidatos:
        return {"sitios": 0, "nuevos_celulares": 0, "nuevos_correos": 0, "nuevas_redes": 0}

    raspador = RaspadorWeb(usar_cache=usar_cache)
    resumen = {"sitios": len(candidatos), "nuevos_celulares": 0,
               "nuevos_correos": 0, "nuevas_redes": 0, "whatsapp_confirmado": 0}

    log.info("Raspando %s sitios web con %s hilos", len(candidatos), WEB_SCRAPE_WORKERS)

    with concurrent.futures.ThreadPoolExecutor(max_workers=WEB_SCRAPE_WORKERS) as pool:
        futuros = {pool.submit(raspador.analizar, n.sitio_web): n for n in candidatos}
        for indice, futuro in enumerate(concurrent.futures.as_completed(futuros), 1):
            negocio = futuros[futuro]
            try:
                resultado = futuro.result()
            except Exception as exc:  # noqa: BLE001 - una web rota no debe tumbar todo
                log.debug("Error analizando %s: %s", negocio.sitio_web, exc)
                continue

            tenia_celular = negocio.tiene_celular
            tenia_correo = negocio.tiene_correo
            tenia_redes = negocio.tiene_redes

            for numero in resultado.moviles:
                if numero not in negocio.moviles:
                    negocio.moviles.append(numero)
            for numero in resultado.fijos:
                if numero not in negocio.fijos:
                    negocio.fijos.append(numero)
            for correo in resultado.correos:
                if correo not in negocio.correos:
                    negocio.correos.append(correo)
            negocio.facebook = negocio.facebook or resultado.facebook
            negocio.instagram = negocio.instagram or resultado.instagram
            negocio.linkedin = negocio.linkedin or resultado.linkedin

            if resultado.aporta_algo() and "Sitio web oficial" not in negocio.fuente:
                negocio.fuente = f"{negocio.fuente}, Sitio web oficial".strip(", ")

            if not tenia_celular and negocio.tiene_celular:
                resumen["nuevos_celulares"] += 1
            if not tenia_correo and negocio.tiene_correo:
                resumen["nuevos_correos"] += 1
            if not tenia_redes and negocio.tiene_redes:
                resumen["nuevas_redes"] += 1
            if resultado.whatsapp_confirmado:
                resumen["whatsapp_confirmado"] += 1

            if progreso:
                progreso(indice, len(candidatos), resumen["nuevos_celulares"])

    raspador.guardar_cache()
    log.info("Web scraping: +%s celulares, +%s correos, +%s redes (%s errores)",
             resumen["nuevos_celulares"], resumen["nuevos_correos"],
             resumen["nuevas_redes"], raspador.errores)
    return resumen
