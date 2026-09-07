"""Modelo canonico de un negocio y su conversion desde las fuentes crudas."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from . import phones
from .config import CIUDAD, COLUMNAS

_ESPACIOS = re.compile(r"\s+")
_URL_LIMPIA = re.compile(r"^(https?://)?(www\.)?", re.IGNORECASE)


def limpiar(texto: Any) -> str:
    """Colapsa espacios y recorta; tolera None y no-str."""
    if texto is None:
        return ""
    return _ESPACIOS.sub(" ", str(texto)).strip()


def normalizar_url(url: str) -> str:
    """Devuelve una URL absoluta con esquema, o cadena vacia."""
    url = limpiar(url)
    if not url or url.lower() in {"no", "none", "yes", "-"}:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        if "." not in url.split("/")[0]:
            return ""
        url = "https://" + url
    return url


def normalizar_red(valor: str, dominio: str) -> str:
    """Normaliza un handle o URL de red social a URL completa.

    OSM guarda indistintamente ``@handle``, ``handle`` o la URL completa.
    """
    valor = limpiar(valor)
    if not valor:
        return ""
    if valor.startswith("http://") or valor.startswith("https://"):
        return valor
    handle = valor.lstrip("@").strip("/")
    if not handle:
        return ""
    if dominio in handle:  # venia como "facebook.com/algo" sin esquema
        return "https://" + handle.lstrip("/")
    return f"https://{dominio}/{handle}"


def nombre_normalizado(nombre: str) -> str:
    """Clave de comparacion para deduplicar por nombre."""
    from .geo import quitar_tildes

    base = quitar_tildes(limpiar(nombre)).lower()
    base = re.sub(r"\b(s\.?a\.?s\.?|ltda|s\.?a\.?|e\.?u\.?|sucursal|bogota)\b", " ", base)
    base = re.sub(r"[^a-z0-9 ]+", " ", base)
    return _ESPACIOS.sub(" ", base).strip()


@dataclass
class Negocio:
    """Un registro de la base, antes de exportarse."""

    nombre: str = ""
    categoria: str = ""
    grupo: str = ""
    direccion: str = ""
    barrio: str = ""
    localidad: str = ""
    ciudad: str = CIUDAD
    distancia_km: float | None = None

    moviles: list[str] = field(default_factory=list)
    fijos: list[str] = field(default_factory=list)
    correos: list[str] = field(default_factory=list)

    sitio_web: str = ""
    facebook: str = ""
    instagram: str = ""
    linkedin: str = ""

    horario: str = ""
    calificacion: float | None = None
    resenas: int | None = None
    propietario: str = ""
    persona_contacto: str = ""

    fuente: str = ""
    place_id: str = ""
    lat: float | None = None
    lon: float | None = None

    # Campos calculados por el enriquecimiento.
    presencia_digital: str = ""
    score: int = 0
    servicios: str = ""
    observaciones: str = ""
    prioridad: str = ""
    id: str = ""

    # ------------------------------------------------------------------
    @property
    def telefono_principal(self) -> str:
        """El mejor numero para llamar: siempre se prefiere el celular."""
        if self.moviles:
            return phones.formato_legible(self.moviles[0])
        if self.fijos:
            return phones.formato_legible(self.fijos[0])
        return ""

    @property
    def telefonos_todos(self) -> str:
        numeros = [phones.formato_legible(n) for n in self.moviles + self.fijos]
        return " / ".join(numeros)

    @property
    def whatsapp(self) -> str:
        return phones.formato_legible(self.moviles[0]) if self.moviles else ""

    @property
    def link_whatsapp(self) -> str:
        return phones.link_whatsapp(self.moviles[0]) if self.moviles else ""

    @property
    def correo(self) -> str:
        return self.correos[0] if self.correos else ""

    @property
    def tiene_celular(self) -> bool:
        return bool(self.moviles)

    @property
    def tiene_fijo(self) -> bool:
        return bool(self.fijos)

    @property
    def tiene_web(self) -> bool:
        return bool(self.sitio_web)

    @property
    def tiene_redes(self) -> bool:
        return bool(self.facebook or self.instagram or self.linkedin)

    @property
    def tiene_correo(self) -> bool:
        return bool(self.correos)

    @property
    def clave_nombre(self) -> str:
        return nombre_normalizado(self.nombre)

    # ------------------------------------------------------------------
    def asignar_id(self) -> str:
        """ID estable y reproducible entre corridas."""
        semilla = self.place_id or f"{self.clave_nombre}|{self.lat:.5f}|{self.lon:.5f}" \
            if self.lat is not None and self.lon is not None else (
                self.place_id or self.clave_nombre)
        digest = hashlib.sha1(str(semilla).encode("utf-8")).hexdigest()[:10]
        self.id = f"GYX-{digest.upper()}"
        return self.id

    def fusionar(self, otro: "Negocio") -> None:
        """Incorpora los datos de un duplicado, quedandose con lo mejor de cada uno."""
        for numero in otro.moviles:
            if numero not in self.moviles:
                self.moviles.append(numero)
        for numero in otro.fijos:
            if numero not in self.fijos:
                self.fijos.append(numero)
        for correo in otro.correos:
            if correo not in self.correos:
                self.correos.append(correo)

        for campo in ("direccion", "barrio", "localidad", "sitio_web", "facebook",
                      "instagram", "linkedin", "horario", "propietario",
                      "persona_contacto", "grupo", "categoria"):
            if not getattr(self, campo) and getattr(otro, campo):
                setattr(self, campo, getattr(otro, campo))

        if self.calificacion is None and otro.calificacion is not None:
            self.calificacion = otro.calificacion
            self.resenas = otro.resenas
        if not self.place_id and otro.place_id:
            self.place_id = otro.place_id

        fuentes = {f.strip() for f in (self.fuente + "," + otro.fuente).split(",") if f.strip()}
        self.fuente = ", ".join(sorted(fuentes))

    def a_fila(self) -> dict[str, Any]:
        """Proyecta el registro al esquema de salida exigido."""
        return {
            "ID": self.id,
            "Nombre del negocio": self.nombre,
            "Categoria": self.categoria,
            "Grupo": self.grupo,
            "Direccion": self.direccion,
            "Barrio": self.barrio,
            "Localidad": self.localidad,
            "Ciudad": self.ciudad,
            "Distancia aprox. (km)": self.distancia_km,
            "Telefono": self.telefonos_todos,
            "WhatsApp": self.whatsapp,
            "Link WhatsApp": self.link_whatsapp,
            "Correo electronico": ", ".join(self.correos),
            "Sitio web": self.sitio_web,
            "Facebook": self.facebook,
            "Instagram": self.instagram,
            "LinkedIn": self.linkedin,
            "Horario de atencion": self.horario,
            "Calificacion Google": self.calificacion,
            "N Resenas": self.resenas,
            "Propietario / Gerente": self.propietario,
            "Persona de contacto": self.persona_contacto,
            "Presencia digital": self.presencia_digital,
            "Score Contacto": self.score,
            "Servicios sugeridos": self.servicios,
            "Observaciones comerciales": self.observaciones,
            "Prioridad": self.prioridad,
            "Fuente": self.fuente,
            "place_id": self.place_id,
            "lat": self.lat,
            "lon": self.lon,
        }

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


assert set(Negocio().a_fila().keys()) == set(COLUMNAS), "El esquema de salida no coincide"
