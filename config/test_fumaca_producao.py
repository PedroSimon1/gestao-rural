"""Fumaça das telas com o armazenamento de estáticos de produção (manifesto do collectstatic).

O CI roda com DEBUG=True e o storage simples, que não exige o manifesto. Em produção
(`CompressedManifestStaticFilesStorage`) um `{% static %}` de arquivo inexistente derruba a página
com erro 500. Este teste roda `collectstatic` num diretório temporário e abre as telas com o
mesmo storage da produção.
"""
import re
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cadastros.models import Papel, Pessoa
from documentos.analises import criar_analise
from comum.sessao import garantir_dono
from documentos.testing import CPF, resultado_da_nota
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

STORAGES_DE_PRODUCAO = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


@override_settings(STORAGES=STORAGES_DE_PRODUCAO, DEBUG=False, **CREDENCIAIS_TESTE)
class FumacaComManifestoTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pasta = tempfile.TemporaryDirectory()
        cls.addClassCleanup(pasta.cleanup)
        cls.enterClassContext(override_settings(STATIC_ROOT=pasta.name))
        call_command("collectstatic", interactive=False, verbosity=0)

    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        self.pessoa = Pessoa.objects.create(documento=CPF, razao_social="Pessoa Teste")
        self.pessoa.atribuir_papel(Papel.FORNECEDOR)
        self.analise = criar_analise(self.client.session, resultado_da_nota())

    def test_telas_abrem_com_arquivos_estaticos_com_hash(self):
        telas = {
            reverse("documento_inicio"): 200,
            reverse("contas"): 200,
            reverse("conta_manual_nova") + "?tipo=APAGAR": 200,
            reverse("pessoas"): 200,
            reverse("pessoa_nova"): 200,
            reverse("pessoa_detalhe", args=[self.pessoa.pk]): 200,
            reverse("classificacoes"): 200,
            reverse("classificacao_nova"): 200,
            reverse("analise_conferencia", args=[self.analise.id]): 200,
            reverse("logout"): 200,
            "/endereco-que-nao-existe/": 404,
        }
        for url, status in telas.items():
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, status)
                # O storage de produção está em uso: o CSS sai com o hash do manifesto.
                self.assertRegex(resposta.content.decode(), r"/static/documentos/documentos\.[0-9a-f]{12}\.css")

    def test_login_anonimo_e_pagina_500(self):
        resposta = Client().get(reverse("login"))
        self.assertEqual(resposta.status_code, 200)
        self.assertRegex(resposta.content.decode(), r"documentos\.[0-9a-f]{12}\.js")
        self.assertIn("Erro inesperado", render_to_string("500.html"))
        self.assertIsNotNone(re.search(r"Página não encontrada", Client().get("/nao-existe/").content.decode()))
