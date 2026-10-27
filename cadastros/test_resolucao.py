"""Resolução das pessoas da nota (GR-22, F-4) no PostgreSQL local de teste.

TestCase e TransactionTestCase: rodam só com as variáveis DB_TEST_*
(config/banco_de_teste.py). Documentos fictícios, com DV calculado; nenhum
dado real.
"""

import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from documentos.models import AnalisePendente
from financeiro.models import MovimentoConta
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

from . import resolucao
from .models import (
    Classificacao, Papel, PapelPessoa, Pessoa, SituacaoDocumental, Status, TipoClassificacao,
)
from .resolucao import (
    Decisao, ParteNota, PessoaResolvida, avaliar_partes, resolver_partes,
)
from .test_models import (
    CNPJ, CNPJ_ALFANUMERICO, CNPJ_DV_INVALIDO, CNPJ_FORMATADO, CPF, CPF_DV_INVALIDO,
    CPF_FORMATADO, criar_incompleta, criar_pessoa,
)

FORNECEDOR = Papel.FORNECEDOR
FATURADO = Papel.FATURADO
TODAS = frozenset(Decisao)
TEMPO_LIMITE = 30


def parte(papel=FORNECEDOR, documento=CNPJ, nome="Agropecuária Teste Ltda", decisoes=(), **extra):
    return ParteNota(papel=papel, documento=documento, nome=nome, decisoes=frozenset(decisoes), **extra)


def pessoa_com_papel(documento=CNPJ, papel=FORNECEDOR, razao_social="Agropecuária Teste Ltda"):
    pessoa = criar_pessoa(documento, razao_social)
    pessoa.atribuir_papel(papel)
    return pessoa


def resolver_uma(*args, **kwargs):
    (resolvida,) = resolver_partes([parte(*args, **kwargs)])
    return resolvida


class ResolucaoTestBase(TestCase):
    def assert_recusa(self, codigo, partes, papel=None):
        with self.assertRaises(ValidationError) as contexto:
            resolver_partes(partes)
        self.assertEqual(contexto.exception.code, codigo)
        if papel is not None:
            self.assertEqual(contexto.exception.params, {"papel": papel})
        return contexto.exception

    def contagens(self):
        return Pessoa.objects.count(), PapelPessoa.objects.count()

    def escritas(self, queries):
        return [q["sql"] for q in queries if not q["sql"].lstrip().upper().startswith(
            ("SELECT", "SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT")
        )]


class ReutilizacaoTests(ResolucaoTestBase):
    def test_existente_ativa_com_papel_ativo_reutiliza_sem_escrita(self):
        pessoa = pessoa_com_papel()
        antes = self.contagens()

        with CaptureQueriesContext(connection) as queries:
            resolvida = resolver_uma(documento=CNPJ_FORMATADO)

        self.assertIsInstance(resolvida, PessoaResolvida)
        self.assertEqual(resolvida.pessoa.pk, pessoa.pk)
        self.assertEqual(resolvida.papel_pessoa.papel, FORNECEDOR)
        self.assertEqual(resolvida.acoes, ())
        self.assertEqual(self.contagens(), antes)
        self.assertEqual(self.escritas(queries.captured_queries), [])

    def test_bloqueia_pessoas_e_papeis_lidos(self):
        # Inativação ou regularização concorrente espera o fim da transação.
        pessoa_com_papel()

        with CaptureQueriesContext(connection) as queries:
            resolver_uma()

        bloqueios = [q["sql"] for q in queries.captured_queries if "FOR NO KEY UPDATE" in q["sql"]]
        self.assertEqual(len(bloqueios), 2)
        self.assertIn('"pessoas"', bloqueios[0])
        self.assertIn('"papeis_pessoa"', bloqueios[1])

    def test_decisoes_desnecessarias_sao_ignoradas(self):
        pessoa = pessoa_com_papel()
        antes = pessoa.atualizado_em

        resolvida = resolver_uma(decisoes=TODAS)

        pessoa.refresh_from_db()
        self.assertEqual(resolvida.pessoa.pk, pessoa.pk)
        self.assertEqual(resolvida.acoes, ())
        self.assertEqual(pessoa.atualizado_em, antes)
        self.assertEqual(Pessoa.objects.count(), 1)

    def test_nome_diferente_nao_altera_nem_impede_o_reuso(self):
        pessoa = pessoa_com_papel(razao_social="Nome Cadastrado")

        resolvida = resolver_uma(nome="Outro Nome Na Nota")

        pessoa.refresh_from_db()
        self.assertEqual(resolvida.pessoa.pk, pessoa.pk)
        self.assertEqual(pessoa.razao_social, "Nome Cadastrado")

    def test_mesmo_nome_com_outro_documento_nao_e_reutilizado(self):
        # Nome nunca identifica: outro documento exige criar outra pessoa.
        pessoa_com_papel(CNPJ, razao_social="Mesmo Nome")

        self.assert_recusa("pessoa_inexistente", [parte(documento=CNPJ_ALFANUMERICO, nome="Mesmo Nome")])
        resolvida = resolver_uma(
            documento=CNPJ_ALFANUMERICO, nome="Mesmo Nome", decisoes={Decisao.CRIAR_PESSOA}
        )

        self.assertEqual(Pessoa.objects.filter(razao_social="Mesmo Nome").count(), 2)
        self.assertEqual(resolvida.pessoa.documento, CNPJ_ALFANUMERICO)


class CriacaoTests(ResolucaoTestBase):
    def test_sem_decisao_nao_cria(self):
        self.assert_recusa("pessoa_inexistente", [parte()], FORNECEDOR)
        self.assertEqual(self.contagens(), (0, 0))

    def test_com_decisao_cria_completa_com_o_papel(self):
        resolvida = resolver_uma(documento=CNPJ_FORMATADO, decisoes={Decisao.CRIAR_PESSOA})

        pessoa = Pessoa.objects.get()
        self.assertEqual(resolvida.pessoa.pk, pessoa.pk)
        self.assertEqual(pessoa.documento, CNPJ)
        self.assertEqual(pessoa.situacao_documental, SituacaoDocumental.COMPLETO)
        self.assertEqual(pessoa.razao_social, "Agropecuária Teste Ltda")
        self.assertEqual(
            list(pessoa.papeis.values_list("papel", "status")), [(FORNECEDOR, Status.ATIVO)]
        )
        self.assertEqual(resolvida.acoes, (Decisao.CRIAR_PESSOA,))

    def test_cnpj_alfanumerico(self):
        resolvida = resolver_uma(documento="12.abc.345/01de-35", decisoes={Decisao.CRIAR_PESSOA})
        self.assertEqual(resolvida.pessoa.documento, CNPJ_ALFANUMERICO)

    def test_nome_ausente_ou_longo_bloqueia_mesmo_com_decisao(self):
        for nome, codigo in ((None, "nome_ausente"), ("   ", "nome_ausente"), ("x" * 256, "nome_invalido")):
            with self.subTest(codigo=codigo):
                self.assert_recusa(codigo, [parte(nome=nome, decisoes=TODAS)])
        self.assertEqual(self.contagens(), (0, 0))

    def test_repetir_a_resolucao_nao_duplica(self):
        primeira = resolver_uma(decisoes={Decisao.CRIAR_PESSOA})
        segunda = resolver_uma(decisoes={Decisao.CRIAR_PESSOA})

        self.assertEqual(segunda.pessoa.pk, primeira.pessoa.pk)
        self.assertEqual(segunda.acoes, ())
        self.assertEqual(self.contagens(), (1, 1))


class DocumentoTests(ResolucaoTestBase):
    def test_ausente_ou_invalido_bloqueia_sem_gravar(self):
        casos = (
            (None, "documento_ausente"), ("", "documento_ausente"), (" ", "documento_ausente"),
            (CPF_DV_INVALIDO, "documento_invalido"), (CNPJ_DV_INVALIDO, "documento_invalido"),
            ("123", "documento_invalido"),
        )
        for documento, codigo in casos:
            with self.subTest(documento=documento):
                self.assert_recusa(codigo, [parte(documento=documento, decisoes=TODAS)], FORNECEDOR)
        self.assertEqual(self.contagens(), (0, 0))

    def test_tipo_nao_e_deduzido_pelo_papel(self):
        # D-03: fornecedor com CPF e faturado com CNPJ são aceitos.
        fornecedor, faturado = resolver_partes([
            parte(FORNECEDOR, CPF_FORMATADO, "Produtor Fornecedor", {Decisao.CRIAR_PESSOA}),
            parte(FATURADO, CNPJ, "Empresa Faturada", {Decisao.CRIAR_PESSOA}),
        ])
        self.assertEqual(fornecedor.pessoa.tipo_documento, "CPF")
        self.assertEqual(faturado.pessoa.tipo_documento, "CNPJ")


class PapelTests(ResolucaoTestBase):
    def test_papel_ausente_exige_decisao_e_nao_cria_outra_pessoa(self):
        pessoa = pessoa_com_papel(CPF, FATURADO)

        self.assert_recusa("papel_ausente", [parte(FORNECEDOR, CPF)], FORNECEDOR)
        self.assertFalse(pessoa.papeis.filter(papel=FORNECEDOR).exists())

        resolvida = resolver_uma(FORNECEDOR, CPF, decisoes={Decisao.ATRIBUIR_PAPEL})
        self.assertEqual(resolvida.pessoa.pk, pessoa.pk)
        self.assertEqual(resolvida.papel_pessoa.status, Status.ATIVO)
        self.assertEqual(resolvida.acoes, (Decisao.ATRIBUIR_PAPEL,))
        self.assertEqual(Pessoa.objects.count(), 1)

    def test_criar_pessoa_nao_autoriza_atribuir_papel_em_existente(self):
        pessoa_com_papel(CPF, FATURADO)
        self.assert_recusa("papel_ausente", [parte(FORNECEDOR, CPF, decisoes={Decisao.CRIAR_PESSOA})])

    def test_papel_inativo_exige_decisao(self):
        pessoa = pessoa_com_papel()
        vinculo = pessoa.papeis.get()
        vinculo.inativar()

        self.assert_recusa("papel_inativo", [parte(decisoes={Decisao.ATRIBUIR_PAPEL})], FORNECEDOR)
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.status, Status.INATIVO)

        resolvida = resolver_uma(decisoes={Decisao.REATIVAR_PAPEL})
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.status, Status.ATIVO)
        self.assertEqual(resolvida.papel_pessoa.pk, vinculo.pk)
        self.assertEqual(resolvida.acoes, (Decisao.REATIVAR_PAPEL,))


class PessoaInativaTests(ResolucaoTestBase):
    def test_sem_decisao_nao_reativa(self):
        pessoa = pessoa_com_papel()
        pessoa.inativar()

        self.assert_recusa("pessoa_inativa", [parte(decisoes={Decisao.REATIVAR_PAPEL})], FORNECEDOR)
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.INATIVO)

    def test_com_decisao_reativa_o_mesmo_registro(self):
        pessoa = pessoa_com_papel()
        pessoa.inativar()

        resolvida = resolver_uma(decisoes={Decisao.REATIVAR_PESSOA})

        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.ATIVO)
        self.assertEqual(resolvida.pessoa.pk, pessoa.pk)
        self.assertEqual(resolvida.acoes, (Decisao.REATIVAR_PESSOA,))

    def test_inativa_e_sem_papel_exige_as_duas_decisoes(self):
        pessoa = criar_pessoa(CNPJ, "Inativa Sem Papel")
        pessoa.inativar()

        self.assert_recusa("papel_ausente", [parte(decisoes={Decisao.REATIVAR_PESSOA})])
        pessoa.refresh_from_db()
        # Todas as decisões são conferidas antes de qualquer gravação.
        self.assertEqual(pessoa.status, Status.INATIVO)

        resolvida = resolver_uma(decisoes={Decisao.REATIVAR_PESSOA, Decisao.ATRIBUIR_PAPEL})
        self.assertEqual(resolvida.acoes, (Decisao.REATIVAR_PESSOA, Decisao.ATRIBUIR_PAPEL))


class MesmoDocumentoTests(ResolucaoTestBase):
    def test_pessoa_nova_nas_duas_partes(self):
        fornecedor, faturado = resolver_partes([
            parte(FORNECEDOR, CPF, "Produtor Teste", {Decisao.CRIAR_PESSOA}),
            parte(FATURADO, CPF_FORMATADO, None, {Decisao.CRIAR_PESSOA}),
        ])

        self.assertEqual(fornecedor.pessoa.pk, faturado.pessoa.pk)
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(
            sorted(fornecedor.pessoa.papeis.values_list("papel", flat=True)), [FATURADO, FORNECEDOR]
        )

    def test_cada_parte_precisa_consentir_com_a_criacao(self):
        self.assert_recusa("pessoa_inexistente", [
            parte(FORNECEDOR, CPF, "Produtor Teste", {Decisao.CRIAR_PESSOA}),
            parte(FATURADO, CPF, "Produtor Teste"),
        ], FATURADO)
        self.assertEqual(self.contagens(), (0, 0))

    def test_nomes_divergentes_bloqueiam_a_criacao(self):
        self.assert_recusa("nomes_divergentes", [
            parte(FORNECEDOR, CPF, "Produtor Teste", TODAS),
            parte(FATURADO, CPF, "Outro Produtor", TODAS),
        ])
        self.assertEqual(self.contagens(), (0, 0))

    def test_existente_com_um_papel_recebe_o_outro(self):
        pessoa = pessoa_com_papel(CPF, FORNECEDOR)

        fornecedor, faturado = resolver_partes([
            parte(FORNECEDOR, CPF),
            parte(FATURADO, CPF, decisoes={Decisao.ATRIBUIR_PAPEL}),
        ])

        self.assertEqual({fornecedor.pessoa.pk, faturado.pessoa.pk}, {pessoa.pk})
        self.assertEqual(fornecedor.acoes, ())
        self.assertEqual(faturado.acoes, (Decisao.ATRIBUIR_PAPEL,))
        self.assertEqual(Pessoa.objects.count(), 1)

    def test_existente_inativa_exige_a_decisao_em_cada_parte(self):
        pessoa = pessoa_com_papel(CPF, FORNECEDOR)
        pessoa.atribuir_papel(FATURADO)
        pessoa.inativar()

        self.assert_recusa("pessoa_inativa", [
            parte(FORNECEDOR, CPF, decisoes={Decisao.REATIVAR_PESSOA}),
            parte(FATURADO, CPF),
        ], FATURADO)
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.INATIVO)


class IncompletaTests(ResolucaoTestBase):
    def test_selecionada_sem_regularizar_e_recusada(self):
        incompleta = criar_incompleta()

        self.assert_recusa("pessoa_incompleta", [
            parte(documento=CNPJ, pessoa_incompleta_id=incompleta.pk, decisoes={Decisao.ATRIBUIR_PAPEL}),
        ], FORNECEDOR)
        incompleta.refresh_from_db()
        self.assertEqual(incompleta.situacao_documental, SituacaoDocumental.INCOMPLETO)
        self.assertFalse(incompleta.papeis.exists())

    def test_regularizada_no_mesmo_registro(self):
        incompleta = criar_incompleta()
        incompleta.atribuir_papel(FORNECEDOR)

        resolvida = resolver_uma(
            documento=CNPJ_FORMATADO, pessoa_incompleta_id=incompleta.pk,
            decisoes={Decisao.REGULARIZAR},
        )

        incompleta.refresh_from_db()
        self.assertEqual(resolvida.pessoa.pk, incompleta.pk)
        self.assertEqual(incompleta.documento, CNPJ)
        self.assertEqual(incompleta.situacao_documental, SituacaoDocumental.COMPLETO)
        self.assertEqual(resolvida.acoes, (Decisao.REGULARIZAR,))
        self.assertEqual(Pessoa.objects.count(), 1)

    def test_regularizar_nao_autoriza_o_papel(self):
        incompleta = criar_incompleta()

        self.assert_recusa("papel_ausente", [
            parte(pessoa_incompleta_id=incompleta.pk, decisoes={Decisao.REGULARIZAR}),
        ])
        incompleta.refresh_from_db()
        # Recusada antes de gravar: o cadastro continua incompleto.
        self.assertIsNone(incompleta.documento)

    def test_documento_de_outra_pessoa_bloqueia(self):
        pessoa_com_papel(CNPJ)
        incompleta = criar_incompleta()

        self.assert_recusa("documento_em_uso", [
            parte(pessoa_incompleta_id=incompleta.pk, decisoes=TODAS),
        ])

    def test_selecao_invalida(self):
        completa = pessoa_com_papel(CPF)
        for selecionada in (completa.pk, 999999):
            with self.subTest(selecionada=selecionada):
                self.assert_recusa("selecao_invalida", [
                    parte(pessoa_incompleta_id=selecionada, decisoes=TODAS),
                ])

    def test_documento_invalido_nao_regulariza(self):
        incompleta = criar_incompleta()
        self.assert_recusa("documento_invalido", [
            parte(documento=CNPJ_DV_INVALIDO, pessoa_incompleta_id=incompleta.pk, decisoes=TODAS),
        ])

    def test_outra_parte_com_o_mesmo_documento_usa_o_regularizado(self):
        incompleta = criar_incompleta()

        fornecedor, faturado = resolver_partes([
            parte(FORNECEDOR, CPF, pessoa_incompleta_id=incompleta.pk,
                  decisoes={Decisao.REGULARIZAR, Decisao.ATRIBUIR_PAPEL}),
            parte(FATURADO, CPF, decisoes={Decisao.ATRIBUIR_PAPEL}),
        ])

        self.assertEqual({fornecedor.pessoa.pk, faturado.pessoa.pk}, {incompleta.pk})
        self.assertEqual(Pessoa.objects.count(), 1)


class RollbackTests(ResolucaoTestBase):
    def test_recusa_na_segunda_parte_nao_grava_a_primeira(self):
        pessoa_com_papel(CPF, FORNECEDOR)

        self.assert_recusa("papel_ausente", [
            parte(FORNECEDOR, CNPJ, decisoes={Decisao.CRIAR_PESSOA}),
            parte(FATURADO, CPF, "Produtor Teste"),
        ], FATURADO)
        self.assertFalse(Pessoa.objects.filter(documento=CNPJ).exists())

    def test_falha_durante_a_gravacao_nao_deixa_nada(self):
        pessoa = pessoa_com_papel(CPF, FATURADO)
        pessoa.inativar()

        with mock.patch.object(Pessoa, "atribuir_papel", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                resolver_partes([
                    parte(FATURADO, CPF, decisoes={Decisao.REATIVAR_PESSOA}),
                    parte(FORNECEDOR, CNPJ, decisoes={Decisao.CRIAR_PESSOA}),
                ])

        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.INATIVO)
        self.assertFalse(Pessoa.objects.filter(documento=CNPJ).exists())

    def test_dentro_de_transacao_externa_a_recusa_nao_a_invalida(self):
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                resolver_partes([parte()])
            resolvida = resolver_uma(decisoes={Decisao.CRIAR_PESSOA})
        self.assertTrue(Pessoa.objects.filter(pk=resolvida.pessoa.pk).exists())

    def test_concorrencia_persistente_vira_codigo_estavel(self):
        with mock.patch.object(resolucao, "_criar", side_effect=resolucao._Concorrencia):
            self.assert_recusa("cadastro_concorrente", [parte(decisoes={Decisao.CRIAR_PESSOA})])
        self.assertEqual(self.contagens(), (0, 0))


class AvaliacaoTests(ResolucaoTestBase):
    def test_so_leitura_e_mesmas_regras(self):
        pessoa = pessoa_com_papel(CPF, FATURADO)
        pessoa.inativar()
        incompleta = criar_incompleta()

        with CaptureQueriesContext(connection) as queries:
            avaliacoes = avaliar_partes([
                parte(FORNECEDOR, CNPJ, decisoes={Decisao.CRIAR_PESSOA}),
                parte(FATURADO, CPF),
                parte(FORNECEDOR, None),
                parte(FATURADO, CNPJ_ALFANUMERICO, pessoa_incompleta_id=incompleta.pk),
            ])

        self.assertEqual(self.escritas(queries.captured_queries), [])
        self.assertFalse(any("FOR " in q["sql"] for q in queries.captured_queries))
        nova, inativa, sem_documento, selecionada = avaliacoes
        self.assertTrue(nova.pronta)
        self.assertIsNone(nova.pessoa_id)
        self.assertEqual(nova.decisoes_necessarias, {Decisao.CRIAR_PESSOA})
        self.assertEqual(inativa.pessoa_id, pessoa.pk)
        self.assertEqual(inativa.decisoes_faltando, {Decisao.REATIVAR_PESSOA})
        self.assertFalse(inativa.pronta)
        self.assertEqual(sem_documento.bloqueio, "documento_ausente")
        self.assertEqual(selecionada.pessoa_id, incompleta.pk)
        self.assertEqual(
            selecionada.decisoes_necessarias, {Decisao.REGULARIZAR, Decisao.ATRIBUIR_PAPEL}
        )
        self.assertEqual(self.contagens(), (2, 1))

    def test_sem_partes(self):
        self.assertEqual(avaliar_partes([]), ())
        self.assertEqual(resolver_partes([]), ())


class EntradaTests(ResolucaoTestBase):
    def test_entradas_invalidas(self):
        casos = (
            (ValueError, [parte(papel="SOCIO")]),
            (ValueError, [parte(decisoes={"REATIVAR_TUDO"})]),
            (TypeError, [parte(documento=11222333000181)]),
            (TypeError, [parte(nome=123)]),
            (TypeError, [parte(pessoa_incompleta_id="1")]),
            (TypeError, [parte(pessoa_incompleta_id=True)]),
            (TypeError, [{"papel": FORNECEDOR, "documento": CNPJ}]),
            (TypeError, parte()),
        )
        for erro, partes in casos:
            with self.subTest(partes=partes), self.assertRaises(erro):
                resolver_partes(partes)
        self.assertEqual(self.contagens(), (0, 0))

    def test_decisoes_como_texto(self):
        resolvida = resolver_uma(decisoes={"CRIAR_PESSOA"})
        self.assertEqual(resolvida.acoes, (Decisao.CRIAR_PESSOA,))

    def test_mensagem_sem_documento(self):
        erro = self.assert_recusa("pessoa_inexistente", [parte(FATURADO, CPF_FORMATADO, "Produtor")])
        self.assertNotIn(CPF, str(erro))
        self.assertNotIn("Produtor", str(erro))


class UsoNoLancamentoTests(ResolucaoTestBase):
    """Contrato com a F-5: o que a resolução devolve é aceito por
    registrar_movimento; a resolução sozinha não cria movimento nem análise."""

    def dados(self, fornecedor, faturado):
        classificacao = Classificacao.objects.filter(
            tipo=TipoClassificacao.DESPESA, status=Status.ATIVO
        ).first()
        return DadosMovimento(
            tipo="APAGAR", origem="NOTA_FISCAL", contraparte=fornecedor, faturado=faturado,
            valor_total=Decimal("10.00"),
            classificacoes=(ItemClassificacao(classificacao, principal=True),),
            analise_origem_id=uuid.uuid4(),
            parcelas=(ItemParcela(1, date(2026, 11, 1), Decimal("10.00")),),
        )

    def test_pessoas_resolvidas_servem_ao_lancamento(self):
        fornecedor, faturado = resolver_partes([
            parte(FORNECEDOR, CNPJ, decisoes={Decisao.CRIAR_PESSOA}),
            parte(FATURADO, CPF, "Produtor Teste", decisoes={Decisao.CRIAR_PESSOA}),
        ])
        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertEqual(AnalisePendente.objects.count(), 0)

        movimento, criado = registrar_movimento(self.dados(fornecedor.pessoa, faturado.pessoa))
        self.assertTrue(criado)
        self.assertEqual(movimento.contraparte_id, fornecedor.pessoa.pk)

    def test_incompleta_nunca_chega_ao_lancamento(self):
        incompleta = criar_incompleta()
        incompleta.atribuir_papel(FORNECEDOR)

        self.assert_recusa("pessoa_incompleta", [parte(pessoa_incompleta_id=incompleta.pk)])
        self.assertEqual(MovimentoConta.objects.count(), 0)


class ConcorrenciaTests(TransactionTestCase):
    """Conexões reais em paralelo: cada thread tem a própria conexão."""

    serialized_rollback = True

    def em_paralelo(self, *chamadas):
        resultados = [None] * len(chamadas)
        erros = []

        def executar(indice, chamada):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                resultados[indice] = chamada()
            except BaseException as erro:
                erros.append((indice, erro))
            finally:
                connection.close()

        threads = [
            threading.Thread(target=executar, args=(i, c), daemon=True) for i, c in enumerate(chamadas)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TEMPO_LIMITE)
        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        return resultados, erros

    def resolver(self, papel, gravado=None, esperar=None, segurar=0):
        if esperar is not None:
            esperar.wait(TEMPO_LIMITE)
        # Como na F-5: a resolução dentro de uma transação externa.
        with transaction.atomic():
            (resolvida,) = resolver_partes([
                parte(papel, CNPJ, decisoes={Decisao.CRIAR_PESSOA}),
            ])
            if gravado is not None:
                gravado.set()
            time.sleep(segurar)
        return resolvida

    def test_mesmo_documento_criado_em_duas_transacoes(self):
        # A segunda não acha a pessoa (a primeira ainda não fez COMMIT), o INSERT
        # espera o índice único, falha e a nova tentativa reutiliza a pessoa.
        gravado = threading.Event()

        with mock.patch.object(resolucao, "_criar", wraps=resolucao._criar) as criar:
            resultados, erros = self.em_paralelo(
                lambda: self.resolver(FORNECEDOR, gravado=gravado, segurar=0.5),
                lambda: self.resolver(FORNECEDOR, esperar=gravado),
            )

        # Duas tentativas de INSERT (a segunda barrada pelo índice único) e
        # nenhuma na nova tentativa, que encontra a pessoa.
        self.assertEqual(criar.call_count, 2)
        self.assertEqual(erros, [])
        self.assertEqual(resultados[0].pessoa.pk, resultados[1].pessoa.pk)
        self.assertEqual(resultados[1].acoes, ())
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(PapelPessoa.objects.count(), 1)

    def test_corrida_com_outro_papel_exige_nova_decisao(self):
        # A pessoa criada pela outra transação não tem o papel FATURADO: a
        # decisão CRIAR_PESSOA não autoriza atribuí-lo, e nada é gravado.
        gravado = threading.Event()

        resultados, erros = self.em_paralelo(
            lambda: self.resolver(FORNECEDOR, gravado=gravado, segurar=0.5),
            lambda: self.resolver(FATURADO, esperar=gravado),
        )

        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, getattr(e, "code", e)) for i, e in erros], [(1, "papel_ausente")])
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(list(PapelPessoa.objects.values_list("papel", flat=True)), [FORNECEDOR])

    def test_varias_simultaneas_criam_uma(self):
        barreira = threading.Barrier(4)

        def resolver():
            barreira.wait(TEMPO_LIMITE)
            return self.resolver(FORNECEDOR)

        resultados, erros = self.em_paralelo(*[resolver] * 4)

        self.assertEqual(erros, [])
        self.assertEqual(len({r.pessoa.pk for r in resultados}), 1)
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(PapelPessoa.objects.count(), 1)
