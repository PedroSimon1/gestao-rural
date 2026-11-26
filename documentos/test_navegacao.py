"""Menu principal: página atual marcada, "Sair" no formato fixado pelos testes e link de atalho."""
import re
from types import SimpleNamespace

from django.template import Context
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from documentos.templatetags.navegacao import SECOES, secao_atual
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo


def _contexto(url_name):
    request = SimpleNamespace(resolver_match=SimpleNamespace(url_name=url_name) if url_name else None)
    return Context({"request": request})


class SecaoAtualTests(SimpleTestCase):
    def test_cada_rota_do_menu_pertence_a_uma_secao(self):
        for secao, nomes in SECOES.items():
            for nome in nomes:
                with self.subTest(rota=nome):
                    self.assertEqual(secao_atual(_contexto(nome)), secao)

    def test_rotas_fora_do_menu_e_sem_request(self):
        for nome in ("login", "logout", "inicio", None):
            with self.subTest(rota=nome):
                self.assertEqual(secao_atual(_contexto(nome)), "")
        self.assertEqual(secao_atual(Context({})), "")

    def test_nenhuma_rota_em_duas_secoes(self):
        todas = [nome for nomes in SECOES.values() for nome in nomes]
        self.assertEqual(len(todas), len(set(todas)))


@override_settings(**CREDENCIAIS_TESTE)
class MenuNaPaginaTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)

    def atuais(self, nome_da_rota):
        html = self.client.get(reverse(nome_da_rota)).content.decode()
        return re.findall(r'<a href="[^"]+" aria-current="page">([^<]+)</a>', html)

    def test_pagina_atual_fica_marcada_uma_vez(self):
        esperado = {
            "contas": "Contas", "documento_inicio": "Enviar nota",
            "pessoas": "Pessoas", "classificacoes": "Classificações",
        }
        for rota, rotulo in esperado.items():
            with self.subTest(rota=rota):
                self.assertEqual(self.atuais(rota), [rotulo])

    def test_estrutura_comum_da_pagina(self):
        resposta = self.client.get(reverse("contas"))
        self.assertContains(resposta, '<a class="pular" href="#conteudo">Pular para o conteúdo</a>', html=True)
        self.assertContains(resposta, '<main id="conteudo" class="container">')
        # Formato exigido por outros testes: sem classe nem atributo extra.
        self.assertContains(resposta, f'<a href="{reverse("logout")}">Sair</a>', html=True)
