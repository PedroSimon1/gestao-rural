"""Classificacao e categorias iniciais (GR-36) no PostgreSQL local de teste.

TestCase: rodam só com as variáveis DB_TEST_* (config/banco_de_teste.py). As
migrations são aplicadas na criação do banco de teste, então as categorias
iniciais (0003_categorias_iniciais) já existem em cada teste. Um
TransactionTestCase apagaria esses dados no flush ao terminar: testes desse
tipo que dependam delas devem criá-las ou usar serialized_rollback=True.
"""

import importlib

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from agents.classificador.schemas import TipoDespesa

from .models import Classificacao, ExclusaoNaoPermitida, Status, TipoClassificacao

carga = importlib.import_module("cadastros.migrations.0003_categorias_iniciais")

DESPESA = TipoClassificacao.DESPESA
RECEITA = TipoClassificacao.RECEITA


def criar(tipo=RECEITA, codigo="VENDA_PRODUCAO", descricao="VENDA DE PRODUÇÃO"):
    return Classificacao.objects.create(tipo=tipo, codigo=codigo, descricao=descricao)


def rodar_carga():
    carga.criar_categorias_iniciais(apps, None)


class CriacaoTests(TestCase):
    def test_classificacao_de_despesa_e_de_receita(self):
        despesa = criar(DESPESA, "INSUMOS", "INSUMOS")
        receita = criar(RECEITA, "VENDA_PRODUCAO", "VENDA DE PRODUÇÃO")

        self.assertEqual((despesa.tipo, receita.tipo), ("DESPESA", "RECEITA"))
        self.assertEqual(despesa.status, Status.ATIVO)
        self.assertEqual(str(receita), "Receita: VENDA DE PRODUÇÃO")

    def test_codigo_e_descricao_normalizados(self):
        classificacao = criar(RECEITA, "  venda_producao ", "  Venda   de  produção ")
        classificacao.refresh_from_db()

        self.assertEqual(classificacao.codigo, "VENDA_PRODUCAO")
        self.assertEqual(classificacao.descricao, "Venda de produção")

    def test_full_clean_aceita_classificacao_valida(self):
        Classificacao(tipo=RECEITA, codigo="arrendamento", descricao="Arrendamento").full_clean()


class UnicidadeTests(TestCase):
    def test_banco_recusa_tipo_e_codigo_duplicados(self):
        criar()

        with self.assertRaises(IntegrityError), transaction.atomic():
            criar(descricao="Outra descrição")

    def test_duplicado_com_outra_caixa_tambem_e_recusado(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            criar(DESPESA, "manutencao_e_operacao", "Repetida")

    def test_full_clean_informa_duplicidade(self):
        with self.assertRaisesMessage(
            ValidationError, "Já existe uma classificação com este tipo e código."
        ):
            Classificacao(tipo=DESPESA, codigo="MANUTENCAO_E_OPERACAO",
                          descricao="Repetida").full_clean()

    def test_mesmo_codigo_em_tipos_distintos(self):
        criar(DESPESA, "ARRENDAMENTO", "Arrendamento pago")
        criar(RECEITA, "ARRENDAMENTO", "Arrendamento recebido")

        self.assertEqual(Classificacao.objects.filter(codigo="ARRENDAMENTO").count(), 2)


class ConstraintsTests(TestCase):
    def setUp(self):
        self.classificacao = criar()

    def atualizar(self, **campos):
        return Classificacao.objects.filter(pk=self.classificacao.pk).update(**campos)

    def test_banco_recusa_codigo_fora_do_formato(self):
        for codigo in ("venda", "VENDA PRODUCAO", "_VENDA", "VENDA_", "VENDA__X", "VENDA-X", ""):
            with self.subTest(codigo=codigo):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.atualizar(codigo=codigo)

    def test_banco_recusa_tipo_status_e_descricao_invalidos(self):
        for campos in ({"tipo": "OUTRO"}, {"status": "PAUSADO"}, {"descricao": "  "}):
            with self.subTest(**campos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.atualizar(**campos)

    def test_full_clean_recusa_codigo_e_descricao_invalidos(self):
        for campos, erro in (
            ({"codigo": "VENDA PRODUCAO"}, "Use letras maiúsculas"),
            ({"descricao": "   "}, "descricao"),
        ):
            with self.subTest(**campos):
                dados = {"tipo": RECEITA, "codigo": "NOVA", "descricao": "Nova", **campos}
                with self.assertRaisesMessage(ValidationError, erro):
                    Classificacao(**dados).full_clean()


class StatusEExclusaoTests(TestCase):
    def setUp(self):
        self.classificacao = criar()

    def test_inativar_e_reativar_preservam_a_identidade(self):
        pk, codigo = self.classificacao.pk, self.classificacao.codigo

        self.classificacao.inativar()
        self.assertNotIn(self.classificacao, Classificacao.objects.ativos())
        encontrada = Classificacao.objects.por_codigo(RECEITA, "venda_producao").get()
        self.assertEqual((encontrada.pk, encontrada.status), (pk, Status.INATIVO))

        self.classificacao.reativar()
        self.classificacao.refresh_from_db()
        self.assertEqual((self.classificacao.pk, self.classificacao.codigo), (pk, codigo))
        self.assertIn(self.classificacao, Classificacao.objects.ativos())

    def test_exclusao_fisica_bloqueada(self):
        total = Classificacao.objects.count()

        for operacao in (self.classificacao.delete, Classificacao.objects.all().delete):
            with self.subTest(operacao=operacao):
                with self.assertRaises(ExclusaoNaoPermitida):
                    operacao()
        self.assertEqual(Classificacao.objects.count(), total)


class IdentidadeEstavelTests(TestCase):
    def setUp(self):
        self.classificacao = criar()

    def test_codigo_e_tipo_nao_mudam_depois_de_gravados(self):
        for campo, valor in (("codigo", "OUTRO_CODIGO"), ("tipo", DESPESA)):
            with self.subTest(campo=campo):
                classificacao = Classificacao.objects.get(pk=self.classificacao.pk)
                setattr(classificacao, campo, valor)
                with self.assertRaisesMessage(ValidationError, "não podem ser alterados"):
                    classificacao.save()
                with self.assertRaisesMessage(ValidationError, "não podem ser alterados"):
                    classificacao.full_clean()
        self.classificacao.refresh_from_db()
        self.assertEqual((self.classificacao.tipo, self.classificacao.codigo),
                         (RECEITA, "VENDA_PRODUCAO"))

    def test_objeto_novo_com_pk_existente_nao_contorna_a_verificacao(self):
        copia = Classificacao(
            pk=self.classificacao.pk, tipo=RECEITA, codigo="OUTRO_CODIGO",
            descricao="Outra", criado_em=self.classificacao.criado_em,
        )

        with self.assertRaisesMessage(ValidationError, "não podem ser alterados"):
            copia.save()
        self.classificacao.refresh_from_db()
        self.assertEqual(self.classificacao.codigo, "VENDA_PRODUCAO")

    def test_mesmo_codigo_com_outra_caixa_nao_e_alteracao(self):
        self.classificacao.codigo = "venda_producao"

        self.classificacao.save()

        self.classificacao.refresh_from_db()
        self.assertEqual(self.classificacao.codigo, "VENDA_PRODUCAO")

    def test_descricao_pode_ser_corrigida(self):
        self.classificacao.descricao = "Venda da produção"
        self.classificacao.save()

        self.classificacao.refresh_from_db()
        self.assertEqual(self.classificacao.descricao, "Venda da produção")

    def test_inativar_nao_revalida_a_identidade(self):
        # update_fields só com status: nenhuma consulta extra de identidade.
        with self.assertNumQueries(1):
            self.classificacao.inativar()


class CategoriasIniciaisTests(TestCase):
    def test_carga_cria_as_categorias_do_classificador(self):
        despesas = Classificacao.objects.filter(tipo=DESPESA).order_by("codigo")

        self.assertEqual(
            list(despesas.values_list("codigo", "descricao", "status")),
            [
                ("INFRAESTRUTURA_E_UTILIDADES", "INFRAESTRUTURA E UTILIDADES", "ATIVO"),
                ("MANUTENCAO_E_OPERACAO", "MANUTENÇÃO E OPERAÇÃO", "ATIVO"),
            ],
        )

    def test_codigos_iguais_aos_valores_do_enum_do_classificador(self):
        codigos = {codigo for tipo, codigo, _ in carga.CATEGORIAS_INICIAIS if tipo == DESPESA}

        self.assertEqual(codigos, {item.value for item in TipoDespesa})

    def test_carga_repetida_nao_duplica_nem_muda_a_identidade(self):
        ids = dict(Classificacao.objects.values_list("codigo", "pk"))

        rodar_carga()
        rodar_carga()

        self.assertEqual(dict(Classificacao.objects.values_list("codigo", "pk")), ids)

    def test_carga_repetida_preserva_inativacao_e_descricao_editada(self):
        manutencao = Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO")
        manutencao.inativar()
        infraestrutura = Classificacao.objects.get(codigo="INFRAESTRUTURA_E_UTILIDADES")
        infraestrutura.descricao = "Infraestrutura e utilidades (editada)"
        infraestrutura.save()

        rodar_carga()

        manutencao.refresh_from_db()
        infraestrutura.refresh_from_db()
        self.assertEqual(manutencao.status, Status.INATIVO)
        self.assertEqual(infraestrutura.descricao, "Infraestrutura e utilidades (editada)")

    def test_carga_cria_apenas_o_que_falta(self):
        # Simula um ambiente em que só uma categoria existia: a carga completa
        # o que falta sem tocar no restante.
        Classificacao.objects.filter(codigo="INFRAESTRUTURA_E_UTILIDADES").update(
            codigo="INFRAESTRUTURA_ANTIGA"
        )

        rodar_carga()

        self.assertEqual(
            sorted(Classificacao.objects.values_list("codigo", flat=True)),
            ["INFRAESTRUTURA_ANTIGA", "INFRAESTRUTURA_E_UTILIDADES", "MANUTENCAO_E_OPERACAO"],
        )
