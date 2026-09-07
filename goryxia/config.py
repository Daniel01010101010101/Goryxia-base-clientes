"""Configuracion central del generador de base de clientes GoryxIA - Bogota D.C.

Todo lo que un operador comercial querria ajustar (localidades, categorias,
prioridades, servicios ofertados, umbrales de scoring) vive aqui.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GORYXIA_DATA_DIR", BASE_DIR / "data"))
CACHE_DIR = DATA_DIR / "cache"

XLSX_PATH = DATA_DIR / "Base_Clientes_GoryxIA.xlsx"
CSV_PATH = DATA_DIR / "Base_Clientes_GoryxIA.csv"
PDF_PATH = DATA_DIR / "Base_Clientes_GoryxIA.pdf"
GEOJSON_PATH = DATA_DIR / "clientes.geojson"

# --------------------------------------------------------------------------
# Geografia de Bogota
# --------------------------------------------------------------------------
# Bounding box del area urbana de Bogota D.C. (excluye la ruralidad de Sumapaz,
# que no aporta PYMEs contactables). Formato Overpass: (sur, oeste, norte, este)
BOGOTA_BBOX = (4.4600, -74.2400, 4.8400, -73.9900)

# Punto de referencia para "Distancia aprox. (km)". Por defecto Plaza de Bolivar.
REFERENCE_POINT = (
    float(os.environ.get("GORYXIA_REF_LAT", "4.5981")),
    float(os.environ.get("GORYXIA_REF_LON", "-74.0758")),
)
REFERENCE_NAME = os.environ.get("GORYXIA_REF_NAME", "Plaza de Bolivar, Bogota")

CIUDAD = "Bogota D.C."

# Localidades priorizadas (se recorren primero y reciben un bonus de prioridad).
LOCALIDADES_PRIORITARIAS = [
    "Bosa",
    "Kennedy",
    "Ciudad Bolivar",
    "Tunjuelito",
    "Fontibon",
    "Engativa",
    "Puente Aranda",
]

# Las 20 localidades del Distrito Capital.
LOCALIDADES_BOGOTA = LOCALIDADES_PRIORITARIAS + [
    "Usaquen",
    "Chapinero",
    "Santa Fe",
    "San Cristobal",
    "Usme",
    "Barrios Unidos",
    "Teusaquillo",
    "Los Martires",
    "Antonio Narino",
    "La Candelaria",
    "Rafael Uribe Uribe",
    "Suba",
    "Sumapaz",
]

# Bounding boxes aproximados por localidad. Se usan para (a) trocear las
# consultas Overpass y (b) asignar localidad cuando no se pudo descargar el
# poligono administrativo real. El poligono real de OSM siempre tiene prioridad.
LOCALIDAD_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "Bosa": (4.5800, -74.2200, 4.6400, -74.1600),
    "Kennedy": (4.5850, -74.1900, 4.6650, -74.1150),
    "Ciudad Bolivar": (4.4600, -74.2100, 4.5900, -74.1200),
    "Tunjuelito": (4.5550, -74.1600, 4.6000, -74.1200),
    "Fontibon": (4.6300, -74.1900, 4.7200, -74.1150),
    "Engativa": (4.6700, -74.1600, 4.7400, -74.0800),
    "Puente Aranda": (4.6000, -74.1400, 4.6400, -74.0800),
    "Usaquen": (4.6900, -74.0700, 4.8100, -74.0000),
    "Chapinero": (4.6300, -74.0700, 4.7200, -74.0100),
    "Santa Fe": (4.5800, -74.0900, 4.6400, -74.0100),
    "San Cristobal": (4.5200, -74.1100, 4.5900, -74.0500),
    "Usme": (4.4600, -74.1600, 4.5600, -74.0700),
    "Barrios Unidos": (4.6550, -74.0950, 4.6950, -74.0550),
    "Teusaquillo": (4.6200, -74.1050, 4.6650, -74.0650),
    "Los Martires": (4.5950, -74.1100, 4.6200, -74.0750),
    "Antonio Narino": (4.5750, -74.1100, 4.6050, -74.0850),
    "La Candelaria": (4.5850, -74.0800, 4.6050, -74.0650),
    "Rafael Uribe Uribe": (4.5350, -74.1300, 4.5850, -74.0850),
    "Suba": (4.7100, -74.1600, 4.8100, -74.0300),
    "Sumapaz": (3.7300, -74.4500, 4.3200, -74.1000),
}

# --------------------------------------------------------------------------
# Catalogo de categorias objetivo
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Categoria:
    """Una categoria comercial objetivo y como encontrarla en OpenStreetMap."""

    nombre: str            # Etiqueta legible en la base final
    grupo: str             # Salud / Belleza / Alimentacion / Servicios / Comercio
    prioridad: str         # "Muy Alta" | "Alta"
    osm: tuple[tuple[str, str], ...]   # pares (llave, valor) de OSM
    google_types: tuple[str, ...] = ()  # tipos para Google Places (opcional)
    keywords: tuple[str, ...] = ()      # palabras clave de respaldo


CATEGORIAS: list[Categoria] = [
    # ---------------------------- MUY ALTA PRIORIDAD ----------------------
    Categoria("Odontologia", "Salud", "Muy Alta",
              (("amenity", "dentist"), ("healthcare", "dentist"), ("shop", "dental")),
              ("dentist",), ("odontologia", "odontologo", "consultorio odontologico")),
    Categoria("Veterinaria", "Salud", "Muy Alta",
              (("amenity", "veterinary"), ("healthcare", "veterinary")),
              ("veterinary_care",), ("veterinaria", "clinica veterinaria")),
    Categoria("Peluqueria", "Belleza", "Muy Alta",
              (("shop", "hairdresser"),),
              ("hair_care",), ("peluqueria", "salon de belleza")),
    Categoria("Barberia", "Belleza", "Muy Alta",
              (("shop", "barber"), ("shop", "hairdresser;barber")),
              ("hair_care",), ("barberia", "barber shop")),
    Categoria("Centro estetico", "Belleza", "Muy Alta",
              (("shop", "beauty"), ("shop", "cosmetics"), ("healthcare", "cosmetic")),
              ("beauty_salon",), ("estetica", "centro estetico", "unas")),
    Categoria("Spa", "Belleza", "Muy Alta",
              (("leisure", "spa"), ("shop", "massage"), ("amenity", "spa")),
              ("spa",), ("spa", "masajes")),
    Categoria("Gimnasio", "Bienestar", "Muy Alta",
              (("leisure", "fitness_centre"), ("leisure", "sports_centre"),
               ("amenity", "gym")),
              ("gym",), ("gimnasio", "crossfit", "fitness")),
    Categoria("Restaurante", "Alimentacion", "Muy Alta",
              (("amenity", "restaurant"), ("amenity", "fast_food"),
               ("amenity", "food_court")),
              ("restaurant", "meal_takeaway"), ("restaurante", "asadero", "comidas")),
    Categoria("Cafeteria", "Alimentacion", "Muy Alta",
              (("amenity", "cafe"), ("amenity", "ice_cream"), ("shop", "coffee")),
              ("cafe",), ("cafeteria", "cafe", "heladeria")),
    Categoria("Panaderia", "Alimentacion", "Muy Alta",
              (("shop", "bakery"), ("shop", "pastry")),
              ("bakery",), ("panaderia", "reposteria")),
    Categoria("Consultorio medico", "Salud", "Muy Alta",
              (("amenity", "doctors"), ("amenity", "clinic"),
               ("healthcare", "doctor"), ("healthcare", "centre"),
               ("healthcare", "physiotherapist"), ("healthcare", "psychotherapist"),
               ("healthcare", "optometrist"), ("healthcare", "nutrition_counselling")),
              ("doctor", "physiotherapist"), ("consultorio", "ips", "medico")),
    Categoria("Inmobiliaria", "Servicios profesionales", "Muy Alta",
              (("office", "estate_agent"), ("shop", "estate_agent")),
              ("real_estate_agency",), ("inmobiliaria", "finca raiz", "arrendamientos")),
    Categoria("Contaduria", "Servicios profesionales", "Muy Alta",
              (("office", "accountant"), ("office", "tax_advisor"),
               ("office", "financial")),
              ("accounting",), ("contador", "contaduria", "asesoria contable")),
    Categoria("Abogados", "Servicios profesionales", "Muy Alta",
              (("office", "lawyer"), ("office", "notary")),
              ("lawyer",), ("abogado", "juridica", "notaria")),
    Categoria("Constructora", "Servicios profesionales", "Muy Alta",
              (("office", "construction_company"), ("craft", "builder"),
               ("office", "architect"), ("craft", "carpenter")),
              ("general_contractor",), ("constructora", "arquitecto", "remodelacion")),

    # ------------------------------ ALTA PRIORIDAD ------------------------
    Categoria("Ferreteria", "Comercio", "Alta",
              (("shop", "hardware"), ("shop", "doityourself"),
               ("shop", "paint"), ("shop", "trade")),
              ("hardware_store",), ("ferreteria",)),
    Categoria("Drogueria", "Salud", "Alta",
              (("amenity", "pharmacy"), ("healthcare", "pharmacy"),
               ("shop", "chemist")),
              ("pharmacy", "drugstore"), ("drogueria", "farmacia")),
    Categoria("Papeleria", "Comercio", "Alta",
              (("shop", "stationery"), ("shop", "copyshop"),
               ("shop", "books"), ("shop", "printing")),
              ("book_store",), ("papeleria", "miscelanea", "fotocopias")),
    Categoria("Floristeria", "Comercio", "Alta",
              (("shop", "florist"), ("shop", "garden_centre")),
              ("florist",), ("floristeria", "flores")),
    Categoria("Minimercado", "Comercio", "Alta",
              (("shop", "convenience"), ("shop", "supermarket"),
               ("shop", "greengrocer"), ("shop", "butcher"),
               ("shop", "deli"), ("shop", "seafood")),
              ("convenience_store", "supermarket"), ("minimercado", "supermercado", "tienda")),
    Categoria("Tienda de ropa", "Comercio", "Alta",
              (("shop", "clothes"), ("shop", "shoes"), ("shop", "boutique"),
               ("shop", "fashion_accessories"), ("shop", "bag"),
               ("shop", "jewelry"), ("shop", "tailor")),
              ("clothing_store", "shoe_store"), ("ropa", "boutique", "calzado")),
    Categoria("Tienda especializada", "Comercio", "Alta",
              (("shop", "mobile_phone"), ("shop", "computer"),
               ("shop", "electronics"), ("shop", "pet"), ("shop", "optician"),
               ("shop", "furniture"), ("shop", "sports"), ("shop", "toys"),
               ("shop", "car_repair"), ("shop", "motorcycle_repair"),
               ("shop", "laundry"), ("shop", "dry_cleaning"),
               ("shop", "car_parts"), ("shop", "bicycle"),
               ("shop", "musical_instrument"), ("shop", "photo"),
               ("craft", "electrician"), ("craft", "plumber"),
               ("craft", "shoemaker"), ("craft", "locksmith"),
               ("office", "insurance"), ("office", "travel_agent"),
               ("office", "it"), ("office", "advertising_agency"),
               ("office", "employment_agency"), ("office", "educational_institution"),
               ("amenity", "driving_school"), ("amenity", "language_school"),
               ("tourism", "hotel"), ("tourism", "guest_house"),
               ("tourism", "apartment")),
              ("store",), ("celulares", "tecnologia", "mascotas")),
]

CATEGORIA_POR_OSM: dict[tuple[str, str], Categoria] = {
    par: cat for cat in CATEGORIAS for par in cat.osm
}

GRUPOS_MUY_ALTA = {c.nombre for c in CATEGORIAS if c.prioridad == "Muy Alta"}

# --------------------------------------------------------------------------
# Servicios GoryxIA por grupo comercial
# --------------------------------------------------------------------------
SERVICIOS_POR_GRUPO: dict[str, list[str]] = {
    "Alimentacion": ["Menu QR", "Pedidos por WhatsApp", "Chatbot IA", "Pagina web"],
    "Salud": ["Agenda online", "CRM", "Automatizacion de citas", "Agente IA"],
    "Belleza": ["Agenda online", "CRM", "Automatizacion de citas", "Agente IA"],
    "Bienestar": ["Agenda online", "CRM", "Automatizacion de citas", "Agente IA"],
    "Comercio": ["Inventario", "Dashboard BI", "Catalogo digital"],
    "Servicios profesionales": ["Landing page", "CRM", "Automatizacion de leads", "Power BI"],
}
SERVICIOS_DEFECTO = ["Landing page", "CRM", "Automatizacion de leads", "Power BI"]

# --------------------------------------------------------------------------
# Scoring de contactabilidad
# --------------------------------------------------------------------------
SCORE_CELULAR = 100      # celular o WhatsApp
SCORE_FIJO_WEB = 80      # telefono fijo + sitio web
SCORE_WEB = 60           # solo sitio web
SCORE_REDES = 40         # solo redes sociales
SCORE_SIN_CONTACTO = 0

# --------------------------------------------------------------------------
# Marcas / cadenas que se degradan a prioridad BAJA
# --------------------------------------------------------------------------
CADENAS_NACIONALES = {
    "exito", "carulla", "olimpica", "ara", "d1", "justo & bueno", "justo y bueno",
    "jumbo", "metro", "makro", "pricesmart", "alkosto", "ktronix", "falabella",
    "homecenter", "easy", "cruz verde", "farmatodo", "drogas la rebaja",
    "locatel", "copservir", "colsubsidio", "cafam", "juan valdez", "tostao",
    "oma", "starbucks", "mcdonald", "burger king", "kfc", "dominos", "domino's",
    "papa john", "subway", "el corral", "frisby", "presto", "crepes & waffles",
    "sandwich qbano", "cinnabon", "dunkin", "popsy", "mimos", "bodytech",
    "smart fit", "stark", "spinning center", "claro", "movistar", "tigo", "wom",
    "bancolombia", "davivienda", "banco de bogota", "bbva", "scotiabank",
    "banco caja social", "av villas", "itau", "efecty", "baloto", "sao",
    "surtimax", "surtifruver", "koba", "ripley", "zara", "h&m", "adidas",
    "nike", "arturo calle", "totto", "bosi", "vélez", "velez", "spring step",
    "panaderia san marcos", "pan pa ya", "servientrega", "coordinadora",
    "interrapidisimo", "inter rapidisimo", "texaco", "terpel", "primax",
    "biomax", "esso", "mobil", "shell", "movich", "ibis", "marriott", "hilton",
    "nh hotel", "gh hoteles", "estelar",
}

# --------------------------------------------------------------------------
# Parametros de red
# --------------------------------------------------------------------------
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]
OVERPASS_TIMEOUT = int(os.environ.get("GORYXIA_OVERPASS_TIMEOUT", "180"))
OVERPASS_PAUSA_SEG = float(os.environ.get("GORYXIA_OVERPASS_PAUSE", "4"))
OVERPASS_REINTENTOS = int(os.environ.get("GORYXIA_OVERPASS_RETRIES", "4"))

USER_AGENT = os.environ.get(
    "GORYXIA_USER_AGENT",
    "GoryxIA-LeadGen/1.0 (prospeccion comercial Bogota; contacto: comercial@goryxia.com)",
)

WEB_SCRAPE_WORKERS = int(os.environ.get("GORYXIA_WEB_WORKERS", "8"))
WEB_SCRAPE_TIMEOUT = int(os.environ.get("GORYXIA_WEB_TIMEOUT", "12"))
WEB_SCRAPE_MAX_BYTES = 900_000

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
GOOGLE_PLACES_HABILITADO = bool(GOOGLE_PLACES_API_KEY)

# Datos Abiertos Bogota / datos.gov.co (portales Socrata).
# Se configuran por variable de entorno porque los identificadores de dataset
# cambian con el tiempo; cada entrada es "dominio:dataset_id".
DATOS_ABIERTOS_DATASETS = [
    d.strip() for d in os.environ.get("GORYXIA_SOCRATA_DATASETS", "").split(",") if d.strip()
]
SOCRATA_APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "").strip()

# --------------------------------------------------------------------------
# Esquema de salida (orden exacto de columnas)
# --------------------------------------------------------------------------
COLUMNAS = [
    "ID",
    "Nombre del negocio",
    "Categoria",
    "Grupo",
    "Direccion",
    "Barrio",
    "Localidad",
    "Ciudad",
    "Distancia aprox. (km)",
    "Telefono",
    "WhatsApp",
    "Link WhatsApp",
    "Correo electronico",
    "Sitio web",
    "Facebook",
    "Instagram",
    "LinkedIn",
    "Horario de atencion",
    "Calificacion Google",
    "N Resenas",
    "Propietario / Gerente",
    "Persona de contacto",
    "Presencia digital",
    "Score Contacto",
    "Servicios sugeridos",
    "Observaciones comerciales",
    "Prioridad",
    "Fuente",
    "place_id",
    "lat",
    "lon",
]


@dataclass
class Ajustes:
    """Ajustes de una corrida concreta del pipeline."""

    localidades: list[str] = field(default_factory=lambda: list(LOCALIDADES_BOGOTA))
    categorias: list[str] = field(default_factory=lambda: [c.nombre for c in CATEGORIAS])
    usar_overpass: bool = True
    usar_google: bool = GOOGLE_PLACES_HABILITADO
    usar_datos_abiertos: bool = True
    scrapear_webs: bool = True
    max_webs: int = 4000
    usar_cache: bool = True
    limite: int | None = None

    @property
    def categorias_activas(self) -> list[Categoria]:
        elegidas = set(self.categorias)
        return [c for c in CATEGORIAS if c.nombre in elegidas]
