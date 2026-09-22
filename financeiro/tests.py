from decimal import Decimal

from django.test import TestCase

from usuarios.models import Titular
from .models import LancamentoFinanceiro


class LancamentoFinanceiroModelTest(TestCase):
    def setUp(self):
        self.titular = Titular.objects.create(
            nome="Titular Teste",
            cpf="12345678900",
        )

    def test_criar_lancamento_despesa(self):
        lancamento = LancamentoFinanceiro.objects.create(
            titular=self.titular,
            categoria=LancamentoFinanceiro.Categoria.DESPESA,
            subcategoria="Insumos",
            descricao="Compra de sementes",
            valor_total=Decimal("1500.00"),
            data_lancamento="2026-09-22",
        )

        self.assertEqual(lancamento.titular, self.titular)
        self.assertEqual(
            lancamento.categoria,
            LancamentoFinanceiro.Categoria.DESPESA,
        )
        self.assertEqual(lancamento.valor_total, Decimal("1500.00"))

    def test_relacionamento_titular_lancamentos(self):
        LancamentoFinanceiro.objects.create(
            titular=self.titular,
            categoria=LancamentoFinanceiro.Categoria.RECEITA,
            descricao="Venda de produção",
            valor_total=Decimal("2500.00"),
            data_lancamento="2026-09-22",
        )

        self.assertEqual(self.titular.lancamentos.count(), 1)