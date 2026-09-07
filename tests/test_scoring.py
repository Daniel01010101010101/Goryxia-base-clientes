"""Pruebas de score de contactabilidad, presencia digital y prioridad."""
import unittest

from goryxia import scoring, services
from goryxia.config import SCORE_CELULAR, SCORE_FIJO_WEB, SCORE_REDES, SCORE_WEB
from goryxia.models import Negocio


def negocio(**campos) -> Negocio:
    base = dict(nombre="Negocio de prueba", categoria="Panaderia",
                grupo="Alimentacion", localidad="Bosa")
    base.update(campos)
    return Negocio(**base)


class TestScore(unittest.TestCase):
    def test_celular_vale_cien(self):
        self.assertEqual(scoring.calcular_score(negocio(moviles=["573001234567"])),
                         SCORE_CELULAR)

    def test_fijo_mas_web_vale_ochenta(self):
        n = negocio(fijos=["576013456789"], sitio_web="https://x.co")
        self.assertEqual(scoring.calcular_score(n), SCORE_FIJO_WEB)

    def test_solo_web_vale_sesenta(self):
        self.assertEqual(scoring.calcular_score(negocio(sitio_web="https://x.co")),
                         SCORE_WEB)

    def test_solo_redes_vale_cuarenta(self):
        n = negocio(instagram="https://instagram.com/x")
        self.assertEqual(scoring.calcular_score(n), SCORE_REDES)

    def test_sin_contacto_vale_cero(self):
        self.assertEqual(scoring.calcular_score(negocio()), 0)

    def test_el_celular_manda_sobre_el_resto(self):
        n = negocio(moviles=["573001234567"], fijos=["576013456789"],
                    sitio_web="https://x.co", instagram="https://instagram.com/x")
        self.assertEqual(scoring.calcular_score(n), SCORE_CELULAR)


class TestPresenciaDigital(unittest.TestCase):
    def test_alta_requiere_web_facebook_e_instagram(self):
        n = negocio(sitio_web="https://x.co", facebook="https://facebook.com/x",
                    instagram="https://instagram.com/x")
        self.assertEqual(scoring.calcular_presencia_digital(n), "ALTA")

    def test_media_con_solo_una_senal(self):
        self.assertEqual(
            scoring.calcular_presencia_digital(negocio(sitio_web="https://x.co")), "MEDIA")

    def test_baja_sin_nada(self):
        self.assertEqual(scoring.calcular_presencia_digital(negocio()), "BAJA")


class TestPrioridad(unittest.TestCase):
    def test_alta_con_celular_y_poca_presencia(self):
        n = scoring.enriquecer(negocio(moviles=["573001234567"]))
        self.assertEqual(n.prioridad, "ALTA")

    def test_cadena_nacional_es_baja(self):
        n = scoring.enriquecer(negocio(nombre="Exito Kennedy",
                                       moviles=["573001234567"]))
        self.assertEqual(n.prioridad, "BAJA")

    def test_media_con_fijo_sin_celular(self):
        n = scoring.enriquecer(negocio(fijos=["576013456789"]))
        self.assertEqual(n.prioridad, "MEDIA")


class TestOrden(unittest.TestCase):
    def test_orden_celular_correo_web_nada(self):
        con_celular = scoring.enriquecer(negocio(moviles=["573001234567"]))
        con_correo = scoring.enriquecer(negocio(correos=["a@b.co"]))
        con_web = scoring.enriquecer(negocio(sitio_web="https://x.co"))
        sin_nada = scoring.enriquecer(negocio())

        ordenados = sorted([sin_nada, con_web, con_correo, con_celular],
                           key=scoring.clave_orden)
        self.assertEqual(ordenados, [con_celular, con_correo, con_web, sin_nada])


class TestServicios(unittest.TestCase):
    def test_restaurante_recibe_menu_qr(self):
        n = services.enriquecer(scoring.enriquecer(
            negocio(categoria="Restaurante", grupo="Alimentacion")))
        self.assertIn("Menu QR", n.servicios)

    def test_salud_recibe_agenda_online(self):
        n = services.enriquecer(scoring.enriquecer(
            negocio(categoria="Odontologia", grupo="Salud")))
        self.assertIn("Agenda online", n.servicios)

    def test_observacion_indica_accion_inmediata_con_celular(self):
        n = services.enriquecer(scoring.enriquecer(negocio(moviles=["573001234567"])))
        self.assertIn("whatsapp", n.observaciones.lower())


if __name__ == "__main__":
    unittest.main()
