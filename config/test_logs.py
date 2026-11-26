"""Logs de produção: 5xx aparecem no console sem a mensagem da exceção (B-05)."""
import io
import logging
import sys
from unittest import mock

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .logs import FormatadorSemMensagemDaExcecao

SEGREDO = "documento=123.456.789-09"


class FormatadorTests(SimpleTestCase):
    def test_rastreio_sem_a_mensagem_da_excecao(self):
        try:
            raise ValueError(SEGREDO)
        except ValueError:
            registro = logging.LogRecord("x", logging.ERROR, __file__, 1, "falhou", (), sys.exc_info())

        saida = FormatadorSemMensagemDaExcecao("%(message)s").format(registro)

        self.assertIn("falhou", saida)
        self.assertIn("ValueError", saida)
        self.assertIn("test_rastreio_sem_a_mensagem_da_excecao", saida)
        self.assertNotIn(SEGREDO, saida)


@override_settings(**CREDENCIAIS_TESTE, DEBUG=False)
class LogDeFalha5xxTests(SimpleTestCase):
    def test_erro_interno_chega_ao_console_sem_a_mensagem(self):
        console = logging.getLogger("django").handlers[0]
        saida = io.StringIO()
        cliente = Client(raise_request_exception=False)
        autenticar_demo(cliente)

        with mock.patch.object(console, "stream", saida), \
                mock.patch("cadastros.views.Paginator", side_effect=RuntimeError(SEGREDO)):
            resposta = cliente.get(reverse("pessoas"), {"modo": "todos"})

        self.assertEqual(resposta.status_code, 500)
        self.assertIn("Internal Server Error: /cadastros/pessoas/", saida.getvalue())
        self.assertIn("RuntimeError", saida.getvalue())
        self.assertNotIn(SEGREDO, saida.getvalue())
