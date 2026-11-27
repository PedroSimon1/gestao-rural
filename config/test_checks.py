"""Aviso de implantação sobre o TLS da conexão com o banco."""
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from .checks import tls_do_banco_sem_verificacao_do_servidor


class TlsDoBancoTests(SimpleTestCase):
    def avisos(self, modo):
        with mock.patch.dict(settings.DATABASES["default"]["OPTIONS"], {"sslmode": modo}):
            return tls_do_banco_sem_verificacao_do_servidor(None)

    def test_require_gera_aviso_com_o_caminho_da_correcao(self):
        avisos = self.avisos("require")

        self.assertEqual([a.id for a in avisos], ["config.W001"])
        self.assertIn("verify-full", avisos[0].hint)

    def test_modos_que_verificam_o_servidor_nao_geram_aviso(self):
        for modo in ("verify-ca", "verify-full"):
            with self.subTest(modo=modo):
                self.assertEqual(self.avisos(modo), [])
