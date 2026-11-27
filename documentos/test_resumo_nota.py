"""Ficha da nota (etapas 2 a 4) e resumo do lançamento concluído."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from .conferencia import conferir_nota
from .resumo_nota import ficha_da_nota, resumo_do_lancamento
from .testing import resultado_da_nota


def nota_com_parcelas(*parcelas):
    resultado = resultado_da_nota("300.00")
    resultado["parcelas"] = [
        {"numero": numero, "data_vencimento": vencimento, "valor": valor}
        for numero, (vencimento, valor) in enumerate(parcelas, 1)
    ]
    return conferir_nota(resultado, {})


class FichaDaNotaTests(TestCase):
    def test_ficha_traz_nota_partes_total_e_parcelas_iguais_resumidas(self):
        ficha = ficha_da_nota(conferir_nota(resultado_da_nota(), {}))
        self.assertEqual(ficha.numero, 123)
        self.assertEqual(ficha.fornecedor, "Fornecedor Teste Ltda")
        self.assertEqual(ficha.faturado, "Produtor Teste")
        self.assertEqual(ficha.valor_total, Decimal("150.00"))
        self.assertEqual(ficha.parcelas, "1 × R$ 150,00")

    def test_parcelas_de_valores_iguais_viram_n_vezes_valor(self):
        nota = nota_com_parcelas(("2026-11-01", "150.00"), ("2026-12-01", "150.00"))
        self.assertEqual(ficha_da_nota(nota).parcelas, "2 × R$ 150,00")

    def test_parcelas_de_valores_diferentes_dizem_so_a_quantidade(self):
        nota = nota_com_parcelas(("2026-11-01", "100.00"), ("2026-12-01", "200.00"))
        self.assertEqual(ficha_da_nota(nota).parcelas, "2 parcelas")

    def test_sem_parcelas_mostra_travessao(self):
        self.assertEqual(ficha_da_nota(nota_com_parcelas()).parcelas, "—")


class ResumoDoLancamentoTests(TestCase):
    def test_quantidade_valor_e_primeiro_vencimento_mesmo_fora_de_ordem(self):
        nota = nota_com_parcelas(("2026-12-01", "100.00"), ("2026-11-01", "200.00"))
        resumo = resumo_do_lancamento(nota)
        self.assertEqual(resumo.quantidade_parcelas, 2)
        self.assertEqual(resumo.primeiro_vencimento, date(2026, 11, 1))
        self.assertEqual(resumo.valor_total, Decimal("300.00"))

    def test_sem_parcelas_nao_ha_primeiro_vencimento(self):
        self.assertIsNone(resumo_do_lancamento(nota_com_parcelas()).primeiro_vencimento)
