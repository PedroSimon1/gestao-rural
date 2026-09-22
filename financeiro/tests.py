from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from usuarios.models import Titular

from .models import Amortizacao, LancamentoFinanceiro, Parcela


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


class ParcelaModelTest(TestCase):
    def setUp(self):
        self.titular = Titular.objects.create(
            nome="Titular Parcela",
            cpf="98765432100",
        )

        self.lancamento = LancamentoFinanceiro.objects.create(
            titular=self.titular,
            categoria=LancamentoFinanceiro.Categoria.DESPESA,
            descricao="Compra de insumos",
            valor_total=Decimal("3000.00"),
            data_lancamento="2026-09-22",
        )

    def test_criar_parcela(self):
        parcela = Parcela.objects.create(
            lancamento=self.lancamento,
            numero=1,
            valor_nominal=Decimal("1000.00"),
            data_vencimento="2026-10-22",
        )

        self.assertEqual(parcela.lancamento, self.lancamento)
        self.assertEqual(parcela.numero, 1)
        self.assertEqual(parcela.valor_nominal, Decimal("1000.00"))

    def test_parcelas_sao_ordenadas_por_numero(self):
        Parcela.objects.create(
            lancamento=self.lancamento,
            numero=2,
            valor_nominal=Decimal("1000.00"),
            data_vencimento="2026-11-22",
        )

        Parcela.objects.create(
            lancamento=self.lancamento,
            numero=1,
            valor_nominal=Decimal("1000.00"),
            data_vencimento="2026-10-22",
        )

        parcelas = list(self.lancamento.parcelas.all())

        self.assertEqual(parcelas[0].numero, 1)
        self.assertEqual(parcelas[1].numero, 2)

    def test_nao_permite_numero_repetido_no_mesmo_lancamento(self):
        Parcela.objects.create(
            lancamento=self.lancamento,
            numero=1,
            valor_nominal=Decimal("1000.00"),
            data_vencimento="2026-10-22",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Parcela.objects.create(
                    lancamento=self.lancamento,
                    numero=1,
                    valor_nominal=Decimal("2000.00"),
                    data_vencimento="2026-11-22",
                )


class AmortizacaoModelTest(TestCase):
    def setUp(self):
        self.titular = Titular.objects.create(
            nome="Titular Amortizacao",
            cpf="11122233344",
        )

        self.lancamento = LancamentoFinanceiro.objects.create(
            titular=self.titular,
            categoria=LancamentoFinanceiro.Categoria.DESPESA,
            descricao="Compra parcelada",
            valor_total=Decimal("3000.00"),
            data_lancamento="2026-09-22",
        )

        self.parcela = Parcela.objects.create(
            lancamento=self.lancamento,
            numero=1,
            valor_nominal=Decimal("1000.00"),
            data_vencimento="2026-10-22",
        )

    def test_criar_amortizacao(self):
        amortizacao = Amortizacao.objects.create(
            parcela=self.parcela,
            valor_pago=Decimal("400.00"),
            data_pagamento="2026-10-10",
        )

        self.assertEqual(amortizacao.parcela, self.parcela)
        self.assertEqual(amortizacao.valor_pago, Decimal("400.00"))

    def test_relacionamento_parcela_amortizacoes(self):
        Amortizacao.objects.create(
            parcela=self.parcela,
            valor_pago=Decimal("300.00"),
            data_pagamento="2026-10-10",
        )

        Amortizacao.objects.create(
            parcela=self.parcela,
            valor_pago=Decimal("200.00"),
            data_pagamento="2026-10-15",
        )

        self.assertEqual(self.parcela.amortizacoes.count(), 2)


class ParcelaCalculosFinanceirosTest(TestCase):
    def setUp(self):
        self.titular = Titular.objects.create(
            nome="Titular Calculos",
            cpf="55566677788",
        )

        self.lancamento = LancamentoFinanceiro.objects.create(
            titular=self.titular,
            categoria=LancamentoFinanceiro.Categoria.DESPESA,
            descricao="Compra parcelada para calculos",
            valor_total=Decimal("3000.00"),
            data_lancamento="2026-09-22",
        )

    def _criar_parcela(self, numero, valor_nominal):
        return Parcela.objects.create(
            lancamento=self.lancamento,
            numero=numero,
            valor_nominal=valor_nominal,
            data_vencimento="2026-10-22",
        )

    def test_parcela_sem_amortizacoes(self):
        parcela = self._criar_parcela(1, Decimal("1000.00"))

        self.assertEqual(parcela.total_pago, Decimal("0.00"))
        self.assertEqual(parcela.saldo_restante, Decimal("1000.00"))
        self.assertFalse(parcela.quitada)

    def test_parcela_parcialmente_paga(self):
        parcela = self._criar_parcela(2, Decimal("1000.00"))

        Amortizacao.objects.create(
            parcela=parcela,
            valor_pago=Decimal("400.00"),
            data_pagamento="2026-10-10",
        )

        self.assertEqual(parcela.total_pago, Decimal("400.00"))
        self.assertEqual(parcela.saldo_restante, Decimal("600.00"))
        self.assertFalse(parcela.quitada)

    def test_parcela_com_multiplas_amortizacoes(self):
        parcela = self._criar_parcela(3, Decimal("1000.00"))

        Amortizacao.objects.create(
            parcela=parcela,
            valor_pago=Decimal("300.00"),
            data_pagamento="2026-10-10",
        )
        Amortizacao.objects.create(
            parcela=parcela,
            valor_pago=Decimal("250.00"),
            data_pagamento="2026-10-15",
        )
        Amortizacao.objects.create(
            parcela=parcela,
            valor_pago=Decimal("50.00"),
            data_pagamento="2026-10-20",
        )

        self.assertEqual(parcela.total_pago, Decimal("600.00"))
        self.assertEqual(parcela.saldo_restante, Decimal("400.00"))
        self.assertFalse(parcela.quitada)

    def test_parcela_totalmente_quitada(self):
        parcela = self._criar_parcela(4, Decimal("1000.00"))

        Amortizacao.objects.create(
            parcela=parcela,
            valor_pago=Decimal("1000.00"),
            data_pagamento="2026-10-10",
        )

        self.assertEqual(parcela.total_pago, Decimal("1000.00"))
        self.assertEqual(parcela.saldo_restante, Decimal("0.00"))
        self.assertTrue(parcela.quitada)

    def test_pagamento_acima_do_valor_nominal_nao_gera_saldo_negativo(self):
        parcela = self._criar_parcela(5, Decimal("1000.00"))

        Amortizacao.objects.create(
            parcela=parcela,
            valor_pago=Decimal("1200.00"),
            data_pagamento="2026-10-10",
        )

        self.assertEqual(parcela.total_pago, Decimal("1200.00"))
        self.assertEqual(parcela.saldo_restante, Decimal("0.00"))
        self.assertTrue(parcela.quitada)
