"""Parcelas de movimentos (ParcelaConta, GR-38) no PostgreSQL local de teste.

TestCase: rodam só com as variáveis DB_TEST_* (config/banco_de_teste.py). Em
TestCase nada é commitado, então o gatilho diferido da migration 0002 é
disparado com connection.check_constraints() (SET CONSTRAINTS ALL IMMEDIATE)
dentro de transaction.atomic(). O próprio TestCase chama check_constraints()
ao terminar cada teste: todo teste precisa deixar o banco coerente (movimento
CONFIRMADO com parcelas ATIVAS que somam o valor total), senão falha no
teardown. Os TransactionTestCase usam o COMMIT real e serialized_rollback=True
para que o flush ao terminar não apague a carga de classificações. Documentos
fictícios, os mesmos de test_servicos.py; nenhum dado real.
"""

import threading
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase, TransactionTestCase

from cadastros.models import Papel

from .models import (
    AlteracaoNaoPermitida, ExclusaoDeMovimentoNaoPermitida, MovimentoClassificacao,
    MovimentoConta, OrigemMovimento, ParcelaConta, StatusMovimento, StatusParcela,
    TipoMovimento,
)
from .servicos import MAXIMO_DE_PARCELAS, ItemClassificacao, ItemParcela, registrar_movimento
from .test_servicos import DadosDeServico, ServicoTestBase

VENCIMENTOS = (date(2026, 11, 30), date(2026, 12, 30), date(2027, 1, 30), date(2027, 3, 1))
RECUSA_DE_VINCULO = "Os vínculos de um registro financeiro não podem ser trocados."
SEM_PARCELA_ATIVA = "movimento_com_parcela_ativa"
SOMA_DAS_PARCELAS = "movimento_soma_das_parcelas"
# Tempo máximo de espera por uma thread: além disso, consideramos travada.
TEMPO_LIMITE = 30


def parcelas(*valores):
    """ItemParcela numeradas de 1 a n, com vencimentos mensais."""
    return tuple(
        ItemParcela(numero, VENCIMENTOS[numero - 1], Decimal(valor))
        for numero, valor in enumerate(valores, start=1)
    )


def restricao_violada(erro):
    """Nome da constraint que o PostgreSQL informou no erro (diag do psycopg)."""
    return erro.__cause__.diag.constraint_name


def estado_sql(erro):
    """SQLSTATE do erro: 23502 NOT NULL, 23505 unique, 23514 check."""
    return erro.__cause__.sqlstate


def sql(comando, parametros=()):
    with connection.cursor() as cursor:
        cursor.execute(comando, parametros)


class ParcelasTestBase(ServicoTestBase):
    def movimento_pelo_orm(self, valor_total=Decimal("100.00"), **campos):
        """Movimento gravado direto, sem parcelas: completar antes do fim do teste."""
        return MovimentoConta.objects.create(
            tipo=TipoMovimento.ARECEBER, origem=OrigemMovimento.MANUAL,
            contraparte=self.cliente, valor_total=valor_total, **campos,
        )

    def parcela(self, movimento, numero=1, valor=Decimal("100.00"), **campos):
        campos.setdefault("data_vencimento", VENCIMENTOS[numero - 1])
        # A parcela nasce ATIVA (gatilho); o cancelamento, ainda sem operação
        # própria, é simulado por SQL direto.
        cancelada = campos.get("status") == StatusParcela.CANCELADA
        if cancelada:
            del campos["status"]
        parcela = ParcelaConta.objects.create(
            movimento=movimento, numero=numero, valor=valor, **campos
        )
        if cancelada:
            sql("UPDATE parcelas_contas SET status = 'CANCELADA' WHERE id = %s", [parcela.pk])
            parcela.refresh_from_db()
        return parcela

    def lancamento_pelo_orm(self, valor=Decimal("100.00")):
        """Movimento e parcela única coerentes, sem passar pelo serviço."""
        movimento = self.movimento_pelo_orm(valor_total=valor)
        self.parcela(movimento, valor=valor)
        return movimento

    def assert_recusado_no_commit(self, operacao, restricao):
        """A operação passa, mas o gatilho diferido recusa ao conferir."""
        with self.assertRaises(IntegrityError) as contexto, transaction.atomic():
            operacao()
            connection.check_constraints()
        self.assertEqual(restricao_violada(contexto.exception), restricao)

    def assert_recusado_sem_parcelas(self, dados, codigo):
        self.assert_recusado(dados, codigo)
        self.assertEqual(ParcelaConta.objects.count(), 0)


class RegistroComParcelasTests(ParcelasTestBase):
    def test_parcela_unica_com_o_valor_total(self):
        dados = self.apagar()

        movimento, criado = registrar_movimento(dados)

        self.assertTrue(criado)
        parcela = movimento.parcelas.get()
        self.assertEqual((parcela.numero, parcela.data_vencimento, parcela.valor),
                         (1, dados.parcelas[0].data_vencimento, Decimal("1250.40")))
        self.assertEqual(parcela.status, StatusParcela.ATIVA)
        self.assertIsInstance(parcela.identificador, uuid.UUID)
        self.assertIsNotNone(parcela.criado_em)
        connection.check_constraints()

    def test_varias_parcelas_com_vencimentos_distintos(self):
        itens = parcelas("400.00", "400.00", "450.40")

        movimento, _ = registrar_movimento(self.apagar(parcelas=itens))

        gravadas = list(movimento.parcelas.values_list("numero", "data_vencimento", "valor"))
        self.assertEqual(gravadas, [(p.numero, p.data_vencimento, p.valor) for p in itens])
        self.assertEqual(len({p.identificador for p in movimento.parcelas.all()}), 3)
        self.assertEqual(movimento.parcelas.ativas().count(), 3)
        connection.check_constraints()

    def test_conta_a_receber_com_parcelas(self):
        itens = parcelas("300.00", "600.00")

        movimento, _ = registrar_movimento(self.areceber(parcelas=itens))

        self.assertEqual(list(movimento.parcelas.values_list("numero", "data_vencimento", "valor")),
                         [(p.numero, p.data_vencimento, p.valor) for p in itens])
        connection.check_constraints()

    def test_parcelas_fora_de_ordem_sao_gravadas_por_numero(self):
        itens = parcelas("400.00", "400.00", "450.40")

        movimento, _ = registrar_movimento(self.apagar(parcelas=(itens[2], itens[0], itens[1])))

        self.assertEqual(list(movimento.parcelas.values_list("numero", "data_vencimento", "valor")),
                         [(p.numero, p.data_vencimento, p.valor) for p in itens])

    def test_parcelas_em_gerador_sao_validadas_e_gravadas(self):
        itens = (item for item in parcelas("625.20", "625.20"))

        movimento, criado = registrar_movimento(self.apagar(parcelas=itens))

        self.assertTrue(criado)
        self.assertEqual(movimento.parcelas.count(), 2)
        connection.check_constraints()

    def test_valores_limite_da_parcela(self):
        for valor in (Decimal("0.01"), Decimal("9999999999.99")):
            with self.subTest(valor=valor):
                movimento, _ = registrar_movimento(self.apagar(valor_total=valor))
                self.assertEqual(movimento.parcelas.get().valor, valor)


class ParcelasInvalidasTests(ParcelasTestBase):
    def test_sem_parcela(self):
        self.assert_recusado_sem_parcelas(self.apagar(parcelas=()), "sem_parcela")
        self.assert_recusado_sem_parcelas(self.areceber(parcelas=[]), "sem_parcela")

    def test_no_maximo_120_parcelas(self):
        def lancamento(quantidade):
            itens = tuple(ItemParcela(n, VENCIMENTOS[0], Decimal("0.01"))
                          for n in range(1, quantidade + 1))
            return self.apagar(valor_total=Decimal("0.01") * quantidade, parcelas=itens)

        # 32768 estouraria o smallint de numero (DataError) sem o teto.
        for quantidade in (MAXIMO_DE_PARCELAS + 1, 32768):
            with self.subTest(quantidade=quantidade):
                self.assert_recusado_sem_parcelas(lancamento(quantidade), "parcela_quantidade")
        movimento, _ = registrar_movimento(lancamento(MAXIMO_DE_PARCELAS))
        self.assertEqual(movimento.parcelas.count(), 120)
        connection.check_constraints()

    def test_parcelas_que_nao_sao_sequencia_sao_recusadas(self):
        for valor in (None, 1, ItemParcela(1, VENCIMENTOS[0], Decimal("1250.40"))):
            with self.subTest(parcelas=valor):
                self.assert_recusado_sem_parcelas(self.apagar(parcelas=valor), "parcela")

    def test_itens_precisam_ser_item_parcela(self):
        for item in (
            {"numero": 1, "data_vencimento": VENCIMENTOS[0], "valor": Decimal("1250.40")},
            (1, VENCIMENTOS[0], Decimal("1250.40")),
            Decimal("1250.40"),
            ItemClassificacao(self.manutencao, principal=True),
        ):
            with self.subTest(item=item):
                self.assert_recusado_sem_parcelas(self.apagar(parcelas=(item,)), "parcela")

    def test_numero_precisa_ser_inteiro_positivo(self):
        # True é int em Python e "1" seria convertido pelo ORM: os dois são recusados.
        for numero in (0, -1, True, "1", 1.0, None):
            with self.subTest(numero=numero):
                item = ItemParcela(numero, VENCIMENTOS[0], Decimal("1250.40"))
                self.assert_recusado_sem_parcelas(self.apagar(parcelas=(item,)),
                                                  "parcela_numero")

    def test_vencimento_precisa_ser_data(self):
        # datetime é subclasse de date, mas o DateField descartaria a hora.
        for vencimento in (None, "2026-11-30", datetime(2026, 11, 30, 10, 0)):
            with self.subTest(vencimento=vencimento):
                item = ItemParcela(1, vencimento, Decimal("1250.40"))
                self.assert_recusado_sem_parcelas(self.apagar(parcelas=(item,)),
                                                  "parcela_vencimento")

    def test_valor_invalido_da_parcela(self):
        for valor, codigo in (
            (1250.40, "parcela_valor_tipo"), (1250, "parcela_valor_tipo"),
            ("1250.40", "parcela_valor_tipo"), (None, "parcela_valor_tipo"),
            (Decimal("NaN"), "parcela_valor_tipo"), (Decimal("Infinity"), "parcela_valor_tipo"),
            (Decimal("0"), "parcela_valor"), (Decimal("-1.00"), "parcela_valor"),
            (Decimal("10000000000.00"), "parcela_valor"),
            (Decimal("1250.401"), "parcela_valor_centavos"),
        ):
            with self.subTest(valor=valor):
                item = ItemParcela(1, VENCIMENTOS[0], valor)
                self.assert_recusado_sem_parcelas(self.apagar(parcelas=(item,)), codigo)

    def test_valor_invalido_em_uma_das_parcelas(self):
        itens = parcelas("1250.40", "0")

        self.assert_recusado_sem_parcelas(self.apagar(parcelas=itens), "parcela_valor")

    def test_numero_repetido(self):
        itens = (ItemParcela(1, VENCIMENTOS[0], Decimal("625.20")),
                 ItemParcela(1, VENCIMENTOS[1], Decimal("625.20")))

        self.assert_recusado_sem_parcelas(self.apagar(parcelas=itens), "parcela_repetida")

    def test_numeracao_com_lacuna_ou_fora_do_inicio(self):
        for numeros in ((1, 3), (2,), (2, 3), (1, 2, 4)):
            with self.subTest(numeros=numeros):
                valor = Decimal("1250.40") / len(numeros)
                itens = tuple(
                    ItemParcela(n, VENCIMENTOS[i], valor.quantize(Decimal("0.01")))
                    for i, n in enumerate(numeros)
                )
                total = sum(item.valor for item in itens)
                self.assert_recusado_sem_parcelas(
                    self.apagar(valor_total=total, parcelas=itens), "parcela_numeracao"
                )

    def test_soma_diferente_do_valor_total(self):
        for itens in (
            parcelas("1250.41"), parcelas("1250.39"),
            parcelas("625.20", "625.21"), parcelas("625.20", "625.19"),
            parcelas("400.00", "400.00", "400.00"),
        ):
            with self.subTest(parcelas=[str(p.valor) for p in itens]):
                self.assert_recusado_sem_parcelas(self.apagar(parcelas=itens), "parcela_soma")

    def test_classificacao_invalida_tambem_nao_grava_parcelas(self):
        self.assert_recusado_sem_parcelas(self.apagar(classificacoes=()), "sem_classificacao")
        self.assert_recusado_sem_parcelas(self.apagar(contraparte=self.cliente), "papel_ausente")


class IdempotenciaComParcelasTests(ParcelasTestBase):
    def setUp(self):
        super().setUp()
        self.analise = uuid.uuid4()
        self.itens = parcelas("600.00", "650.40")
        self.existente, _ = registrar_movimento(
            self.apagar(analise_origem_id=self.analise, parcelas=self.itens)
        )

    def assert_analise_recusada(self, itens):
        with self.assertRaises(ValidationError) as contexto:
            registrar_movimento(self.apagar(analise_origem_id=self.analise, parcelas=itens))
        self.assertEqual(contexto.exception.code, "analise_ja_lancada")
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(ParcelaConta.objects.count(), 2)

    def test_mesmas_parcelas_devolvem_o_existente_sem_duplicar(self):
        for itens in (self.itens, (self.itens[1], self.itens[0]), (p for p in self.itens)):
            with self.subTest(itens=itens):
                movimento, criado = registrar_movimento(
                    self.apagar(analise_origem_id=self.analise, parcelas=itens)
                )
                self.assertFalse(criado)
                self.assertEqual(movimento.pk, self.existente.pk)
                self.assertEqual(ParcelaConta.objects.count(), 2)
                self.assertEqual(MovimentoClassificacao.objects.count(), 1)

    def test_valor_redistribuido_com_o_mesmo_total_e_recusado(self):
        self.assert_analise_recusada(parcelas("625.20", "625.20"))

    def test_vencimento_diferente_e_recusado(self):
        alterado = (self.itens[0], ItemParcela(2, VENCIMENTOS[3], Decimal("650.40")))

        self.assert_analise_recusada(alterado)

    def test_parcela_cancelada_nao_entra_na_comparacao(self):
        # Estado futuro (cancelamento ainda sem operação): uma parcela extra,
        # cancelada por SQL, não muda as parcelas ATIVAS do lançamento.
        self.parcela(self.existente, 3, Decimal("10.00"), status=StatusParcela.CANCELADA)

        movimento, criado = registrar_movimento(
            self.apagar(analise_origem_id=self.analise, parcelas=self.itens)
        )

        self.assertFalse(criado)
        self.assertEqual(movimento.pk, self.existente.pk)
        self.assertEqual(self.existente.parcelas.ativas().count(), 2)

    def test_outra_quantidade_de_parcelas_e_recusada(self):
        self.assert_analise_recusada(parcelas("1250.40"))
        self.assert_analise_recusada(parcelas("400.00", "400.00", "450.40"))


class AtomicidadeComParcelasTests(ParcelasTestBase):
    def test_falha_nas_parcelas_nao_deixa_movimento_nem_vinculos(self):
        for analise in (None, uuid.uuid4()):
            with self.subTest(analise=analise):
                with mock.patch.object(
                    ParcelaConta.objects, "bulk_create", side_effect=IntegrityError("falha")
                ):
                    with self.assertRaises(IntegrityError):
                        registrar_movimento(self.apagar(analise_origem_id=analise,
                                                        parcelas=parcelas("600.00", "650.40")))

                self.assertEqual(MovimentoConta.objects.count(), 0)
                self.assertEqual(MovimentoClassificacao.objects.count(), 0)
                self.assertEqual(ParcelaConta.objects.count(), 0)

    def test_falha_nas_parcelas_nao_apaga_lancamento_anterior(self):
        anterior, _ = registrar_movimento(self.apagar())

        with mock.patch.object(
            ParcelaConta.objects, "bulk_create", side_effect=IntegrityError("falha")
        ):
            with self.assertRaises(IntegrityError):
                registrar_movimento(self.apagar())

        self.assertEqual(list(MovimentoConta.objects.values_list("pk", flat=True)), [anterior.pk])
        self.assertEqual(ParcelaConta.objects.count(), 1)


class GatilhoDasParcelasTests(ParcelasTestBase):
    """Gatilho diferido: a regra vale para qualquer caminho de escrita."""

    def test_lancamento_coerente_pelo_orm_e_aceito(self):
        movimento = self.movimento_pelo_orm(valor_total=Decimal("100.00"))
        self.parcela(movimento, 1, Decimal("30.00"))
        self.parcela(movimento, 2, Decimal("70.00"))

        connection.check_constraints()

    def test_movimento_pelo_orm_sem_parcela_e_recusado(self):
        self.assert_recusado_no_commit(self.movimento_pelo_orm, SEM_PARCELA_ATIVA)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_movimento_com_soma_menor_ou_maior_e_recusado(self):
        for valores in (("40.00",), ("40.00", "59.99"), ("100.01",), ("60.00", "40.01")):
            with self.subTest(valores=valores):
                def lancar():
                    movimento = self.movimento_pelo_orm(valor_total=Decimal("100.00"))
                    for numero, valor in enumerate(valores, start=1):
                        self.parcela(movimento, numero, Decimal(valor))

                self.assert_recusado_no_commit(lancar, SOMA_DAS_PARCELAS)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_parcela_a_mais_no_lancamento_do_servico_e_recusada(self):
        movimento, _ = registrar_movimento(self.apagar())

        self.assert_recusado_no_commit(
            lambda: self.parcela(movimento, 2, Decimal("10.00")), SOMA_DAS_PARCELAS
        )
        self.assertEqual(movimento.parcelas.count(), 1)

    def test_parcela_cancelada_nao_conta_na_soma(self):
        def lancar():
            movimento = self.movimento_pelo_orm(valor_total=Decimal("100.00"))
            self.parcela(movimento, 1, Decimal("60.00"))
            self.parcela(movimento, 2, Decimal("40.00"), status=StatusParcela.CANCELADA)

        self.assert_recusado_no_commit(lancar, SOMA_DAS_PARCELAS)

        movimento = self.movimento_pelo_orm(valor_total=Decimal("100.00"))
        self.parcela(movimento, 1, Decimal("100.00"))
        self.parcela(movimento, 2, Decimal("40.00"), status=StatusParcela.CANCELADA)
        connection.check_constraints()

    def test_so_parcelas_canceladas_e_recusado(self):
        def lancar():
            movimento = self.movimento_pelo_orm(valor_total=Decimal("100.00"))
            self.parcela(movimento, 1, Decimal("100.00"), status=StatusParcela.CANCELADA)

        self.assert_recusado_no_commit(lancar, SEM_PARCELA_ATIVA)

    def test_parcela_nova_cancelada_e_recusada(self):
        # Acrescentar uma parcela CANCELADA não muda a soma, mas anteciparia um
        # cancelamento que ainda não tem contrato.
        movimento = self.lancamento_pelo_orm()

        self.assert_recusado_no_commit(
            lambda: ParcelaConta.objects.create(
                movimento=movimento, numero=2, data_vencimento=VENCIMENTOS[1],
                valor=Decimal("50.00"), status=StatusParcela.CANCELADA,
            ),
            "parcela_nasce_ativa",
        )
        self.assertEqual(movimento.parcelas.count(), 1)

    def test_tabela_temporaria_homonima_nao_engana_o_gatilho(self):
        def operacao():
            movimento = self.movimento_pelo_orm()
            sql("CREATE TEMP TABLE parcelas_contas"
                " (movimento_id bigint, status varchar, valor numeric)")
            sql("INSERT INTO pg_temp.parcelas_contas VALUES (%s, 'ATIVA', 100.00)",
                [movimento.pk])
            # Sem o plano já guardado pela sessão, a função resolve os nomes de novo.
            sql("DISCARD PLANS")

        self.assert_recusado_no_commit(operacao, SEM_PARCELA_ATIVA)

    def test_movimento_cancelado_sem_parcelas_e_aceito(self):
        self.movimento_pelo_orm(status=StatusMovimento.CANCELADO)

        connection.check_constraints()

    def test_cancelar_por_sql_libera_a_conferencia(self):
        # O cancelamento ainda não existe: simula o estado futuro direto no banco.
        movimento, _ = registrar_movimento(self.apagar())
        sql("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s", [movimento.pk])
        sql("DELETE FROM parcelas_contas WHERE movimento_id = %s", [movimento.pk])

        connection.check_constraints()
        self.assertEqual(ParcelaConta.objects.count(), 0)

    def test_reconfirmar_por_sql_sem_parcela_e_recusado(self):
        movimento = self.movimento_pelo_orm(status=StatusMovimento.CANCELADO)

        self.assert_recusado_no_commit(
            lambda: sql("UPDATE movimentos_contas SET status = 'CONFIRMADO' WHERE id = %s",
                        [movimento.pk]),
            SEM_PARCELA_ATIVA,
        )

    def test_sql_direto_nas_parcelas_que_quebra_a_soma_e_recusado(self):
        movimento, _ = registrar_movimento(self.apagar(parcelas=parcelas("600.00", "650.40")))
        primeira, segunda = movimento.parcelas.order_by("numero")
        comandos = {
            "valor": ("UPDATE parcelas_contas SET valor = valor - 0.01 WHERE id = %s",
                      [primeira.pk], SOMA_DAS_PARCELAS),
            "delete_uma": ("DELETE FROM parcelas_contas WHERE id = %s",
                           [segunda.pk], SOMA_DAS_PARCELAS),
            "cancelar_uma": ("UPDATE parcelas_contas SET status = 'CANCELADA' WHERE id = %s",
                             [segunda.pk], SOMA_DAS_PARCELAS),
            "delete_todas": ("DELETE FROM parcelas_contas WHERE movimento_id = %s",
                             [movimento.pk], SEM_PARCELA_ATIVA),
            "cancelar_todas": (
                "UPDATE parcelas_contas SET status = 'CANCELADA' WHERE movimento_id = %s",
                [movimento.pk], SEM_PARCELA_ATIVA,
            ),
        }
        for nome, (comando, parametros, restricao) in comandos.items():
            with self.subTest(comando=nome):
                self.assert_recusado_no_commit(
                    lambda comando=comando, parametros=parametros: sql(comando, parametros),
                    restricao,
                )
        self.assertEqual(movimento.parcelas.ativas().count(), 2)

    def test_sql_direto_no_valor_total_e_recusado(self):
        movimento, _ = registrar_movimento(self.apagar())

        self.assert_recusado_no_commit(
            lambda: sql("UPDATE movimentos_contas SET valor_total = 1250.41 WHERE id = %s",
                        [movimento.pk]),
            SOMA_DAS_PARCELAS,
        )

    def test_mover_parcela_para_outro_movimento_e_recusado(self):
        # O gatilho confere o movimento antigo (OLD) e o novo (NEW). Outro
        # número: com o mesmo, a unicidade (imediata) recusaria antes do gatilho.
        origem = self.lancamento_pelo_orm()
        destino = self.lancamento_pelo_orm()
        parcela = origem.parcelas.get()

        self.assert_recusado_no_commit(
            lambda: sql("UPDATE parcelas_contas SET movimento_id = %s, numero = 2 WHERE id = %s",
                        [destino.pk, parcela.pk]),
            SEM_PARCELA_ATIVA,
        )

    def test_gatilhos_e_funcoes_existem_e_sao_diferidos(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname, c.relname, t.tgdeferrable, t.tginitdeferred"
                " FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
                " WHERE t.tgname IN ('movimento_confere_parcelas', 'parcela_confere_movimento')"
            )
            gatilhos = set(cursor.fetchall())
            cursor.execute(
                "SELECT proname FROM pg_proc WHERE proname IN"
                " ('financeiro_conferir_parcelas', 'financeiro_gatilho_parcelas')"
            )
            funcoes = {linha[0] for linha in cursor.fetchall()}

        self.assertEqual(gatilhos, {
            ("movimento_confere_parcelas", "movimentos_contas", True, True),
            ("parcela_confere_movimento", "parcelas_contas", True, True),
        })
        self.assertEqual(funcoes, {"financeiro_conferir_parcelas", "financeiro_gatilho_parcelas"})


class ConstraintsDaParcelaTests(ParcelasTestBase):
    def setUp(self):
        super().setUp()
        self.movimento = self.lancamento_pelo_orm()

    def assert_banco_recusa(self, restricao=None, sqlstate=None, **campos):
        campos.setdefault("numero", 2)
        with self.assertRaises(IntegrityError) as contexto, transaction.atomic():
            self.parcela(self.movimento, **campos)
        if restricao:
            self.assertEqual(restricao_violada(contexto.exception), restricao)
        if sqlstate:
            self.assertEqual(estado_sql(contexto.exception), sqlstate)
        self.assertEqual(ParcelaConta.objects.count(), 1)

    def test_banco_recusa_numero_zero(self):
        self.assert_banco_recusa("parcela_numero_positivo", numero=0,
                                 data_vencimento=VENCIMENTOS[0])

    def test_banco_recusa_numero_repetido_no_movimento(self):
        self.assert_banco_recusa("parcela_numero_unico_no_movimento", numero=1)

    def test_mesmo_numero_em_movimentos_diferentes(self):
        outro = self.lancamento_pelo_orm()

        self.assertEqual(outro.parcelas.get().numero, self.movimento.parcelas.get().numero)

    def test_banco_recusa_valor_zero_ou_negativo(self):
        for valor in (Decimal("0"), Decimal("-0.01"), Decimal("-100.00")):
            with self.subTest(valor=valor):
                self.assert_banco_recusa("parcela_valor_positivo", valor=valor)

    def test_banco_recusa_status_invalido(self):
        self.assert_banco_recusa("parcela_status_valido", status="PAGA")

    def test_banco_recusa_parcela_sem_vencimento(self):
        self.assert_banco_recusa(sqlstate="23502", data_vencimento=None)

    def test_banco_recusa_identificador_repetido(self):
        existente = self.movimento.parcelas.get()

        self.assert_banco_recusa(sqlstate="23505", identificador=existente.identificador)

    def test_valores_nos_limites_sao_aceitos(self):
        for valor in (Decimal("0.01"), Decimal("9999999999.99")):
            with self.subTest(valor=valor):
                parcela = self.lancamento_pelo_orm(valor).parcelas.get()
                parcela.refresh_from_db()
                self.assertEqual(parcela.valor, valor)
        connection.check_constraints()

    def test_status_padrao_e_ativa(self):
        self.assertEqual(self.movimento.parcelas.get().status, StatusParcela.ATIVA)
        self.assertEqual(ParcelaConta.objects.ativas().count(), 1)

    def test_full_clean_informa_numero_repetido_e_valor_invalido(self):
        parcela = ParcelaConta(movimento=self.movimento, numero=1,
                               data_vencimento=VENCIMENTOS[0], valor=Decimal("0"))

        with self.assertRaises(ValidationError) as contexto:
            parcela.full_clean()
        self.assertIn("Este número de parcela já existe no movimento.",
                      contexto.exception.messages)
        self.assertIn("O valor da parcela deve ser maior que zero e menor que R$ 10 bilhões.",
                      contexto.exception.messages)


class IntegridadeReferencialDaParcelaTests(ParcelasTestBase):
    def fk_das_parcelas(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "parcelas_contas")
        return next(nome for nome, c in constraints.items()
                    if c["foreign_key"] and c["columns"] == ["movimento_id"])

    def test_banco_impede_excluir_movimento_com_parcelas(self):
        # Sem classificações: a única FK que aponta para o movimento é a da parcela.
        movimento = self.lancamento_pelo_orm()

        # A FK é DEFERRABLE INITIALLY DEFERRED: a checagem vem no commit.
        self.assert_recusado_no_commit(
            lambda: sql("DELETE FROM movimentos_contas WHERE id = %s", [movimento.pk]),
            self.fk_das_parcelas(),
        )
        self.assertTrue(MovimentoConta.objects.filter(pk=movimento.pk).exists())

    def test_banco_recusa_parcela_de_movimento_inexistente(self):
        self.assert_recusado_no_commit(
            lambda: ParcelaConta.objects.create(
                movimento_id=999_999, numero=1, data_vencimento=VENCIMENTOS[0],
                valor=Decimal("10.00"),
            ),
            self.fk_das_parcelas(),
        )

    def test_movimento_com_parcelas_nao_e_excluido_pelo_orm(self):
        movimento = self.lancamento_pelo_orm()

        with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
            movimento.delete()
        self.assertEqual(ParcelaConta.objects.count(), 1)


class ImutabilidadeDaParcelaTests(ParcelasTestBase):
    def setUp(self):
        super().setUp()
        self.movimento, _ = registrar_movimento(
            self.apagar(parcelas=parcelas("600.00", "650.40"))
        )
        self.outro, _ = registrar_movimento(self.areceber())
        self.parcela = self.movimento.parcelas.get(numero=1)

    def estado_no_banco(self):
        return list(ParcelaConta.objects.order_by("pk").values(
            "pk", *ParcelaConta.campos_imutaveis
        ))

    def test_alteracao_de_campo_essencial_e_recusada(self):
        original = self.estado_no_banco()
        alteracoes = {
            "identificador": uuid.uuid4(),
            "movimento": self.outro,
            "numero": 3,
            "data_vencimento": VENCIMENTOS[3],
            "valor": Decimal("1.00"),
            "status": StatusParcela.CANCELADA,
            "criado_em": self.parcela.criado_em.replace(year=2000),
        }
        for campo, valor in alteracoes.items():
            with self.subTest(campo=campo):
                parcela = ParcelaConta.objects.get(pk=self.parcela.pk)
                setattr(parcela, campo, valor)

                with self.assertRaises(AlteracaoNaoPermitida) as contexto:
                    parcela.save()
                self.assertEqual(contexto.exception.code, "campo_imutavel")
                self.assertIn(campo, contexto.exception.messages[0])
                self.assertEqual(self.estado_no_banco(), original)

    def test_salvar_sem_alteracoes_funciona(self):
        parcela = ParcelaConta.objects.get(pk=self.parcela.pk)
        parcela.valor = "600.00"

        parcela.save()

        self.assertEqual(ParcelaConta.objects.get(pk=self.parcela.pk).valor, Decimal("600.00"))

    def test_update_bulk_update_e_upsert_sao_recusados(self):
        original = self.estado_no_banco()
        parcela = ParcelaConta.objects.get(pk=self.parcela.pk)
        parcela.valor = Decimal("1.00")
        copia = ParcelaConta(movimento=self.movimento, numero=1,
                             data_vencimento=VENCIMENTOS[0], valor=Decimal("1.00"))
        operacoes = {
            "update_valor": lambda: ParcelaConta.objects.filter(pk=parcela.pk).update(
                valor=Decimal("1.00")),
            "update_status": lambda: ParcelaConta.objects.update(
                status=StatusParcela.CANCELADA),
            "update_movimento": lambda: ParcelaConta.objects.update(movimento_id=self.outro.pk),
            "bulk_update": lambda: ParcelaConta.objects.bulk_update([parcela], ["valor"]),
            "upsert": lambda: ParcelaConta.objects.bulk_create(
                [copia], update_conflicts=True, unique_fields=["movimento", "numero"],
                update_fields=["valor"],
            ),
            "base_manager": lambda: ParcelaConta._base_manager.filter(pk=parcela.pk).update(
                data_vencimento=VENCIMENTOS[3]),
        }
        for nome, operacao in operacoes.items():
            with self.subTest(operacao=nome):
                with self.assertRaises(AlteracaoNaoPermitida):
                    operacao()
                self.assertFalse(connection.needs_rollback)
                self.assertEqual(self.estado_no_banco(), original)

    def test_objeto_novo_com_pk_existente_e_recusado(self):
        impostor = ParcelaConta(pk=self.parcela.pk, movimento=self.outro, numero=1,
                                data_vencimento=VENCIMENTOS[0], valor=Decimal("900.00"))

        with self.assertRaises(AlteracaoNaoPermitida) as contexto:
            impostor.save()
        self.assertEqual(contexto.exception.code, "registro_existente")
        self.assertEqual(ParcelaConta.objects.get(pk=self.parcela.pk).movimento_id,
                         self.movimento.pk)

    def test_parcela_nao_e_excluida(self):
        for operacao in (self.parcela.delete, ParcelaConta.objects.all().delete,
                         ParcelaConta._base_manager.all().delete,
                         self.movimento.parcelas.all().delete):
            with self.subTest(operacao=operacao):
                with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
                    operacao()
        self.assertEqual(ParcelaConta.objects.count(), 3)

    def test_gerenciador_reverso_nao_troca_o_movimento(self):
        original = self.estado_no_banco()
        operacoes = {
            "add": lambda bulk: self.outro.parcelas.add(
                ParcelaConta.objects.get(pk=self.parcela.pk), bulk=bulk),
            "set": lambda bulk: self.outro.parcelas.set(
                [ParcelaConta.objects.get(pk=self.parcela.pk)], bulk=bulk),
        }
        for nome, operacao in operacoes.items():
            for bulk in (True, False):
                with self.subTest(operacao=nome, bulk=bulk):
                    with self.assertRaisesMessage(AlteracaoNaoPermitida, RECUSA_DE_VINCULO):
                        operacao(bulk)
                    self.assertFalse(connection.needs_rollback)
                    self.assertEqual(self.estado_no_banco(), original)

    def test_fk_obrigatoria_nao_tem_remove_nem_clear(self):
        # O Django só cria remove() e clear() no reverso de uma FK que aceita nulo.
        for nome in ("remove", "clear"):
            with self.subTest(metodo=nome):
                self.assertFalse(hasattr(self.movimento.parcelas, nome))

    async def test_versoes_assincronas_recusam(self):
        parcela = await ParcelaConta.objects.aget(pk=self.parcela.pk)
        parcela.valor = Decimal("1.00")

        with self.assertRaises(AlteracaoNaoPermitida):
            await parcela.asave()
        with self.assertRaises(AlteracaoNaoPermitida):
            await ParcelaConta.objects.filter(pk=parcela.pk).aupdate(valor=Decimal("1.00"))
        with self.assertRaises(AlteracaoNaoPermitida):
            await self.outro.parcelas.aadd(parcela)


class MigrationDasParcelasTests(TestCase):
    def test_tabela_e_constraints_criadas_pela_migration(self):
        with connection.cursor() as cursor:
            tabelas = connection.introspection.table_names(cursor)
            constraints = connection.introspection.get_constraints(cursor, "parcelas_contas")

        self.assertIn("parcelas_contas", tabelas)
        for nome in ("parcela_numero_positivo", "parcela_valor_positivo",
                     "parcela_status_valido"):
            self.assertTrue(constraints[nome]["check"], nome)
        unica = constraints["parcela_numero_unico_no_movimento"]
        self.assertTrue(unica["unique"])
        self.assertEqual(unica["columns"], ["movimento_id", "numero"])
        self.assertTrue(any(c["unique"] and c["columns"] == ["identificador"]
                            for c in constraints.values()))

    def test_chave_estrangeira_para_movimentos(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "parcelas_contas")

        fks = {tuple(c["columns"]): c["foreign_key"]
               for c in constraints.values() if c["foreign_key"]}
        self.assertEqual(fks, {("movimento_id",): ("movimentos_contas", "id")})
        campo = ParcelaConta._meta.get_field("movimento")
        self.assertIs(campo.remote_field.on_delete, models.PROTECT)
        self.assertEqual(campo.remote_field.related_name, "parcelas")


class AutocommitComParcelasTests(DadosDeServico, TransactionTestCase):
    """COMMIT real: sem transação externa, o gatilho confere no fim de cada comando."""

    serialized_rollback = True

    def test_servico_grava_parcelas_fora_de_transacao(self):
        self.assertFalse(connection.in_atomic_block)

        movimento, criado = registrar_movimento(
            self.apagar(parcelas=parcelas("600.00", "650.40"))
        )

        self.assertTrue(criado)
        self.assertEqual(movimento.parcelas.count(), 2)

    def test_movimento_pelo_orm_sem_parcela_nao_e_commitado(self):
        with self.assertRaises(IntegrityError) as contexto:
            MovimentoConta.objects.create(
                tipo=TipoMovimento.ARECEBER, origem=OrigemMovimento.MANUAL,
                contraparte=self.cliente, valor_total=Decimal("100.00"),
            )

        self.assertEqual(restricao_violada(contexto.exception), SEM_PARCELA_ATIVA)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_transacao_com_soma_errada_nao_e_commitada(self):
        with self.assertRaises(IntegrityError) as contexto:
            with transaction.atomic():
                movimento = MovimentoConta.objects.create(
                    tipo=TipoMovimento.ARECEBER, origem=OrigemMovimento.MANUAL,
                    contraparte=self.cliente, valor_total=Decimal("100.00"),
                )
                ParcelaConta.objects.create(movimento=movimento, numero=1,
                                            data_vencimento=VENCIMENTOS[0],
                                            valor=Decimal("99.99"))

        self.assertEqual(restricao_violada(contexto.exception), SOMA_DAS_PARCELAS)
        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertEqual(ParcelaConta.objects.count(), 0)

    def test_transacao_coerente_pelo_orm_e_commitada(self):
        with transaction.atomic():
            movimento = MovimentoConta.objects.create(
                tipo=TipoMovimento.ARECEBER, origem=OrigemMovimento.MANUAL,
                contraparte=self.cliente, valor_total=Decimal("100.00"),
            )
            ParcelaConta.objects.create(movimento=movimento, numero=1,
                                        data_vencimento=VENCIMENTOS[0], valor=Decimal("100.00"))

        self.assertEqual(MovimentoConta.objects.get().parcelas.count(), 1)

    def test_sql_direto_que_quebra_a_soma_nao_e_commitado(self):
        movimento, _ = registrar_movimento(self.apagar(parcelas=parcelas("600.00", "650.40")))
        segunda = movimento.parcelas.get(numero=2)

        for comando in ("DELETE FROM parcelas_contas WHERE id = %s",
                        "UPDATE parcelas_contas SET valor = 1.00 WHERE id = %s"):
            with self.subTest(comando=comando):
                with self.assertRaises(IntegrityError) as contexto:
                    sql(comando, [segunda.pk])
                self.assertEqual(restricao_violada(contexto.exception), SOMA_DAS_PARCELAS)
        self.assertEqual(ParcelaConta.objects.get(pk=segunda.pk).valor, Decimal("650.40"))

    def test_falha_nas_parcelas_desfaz_movimento_e_vinculos(self):
        for analise in (None, uuid.uuid4()):
            with self.subTest(analise=analise):
                with mock.patch.object(
                    ParcelaConta.objects, "bulk_create", side_effect=IntegrityError("falha")
                ):
                    with self.assertRaises(IntegrityError):
                        registrar_movimento(self.apagar(analise_origem_id=analise))

                self.assertEqual(MovimentoConta.objects.count(), 0)
                self.assertEqual(MovimentoClassificacao.objects.count(), 0)
                self.assertEqual(ParcelaConta.objects.count(), 0)


class ConcorrenciaTests(DadosDeServico, TransactionTestCase):
    """Requisições simultâneas reais: cada thread tem a própria conexão."""

    serialized_rollback = True

    def em_paralelo(self, *chamadas):
        """Executa as chamadas ao mesmo tempo; devolve (resultados, erros)."""
        barreira = threading.Barrier(len(chamadas))
        resultados = [None] * len(chamadas)
        erros = []

        def executar(indice, chamada):
            try:
                # Uma espera por bloqueio vira erro, e não um teste travado.
                sql("SET lock_timeout = '10s'")
                barreira.wait(timeout=TEMPO_LIMITE)
                resultados[indice] = chamada()
            # BaseException: inclusive a barreira quebrada; o teste confere depois.
            except BaseException as erro:
                erros.append((indice, erro))
            finally:
                # Conexão aberta nesta thread impediria apagar o banco de teste.
                connection.close()

        threads = [
            threading.Thread(target=executar, args=(indice, chamada), daemon=True)
            for indice, chamada in enumerate(chamadas)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TEMPO_LIMITE)
        travadas = [thread.name for thread in threads if thread.is_alive()]
        self.assertEqual(travadas, [], "Thread travada: possível deadlock.")
        return resultados, erros

    def test_reconfirmacao_e_cancelamento_simultaneos_nao_quebram_a_soma(self):
        # Sem o bloqueio do movimento no gatilho, cada transação conferiria um
        # estado sem a mudança da outra: o movimento volta a CONFIRMADO, a
        # parcela é cancelada, e as duas fariam COMMIT com a soma errada.
        movimento, _ = registrar_movimento(self.apagar(parcelas=parcelas("600.00", "650.40")))
        sql("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s", [movimento.pk])
        segunda = movimento.parcelas.get(numero=2)
        reconfirmado, conferido = threading.Event(), threading.Event()

        def reconfirmar():
            with transaction.atomic():
                sql("UPDATE movimentos_contas SET status = 'CONFIRMADO' WHERE id = %s",
                    [movimento.pk])
                reconfirmado.set()
                # Com o bloqueio, a outra transação espera aqui e não confere.
                conferido.wait(1)

        def cancelar_parcela():
            reconfirmado.wait(TEMPO_LIMITE)
            with transaction.atomic():
                sql("UPDATE parcelas_contas SET status = 'CANCELADA' WHERE id = %s",
                    [segunda.pk])
                # Confere antes do COMMIT, enquanto a reconfirmação está pendente.
                sql("SET CONSTRAINTS ALL IMMEDIATE")
                conferido.set()

        _, erros = self.em_paralelo(reconfirmar, cancelar_parcela)

        self.assertEqual([indice for indice, _ in erros], [1])
        self.assertEqual(restricao_violada(erros[0][1]), SOMA_DAS_PARCELAS)
        movimento.refresh_from_db()
        self.assertEqual(movimento.status, StatusMovimento.CONFIRMADO)
        self.assertEqual(movimento.parcelas.ativas().count(), 2)

    def test_mesma_analise_com_mesmos_dados_grava_uma_vez(self):
        dados = self.apagar(analise_origem_id=uuid.uuid4(),
                            parcelas=parcelas("400.00", "400.00", "450.40"))

        resultados, erros = self.em_paralelo(*[lambda: registrar_movimento(dados)] * 3)

        self.assertEqual(erros, [])
        self.assertEqual(sorted(criado for _, criado in resultados), [False, False, True])
        self.assertEqual(len({movimento.pk for movimento, _ in resultados}), 1)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(MovimentoClassificacao.objects.count(), 1)
        self.assertEqual(ParcelaConta.objects.count(), 3)

    def test_mesma_analise_com_dados_diferentes_grava_so_um(self):
        analise = uuid.uuid4()
        pedidos = (
            self.apagar(analise_origem_id=analise, parcelas=parcelas("600.00", "650.40")),
            self.apagar(analise_origem_id=analise, parcelas=parcelas("625.20", "625.20")),
        )

        resultados, erros = self.em_paralelo(
            *[lambda dados=dados: registrar_movimento(dados) for dados in pedidos]
        )

        self.assertEqual(len(erros), 1, erros)
        perdedor, erro = erros[0]
        self.assertIsInstance(erro, ValidationError)
        self.assertEqual(erro.code, "analise_ja_lancada")
        vencedor = 1 - perdedor
        movimento, criado = resultados[vencedor]
        self.assertTrue(criado)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        gravadas = set(movimento.parcelas.values_list("numero", "data_vencimento", "valor"))
        self.assertEqual(gravadas, {(p.numero, p.data_vencimento, p.valor)
                                    for p in pedidos[vencedor].parcelas})

    def test_papeis_cruzados_sem_deadlock(self):
        # A paga a B e B paga a A ao mesmo tempo: os bloqueios seguem a ordem da pk.
        self.fornecedor.atribuir_papel(Papel.FATURADO)
        self.faturado.atribuir_papel(Papel.FORNECEDOR)
        a_paga_b = self.apagar(contraparte=self.fornecedor, faturado=self.faturado,
                               parcelas=parcelas("600.00", "650.40"))
        b_paga_a = self.apagar(contraparte=self.faturado, faturado=self.fornecedor,
                               parcelas=parcelas("1250.40"))

        resultados, erros = self.em_paralelo(
            *[lambda dados=dados: registrar_movimento(dados)
              for dados in (a_paga_b, b_paga_a, a_paga_b, b_paga_a)]
        )

        self.assertEqual(erros, [])
        self.assertTrue(all(criado for _, criado in resultados))
        self.assertEqual(MovimentoConta.objects.count(), 4)
        self.assertEqual(ParcelaConta.objects.count(), 6)
        self.assertEqual(
            MovimentoConta.objects.filter(contraparte=self.faturado,
                                          faturado=self.fornecedor).count(),
            2,
        )
