"""Pruebas del cliente Overpass: consultas, salud de mirrors y parseo.

Ningun test sale a la red: se sustituye la sesion HTTP por dobles de prueba.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from goryxia.config import CATEGORIAS, OVERPASS_FALLOS_PARA_APARTAR
from goryxia.sources.overpass import (
    ClienteOverpass,
    construir_consulta,
    elemento_a_negocio,
    mosaicos,
)


class RespuestaFalsa:
    def __init__(self, status_code=200, datos=None):
        self.status_code = status_code
        self._datos = datos if datos is not None else {"elements": []}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._datos


def cliente_de_prueba(directorio):
    cliente = ClienteOverpass(usar_cache=False, cache_dir=Path(directorio))
    return cliente


class TestConstruccionDeConsultas(unittest.TestCase):
    def test_agrupa_las_categorias_por_llave_osm(self):
        consulta = construir_consulta((4.5, -74.2, 4.6, -74.1), CATEGORIAS)
        # Una sola sentencia por llave, no una por categoria.
        self.assertEqual(consulta.count("nwr["), 7)
        self.assertIn('nwr["amenity"~"^(', consulta)
        self.assertIn("out center tags;", consulta)

    def test_el_bbox_va_en_todas_las_sentencias(self):
        consulta = construir_consulta((4.5, -74.2, 4.6, -74.1), CATEGORIAS)
        self.assertEqual(consulta.count("(4.50000,-74.20000,4.60000,-74.10000)"), 7)

    def test_los_mosaicos_cubren_el_bbox_completo(self):
        tiles = list(mosaicos((4.58, -74.22, 4.64, -74.16), 0.03))
        self.assertEqual(len(tiles), 4)
        self.assertAlmostEqual(min(t[0] for t in tiles), 4.58)
        self.assertAlmostEqual(max(t[2] for t in tiles), 4.64)


class TestSaludDeMirrors(unittest.TestCase):
    """Un mirror caido no debe consumir el presupuesto de toda la corrida."""

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.cliente = cliente_de_prueba(self.temporal.name)

    def test_un_error_de_tls_aparta_el_mirror_de_inmediato(self):
        malo = self.cliente.endpoints[0]

        def responder(url, **kwargs):
            if url == malo:
                raise requests.exceptions.SSLError("certificado no valido")
            return RespuestaFalsa(datos={"elements": [{"id": 1}]})

        with mock.patch.object(self.cliente.sesion, "post", side_effect=responder), \
             mock.patch("goryxia.sources.overpass.time.sleep"):
            self.cliente.ejecutar("[out:json];out;")

        self.assertGreaterEqual(self.cliente.fallos_por_endpoint[malo],
                                OVERPASS_FALLOS_PARA_APARTAR)
        self.assertNotIn(malo, self.cliente._endpoints_sanos())

    def test_un_504_penaliza_pero_no_aparta_a_la_primera(self):
        endpoint = self.cliente.endpoints[0]
        with mock.patch.object(self.cliente.sesion, "post",
                               return_value=RespuestaFalsa(504)), \
             mock.patch("goryxia.sources.overpass.time.sleep"):
            resultado = self.cliente.ejecutar("[out:json];out;")

        self.assertIsNone(resultado)
        self.assertGreater(self.cliente.fallos_por_endpoint[endpoint], 0)

    def test_una_respuesta_correcta_limpia_el_historial_del_mirror(self):
        endpoint = self.cliente.endpoints[0]
        self.cliente.fallos_por_endpoint[endpoint] = 2
        with mock.patch.object(self.cliente.sesion, "post",
                               return_value=RespuestaFalsa(datos={"elements": []})), \
             mock.patch("goryxia.sources.overpass.time.sleep"):
            self.cliente.ejecutar("[out:json];out;")
        self.assertEqual(self.cliente.fallos_por_endpoint[endpoint], 0)

    def test_si_se_apartan_todos_se_reinicia_el_conteo(self):
        for endpoint in self.cliente.endpoints:
            self.cliente.fallos_por_endpoint[endpoint] = 99
        sanos = self.cliente._endpoints_sanos()
        self.assertEqual(len(sanos), len(self.cliente.endpoints))

    def test_devuelve_los_datos_cuando_el_mirror_responde(self):
        esperado = {"elements": [{"type": "node", "id": 5}]}
        with mock.patch.object(self.cliente.sesion, "post",
                               return_value=RespuestaFalsa(datos=esperado)), \
             mock.patch("goryxia.sources.overpass.time.sleep"):
            self.assertEqual(self.cliente.ejecutar("[out:json];out;"), esperado)


class TestParseoDeElementos(unittest.TestCase):
    def test_lee_el_celular_del_tag_contact_mobile(self):
        elemento = {
            "type": "node", "id": 1, "lat": 4.6, "lon": -74.19,
            "tags": {"amenity": "dentist", "name": "Clinica Dental",
                     "contact:mobile": "+57 310 555 4433"},
        }
        negocio = elemento_a_negocio(elemento)
        self.assertEqual(negocio.moviles, ["573105554433"])
        self.assertEqual(negocio.categoria, "Odontologia")

    def test_usa_el_centro_en_ways_y_relations(self):
        elemento = {
            "type": "way", "id": 2, "center": {"lat": 4.61, "lon": -74.18},
            "tags": {"shop": "bakery", "name": "Panaderia"},
        }
        negocio = elemento_a_negocio(elemento)
        self.assertEqual((negocio.lat, negocio.lon), (4.61, -74.18))

    def test_descarta_lo_que_no_tiene_nombre(self):
        elemento = {"type": "node", "id": 3, "lat": 4.6, "lon": -74.1,
                    "tags": {"amenity": "dentist"}}
        self.assertIsNone(elemento_a_negocio(elemento))

    def test_descarta_lo_que_no_es_categoria_objetivo(self):
        elemento = {"type": "node", "id": 4, "lat": 4.6, "lon": -74.1,
                    "tags": {"amenity": "bench", "name": "Banca"}}
        self.assertIsNone(elemento_a_negocio(elemento))

    def test_reconoce_valores_compuestos_con_punto_y_coma(self):
        elemento = {"type": "node", "id": 5, "lat": 4.6, "lon": -74.1,
                    "tags": {"shop": "hairdresser;beauty", "name": "Salon"}}
        negocio = elemento_a_negocio(elemento)
        self.assertIsNotNone(negocio)
        self.assertEqual(negocio.grupo, "Belleza")


if __name__ == "__main__":
    unittest.main()
