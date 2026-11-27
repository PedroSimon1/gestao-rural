"""O Classificador escolhe entre as classificações de DESPESA ativas do cadastro (Q-05).

Banco: TestCase. Só o SDK do Gemini é simulado; as categorias iniciais vêm da migration 0003 de cadastros.
"""
from copy import deepcopy
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from cadastros.models import Classificacao, TipoClassificacao
from comum.sessao import garantir_dono
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .categorias import categorias_de_despesa
from .models import AnalisePendente
from .testing import resultado_da_nota


class CategoriasDeDespesaTests(TestCase):
    def test_so_despesas_ativas_ordenadas_por_descricao(self):
        Classificacao.objects.create(tipo="DESPESA", codigo="ZEBRA_ATIVA", descricao="Zebra ativa")
        Classificacao.objects.create(tipo="DESPESA", codigo="ABELHA_ATIVA", descricao="Abelha ativa")
        Classificacao.objects.create(tipo="DESPESA", codigo="OUTRA_INATIVA", descricao="Outra", status="INATIVO")
        Classificacao.objects.create(tipo="RECEITA", codigo="VENDA_FICTICIA", descricao="Venda fictícia")

        codigos = [categoria.codigo for categoria in categorias_de_despesa()]

        self.assertEqual(codigos[0], "ABELHA_ATIVA")
        self.assertEqual(codigos[-1], "ZEBRA_ATIVA")
        self.assertIn("MANUTENCAO_E_OPERACAO", codigos)
        self.assertNotIn("OUTRA_INATIVA", codigos)
        self.assertNotIn("VENDA_FICTICIA", codigos)
        self.assertEqual(
            len(codigos),
            Classificacao.objects.ativos().filter(tipo=TipoClassificacao.DESPESA).count(),
        )


@override_settings(**CREDENCIAIS_TESTE)
class ClassificadorComCategoriasDoBancoTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        bruto = deepcopy(resultado_da_nota())
        bruto["documento_e_nota_fiscal"] = True
        bruto["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        self.bruto = bruto

    def enviar(self, resposta_do_classificador):
        cliente = mock.Mock()
        cliente.gerar_json.side_effect = [self.bruto, resposta_do_classificador]
        with mock.patch("documentos.processamento._criar_cliente", return_value=cliente):
            resposta = self.client.post(reverse("analise_criar"), {
                "gemini_api_key": "ficticia-nao-guardar",
                "arquivo": SimpleUploadedFile("nota.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            })
        return resposta, cliente.gerar_json.call_args_list[-1].kwargs

    def test_categoria_criada_pelo_usuario_e_oferecida_e_aceita(self):
        Classificacao.objects.create(tipo="DESPESA", codigo="PECAS_E_IMPLEMENTOS", descricao="Peças e implementos")

        resposta, chamada = self.enviar({"tipo_despesa": "PECAS_E_IMPLEMENTOS", "justificativa": "Peça."})

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("PECAS_E_IMPLEMENTOS — Peças e implementos", chamada["instrucao_sistema"])
        self.assertEqual(AnalisePendente.objects.get().dados["tipo_despesa"], "PECAS_E_IMPLEMENTOS")

    def test_categoria_inativa_nao_e_oferecida_e_a_resposta_com_ela_e_recusada(self):
        Classificacao.objects.get(tipo="DESPESA", codigo="MANUTENCAO_E_OPERACAO").inativar()

        resposta, chamada = self.enviar({"tipo_despesa": "MANUTENCAO_E_OPERACAO", "justificativa": "x"})

        self.assertNotIn("MANUTENCAO_E_OPERACAO", chamada["instrucao_sistema"])
        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, "A classificação retornada não é válida", status_code=400)
        self.assertEqual(AnalisePendente.objects.count(), 0)

    def test_sem_categoria_ativa_a_nota_segue_para_conferencia_sem_classificacao(self):
        for categoria in Classificacao.objects.ativos().filter(tipo="DESPESA"):
            categoria.inativar()
        cliente = mock.Mock()
        cliente.gerar_json.side_effect = [self.bruto]
        with mock.patch("documentos.processamento._criar_cliente", return_value=cliente):
            resposta = self.client.post(reverse("analise_criar"), {
                "gemini_api_key": "ficticia-nao-guardar",
                "arquivo": SimpleUploadedFile("nota.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            })

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(cliente.gerar_json.call_count, 1)
        self.assertIsNone(AnalisePendente.objects.get().dados["tipo_despesa"])
