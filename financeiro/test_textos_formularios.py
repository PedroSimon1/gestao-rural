"""Textos em português nos formulários da conta manual (sem o padrão em inglês do Django)."""
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo


@override_settings(**CREDENCIAIS_TESTE)
class SelectsEmPortuguesTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)

    def test_nenhum_select_mostra_texto_em_ingles(self):
        for tipo in ("APAGAR", "ARECEBER"):
            with self.subTest(tipo=tipo):
                resposta = self.client.get(reverse("conta_manual_nova"), {"tipo": tipo})
                self.assertNotContains(resposta, "Select an option")
                self.assertNotContains(resposta, "---------")

    def test_opcao_vazia_diz_o_que_escolher(self):
        pagar = self.client.get(reverse("conta_manual_nova"), {"tipo": "APAGAR"})
        receber = self.client.get(reverse("conta_manual_nova"), {"tipo": "ARECEBER"})
        self.assertContains(pagar, ">Selecione o fornecedor</option>")
        self.assertContains(pagar, ">Selecione o faturado</option>")
        self.assertContains(pagar, ">Selecione a classificação principal</option>")
        self.assertContains(receber, ">Selecione o cliente</option>")
