"""Genera una fixture sintetica con forma de respuesta Overpass.

IMPORTANTE: los negocios de esta fixture son INVENTADOS. Existen unicamente
para probar el pipeline sin salir a la red; no representan establecimientos
reales de Bogota y nunca deben mezclarse con la base de produccion. Por eso
todos los nombres empiezan por "DEMO" y los telefonos usan el prefijo de
pruebas 300 000 XXXX.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

RUTA = Path(__file__).with_name("overpass_demo.json")

TIPOS = [
    ("amenity", "dentist", "Odontologia"),
    ("amenity", "veterinary", "Veterinaria"),
    ("shop", "hairdresser", "Peluqueria"),
    ("shop", "barber", "Barberia"),
    ("shop", "beauty", "Estetica"),
    ("leisure", "fitness_centre", "Gimnasio"),
    ("amenity", "restaurant", "Restaurante"),
    ("amenity", "cafe", "Cafeteria"),
    ("shop", "bakery", "Panaderia"),
    ("amenity", "doctors", "Consultorio"),
    ("office", "estate_agent", "Inmobiliaria"),
    ("office", "accountant", "Contaduria"),
    ("office", "lawyer", "Abogados"),
    ("shop", "hardware", "Ferreteria"),
    ("amenity", "pharmacy", "Drogueria"),
    ("shop", "stationery", "Papeleria"),
    ("shop", "florist", "Floristeria"),
    ("shop", "convenience", "Minimercado"),
    ("shop", "clothes", "Ropa"),
    ("shop", "mobile_phone", "Celulares"),
]

ZONAS = [
    ("Bosa", 4.60, -74.19), ("Kennedy", 4.62, -74.15),
    ("Ciudad Bolivar", 4.53, -74.16), ("Tunjuelito", 4.57, -74.14),
    ("Fontibon", 4.67, -74.15), ("Engativa", 4.70, -74.11),
    ("Puente Aranda", 4.62, -74.11), ("Suba", 4.75, -74.08),
    ("Usaquen", 4.72, -74.03), ("Chapinero", 4.65, -74.05),
]


def generar(cantidad: int = 400, semilla: int = 7) -> dict:
    aleatorio = random.Random(semilla)
    elementos = []

    for indice in range(cantidad):
        llave, valor, etiqueta = TIPOS[indice % len(TIPOS)]
        zona, lat_base, lon_base = ZONAS[indice % len(ZONAS)]
        lat = round(lat_base + aleatorio.uniform(-0.02, 0.02), 6)
        lon = round(lon_base + aleatorio.uniform(-0.02, 0.02), 6)

        tags = {
            llave: valor,
            "name": f"DEMO {etiqueta} {zona} {indice:03d}",
            "addr:street": f"Calle {aleatorio.randint(1, 180)} Sur",
            "addr:housenumber": f"{aleatorio.randint(1, 99)}-{aleatorio.randint(10, 99)}",
        }

        # Reparto de contactabilidad parecido al que se observa en OSM Bogota:
        # una minoria trae celular, algo mas trae fijo o web, y muchos no traen nada.
        suerte = aleatorio.random()
        if suerte < 0.18:
            tags["contact:mobile"] = f"+57 300 000 {aleatorio.randint(1000, 9999)}"
        elif suerte < 0.30:
            tags["phone"] = f"+57 300 000 {aleatorio.randint(1000, 9999)}"
        elif suerte < 0.45:
            tags["phone"] = f"+57 601 {aleatorio.randint(200, 799)} {aleatorio.randint(1000, 9999)}"

        if aleatorio.random() < 0.22:
            tags["website"] = f"https://demo-{etiqueta.lower()}-{indice}.example.com"
        if aleatorio.random() < 0.15:
            tags["contact:instagram"] = f"@demo{etiqueta.lower()}{indice}"
        if aleatorio.random() < 0.10:
            tags["contact:facebook"] = f"demo{etiqueta.lower()}{indice}"
        if aleatorio.random() < 0.12:
            tags["email"] = f"contacto@demo-{etiqueta.lower()}-{indice}.example.com"
        if aleatorio.random() < 0.25:
            tags["opening_hours"] = "Mo-Sa 08:00-18:00"
        if aleatorio.random() < 0.08:
            tags["operator"] = f"DEMO Operador {aleatorio.randint(1, 20)}"

        elementos.append({
            "type": "node" if indice % 4 else "way",
            "id": 1_000_000 + indice,
            "lat": lat,
            "lon": lon,
            "tags": tags,
        })

    # Duplicados deliberados para ejercitar las tres reglas de deduplicacion.
    base = elementos[0]
    # Regla 1: mismo place_id exacto, con un dato extra que debe sobrevivir.
    elementos.append({**base, "tags": {**base["tags"],
                                       "email": "duplicado@demo-exacto.co"}})
    elementos.append({**base, "id": base["id"] + 500_000})                      # place_id distinto, mismo sitio
    elementos.append({
        "type": "node", "id": 9_000_001,
        "lat": base["lat"] + 0.00002, "lon": base["lon"],                       # ~2 m
        "tags": {**base["tags"], "website": "https://demo-duplicado.example.com"},
    })
    telefono = elementos[3]["tags"].get("phone") or "+57 300 000 1234"
    elementos.append({
        "type": "node", "id": 9_000_002,
        "lat": 4.71, "lon": -74.07,
        "tags": {"amenity": "cafe", "name": "DEMO Cafeteria Otra Sede",
                 "phone": telefono, "email": "sedes@demo.example.com"},
    })

    return {"version": 0.6, "generator": "fixture sintetica GoryxIA",
            "elements": elementos}


if __name__ == "__main__":
    datos = generar()
    RUTA.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fixture escrita: {RUTA} ({len(datos['elements'])} elementos)")
