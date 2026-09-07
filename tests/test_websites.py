"""Pruebas del extractor de contactos desde HTML (sin salir a la red)."""
import time
import unittest
from unittest import mock

from goryxia.models import Negocio
from goryxia.sources.websites import (
    ResultadoWeb,
    enriquecer_negocios,
    extraer_de_html,
)

HTML = """
<html><head><title>Demo</title></head><body>
  <a href="https://wa.me/573112223344?text=Hola">Escribenos por WhatsApp</a>
  <a href="tel:+576017421122">Fijo</a>
  <p>Celular: 320 456 7890 &nbsp; Correo: contacto@panaderiademo.co</p>
  <a href="https://www.facebook.com/sharer/sharer.php?u=x">Compartir</a>
  <a href="https://www.facebook.com/DemoOficial">Facebook</a>
  <a href="https://instagram.com/demooficial">Instagram</a>
  <a href="https://www.linkedin.com/company/demo-sas">LinkedIn</a>
  <script>var dsn = "abc@sentry.wixpress.com";</script>
</body></html>
"""


class TestExtraccionWeb(unittest.TestCase):
    def setUp(self):
        self.resultado = extraer_de_html(HTML, "https://panaderiademo.co")

    def test_detecta_whatsapp_del_enlace_wa_me(self):
        self.assertIn("573112223344", self.resultado.moviles)
        self.assertTrue(self.resultado.whatsapp_confirmado)

    def test_detecta_celular_escrito_en_el_texto(self):
        self.assertIn("573204567890", self.resultado.moviles)

    def test_detecta_fijo_del_enlace_tel(self):
        self.assertIn("576017421122", self.resultado.fijos)

    def test_detecta_correo_y_descarta_los_tecnicos(self):
        self.assertIn("contacto@panaderiademo.co", self.resultado.correos)
        self.assertTrue(all("sentry" not in c for c in self.resultado.correos))

    def test_descarta_enlaces_de_compartir_de_facebook(self):
        self.assertEqual(self.resultado.facebook, "https://facebook.com/demooficial")

    def test_detecta_instagram_y_linkedin(self):
        self.assertEqual(self.resultado.instagram, "https://instagram.com/demooficial")
        self.assertEqual(self.resultado.linkedin, "https://linkedin.com/company/demo-sas")

    def test_descarta_dominios_reservados_de_documentacion(self):
        # example.com nunca es un negocio real: no debe ensuciar la base.
        reservado = extraer_de_html("<p>hola@algo.example.com</p>", "https://x.co")
        self.assertEqual(reservado.correos, [])

    def test_pagina_vacia_no_aporta_nada(self):
        vacio = extraer_de_html("<html><body>Hola</body></html>", "https://x.co")
        self.assertFalse(vacio.aporta_algo())


if __name__ == "__main__":
    unittest.main()


class TestPresupuestoDeTiempo(unittest.TestCase):
    """La fase de raspado no puede quedarse colgada por sitios lentos."""

    def _negocios(self, cantidad):
        return [Negocio(nombre=f"Negocio {i}", sitio_web=f"https://sitio{i}.co")
                for i in range(cantidad)]

    def test_devuelve_resultados_parciales_al_agotar_el_presupuesto(self):
        def lento(self, url):
            time.sleep(2)
            return ResultadoWeb(url=url, moviles=["573001234567"])

        negocios = self._negocios(40)
        inicio = time.monotonic()
        with mock.patch("goryxia.sources.websites.RaspadorWeb.analizar", lento), \
             mock.patch("goryxia.sources.websites.RaspadorWeb.guardar_cache"):
            resumen = enriquecer_negocios(negocios, usar_cache=False,
                                          presupuesto_minutos=0.05)  # 3 segundos
        transcurrido = time.monotonic() - inicio

        self.assertLess(transcurrido, 20, "El presupuesto no corto la fase")
        self.assertLess(resumen["analizados"], len(negocios))
        self.assertGreater(resumen["sin_analizar_por_tiempo"], 0)

    def test_conserva_lo_ya_obtenido_al_cortar(self):
        def rapido_luego_lento(self, url):
            if url.endswith(("0.co", "1.co", "2.co")):
                return ResultadoWeb(url=url, moviles=["573001234567"])
            time.sleep(5)
            return ResultadoWeb(url=url)

        negocios = self._negocios(12)
        with mock.patch("goryxia.sources.websites.RaspadorWeb.analizar",
                        rapido_luego_lento), \
             mock.patch("goryxia.sources.websites.RaspadorWeb.guardar_cache"):
            resumen = enriquecer_negocios(negocios, usar_cache=False,
                                          presupuesto_minutos=0.03)  # ~2 segundos

        self.assertGreaterEqual(resumen["nuevos_celulares"], 1)
        con_celular = [n for n in negocios if n.tiene_celular]
        self.assertGreaterEqual(len(con_celular), 1)
