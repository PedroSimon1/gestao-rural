"""Rota /saude/: pública, sem dados e sem expor o erro do banco."""
from unittest import mock

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class SaudeComBancoTests(TestCase):
    def test_banco_no_ar_responde_200_sem_login(self):
        resposta = self.client.get(reverse("saude"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})

    def test_aceita_head_e_recusa_escrita(self):
        self.assertEqual(self.client.head(reverse("saude")).status_code, 200)
        for metodo in ("post", "put", "delete"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(reverse("saude")).status_code, 405)

    def test_resposta_nao_e_guardada_em_cache(self):
        self.assertIn("no-store", self.client.get(reverse("saude"))["Cache-Control"])


class SaudeSemBancoTests(SimpleTestCase):
    def test_banco_fora_do_ar_responde_503_sem_detalhes(self):
        erro = OperationalError("senha-interna host-interno")
        with mock.patch("config.saude.verificar_banco", side_effect=erro), self.assertLogs("config.saude", "WARNING") as logs:
            resposta = self.client.get(reverse("saude"))

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"status": "indisponivel"})
        for texto in (resposta.content.decode(), "\n".join(logs.output)):
            self.assertNotIn("senha-interna", texto)
            self.assertNotIn("host-interno", texto)
