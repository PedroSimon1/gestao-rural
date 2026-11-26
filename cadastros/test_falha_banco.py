"""Falha do banco nas telas de cadastros e páginas de erro 404/500 (M-03)."""
from unittest import mock

from django.db import IntegrityError, OperationalError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from documentos.testing import CNPJ, CPF
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .models import Classificacao, Papel, Pessoa, TipoClassificacao

SEGREDO = "SQL-secreto-ficticio"


@override_settings(**CREDENCIAIS_TESTE)
class FalhaDeBancoTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        self.pessoa = Pessoa.objects.create(documento=CPF, razao_social="Pessoa Teste")
        self.papel, _ = self.pessoa.atribuir_papel(Papel.CLIENTE)
        self.classificacao = Classificacao.objects.create(
            tipo=TipoClassificacao.DESPESA, codigo="CUSTO_TESTE", descricao="Custo de teste",
        )

    def verificar_503(self, resposta):
        self.assertEqual(resposta.status_code, 503)
        self.assertTemplateUsed(resposta, "cadastros/erro.html")
        self.assertContains(resposta, "Não foi possível acessar os cadastros agora", status_code=503)
        self.assertNotContains(resposta, SEGREDO, status_code=503)

    def test_telas_respondem_503_sem_expor_o_erro(self):
        pessoa, classificacao = self.pessoa.pk, self.classificacao.pk
        casos = (
            ("lista de pessoas", "cadastros.views.Paginator", "get", reverse("pessoas"), {"modo": "todos"}),
            ("detalhe da pessoa", "cadastros.views.get_object_or_404", "get", reverse("pessoa_detalhe", args=[pessoa]), {}),
            ("editar pessoa", "cadastros.views.get_object_or_404", "get", reverse("pessoa_editar", args=[pessoa]), {}),
            ("atribuir papel", "cadastros.views.get_object_or_404", "post", reverse("pessoa_atribuir_papel", args=[pessoa]), {"papel": Papel.FORNECEDOR}),
            ("status da pessoa", "cadastros.views.get_object_or_404", "get", reverse("pessoa_status", args=[pessoa, "inativar"]), {}),
            ("regularizar pessoa", "cadastros.views.get_object_or_404", "get", reverse("pessoa_regularizar", args=[pessoa]), {}),
            ("criar pessoa", "cadastros.views.resolver_partes", "post", reverse("pessoa_nova"), {
                "razao_social": "Empresa Teste", "documento": CNPJ, "papeis": [Papel.CLIENTE],
            }),
            ("lista de classificações", "cadastros.views_classificacoes.Paginator", "get", reverse("classificacoes"), {"modo": "todos"}),
            ("editar classificação", "cadastros.views_classificacoes.get_object_or_404", "get", reverse("classificacao_editar", args=[classificacao]), {}),
            ("status da classificação", "cadastros.views_classificacoes.get_object_or_404", "get", reverse("classificacao_status", args=[classificacao, "inativar"]), {}),
            ("criar classificação", "cadastros.forms_classificacoes.NovaClassificacaoForm.save", "post", reverse("classificacao_nova"), {
                "tipo": TipoClassificacao.DESPESA, "codigo": "OUTRO_CUSTO", "descricao": "Outro custo",
            }),
        )
        for nome, alvo, metodo, url, dados in casos:
            with self.subTest(tela=nome):
                with mock.patch(alvo, side_effect=OperationalError(SEGREDO)), \
                        self.assertLogs("config.erros_banco", "WARNING") as registro:
                    self.verificar_503(getattr(self.client, metodo)(url, dados))
                self.assertNotIn(SEGREDO, "".join(registro.output))

    def test_anonimo_continua_indo_para_o_login_mesmo_com_banco_fora(self):
        anonimo = Client()
        with mock.patch("cadastros.views.Paginator", side_effect=OperationalError(SEGREDO)):
            resposta = anonimo.get(reverse("pessoas"))
        self.assertRedirects(resposta, reverse("login"), fetch_redirect_response=False)

    def test_integrity_error_tratado_na_view_continua_sendo_mensagem_do_formulario(self):
        with mock.patch("cadastros.views.resolver_partes", side_effect=IntegrityError(SEGREDO)):
            resposta = self.client.post(reverse("pessoa_nova"), {
                "razao_social": "Empresa Teste", "documento": CNPJ, "papeis": [Papel.CLIENTE],
            })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O documento já está em uso")
        self.assertNotContains(resposta, SEGREDO)


@override_settings(**CREDENCIAIS_TESTE, DEBUG=False)
class PaginasDeErroTests(TestCase):
    def test_404_em_portugues(self):
        resposta = Client().get("/endereco-que-nao-existe/")
        self.assertEqual(resposta.status_code, 404)
        self.assertContains(resposta, "Página não encontrada", status_code=404)

    def test_500_em_portugues_sem_expor_o_erro(self):
        cliente = Client(raise_request_exception=False)
        autenticar_demo(cliente)
        with mock.patch("cadastros.views.Paginator", side_effect=RuntimeError(SEGREDO)):
            resposta = cliente.get(reverse("pessoas"), {"modo": "todos"})
        self.assertEqual(resposta.status_code, 500)
        self.assertContains(resposta, "Erro inesperado", status_code=500)
        self.assertNotContains(resposta, SEGREDO, status_code=500)


class Pagina500Tests(SimpleTestCase):
    def test_500_renderiza_sem_contexto_de_request(self):
        # O Django renderiza o 500 sem request: o template não pode depender dele.
        self.assertIn("Erro inesperado", render_to_string("500.html"))
