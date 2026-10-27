"""Serviço registrar_movimento (GR-37) no PostgreSQL local de teste.

TestCase: rodam só com as variáveis DB_TEST_* (config/banco_de_teste.py).
Documentos fictícios; as classificações DESPESA vêm da carga inicial
(cadastros/migrations/0003_categorias_iniciais.py). AutocommitTests é um
TransactionTestCase: usa serialized_rollback=True para que o flush ao terminar
não apague essa carga.
"""

import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from cadastros.models import Classificacao, Papel, Pessoa, SituacaoDocumental

from .models import MovimentoClassificacao, MovimentoConta, ParcelaConta, StatusMovimento
from .servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

VENCIMENTO = date(2026, 11, 30)


def pessoa(documento, razao_social, *papeis):
    registro = Pessoa.objects.create(documento=documento, razao_social=razao_social)
    for papel in papeis:
        registro.atribuir_papel(papel)
    return registro


class DadosDeServico:
    def setUp(self):
        self.fornecedor = pessoa("11222333000181", "Fornecedor Teste", Papel.FORNECEDOR)
        self.faturado = pessoa("12345678909", "Faturado Teste", Papel.FATURADO)
        self.cliente = pessoa("12ABC34501DE35", "Cliente Teste", Papel.CLIENTE)
        self.manutencao = Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO")
        self.infraestrutura = Classificacao.objects.get(codigo="INFRAESTRUTURA_E_UTILIDADES")
        self.venda = Classificacao.objects.create(
            tipo="RECEITA", codigo="VENDA_PRODUCAO", descricao="VENDA DE PRODUÇÃO"
        )

    def apagar(self, **alteracoes):
        dados = DadosMovimento(
            tipo="APAGAR", origem="NOTA_FISCAL", contraparte=self.fornecedor,
            faturado=self.faturado, valor_total=Decimal("1250.40"),
            classificacoes=(ItemClassificacao(self.manutencao, principal=True),),
        )
        return self._com_parcela_unica(replace(dados, **alteracoes), alteracoes)

    def areceber(self, **alteracoes):
        dados = DadosMovimento(
            tipo="ARECEBER", origem="MANUAL", contraparte=self.cliente,
            valor_total=Decimal("900.00"),
            classificacoes=(ItemClassificacao(self.venda, principal=True),),
        )
        return self._com_parcela_unica(replace(dados, **alteracoes), alteracoes)

    def _com_parcela_unica(self, dados, alteracoes):
        # Sem parcelas informadas, uma parcela "ÚNICA" com o valor total (GR-38).
        if "parcelas" in alteracoes:
            return dados
        return replace(dados, parcelas=(ItemParcela(1, VENCIMENTO, dados.valor_total),))

    def assert_recusado(self, dados, codigo):
        with self.assertRaises(ValidationError) as contexto:
            registrar_movimento(dados)
        self.assertEqual(contexto.exception.code, codigo)
        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertEqual(MovimentoClassificacao.objects.count(), 0)
        self.assertEqual(ParcelaConta.objects.count(), 0)


class ServicoTestBase(DadosDeServico, TestCase):
    pass


class RegistroTests(ServicoTestBase):
    def test_conta_a_pagar_com_fornecedor_faturado_e_despesa(self):
        movimento, criado = registrar_movimento(self.apagar())

        self.assertTrue(criado)
        movimento.refresh_from_db()
        self.assertEqual((movimento.tipo, movimento.origem, movimento.status),
                         ("APAGAR", "NOTA_FISCAL", StatusMovimento.CONFIRMADO))
        self.assertEqual((movimento.contraparte, movimento.faturado),
                         (self.fornecedor, self.faturado))
        self.assertEqual(movimento.valor_total, Decimal("1250.40"))
        vinculo = movimento.classificacoes.get()
        self.assertEqual((vinculo.classificacao, vinculo.principal), (self.manutencao, True))

    def test_conta_a_receber_com_cliente_e_receita_sem_faturado(self):
        movimento, criado = registrar_movimento(self.areceber())

        self.assertTrue(criado)
        self.assertIsNone(movimento.faturado)
        self.assertEqual(movimento.classificacoes.get().classificacao, self.venda)

    def test_varias_classificacoes_com_uma_principal(self):
        dados = self.apagar(classificacoes=(
            ItemClassificacao(self.manutencao),
            ItemClassificacao(self.infraestrutura, principal=True),
        ))

        movimento, _ = registrar_movimento(dados)

        self.assertEqual(movimento.classificacoes.count(), 2)
        self.assertEqual(movimento.classificacoes.get(principal=True).classificacao,
                         self.infraestrutura)

    def test_mesma_pessoa_com_dois_papeis(self):
        self.fornecedor.atribuir_papel(Papel.FATURADO)

        movimento, _ = registrar_movimento(self.apagar(faturado=self.fornecedor))

        self.assertEqual(movimento.contraparte, movimento.faturado)

    def test_conta_a_receber_com_faturado_exige_o_papel_vigente(self):
        self.assert_recusado(self.areceber(faturado=self.fornecedor), "papel_ausente")
        self.assert_recusado(self.areceber(faturado="12345678909"), "faturado")
        self.faturado.papeis.get(papel=Papel.FATURADO).inativar()
        self.assert_recusado(self.areceber(faturado=self.faturado), "papel_inativo")

    def test_conta_a_receber_aceita_faturado_com_papel(self):
        movimento, _ = registrar_movimento(self.areceber(faturado=self.faturado))

        self.assertEqual(movimento.faturado, self.faturado)

    def test_valores_limite(self):
        for valor in (Decimal("0.01"), Decimal("9999999999.99"), Decimal("10")):
            with self.subTest(valor=valor):
                movimento, _ = registrar_movimento(self.apagar(valor_total=valor))
                movimento.refresh_from_db()
                self.assertEqual(movimento.valor_total, valor)


class ValoresInvalidosTests(ServicoTestBase):
    def test_valor_total_invalido(self):
        for valor, codigo in (
            (Decimal("0"), "valor"), (Decimal("-1.00"), "valor"),
            (Decimal("10000000000.00"), "valor"), (Decimal("1.001"), "valor_centavos"),
            (1250.40, "valor_tipo"), (1250, "valor_tipo"), ("1250.40", "valor_tipo"),
            (Decimal("NaN"), "valor_tipo"), (Decimal("Infinity"), "valor_tipo"),
        ):
            with self.subTest(valor=valor):
                self.assert_recusado(self.apagar(valor_total=valor), codigo)

    def test_tipo_e_origem_invalidos(self):
        self.assert_recusado(self.apagar(tipo="OUTRO"), "tipo")
        self.assert_recusado(self.apagar(origem="EMAIL"), "origem")


class ContrapartesTests(ServicoTestBase):
    def test_apagar_exige_fornecedor_e_areceber_exige_cliente(self):
        self.assert_recusado(self.apagar(contraparte=self.cliente), "papel_ausente")
        self.assert_recusado(self.areceber(contraparte=self.fornecedor), "papel_ausente")

    def test_apagar_exige_faturado_com_papel_faturado(self):
        self.assert_recusado(self.apagar(faturado=None), "faturado")
        self.assert_recusado(self.apagar(faturado=self.cliente), "papel_ausente")

    def test_pessoa_nao_gravada_e_recusada(self):
        nova = Pessoa(documento="99888777000100", razao_social="Não Gravada")

        self.assert_recusado(self.apagar(contraparte=nova), "contraparte")
        self.assert_recusado(self.apagar(faturado=nova), "faturado")

    def test_pessoa_inexistente_e_recusada(self):
        # Instância com pk, mas sem linha no banco (apagada por SQL, por exemplo).
        inexistente = Pessoa(pk=999_999, documento="99888777000100", razao_social="Inexistente")

        self.assert_recusado(self.apagar(contraparte=inexistente), "pessoa_inexistente")
        self.assert_recusado(self.apagar(faturado=inexistente), "pessoa_inexistente")

    def test_pessoa_inativa_e_recusada_sem_reativar(self):
        self.fornecedor.inativar()

        self.assert_recusado(self.apagar(), "pessoa_inativa")
        self.fornecedor.refresh_from_db()
        self.assertFalse(self.fornecedor.ativo)

    def test_faturado_inativo_e_recusado(self):
        self.faturado.inativar()

        self.assert_recusado(self.apagar(), "pessoa_inativa")

    def test_papel_inativo_e_recusado_sem_reativar(self):
        papel = self.fornecedor.papeis.get(papel=Papel.FORNECEDOR)
        papel.inativar()

        self.assert_recusado(self.apagar(), "papel_inativo")
        papel.refresh_from_db()
        self.assertFalse(papel.ativo)

    def test_pessoa_incompleta_e_recusada(self):
        incompleta = Pessoa.objects.create(
            razao_social="Sem Documento", situacao_documental=SituacaoDocumental.INCOMPLETO
        )
        incompleta.atribuir_papel(Papel.FORNECEDOR)
        incompleta.atribuir_papel(Papel.FATURADO)

        self.assert_recusado(self.apagar(contraparte=incompleta), "pessoa_incompleta")
        self.assert_recusado(self.apagar(faturado=incompleta), "pessoa_incompleta")

    def test_instancia_desatualizada_nao_engana_a_validacao(self):
        # A pessoa foi inativada por outro caminho; a instância em memória
        # ainda diz ATIVO, mas o serviço relê do banco.
        Pessoa.objects.filter(pk=self.fornecedor.pk).update(status="INATIVO")

        self.assert_recusado(self.apagar(), "pessoa_inativa")


class ClassificacoesTests(ServicoTestBase):
    def test_tipos_incompativeis(self):
        self.assert_recusado(
            self.apagar(classificacoes=(ItemClassificacao(self.venda, principal=True),)),
            "classificacao_incompativel",
        )
        self.assert_recusado(
            self.areceber(classificacoes=(ItemClassificacao(self.manutencao, principal=True),)),
            "classificacao_incompativel",
        )

    def test_mistura_de_tipos_e_recusada(self):
        dados = self.apagar(classificacoes=(
            ItemClassificacao(self.manutencao, principal=True), ItemClassificacao(self.venda),
        ))

        self.assert_recusado(dados, "classificacao_incompativel")

    def test_classificacao_inativa_e_recusada_sem_reativar(self):
        self.manutencao.inativar()

        self.assert_recusado(self.apagar(), "classificacao_inativa")
        self.manutencao.refresh_from_db()
        self.assertFalse(self.manutencao.ativo)

    def test_sem_classificacao_ou_repetida(self):
        self.assert_recusado(self.apagar(classificacoes=()), "sem_classificacao")
        self.assert_recusado(
            self.apagar(classificacoes=(
                ItemClassificacao(self.manutencao, principal=True),
                ItemClassificacao(self.manutencao),
            )),
            "classificacao_repetida",
        )

    def test_exatamente_uma_principal(self):
        for itens in (
            (ItemClassificacao(self.manutencao),),
            (ItemClassificacao(self.manutencao), ItemClassificacao(self.infraestrutura)),
            (ItemClassificacao(self.manutencao, principal=True),
             ItemClassificacao(self.infraestrutura, principal=True)),
        ):
            with self.subTest(itens=itens):
                self.assert_recusado(self.apagar(classificacoes=itens), "principal")

    def test_classificacao_inexistente_e_recusada(self):
        inexistente = Classificacao(pk=999_999, tipo="DESPESA", codigo="INEXISTENTE",
                                    descricao="Inexistente")

        self.assert_recusado(
            self.apagar(classificacoes=(ItemClassificacao(inexistente, principal=True),)),
            "classificacao_inexistente",
        )

    def test_classificacao_nao_gravada_e_recusada(self):
        nova = Classificacao(tipo="DESPESA", codigo="NOVA", descricao="Nova")

        self.assert_recusado(
            self.apagar(classificacoes=(ItemClassificacao(nova, principal=True),)),
            "classificacao",
        )


class EntradaTests(ServicoTestBase):
    """Tipos reais, e não só a pk: a GR-51 montará estes dados a partir da tela."""

    def test_classificacoes_em_gerador_sao_validadas_e_gravadas(self):
        itens = (item for item in [ItemClassificacao(self.manutencao, principal=True),
                                   ItemClassificacao(self.infraestrutura)])

        movimento, criado = registrar_movimento(self.apagar(classificacoes=itens))

        self.assertTrue(criado)
        self.assertEqual(movimento.classificacoes.count(), 2)
        self.assertEqual(movimento.classificacoes.get(principal=True).classificacao,
                         self.manutencao)

    def test_gerador_com_classificacao_inativa_e_recusado(self):
        self.manutencao.inativar()
        itens = (item for item in [ItemClassificacao(self.manutencao, principal=True)])

        self.assert_recusado(self.apagar(classificacoes=itens), "classificacao_inativa")

    def test_principal_precisa_ser_booleano(self):
        # "False" é verdadeiro em Python, mas o BooleanField gravaria False.
        for valor in ("False", "True", 1, 0, None):
            with self.subTest(principal=valor):
                itens = (ItemClassificacao(self.manutencao, principal=valor),)
                self.assert_recusado(self.apagar(classificacoes=itens), "principal_tipo")

    def test_contraparte_e_faturado_precisam_ser_pessoas(self):
        # Mesma pk de uma pessoa válida, mas de outro model.
        falsa = Classificacao(pk=self.fornecedor.pk, tipo="DESPESA", codigo="FALSA",
                              descricao="Falsa")
        falso_faturado = Classificacao(pk=self.faturado.pk, tipo="DESPESA", codigo="FALSA",
                                       descricao="Falsa")

        self.assert_recusado(self.apagar(contraparte=falsa), "contraparte")
        self.assert_recusado(self.apagar(faturado=falso_faturado), "faturado")

    def test_itens_precisam_ser_classificacoes(self):
        falsa = Pessoa(pk=self.manutencao.pk, razao_social="Não é classificação")

        self.assert_recusado(
            self.apagar(classificacoes=(ItemClassificacao(falsa, principal=True),)),
            "classificacao",
        )
        self.assert_recusado(self.apagar(classificacoes=(self.manutencao,)), "classificacao")

    def test_classificacoes_que_nao_sao_sequencia_sao_recusadas(self):
        for valor in (None, ItemClassificacao(self.manutencao, principal=True)):
            with self.subTest(classificacoes=valor):
                self.assert_recusado(self.apagar(classificacoes=valor), "classificacao")

    def test_analise_de_origem_precisa_ser_uuid(self):
        self.assert_recusado(self.apagar(analise_origem_id=str(uuid.uuid4())), "analise_origem")


class IdempotenciaTests(ServicoTestBase):
    def setUp(self):
        super().setUp()
        self.analise = uuid.uuid4()

    def test_mesma_analise_devolve_o_mesmo_movimento(self):
        primeiro, criado = registrar_movimento(self.apagar(analise_origem_id=self.analise))
        segundo, criado_de_novo = registrar_movimento(self.apagar(analise_origem_id=self.analise))

        self.assertTrue(criado)
        self.assertFalse(criado_de_novo)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(MovimentoClassificacao.objects.count(), 1)

    def test_mesma_analise_com_outros_dados_e_recusada(self):
        registrar_movimento(self.apagar(analise_origem_id=self.analise))

        for alteracao in (
            {"valor_total": Decimal("1.00")},
            {"classificacoes": (ItemClassificacao(self.infraestrutura, principal=True),)},
            {"classificacoes": (ItemClassificacao(self.manutencao),
                                ItemClassificacao(self.infraestrutura, principal=True))},
            {"origem": "MANUAL"},
            {"contraparte": pessoa("11444777000161", "Outro Fornecedor Teste", Papel.FORNECEDOR)},
            {"faturado": pessoa("52998224725", "Outro Faturado Teste", Papel.FATURADO)},
            # Só o tipo: a busca da análise vem antes da validação das classificações.
            {"tipo": "ARECEBER"},
        ):
            with self.subTest(**{k: str(v) for k, v in alteracao.items()}):
                with self.assertRaises(ValidationError) as contexto:
                    registrar_movimento(self.apagar(analise_origem_id=self.analise, **alteracao))
                self.assertEqual(contexto.exception.code, "analise_ja_lancada")
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_mesma_analise_em_conta_a_receber_e_recusada(self):
        registrar_movimento(self.apagar(analise_origem_id=self.analise))

        with self.assertRaises(ValidationError) as contexto:
            registrar_movimento(self.areceber(analise_origem_id=self.analise))
        self.assertEqual(contexto.exception.code, "analise_ja_lancada")
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_repeticao_com_classificacoes_em_gerador_devolve_o_existente(self):
        existente, _ = registrar_movimento(self.apagar(analise_origem_id=self.analise))
        itens = (item for item in [ItemClassificacao(self.manutencao, principal=True)])

        movimento, criado = registrar_movimento(
            self.apagar(analise_origem_id=self.analise, classificacoes=itens)
        )

        self.assertFalse(criado)
        self.assertEqual(movimento.pk, existente.pk)
        self.assertEqual(MovimentoClassificacao.objects.count(), 1)

    def test_mesma_analise_com_outra_principal_e_recusada(self):
        itens = (ItemClassificacao(self.manutencao, principal=True),
                 ItemClassificacao(self.infraestrutura))
        registrar_movimento(self.apagar(analise_origem_id=self.analise, classificacoes=itens))
        trocada = (ItemClassificacao(self.manutencao),
                   ItemClassificacao(self.infraestrutura, principal=True))

        with self.assertRaises(ValidationError) as contexto:
            registrar_movimento(self.apagar(analise_origem_id=self.analise, classificacoes=trocada))
        self.assertEqual(contexto.exception.code, "analise_ja_lancada")

    def test_analise_de_movimento_cancelado_nao_e_devolvida(self):
        movimento, _ = registrar_movimento(self.apagar(analise_origem_id=self.analise))
        # O cancelamento ainda não existe: simula o estado futuro direto no banco.
        with connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s",
                           [movimento.pk])

        with self.assertRaises(ValidationError) as contexto:
            registrar_movimento(self.apagar(analise_origem_id=self.analise))
        self.assertEqual(contexto.exception.code, "analise_ja_lancada")

    def test_sem_analise_cada_chamada_cria_um_movimento(self):
        registrar_movimento(self.apagar())
        registrar_movimento(self.apagar())

        self.assertEqual(MovimentoConta.objects.count(), 2)

    def test_corrida_na_mesma_analise_devolve_o_existente(self):
        existente, _ = registrar_movimento(self.apagar(analise_origem_id=self.analise))

        # Simula a outra requisição gravando entre a busca e a gravação.
        busca_original = MovimentoConta.objects.filter
        chamadas = []

        def busca_que_nao_ve_na_primeira(*args, **kwargs):
            chamadas.append(kwargs)
            if len(chamadas) == 1:
                return MovimentoConta.objects.none()
            return busca_original(*args, **kwargs)

        with mock.patch.object(MovimentoConta.objects, "filter", side_effect=busca_que_nao_ve_na_primeira):
            movimento, criado = registrar_movimento(self.apagar(analise_origem_id=self.analise))

        self.assertEqual(len(chamadas), 2)
        self.assertFalse(criado)
        self.assertEqual(movimento.pk, existente.pk)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(MovimentoClassificacao.objects.count(), 1)


class AtomicidadeTests(ServicoTestBase):
    def test_falha_nas_classificacoes_nao_deixa_movimento(self):
        with mock.patch.object(
            MovimentoClassificacao.objects, "bulk_create", side_effect=IntegrityError("falha")
        ):
            with self.assertRaises(IntegrityError):
                registrar_movimento(self.apagar())

        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_falha_sem_analise_nao_devolve_movimento_parecido(self):
        # Sem analise_origem_id, um IntegrityError nunca vira "já existente".
        registrar_movimento(self.apagar())

        with mock.patch.object(
            MovimentoClassificacao.objects, "bulk_create", side_effect=IntegrityError("falha")
        ):
            with self.assertRaises(IntegrityError):
                registrar_movimento(self.apagar())

        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_pessoas_papeis_e_classificacoes_sao_bloqueados_na_validacao(self):
        with CaptureQueriesContext(connection) as consultas:
            registrar_movimento(self.apagar())

        bloqueadas = {
            tabela for consulta in consultas.captured_queries
            if "FOR NO KEY UPDATE" in consulta["sql"]
            for tabela in ("pessoas", "papeis_pessoa", "classificacoes")
            if f'FROM "{tabela}"' in consulta["sql"]
        }
        self.assertEqual(bloqueadas, {"pessoas", "papeis_pessoa", "classificacoes"})
        # Ordem fixa por pk em cada bloqueio: evita deadlock entre lançamentos.
        for consulta in consultas.captured_queries:
            if "FOR NO KEY UPDATE" in consulta["sql"]:
                self.assertIn("ORDER BY", consulta["sql"])
        # Os bloqueios ficam dentro do atomic() do serviço: aqui, dentro da
        # transação do TestCase, ele abre um savepoint antes do primeiro.
        sqls = [consulta["sql"] for consulta in consultas.captured_queries]
        primeiro = next(i for i, sql in enumerate(sqls) if "FOR NO KEY UPDATE" in sql)
        self.assertTrue(any(sql.startswith("SAVEPOINT") for sql in sqls[:primeiro]))

    def test_recusa_nao_quebra_a_transacao_de_quem_chamou(self):
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                registrar_movimento(self.apagar(contraparte=self.cliente))
            registrar_movimento(self.apagar())

        self.assertEqual(MovimentoConta.objects.count(), 1)


class AutocommitTests(DadosDeServico, TransactionTestCase):
    """Sem transação externa, como numa view sem ATOMIC_REQUESTS."""

    serialized_rollback = True

    def test_registra_fora_de_transacao(self):
        self.assertFalse(connection.in_atomic_block)
        dados = self.apagar(classificacoes=(
            ItemClassificacao(self.manutencao, principal=True),
            ItemClassificacao(self.infraestrutura),
        ))

        movimento, criado = registrar_movimento(dados)

        self.assertTrue(criado)
        self.assertEqual(movimento.classificacoes.count(), 2)

    def test_falha_nas_classificacoes_desfaz_o_movimento(self):
        with mock.patch.object(
            MovimentoClassificacao.objects, "bulk_create", side_effect=IntegrityError("falha")
        ):
            with self.assertRaises(IntegrityError):
                registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))

        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertEqual(MovimentoClassificacao.objects.count(), 0)

    def test_corrida_na_mesma_analise_devolve_o_existente(self):
        analise = uuid.uuid4()
        existente, _ = registrar_movimento(self.apagar(analise_origem_id=analise))
        busca_original = MovimentoConta.objects.filter
        chamadas = []

        def busca_que_nao_ve_na_primeira(*args, **kwargs):
            chamadas.append(kwargs)
            if len(chamadas) == 1:
                return MovimentoConta.objects.none()
            return busca_original(*args, **kwargs)

        with mock.patch.object(MovimentoConta.objects, "filter", side_effect=busca_que_nao_ve_na_primeira):
            movimento, criado = registrar_movimento(self.apagar(analise_origem_id=analise))

        self.assertFalse(criado)
        self.assertEqual(movimento.pk, existente.pk)
        self.assertEqual(MovimentoClassificacao.objects.count(), 1)
