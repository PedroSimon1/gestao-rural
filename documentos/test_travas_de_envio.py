"""Formulários POST travam o duplo envio; telas de erro de análise e conta manual da auditoria de interface."""
import re
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo


@override_settings(**CREDENCIAIS_TESTE)
class AuditoriaDeInterfaceTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)

    def test_todo_formulario_post_das_telas_de_escrita_trava_o_duplo_envio(self):
        for nome in ("logout", "pessoa_nova", "classificacao_nova", "conta_manual_nova"):
            with self.subTest(tela=nome):
                html = self.client.get(reverse(nome)).content.decode()
                formularios = re.findall(r'<form\b[^>]*method="post"[^>]*>', html)
                self.assertTrue(formularios)
                for tag in formularios:
                    self.assertIn("data-submit-lock", tag)

    def test_conta_manual_usa_navegacao_nomeada_e_legenda_que_o_script_numera(self):
        html = self.client.get(reverse("conta_manual_nova")).content.decode()
        self.assertIn('<nav class="barra-acoes" aria-label="Tipo da conta">', html)
        self.assertNotIn('<p class="barra-acoes"', html)
        self.assertIn("<legend data-titulo-parcela>", html)

    def test_analise_inexistente_e_anunciada_como_alerta(self):
        resposta = self.client.get(reverse("analise_conferencia", args=[uuid4()]))
        self.assertContains(resposta, 'role="alert"', status_code=404)
