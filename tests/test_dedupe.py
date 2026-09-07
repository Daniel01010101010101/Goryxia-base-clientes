"""Pruebas de las tres reglas de deduplicacion y de la fusion de datos."""
import unittest

from goryxia.dedupe import deduplicar
from goryxia.models import Negocio


class TestDeduplicacion(unittest.TestCase):
    def test_place_id_repetido_se_fusiona(self):
        a = Negocio(nombre="Panaderia X", place_id="osm:node/1",
                    moviles=["573001112233"], lat=4.6, lon=-74.1)
        b = Negocio(nombre="Panaderia X", place_id="osm:node/1",
                    correos=["pan@x.co"], lat=4.6, lon=-74.1)
        resultado, conteo = deduplicar([a, b])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(conteo["place_id"], 1)
        self.assertEqual(resultado[0].correos, ["pan@x.co"])
        self.assertEqual(resultado[0].moviles, ["573001112233"])

    def test_telefono_compartido_se_fusiona(self):
        a = Negocio(nombre="Sede Norte", place_id="a", fijos=["576013456789"],
                    lat=4.7, lon=-74.05)
        b = Negocio(nombre="Sede Sur", place_id="b", fijos=["576013456789"],
                    sitio_web="https://x.co", lat=4.5, lon=-74.15)
        resultado, conteo = deduplicar([a, b])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(conteo["telefono"], 1)
        self.assertEqual(resultado[0].sitio_web, "https://x.co")

    def test_mismo_nombre_a_menos_de_50_metros(self):
        a = Negocio(nombre="Cafe Central", place_id="a", lat=4.6000, lon=-74.1000)
        b = Negocio(nombre="CAFE CENTRAL S.A.S.", place_id="b",
                    lat=4.60020, lon=-74.1000)  # ~22 m
        resultado, conteo = deduplicar([a, b])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(conteo["nombre_distancia"], 1)

    def test_mismo_nombre_lejos_no_se_fusiona(self):
        a = Negocio(nombre="Cafe Central", place_id="a", lat=4.60, lon=-74.10)
        b = Negocio(nombre="Cafe Central", place_id="b", lat=4.75, lon=-74.05)
        resultado, _ = deduplicar([a, b])
        self.assertEqual(len(resultado), 2)

    def test_la_fusion_conserva_el_mejor_contacto_de_cada_registro(self):
        a = Negocio(nombre="Veterinaria Patitas", place_id="a",
                    moviles=["573001112233"], lat=4.6, lon=-74.1,
                    fuente="OpenStreetMap")
        b = Negocio(nombre="Veterinaria Patitas", place_id="b",
                    sitio_web="https://patitas.co", correos=["hola@patitas.co"],
                    lat=4.6001, lon=-74.1, fuente="Google Places")
        resultado, _ = deduplicar([a, b])
        self.assertEqual(len(resultado), 1)
        unico = resultado[0]
        self.assertTrue(unico.tiene_celular)
        self.assertTrue(unico.tiene_web)
        self.assertTrue(unico.tiene_correo)
        self.assertIn("Google Places", unico.fuente)
        self.assertIn("OpenStreetMap", unico.fuente)


if __name__ == "__main__":
    unittest.main()
