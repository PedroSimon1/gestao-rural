"""Itens extraídos: persistência e tolerância, apenas no PostgreSQL local de teste."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase

from .identidade_fiscal import identificar_nota, registrar_identidade_fiscal
from .itens_nota import registrar_itens_nota
from .models import AlteracaoNaoPermitida, ExclusaoDeMovimentoNaoPermitida, ItemNotaFiscal
from .servicos import registrar_movimento
from .test_servicos import DadosDeServico


class ItensNotaTests(DadosDeServico, TestCase):
    def setUp(self):
        super().setUp()
        movimento, _ = registrar_movimento(self.apagar())
        self.nota, _ = registrar_identidade_fiscal(movimento, identificar_nota(
            emitente_cnpj=self.fornecedor.documento, modelo="55", serie=1, numero=123,
        ))

    def test_grava_na_ordem_recebida_e_retorna_os_registros(self):
        itens = registrar_itens_nota(self.nota, [
            {"descricao": "Ração", "quantidade": "2.125678", "valor_unitario": "80.10", "valor_total": "170.27"},
            {"descricao": "Sal mineral", "quantidade": "0", "valor_unitario": "0", "valor_total": "0"},
        ])
        self.assertEqual([item.pk for item in itens], list(self.nota.itens.values_list("pk", flat=True)))
        self.assertEqual([(i.ordem, i.descricao) for i in itens], [(1, "Ração"), (2, "Sal mineral")])
        self.assertEqual(itens[0].quantidade, Decimal("2.125678"))
        self.assertEqual(itens[0].valor_unitario, Decimal("80.10"))
        self.assertEqual(itens[0].valor_total, Decimal("170.27"))
        self.assertEqual(itens[1].quantidade, Decimal("0"))

    def test_idempotente_nao_complementa_nem_altera_itens(self):
        primeira = registrar_itens_nota(self.nota, [{"descricao": "Óleo"}])
        segunda = registrar_itens_nota(self.nota, [{"descricao": "Outro item"}])
        self.assertEqual([i.pk for i in primeira], [i.pk for i in segunda])
        self.assertEqual(self.nota.itens.count(), 1)
        self.assertEqual(segunda[0].descricao, "Óleo")

    def test_ignora_descricao_ausente_e_conteudo_malformado(self):
        itens = registrar_itens_nota(self.nota, [
            None, "inválido", {}, {"descricao": None}, {"descricao": "  "}, {"descricao": 42},
            {"descricao": "  Diesel  "}, {"descricao": "x" * 600},
        ])
        self.assertEqual([(i.ordem, len(i.descricao)) for i in itens], [(1, 6), (2, 500)])
        self.assertEqual(itens[0].descricao, "Diesel")
        self.assertIsNone(itens[0].quantidade)
        self.assertIsNone(itens[0].valor_unitario)
        self.assertIsNone(itens[0].valor_total)

    def test_numeros_invalidos_viram_null(self):
        invalidos = (None, "", "abc", True, [], {}, "NaN", "sNaN", "Infinity", "-1", "1e9999")
        itens = registrar_itens_nota(self.nota, [
            {"descricao": f"Item {n}", "quantidade": v, "valor_unitario": v, "valor_total": v}
            for n, v in enumerate(invalidos)
        ])
        for item in itens:
            with self.subTest(descricao=item.descricao):
                self.assertIsNone(item.quantidade)
                self.assertIsNone(item.valor_unitario)
                self.assertIsNone(item.valor_total)

    def test_limites_e_arredondamento_nao_estouram_o_banco(self):
        itens = registrar_itens_nota(self.nota, [
            {"descricao": "Limite", "quantidade": "100000000000000", "valor_total": "10000000000"},
            {"descricao": "Arredondamento", "quantidade": "1.1234567", "valor_unitario": "2.125"},
            {"descricao": "Estouro arredondado", "quantidade": "99999999999999.9999999", "valor_total": "9999999999.999"},
        ])
        self.assertIsNone(itens[0].quantidade)
        self.assertIsNone(itens[0].valor_total)
        self.assertEqual(itens[1].quantidade, Decimal("1.123457"))
        self.assertEqual(itens[1].valor_unitario, Decimal("2.13"))
        self.assertIsNone(itens[2].quantidade)
        self.assertIsNone(itens[2].valor_total)

    def test_lista_vazia_ou_invalida_nao_impede_gravacao_posterior(self):
        for entrada in ([], None, "inválida", {}, 42):
            self.assertEqual(registrar_itens_nota(self.nota, entrada), [])
        self.assertEqual(len(registrar_itens_nota(self.nota, [{"descricao": "Ração"}])), 1)

    def test_erro_de_banco_propaga(self):
        with mock.patch.object(ItemNotaFiscal.objects, "bulk_create", side_effect=DatabaseError):
            with self.assertRaises(DatabaseError):
                registrar_itens_nota(self.nota, [{"descricao": "Ração"}])
        self.assertEqual(self.nota.itens.count(), 0)

    def test_campos_imutaveis_em_instancia_queryset_e_bulk(self):
        item = registrar_itens_nota(self.nota, [{"descricao": "Óleo"}])[0]
        valores = {
            "nota_fiscal": self.nota.pk + 1, "ordem": 2, "descricao": "Outra",
            "quantidade": Decimal("2"), "valor_unitario": Decimal("3"),
            "valor_total": Decimal("6"), "criado_em": item.criado_em + timedelta(days=1),
        }
        for nome, valor in valores.items():
            with self.subTest(campo=nome):
                item.refresh_from_db()
                setattr(item, ItemNotaFiscal._meta.get_field(nome).attname, valor)
                with self.assertRaises(AlteracaoNaoPermitida):
                    item.save()
                with self.assertRaises(AlteracaoNaoPermitida):
                    ItemNotaFiscal.objects.filter(pk=item.pk).update(**{nome: valor})
                with self.assertRaises(AlteracaoNaoPermitida):
                    ItemNotaFiscal.objects.bulk_update([item], [nome])
        item.refresh_from_db()
        with self.assertRaises(AlteracaoNaoPermitida):
            self.nota.itens.add(item)
        with self.assertRaises(AlteracaoNaoPermitida):
            ItemNotaFiscal.objects.bulk_create(
                [item], update_conflicts=True, update_fields=["descricao"], unique_fields=["id"],
            )

    def test_sem_exclusao_nem_por_base_manager(self):
        item = registrar_itens_nota(self.nota, [{"descricao": "Óleo"}])[0]
        for excluir in (item.delete, ItemNotaFiscal.objects.all().delete,
                        ItemNotaFiscal._base_manager.all().delete, self.nota.itens.all().delete):
            with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
                excluir()
        self.assertEqual(ItemNotaFiscal.objects.count(), 1)

    def test_constraints_no_banco(self):
        registrar_itens_nota(self.nota, [{"descricao": "Óleo"}])
        for campos in (
            {"ordem": 1}, {"ordem": 0}, {"descricao": " "}, {"quantidade": "-1"},
            {"valor_unitario": "-1"}, {"valor_total": "-1"},
        ):
            with self.subTest(campos=campos), self.assertRaises(IntegrityError), transaction.atomic():
                ItemNotaFiscal.objects.create(**{
                    "nota_fiscal": self.nota, "ordem": 2, "descricao": "Outro", **campos,
                })
