"""Filtro `moeda`: reais com milhar, vírgula e sempre dois centavos."""
from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from .templatetags.moeda import moeda


class MoedaTests(SimpleTestCase):
    def test_formatos(self):
        casos = {
            Decimal("0"): "R$ 0,00",
            Decimal("5"): "R$ 5,00",
            Decimal("920.5"): "R$ 920,50",
            "1840.00": "R$ 1.840,00",
            1234567.891: "R$ 1.234.567,89",
            Decimal("-1234.5"): "-R$ 1.234,50",
            Decimal("0.005"): "R$ 0,01",
            Decimal("0.004"): "R$ 0,00",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(moeda(entrada), esperado)

    def test_sem_valor_ou_invalido_vira_travessao(self):
        for entrada in (None, "", "abc", Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(entrada=entrada):
                self.assertEqual(moeda(entrada), "—")

    def test_uso_em_template(self):
        saida = Template("{% load moeda %}{{ v|moeda }}").render(Context({"v": Decimal("5095.5")}))
        self.assertEqual(saida, "R$ 5.095,50")
