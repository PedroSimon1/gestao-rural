"""2C: a confirmação da nota avisa quando já existe conta parecida (só aviso; a identidade fiscal é a trava)."""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from cadastros.models import Classificacao, Papel, Pessoa
from financeiro.models import MovimentoConta
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .analises import criar_analise, garantir_dono
from .testing import CNPJ, CPF, resultado_da_nota


@override_settings(**CREDENCIAIS_TESTE)
class AvisoNaConfirmacaoTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        self.fornecedor = Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste Ltda")
        self.fornecedor.atribuir_papel(Papel.FORNECEDOR)
        self.faturado = Pessoa.objects.create(documento=CPF, razao_social="Produtor Teste")
        self.faturado.atribuir_papel(Papel.FATURADO)
        original = resultado_da_nota()
        original["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        self.analise = criar_analise(self.client.session, original)
        self.url = reverse("analise_confirmar", args=[self.analise.id])

    def lancar_a_mao(self, valor="150.00", vencimento=date(2026, 11, 1)):
        classificacao = Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO")
        movimento, _ = registrar_movimento(DadosMovimento(
            tipo="APAGAR", origem="MANUAL", contraparte=self.fornecedor, faturado=self.faturado,
            valor_total=Decimal(valor), classificacoes=(ItemClassificacao(classificacao, principal=True),),
            parcelas=(ItemParcela(1, vencimento, Decimal(valor)),),
        ))
        return movimento

    def test_sem_conta_parecida_nao_avisa(self):
        self.assertNotContains(self.client.get(self.url), "Já existe conta parecida")

    def test_com_conta_parecida_avisa_com_link_e_continua_confirmavel(self):
        existente = self.lancar_a_mao()

        resposta = self.client.get(self.url)

        self.assertContains(resposta, "Já existe conta parecida")
        self.assertContains(resposta, reverse("conta_detalhe", args=[existente.pk]))
        self.assertContains(resposta, "Confirmar lançamento financeiro")  # aviso, não bloqueio
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_valor_ou_vencimento_diferente_nao_avisa(self):
        self.lancar_a_mao(valor="151.00")
        self.lancar_a_mao(vencimento=date(2027, 3, 3))

        self.assertNotContains(self.client.get(self.url), "Já existe conta parecida")
