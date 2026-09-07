"""Pruebas del plan de numeracion colombiano y de la deteccion de WhatsApp."""
import unittest

from goryxia import phones


class TestNormalizacion(unittest.TestCase):
    def test_movil_en_varios_formatos(self):
        for crudo in ("+57 300 123 4567", "3001234567", "57 300 1234567",
                      "(300) 123-4567", "0057 300 123 4567"):
            with self.subTest(crudo=crudo):
                self.assertEqual(phones.normalizar_numero(crudo),
                                 ("573001234567", "movil"))

    def test_fijo_nuevo_de_diez_digitos(self):
        self.assertEqual(phones.normalizar_numero("601 345 6789"),
                         ("576013456789", "fijo"))

    def test_fijo_antiguo_de_siete_digitos_se_migra_a_601(self):
        self.assertEqual(phones.normalizar_numero("3456789"),
                         ("576013456789", "fijo"))

    def test_fijo_con_indicativo_de_un_digito(self):
        self.assertEqual(phones.normalizar_numero("1 345 6789"),
                         ("576013456789", "fijo"))

    def test_numeros_invalidos(self):
        for crudo in ("12345", "", None, "abc", "9"):
            with self.subTest(crudo=crudo):
                self.assertIsNone(phones.normalizar_numero(crudo))

    def test_nit_no_se_confunde_con_telefono(self):
        # Un NIT de 9 digitos no encaja en el plan de numeracion.
        self.assertIsNone(phones.normalizar_numero("900123456"))


class TestExtraccion(unittest.TestCase):
    def test_separa_varios_numeros_y_los_clasifica(self):
        moviles, fijos = phones.extraer_numeros("300 123 4567; 601 234 5678",
                                                "+57 311 222 3344")
        self.assertEqual(moviles, ["573001234567", "573112223344"])
        self.assertEqual(fijos, ["576012345678"])

    def test_no_duplica(self):
        moviles, _ = phones.extraer_numeros("3001234567", "+57 300 123 4567")
        self.assertEqual(moviles, ["573001234567"])

    def test_busca_en_texto_libre(self):
        texto = "Llamanos al 320 456 7890 o al (601) 742 1122. NIT 900123456-7"
        moviles, fijos = phones.buscar_numeros_en_texto(texto)
        self.assertIn("573204567890", moviles)
        self.assertIn("576017421122", fijos)


class TestWhatsApp(unittest.TestCase):
    def test_link_wa_me(self):
        self.assertEqual(phones.link_whatsapp("573001234567"),
                         "https://wa.me/573001234567")

    def test_solo_los_moviles_son_whatsapp(self):
        self.assertTrue(phones.es_movil("573001234567"))
        self.assertFalse(phones.es_movil("576013456789"))

    def test_formato_legible(self):
        self.assertEqual(phones.formato_legible("573001234567"), "+57 300 123 4567")


if __name__ == "__main__":
    unittest.main()
