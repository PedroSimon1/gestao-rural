"""MovimentoConta e MovimentoClassificacao (GR-37) no PostgreSQL local de teste.

TestCase: rodam só com as variáveis DB_TEST_* (config/banco_de_teste.py). Os
registros são criados direto pelo ORM: as regras entre entidades (papéis,
cadastros inativos, classificação principal obrigatória) são testadas em
test_servicos.py. As categorias de despesa já existem pela migration
0003_categorias_iniciais. Documentos fictícios, com DV calculado; nenhum dado real.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.template import Context, Engine
from django.test import TestCase

from cadastros.models import Classificacao, ExclusaoNaoPermitida, Pessoa

from .models import (
    AlteracaoNaoPermitida, ExclusaoDeMovimentoNaoPermitida, MovimentoClassificacao,
    MovimentoConta, OrigemMovimento, StatusMovimento, TipoMovimento,
)

CNPJ = "11222333000181"
CPF = "12345678909"
APAGAR = TipoMovimento.APAGAR
ARECEBER = TipoMovimento.ARECEBER
RECUSA_DE_VINCULO = "Os vínculos de um registro financeiro não podem ser trocados."


def criar_fornecedor():
    return Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste")


def criar_faturado():
    return Pessoa.objects.create(documento=CPF, razao_social="Produtor Teste")


def despesa(codigo="MANUTENCAO_E_OPERACAO"):
    return Classificacao.objects.get(tipo="DESPESA", codigo=codigo)


def criar_receita():
    return Classificacao.objects.create(
        tipo="RECEITA", codigo="VENDA_PRODUCAO", descricao="VENDA DE PRODUÇÃO"
    )


def criar_movimento(contraparte, faturado=None, tipo=ARECEBER, **campos):
    campos.setdefault("origem", OrigemMovimento.MANUAL)
    campos.setdefault("valor_total", Decimal("150.00"))
    return MovimentoConta.objects.create(
        tipo=tipo, contraparte=contraparte, faturado=faturado, **campos
    )


class MovimentoBaseTestCase(TestCase):
    def setUp(self):
        self.fornecedor = criar_fornecedor()
        self.faturado = criar_faturado()

    def criar_apagar(self, **campos):
        return criar_movimento(self.fornecedor, self.faturado, APAGAR, **campos)


class CriacaoTests(MovimentoBaseTestCase):
    def test_movimento_nasce_confirmado_com_data_de_criacao(self):
        movimento = self.criar_apagar(origem=OrigemMovimento.NOTA_FISCAL)
        movimento.refresh_from_db()

        self.assertEqual(movimento.status, StatusMovimento.CONFIRMADO)
        self.assertIsNotNone(movimento.criado_em)
        self.assertEqual(movimento.valor_total, Decimal("150.00"))
        self.assertIsNone(movimento.analise_origem_id)

    def test_varios_movimentos_sem_analise_de_origem(self):
        criar_movimento(self.fornecedor)
        criar_movimento(self.fornecedor)

        self.assertEqual(MovimentoConta.objects.filter(analise_origem_id=None).count(), 2)

    def test_mesma_analise_nao_gera_dois_movimentos(self):
        analise = uuid.uuid4()
        self.criar_apagar(analise_origem_id=analise)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.criar_apagar(analise_origem_id=analise)
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_confirmados_retorna_movimentos_confirmados(self):
        movimento = self.criar_apagar()

        self.assertEqual(list(MovimentoConta.objects.confirmados()), [movimento])


class ConstraintsDoBancoTests(MovimentoBaseTestCase):
    def test_banco_recusa_tipo_origem_e_status_invalidos(self):
        for campos in ({"tipo": "OUTRO"}, {"origem": "EMAIL"}, {"status": "PAUSADO"}):
            with self.subTest(**campos):
                dados = {"tipo": ARECEBER, **campos}
                with self.assertRaises(IntegrityError), transaction.atomic():
                    criar_movimento(self.fornecedor, self.faturado, **dados)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_banco_recusa_valor_zero_ou_negativo(self):
        for valor in (Decimal("0"), Decimal("-0.01"), Decimal("-150.00")):
            with self.subTest(valor=valor):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.criar_apagar(valor_total=valor)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_valores_nos_limites_sao_aceitos(self):
        for valor in (Decimal("0.01"), Decimal("9999999999.99")):
            with self.subTest(valor=valor):
                movimento = self.criar_apagar(valor_total=valor)
                movimento.refresh_from_db()
                self.assertEqual(movimento.valor_total, valor)

    def test_banco_recusa_conta_a_pagar_sem_faturado(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            criar_movimento(self.fornecedor, None, APAGAR)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_conta_a_receber_sem_faturado_e_aceita(self):
        movimento = criar_movimento(self.fornecedor, None, ARECEBER)

        self.assertIsNone(movimento.faturado_id)

    def test_sql_direto_nao_contorna_o_valor_positivo(self):
        movimento = self.criar_apagar()

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE movimentos_contas SET valor_total = 0 WHERE id = %s",
                    [movimento.pk],
                )
        movimento.refresh_from_db()
        self.assertEqual(movimento.valor_total, Decimal("150.00"))

    def test_sql_direto_nao_remove_faturado_da_conta_a_pagar(self):
        movimento = self.criar_apagar()

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE movimentos_contas SET faturado_id = NULL WHERE id = %s",
                    [movimento.pk],
                )


class FullCleanTests(MovimentoBaseTestCase):
    def test_full_clean_aceita_movimento_valido(self):
        MovimentoConta(
            tipo=APAGAR, origem=OrigemMovimento.MANUAL, contraparte=self.fornecedor,
            faturado=self.faturado, valor_total=Decimal("10.00"),
        ).full_clean()

    def test_full_clean_informa_faturado_obrigatorio(self):
        movimento = MovimentoConta(
            tipo=APAGAR, origem=OrigemMovimento.MANUAL, contraparte=self.fornecedor,
            valor_total=Decimal("10.00"),
        )

        with self.assertRaises(ValidationError) as contexto:
            movimento.full_clean()
        self.assertIn("Conta a pagar exige o faturado.", contexto.exception.messages)

    def test_full_clean_informa_valor_invalido(self):
        movimento = MovimentoConta(
            tipo=ARECEBER, origem=OrigemMovimento.MANUAL, contraparte=self.fornecedor,
            valor_total=Decimal("0"),
        )

        with self.assertRaises(ValidationError) as contexto:
            movimento.full_clean()
        self.assertIn(
            "O valor total deve ser maior que zero e menor que R$ 10 bilhões.",
            contexto.exception.messages,
        )


class ImutabilidadeMovimentoTests(MovimentoBaseTestCase):
    def setUp(self):
        super().setUp()
        self.movimento = self.criar_apagar()
        self.outra_pessoa = Pessoa.objects.create(
            documento="11444777000161", razao_social="Outra Empresa Teste"
        )

    def estado_no_banco(self):
        return MovimentoConta.objects.filter(pk=self.movimento.pk).values().get()

    def test_alteracao_de_campo_essencial_e_recusada(self):
        original = self.estado_no_banco()
        alteracoes = {
            "tipo": ARECEBER,
            "origem": OrigemMovimento.NOTA_FISCAL,
            "status": StatusMovimento.CANCELADO,
            "contraparte": self.outra_pessoa,
            "faturado": self.outra_pessoa,
            "valor_total": Decimal("999.00"),
            "analise_origem_id": uuid.uuid4(),
        }
        for campo, valor in alteracoes.items():
            with self.subTest(campo=campo):
                movimento = MovimentoConta.objects.get(pk=self.movimento.pk)
                setattr(movimento, campo, valor)

                with self.assertRaises(AlteracaoNaoPermitida) as contexto:
                    movimento.save()
                self.assertIn(campo, contexto.exception.messages[0])
                self.assertEqual(self.estado_no_banco(), original)

    def test_alteracao_e_um_erro_de_validacao(self):
        self.movimento.valor_total = Decimal("1.00")

        with self.assertRaises(ValidationError):
            self.movimento.save()

    def test_salvar_sem_alteracoes_funciona(self):
        movimento = MovimentoConta.objects.get(pk=self.movimento.pk)

        movimento.save()

        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_update_do_queryset_e_recusado(self):
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.filter(pk=self.movimento.pk).update(
                valor_total=Decimal("1.00")
            )
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.update(contraparte_id=self.outra_pessoa.pk)
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.update(contraparte=self.outra_pessoa)
        self.assertEqual(self.estado_no_banco()["valor_total"], Decimal("150.00"))

    def test_bulk_update_e_recusado(self):
        self.movimento.valor_total = Decimal("1.00")

        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.bulk_update([self.movimento], ["valor_total"])
        # A recusa vem antes da transação do bulk_update: a de quem chamou segue usável.
        self.assertEqual(self.estado_no_banco()["valor_total"], Decimal("150.00"))

    def test_upsert_do_bulk_create_e_recusado(self):
        copia = MovimentoConta(
            tipo=APAGAR, origem=OrigemMovimento.MANUAL, contraparte=self.fornecedor,
            faturado=self.faturado, valor_total=Decimal("1.00"), analise_origem_id=uuid.uuid4(),
        )

        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.bulk_create(
                [copia], update_conflicts=True, unique_fields=["analise_origem_id"],
                update_fields=["valor_total"],
            )
        self.assertEqual(self.estado_no_banco()["valor_total"], Decimal("150.00"))

    def test_upsert_com_argumentos_posicionais_e_recusado(self):
        analise = uuid.uuid4()
        existente = self.criar_apagar(analise_origem_id=analise)
        copia = MovimentoConta(
            tipo=APAGAR, origem=OrigemMovimento.MANUAL, contraparte=self.fornecedor,
            faturado=self.faturado, valor_total=Decimal("1.00"), analise_origem_id=analise,
        )

        # bulk_create(objs, batch_size, ignore_conflicts, update_conflicts,
        # update_fields, unique_fields): a recusa não depende do argumento nomeado.
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.bulk_create(
                [copia], None, False, True, ["valor_total"], ["analise_origem_id"]
            )
        existente.refresh_from_db()
        self.assertEqual(existente.valor_total, Decimal("150.00"))

    async def test_versoes_assincronas_tambem_recusam(self):
        copia = MovimentoConta(
            tipo=APAGAR, origem=OrigemMovimento.MANUAL, contraparte=self.fornecedor,
            faturado=self.faturado, valor_total=Decimal("1.00"),
        )
        self.movimento.valor_total = Decimal("1.00")

        with self.assertRaises(AlteracaoNaoPermitida):
            await MovimentoConta.objects.abulk_create(
                [copia], None, False, True, ["valor_total"], ["analise_origem_id"]
            )
        with self.assertRaises(AlteracaoNaoPermitida):
            await MovimentoConta.objects.abulk_update([self.movimento], ["valor_total"])
        with self.assertRaises(AlteracaoNaoPermitida):
            await MovimentoConta.objects.filter(pk=self.movimento.pk).aupdate(
                valor_total=Decimal("1.00")
            )
        with self.assertRaises(AlteracaoNaoPermitida):
            await self.movimento.asave()
        valor = await MovimentoConta.objects.filter(pk=self.movimento.pk).values_list(
            "valor_total", flat=True
        ).aget()
        self.assertEqual(valor, Decimal("150.00"))

    def test_campos_em_gerador_nao_se_perdem_na_verificacao(self):
        movimento = MovimentoConta.objects.get(pk=self.movimento.pk)
        movimento.valor_total = Decimal("1.00")
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.bulk_update([movimento], (c for c in ["valor_total"]))

        movimento = MovimentoConta.objects.get(pk=self.movimento.pk)
        movimento.atualizado_em = movimento.atualizado_em + timedelta(days=1)
        MovimentoConta.objects.bulk_update([movimento], (c for c in ["atualizado_em"]))

        self.assertEqual(self.estado_no_banco()["atualizado_em"], movimento.atualizado_em)
        self.assertEqual(self.estado_no_banco()["valor_total"], Decimal("150.00"))

    def test_bulk_update_sem_campos_mantem_o_erro_do_django(self):
        with self.assertRaisesMessage(ValueError, "Field names must be given"):
            MovimentoConta.objects.bulk_update([self.movimento], None)

    def test_base_manager_tambem_protege(self):
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta._base_manager.filter(pk=self.movimento.pk).update(
                valor_total=Decimal("1.00")
            )
        with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
            MovimentoConta._base_manager.all().delete()
        with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
            MovimentoClassificacao._base_manager.all().delete()

    def test_criado_em_nao_pode_ser_alterado(self):
        movimento = MovimentoConta.objects.get(pk=self.movimento.pk)
        movimento.criado_em = movimento.criado_em.replace(year=2000)

        with self.assertRaises(AlteracaoNaoPermitida):
            movimento.save()

    def test_objeto_novo_com_pk_existente_nao_sobrescreve(self):
        impostor = MovimentoConta(
            pk=self.movimento.pk, tipo=ARECEBER, origem=OrigemMovimento.MANUAL,
            contraparte=self.outra_pessoa, valor_total=Decimal("1.00"),
        )

        with self.assertRaises(AlteracaoNaoPermitida):
            impostor.save()
        self.assertEqual(self.estado_no_banco()["contraparte_id"], self.fornecedor.pk)

    def test_objeto_novo_com_pk_existente_e_mesmos_dados_e_recusado(self):
        copia = MovimentoConta(**{
            campo: valor for campo, valor in self.estado_no_banco().items()
            if campo not in ("criado_em", "atualizado_em")
        })

        with self.assertRaises(AlteracaoNaoPermitida) as contexto:
            copia.save()
        self.assertEqual(contexto.exception.code, "registro_existente")

    def test_valor_equivalente_em_outro_formato_nao_e_alteracao(self):
        movimento = MovimentoConta.objects.get(pk=self.movimento.pk)
        movimento.valor_total = "150.00"

        movimento.save()

        self.assertEqual(self.estado_no_banco()["valor_total"], Decimal("150.00"))

    def test_uuid_e_pk_em_texto_nao_sao_alteracao(self):
        analise = uuid.uuid4()
        movimento = MovimentoConta.objects.get(pk=self.criar_apagar(analise_origem_id=analise).pk)
        movimento.analise_origem_id = str(analise)
        movimento.contraparte_id = str(self.fornecedor.pk)

        movimento.save()

        movimento.refresh_from_db()
        self.assertEqual((movimento.analise_origem_id, movimento.contraparte_id),
                         (analise, self.fornecedor.pk))


class GerenciadoresReversosTests(MovimentoBaseTestCase):
    """pessoa.movimentos_como_faturado, classificacao.movimentos etc. não trocam FKs."""

    def setUp(self):
        super().setUp()
        self.receber = criar_movimento(self.fornecedor, faturado=self.faturado)
        self.outra = Pessoa.objects.create(
            documento="11444777000161", razao_social="Outra Empresa Teste"
        )
        self.manutencao = despesa("MANUTENCAO_E_OPERACAO")
        self.vinculo = MovimentoClassificacao.objects.create(
            movimento=self.receber, classificacao=self.manutencao, principal=True
        )

    def estado(self):
        return (
            MovimentoConta.objects.filter(pk=self.receber.pk)
            .values_list("contraparte_id", "faturado_id").get(),
            MovimentoClassificacao.objects.filter(pk=self.vinculo.pk)
            .values_list("movimento_id", "classificacao_id").get(),
        )

    def test_add_remove_clear_e_set_sao_recusados(self):
        original = self.estado()
        infraestrutura = despesa("INFRAESTRUTURA_E_UTILIDADES")
        outro = criar_movimento(self.fornecedor)
        operacoes = {
            "remove": lambda bulk: self.faturado.movimentos_como_faturado.remove(
                self.receber, bulk=bulk),
            "clear": lambda bulk: self.faturado.movimentos_como_faturado.clear(bulk=bulk),
            "set": lambda bulk: self.faturado.movimentos_como_faturado.set([], bulk=bulk),
            "add": lambda bulk: self.outra.movimentos_como_contraparte.add(
                MovimentoConta.objects.get(pk=self.receber.pk), bulk=bulk),
            "add_vinculo": lambda bulk: infraestrutura.movimentos.add(
                MovimentoClassificacao.objects.get(pk=self.vinculo.pk), bulk=bulk),
            "add_no_movimento": lambda bulk: outro.classificacoes.add(
                MovimentoClassificacao.objects.get(pk=self.vinculo.pk), bulk=bulk),
            "set_no_movimento": lambda bulk: outro.classificacoes.set(
                [MovimentoClassificacao.objects.get(pk=self.vinculo.pk)], bulk=bulk),
        }
        for nome, operacao in operacoes.items():
            for bulk in (True, False):
                with self.subTest(operacao=nome, bulk=bulk):
                    # A mensagem é a do gerenciador: com bulk=True, o update()
                    # também recusaria, com outra mensagem.
                    with self.assertRaisesMessage(AlteracaoNaoPermitida, RECUSA_DE_VINCULO):
                        operacao(bulk)
                    # Recusa antes do atomic(savepoint=False) do Django: a
                    # transação de quem chamou segue usável.
                    self.assertFalse(connection.needs_rollback)
                    self.assertEqual(self.estado(), original)

    async def test_versoes_assincronas_dos_reversos_recusam(self):
        movimento = await MovimentoConta.objects.aget(pk=self.receber.pk)
        operacoes = {
            "aadd": lambda: self.outra.movimentos_como_contraparte.aadd(movimento),
            "aremove": lambda: self.faturado.movimentos_como_faturado.aremove(movimento),
            "aclear": lambda: self.faturado.movimentos_como_faturado.aclear(),
            "aset": lambda: self.faturado.movimentos_como_faturado.aset([]),
        }
        for nome, operacao in operacoes.items():
            with self.subTest(operacao=nome):
                with self.assertRaisesMessage(AlteracaoNaoPermitida, RECUSA_DE_VINCULO):
                    await operacao()

    def test_template_nao_chama_os_metodos_recusados(self):
        # alters_data: o template ignora o método em vez de chamá-lo.
        for nome in ("add", "remove", "clear", "set"):
            with self.subTest(metodo=nome):
                self.assertTrue(getattr(self.faturado.movimentos_como_faturado, nome).alters_data)
        saida = Engine().from_string("[{{ p.movimentos_como_faturado.clear }}]").render(
            Context({"p": self.faturado})
        )
        self.assertEqual(saida, "[]")

    def test_create_pelo_gerenciador_reverso_continua_permitido(self):
        infraestrutura = despesa("INFRAESTRUTURA_E_UTILIDADES")

        vinculo = self.receber.classificacoes.create(classificacao=infraestrutura)

        self.assertEqual(vinculo.movimento, self.receber)
        self.assertEqual(self.receber.classificacoes.count(), 2)


class ExclusaoTests(MovimentoBaseTestCase):
    def setUp(self):
        super().setUp()
        self.movimento = self.criar_apagar()
        self.vinculo = MovimentoClassificacao.objects.create(
            movimento=self.movimento, classificacao=despesa(), principal=True
        )

    def test_movimento_nao_e_excluido(self):
        for operacao in (self.movimento.delete, MovimentoConta.objects.all().delete):
            with self.subTest(operacao=operacao):
                with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
                    operacao()
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_vinculo_de_classificacao_nao_e_excluido(self):
        for operacao in (self.vinculo.delete, MovimentoClassificacao.objects.all().delete):
            with self.subTest(operacao=operacao):
                with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
                    operacao()
        self.assertEqual(MovimentoClassificacao.objects.count(), 1)

    def test_excecao_e_uma_exclusao_nao_permitida_dos_cadastros(self):
        with self.assertRaises(ExclusaoNaoPermitida):
            self.movimento.delete()
        self.assertTrue(issubclass(ExclusaoDeMovimentoNaoPermitida, ExclusaoNaoPermitida))


class IntegridadeReferencialTests(MovimentoBaseTestCase):
    def test_banco_impede_excluir_contraparte_com_movimento(self):
        self.criar_apagar()

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM pessoas WHERE id = %s", [self.fornecedor.pk])
            # A FK é DEFERRABLE INITIALLY DEFERRED: a checagem vem no commit.
            connection.check_constraints()

    def test_banco_impede_excluir_faturado_com_movimento(self):
        self.criar_apagar()

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM pessoas WHERE id = %s", [self.faturado.pk])
            connection.check_constraints()

    def test_pessoa_com_movimento_continua_sem_exclusao_pelo_orm(self):
        self.criar_apagar()

        with self.assertRaises(ExclusaoNaoPermitida):
            self.fornecedor.delete()
        self.assertTrue(Pessoa.objects.filter(pk=self.fornecedor.pk).exists())

    def test_banco_recusa_classificacao_de_movimento_inexistente(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovimentoClassificacao.objects.create(
                movimento_id=999999, classificacao=despesa(), principal=True
            )
            connection.check_constraints()

    def test_banco_recusa_movimento_com_contraparte_inexistente(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovimentoConta.objects.create(
                tipo=ARECEBER, origem=OrigemMovimento.MANUAL, contraparte_id=999999,
                valor_total=Decimal("10.00"),
            )
            connection.check_constraints()


class MovimentoClassificacaoTests(MovimentoBaseTestCase):
    def setUp(self):
        super().setUp()
        self.movimento = self.criar_apagar()
        self.manutencao = despesa("MANUTENCAO_E_OPERACAO")
        self.infraestrutura = despesa("INFRAESTRUTURA_E_UTILIDADES")

    def vincular(self, classificacao, principal=False, movimento=None):
        return MovimentoClassificacao.objects.create(
            movimento=movimento or self.movimento, classificacao=classificacao,
            principal=principal,
        )

    def test_principal_e_secundarias_no_mesmo_movimento(self):
        self.vincular(self.manutencao, principal=True)
        self.vincular(self.infraestrutura)
        self.vincular(criar_receita())

        self.assertEqual(self.movimento.classificacoes.count(), 3)
        self.assertEqual(self.movimento.classificacoes.filter(principal=True).count(), 1)
        self.assertEqual(self.movimento.classificacoes.first().classificacao, self.manutencao)

    def test_varias_secundarias_sem_principal_sao_aceitas_pelo_banco(self):
        self.vincular(self.manutencao)
        self.vincular(self.infraestrutura)

        self.assertEqual(self.movimento.classificacoes.filter(principal=False).count(), 2)

    def test_banco_recusa_classificacao_repetida_no_movimento(self):
        self.vincular(self.manutencao, principal=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.vincular(self.manutencao)

    def test_banco_recusa_duas_principais_no_mesmo_movimento(self):
        self.vincular(self.manutencao, principal=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.vincular(self.infraestrutura, principal=True)

    def test_principal_em_movimentos_diferentes(self):
        outro = criar_movimento(self.fornecedor)
        self.vincular(self.manutencao, principal=True)
        self.vincular(self.manutencao, principal=True, movimento=outro)

        self.assertEqual(MovimentoClassificacao.objects.filter(principal=True).count(), 2)

    def test_full_clean_informa_principal_repetida(self):
        self.vincular(self.manutencao, principal=True)
        vinculo = MovimentoClassificacao(
            movimento=self.movimento, classificacao=self.infraestrutura, principal=True
        )

        with self.assertRaises(ValidationError) as contexto:
            vinculo.full_clean()
        self.assertIn(
            "O movimento já tem uma classificação principal.", contexto.exception.messages
        )

    def test_vinculo_gravado_nao_muda(self):
        vinculo = self.vincular(self.manutencao, principal=True)
        outro = criar_movimento(self.fornecedor)
        for campo, valor in (("principal", False), ("classificacao", self.infraestrutura),
                             ("movimento", outro)):
            with self.subTest(campo=campo):
                atual = MovimentoClassificacao.objects.get(pk=vinculo.pk)
                setattr(atual, campo, valor)

                with self.assertRaises(AlteracaoNaoPermitida):
                    atual.save()
        vinculo.refresh_from_db()
        self.assertEqual((vinculo.classificacao, vinculo.principal), (self.manutencao, True))

    def test_update_do_queryset_de_vinculos_e_recusado(self):
        self.vincular(self.infraestrutura)

        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoClassificacao.objects.update(principal=True)
        self.assertFalse(MovimentoClassificacao.objects.filter(principal=True).exists())


class MigrationTests(TestCase):
    def test_tabelas_e_constraints_criadas_pela_migration(self):
        with connection.cursor() as cursor:
            tabelas = connection.introspection.table_names(cursor)
            movimentos = connection.introspection.get_constraints(cursor, "movimentos_contas")
            vinculos = connection.introspection.get_constraints(
                cursor, "movimentos_classificacoes"
            )

        self.assertIn("movimentos_contas", tabelas)
        self.assertIn("movimentos_classificacoes", tabelas)
        for nome in ("movimento_tipo_valido", "movimento_origem_valida",
                     "movimento_status_valido", "movimento_valor_total_positivo",
                     "movimento_apagar_com_faturado"):
            self.assertTrue(movimentos[nome]["check"], nome)
        self.assertTrue(any(c["unique"] and c["columns"] == ["analise_origem_id"]
                            for c in movimentos.values()))

        unica = vinculos["movimento_classificacao_unica"]
        self.assertTrue(unica["unique"])
        self.assertEqual(unica["columns"], ["movimento_id", "classificacao_id"])
        self.assertTrue(vinculos["movimento_uma_classificacao_principal"]["unique"])

    def test_chaves_estrangeiras_criadas_pela_migration(self):
        with connection.cursor() as cursor:
            movimentos = connection.introspection.get_constraints(cursor, "movimentos_contas")
            vinculos = connection.introspection.get_constraints(
                cursor, "movimentos_classificacoes"
            )

        def fks(constraints):
            return {
                tuple(c["columns"]): c["foreign_key"]
                for c in constraints.values() if c["foreign_key"]
            }

        self.assertEqual(fks(movimentos), {
            ("contraparte_id",): ("pessoas", "id"),
            ("faturado_id",): ("pessoas", "id"),
        })
        self.assertEqual(fks(vinculos), {
            ("movimento_id",): ("movimentos_contas", "id"),
            ("classificacao_id",): ("classificacoes", "id"),
        })

    def test_chaves_estrangeiras_sao_protect(self):
        for model, campo in ((MovimentoConta, "contraparte"), (MovimentoConta, "faturado"),
                             (MovimentoClassificacao, "movimento"),
                             (MovimentoClassificacao, "classificacao")):
            with self.subTest(campo=campo):
                self.assertIs(model._meta.get_field(campo).remote_field.on_delete,
                              models.PROTECT)
