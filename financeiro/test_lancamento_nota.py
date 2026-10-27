"""Lançamento da nota a partir da análise (GR-22, F-5) no PostgreSQL local.

TestCase e TransactionTestCase: rodam só com as variáveis DB_TEST_*
(config/banco_de_teste.py). Documentos fictícios, com DV calculado; nenhum
dado real. As categorias iniciais de DESPESA vêm da migration 0003 de cadastros.

O JSON v1 não traz modelo nem chave de acesso: sem a G-01 ou o JSON fiscal v2,
toda nota real é recusada com identidade_fiscal_insuficiente. Os testes de
lançamento simulam essa origem com `com_modelo()`, injetando o modelo na
chamada de identificar_nota() feita pela F-3; registrar_identidade_fiscal()
revalida a identidade com o serviço real.
"""

import threading
import time
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from cadastros.models import Classificacao, Papel, PapelPessoa, Pessoa, SituacaoDocumental, Status
from cadastros.resolucao import Decisao, resolver_partes
from documentos import analises
from documentos.analises import AnaliseError, cancelar_analise, criar_analise, registrar_correcoes
from documentos.conferencia import conferir_nota
from documentos.models import AnalisePendente, StatusAnalise
from documentos.testing import CNPJ, CPF, nova_sessao, resultado_da_nota

from . import lancamento_nota
from .identidade_fiscal import identificar_nota
from .lancamento_nota import (
    DecisoesDaParte, LancamentoNota, SolicitacaoLancamento, lancar_nota,
)
from .models import (
    MovimentoClassificacao, MovimentoConta, NotaFiscalLancada, ParcelaConta, StatusMovimento,
)
from .test_identidade_fiscal import chave

TEMPO_LIMITE = 30
CRIAR = DecisoesDaParte(frozenset({Decisao.CRIAR_PESSOA}))


@contextmanager
def com_modelo(modelo="55", **extra):
    """Simula a origem do modelo (G-01 ou JSON v2), ainda inexistente no fluxo."""
    def identificar(**argumentos):
        return identificar_nota(**{**argumentos, "modelo": modelo, **extra})

    with mock.patch("documentos.conferencia.identificar_nota", side_effect=identificar):
        yield


def cadastrar_pessoas():
    fornecedor = Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste Ltda")
    fornecedor.atribuir_papel(Papel.FORNECEDOR)
    faturado = Pessoa.objects.create(documento=CPF, razao_social="Produtor Teste")
    faturado.atribuir_papel(Papel.FATURADO)
    return fornecedor, faturado


def contagens():
    return {
        model.__name__: model.objects.count()
        for model in (Pessoa, PapelPessoa, MovimentoConta, MovimentoClassificacao, ParcelaConta,
                      NotaFiscalLancada)
    }


def codigos(erro):
    return [item.code for item in erro.error_list]


class LancamentoTestBase(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()

    def nova_analise(self, correcoes=None, resultado=None, sessao=None):
        """Análise com a série corrigida (o JSON v1 não tem série); versão 1."""
        sessao = sessao or self.sessao
        analise = criar_analise(sessao, resultado or resultado_da_nota())
        registrar_correcoes(sessao, analise.id, {"serie": 1, **(correcoes or {})}, 0)
        return analise

    def lancar(self, analise, fornecedor=DecisoesDaParte(), faturado=DecisoesDaParte(), versao=1,
               sessao=None):
        return lancar_nota(sessao or self.sessao, analise.id, SolicitacaoLancamento(
            versao_correcoes=versao, fornecedor=fornecedor, faturado=faturado,
        ))

    def assert_recusa(self, codigo, analise, *args, **kwargs):
        antes = contagens()
        with self.assertRaises(ValidationError) as contexto:
            self.lancar(analise, *args, **kwargs)
        self.assertIn(codigo, codigos(contexto.exception))
        self.assert_nada_gravado(analise, antes)
        return contexto.exception

    def assert_nada_gravado(self, analise, antes):
        self.assertEqual(contagens(), antes)
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)
        self.assertIsNotNone(analise.dados)
        self.assertEqual(analise.correcoes["serie"], 1)


class LancamentoValidoTests(LancamentoTestBase):
    def test_reutiliza_pessoas_e_grava_tudo_na_mesma_confirmacao(self):
        fornecedor, faturado = cadastrar_pessoas()
        analise = self.nova_analise()

        with com_modelo():
            lancamento = self.lancar(analise)

        self.assertIsInstance(lancamento, LancamentoNota)
        movimento = MovimentoConta.objects.get()
        self.assertEqual(lancamento.movimento.pk, movimento.pk)
        self.assertEqual(
            (movimento.tipo, movimento.origem, movimento.status, movimento.valor_total),
            ("APAGAR", "NOTA_FISCAL", StatusMovimento.CONFIRMADO, Decimal("150.00")),
        )
        self.assertEqual((movimento.contraparte_id, movimento.faturado_id), (fornecedor.pk, faturado.pk))
        self.assertEqual(movimento.analise_origem_id, analise.id)
        self.assertEqual(
            list(movimento.classificacoes.values_list("classificacao__codigo", "principal")),
            [("MANUTENCAO_E_OPERACAO", True)],
        )
        self.assertEqual(
            list(movimento.parcelas.values_list("numero", "data_vencimento", "valor")),
            [(1, date(2026, 11, 1), Decimal("150.00"))],
        )
        nota = NotaFiscalLancada.objects.get()
        self.assertEqual(lancamento.nota_fiscal.pk, nota.pk)
        self.assertEqual((nota.movimento_id, nota.emitente_cnpj, nota.modelo, nota.serie, nota.numero),
                         (movimento.pk, CNPJ, "55", 1, 123))
        self.assertEqual(lancamento.fornecedor.acoes, ())
        self.assertEqual(lancamento.faturado.acoes, ())
        self.assertEqual(Pessoa.objects.count(), 2)

        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.CONFIRMADA)
        self.assertIsNone(analise.dados)
        self.assertIsNone(analise.correcoes)
        self.assertEqual(analise.campos_corrigidos, ["serie"])

    def test_cria_pessoas_com_autorizacao_explicita(self):
        analise = self.nova_analise()

        with com_modelo():
            lancamento = self.lancar(analise, CRIAR, CRIAR)

        self.assertEqual(lancamento.fornecedor.acoes, (Decisao.CRIAR_PESSOA,))
        self.assertEqual(lancamento.fornecedor.pessoa.documento, CNPJ)
        self.assertEqual(lancamento.faturado.pessoa.razao_social, "Produtor Teste")
        self.assertEqual(Pessoa.objects.count(), 2)
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_correcoes_prevalecem_sobre_o_extraido(self):
        cadastrar_pessoas()
        analise = self.nova_analise({
            "tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES",
            "valor_total": "200.00",
            "parcelas": [
                {"numero": 1, "data_vencimento": "2026-11-01", "valor": "120.00"},
                {"numero": 2, "data_vencimento": "2026-12-01", "valor": "80.00"},
            ],
        })

        with com_modelo():
            lancamento = self.lancar(analise)

        movimento = lancamento.movimento
        self.assertEqual(movimento.valor_total, Decimal("200.00"))
        self.assertEqual(movimento.parcelas.count(), 2)
        self.assertEqual(movimento.classificacoes.get().classificacao.codigo, "INFRAESTRUTURA_E_UTILIDADES")

    def test_faturado_com_cnpj_escolhido(self):
        fornecedor, _ = cadastrar_pessoas()
        analise = self.nova_analise({"faturado.documento": "12.abc.345/01de-35", "faturado.nome": "Empresa"})

        with com_modelo():
            lancamento = self.lancar(analise, faturado=CRIAR)

        self.assertEqual(lancamento.faturado.pessoa.documento, "12ABC34501DE35")
        self.assertEqual(lancamento.fornecedor.pessoa.pk, fornecedor.pk)


class DecisoesTests(LancamentoTestBase):
    def test_pessoa_inexistente_sem_decisao(self):
        analise = self.nova_analise()
        with com_modelo():
            erro = self.assert_recusa("pessoa_inexistente", analise)
        self.assertEqual(erro.error_list[0].params, {"papel": Papel.FORNECEDOR})

    def test_decisao_de_uma_parte_nao_vale_para_a_outra(self):
        analise = self.nova_analise()
        with com_modelo():
            erro = self.assert_recusa("pessoa_inexistente", analise, CRIAR)
        self.assertEqual(erro.error_list[0].params, {"papel": Papel.FATURADO})

    def test_pessoa_inativa_so_com_reativacao(self):
        fornecedor, _ = cadastrar_pessoas()
        fornecedor.inativar()
        analise = self.nova_analise()

        with com_modelo():
            self.assert_recusa("pessoa_inativa", analise)
            lancamento = self.lancar(analise, DecisoesDaParte({Decisao.REATIVAR_PESSOA}))

        fornecedor.refresh_from_db()
        self.assertEqual(fornecedor.status, Status.ATIVO)
        self.assertEqual(lancamento.fornecedor.acoes, (Decisao.REATIVAR_PESSOA,))

    def test_papel_ausente_so_com_atribuicao(self):
        _, faturado = cadastrar_pessoas()
        faturado.papeis.update(papel=Papel.CLIENTE)
        analise = self.nova_analise()

        with com_modelo():
            self.assert_recusa("papel_ausente", analise)
            self.lancar(analise, faturado=DecisoesDaParte({Decisao.ATRIBUIR_PAPEL}))

        self.assertTrue(faturado.papeis.filter(papel=Papel.FATURADO, status=Status.ATIVO).exists())

    def test_incompleta_sem_regularizar_bloqueia(self):
        fornecedor = Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste Ltda")
        fornecedor.atribuir_papel(Papel.FORNECEDOR)
        incompleta = Pessoa.objects.create(
            razao_social="Produtor Sem CPF", situacao_documental=SituacaoDocumental.INCOMPLETO,
        )
        incompleta.atribuir_papel(Papel.FATURADO)
        analise = self.nova_analise()
        selecao = DecisoesDaParte(pessoa_incompleta_id=incompleta.pk)

        with com_modelo():
            self.assert_recusa("pessoa_incompleta", analise, faturado=selecao)
            lancamento = self.lancar(analise, faturado=DecisoesDaParte(
                frozenset({Decisao.REGULARIZAR}), pessoa_incompleta_id=incompleta.pk,
            ))

        incompleta.refresh_from_db()
        self.assertEqual(incompleta.documento, CPF)
        self.assertEqual(lancamento.faturado.pessoa.pk, incompleta.pk)
        self.assertEqual(lancamento.movimento.faturado_id, incompleta.pk)

    def test_decisoes_nao_sao_gravadas_na_analise(self):
        analise = self.nova_analise()
        with com_modelo():
            self.assert_recusa("pessoa_inexistente", analise, CRIAR)
        analise.refresh_from_db()
        self.assertEqual(analise.correcoes, {"serie": 1})
        self.assertEqual(analise.versao_correcoes, 1)


class RecusasDaConferenciaTests(LancamentoTestBase):
    def setUp(self):
        super().setUp()
        cadastrar_pessoas()

    def test_identidade_insuficiente_com_o_json_v1(self):
        # Estado real: sem G-01 nem JSON v2, nenhuma nota é lançada.
        analise = self.nova_analise()
        erro = self.assert_recusa("identidade_fiscal_insuficiente", analise)
        self.assertEqual(erro.error_list[0].params,
                         {"campo": "identidade_fiscal", "codigo": "identidade_fiscal_insuficiente"})

    def test_identidade_divergente(self):
        analise = self.nova_analise()
        with com_modelo(chave_acesso=chave(numero=999)):
            self.assert_recusa("identidade_fiscal_divergente", analise)

    def test_modelo_nao_suportado(self):
        analise = self.nova_analise()
        with com_modelo("57"):
            self.assert_recusa("identidade_fiscal_nao_suportada", analise)

    def test_todos_os_problemas_sao_informados(self):
        analise = self.nova_analise({"parcelas": [
            {"numero": 1, "data_vencimento": "2026-11-01", "valor": "100.00"},
        ]})
        with self.assertRaises(ValidationError) as contexto:
            self.lancar(analise)
        self.assertEqual(set(codigos(contexto.exception)),
                         {"parcela_soma", "identidade_fiscal_insuficiente"})
        self.assertNotIn("100.00", str(contexto.exception))

    def test_parcelas_inconsistentes(self):
        casos = (
            ([{"numero": 1, "data_vencimento": "2026-11-01", "valor": "100.00"}], "parcela_soma"),
            ([{"numero": 2, "data_vencimento": "2026-11-01", "valor": "150.00"}], "parcela_numeracao"),
        )
        for parcelas, codigo in casos:
            with self.subTest(codigo=codigo), com_modelo():
                self.assert_recusa(codigo, self.nova_analise({"parcelas": parcelas}))

    def test_parcela_extraida_sem_vencimento(self):
        resultado = resultado_da_nota()
        resultado["parcelas"][0]["data_vencimento"] = None
        with com_modelo():
            self.assert_recusa("invalido", self.nova_analise(resultado=resultado))

    def test_classificacao_ausente_ou_inexistente(self):
        resultado = resultado_da_nota()
        resultado["tipo_despesa"] = None
        with com_modelo():
            self.assert_recusa("ausente", self.nova_analise(resultado=resultado))

    def test_documento_invalido(self):
        resultado = resultado_da_nota()
        resultado["fornecedor"]["cnpj"] = "11222333000182"
        with com_modelo():
            self.assert_recusa("invalido", self.nova_analise(resultado=resultado))

    def test_classificacao_inativa_nao_e_reativada(self):
        classificacao = Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO")
        classificacao.inativar()
        analise = self.nova_analise()

        with com_modelo():
            self.assert_recusa("classificacao_inativa", analise)

        classificacao.refresh_from_db()
        self.assertEqual(classificacao.status, Status.INATIVO)


class DuplicidadeTests(LancamentoTestBase):
    def test_mesma_nota_em_outra_analise(self):
        cadastrar_pessoas()
        primeira, segunda = self.nova_analise(), self.nova_analise()

        with com_modelo():
            self.lancar(primeira)
            self.assert_recusa("nota_ja_lancada", segunda)

        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_nota_ja_lancada_recusada_antes_dos_cadastros(self):
        cadastrar_pessoas()
        with com_modelo():
            self.lancar(self.nova_analise())
        # Outra análise da mesma nota com outro faturado, a criar: a recusa
        # acontece na F-3, antes de qualquer cadastro.
        analise = self.nova_analise({"faturado.documento": "52998224725", "faturado.nome": "Outro"})
        with com_modelo():
            self.assert_recusa("nota_ja_lancada", analise, faturado=CRIAR)
        self.assertFalse(Pessoa.objects.filter(documento="52998224725").exists())

    def test_dupla_confirmacao(self):
        cadastrar_pessoas()
        analise = self.nova_analise()

        with com_modelo():
            self.lancar(analise)
            with self.assertRaises(AnaliseError) as contexto:
                self.lancar(analise)

        self.assertEqual(contexto.exception.codigo, "analise_confirmada")
        self.assertEqual(MovimentoConta.objects.count(), 1)


class RollbackTests(LancamentoTestBase):
    """Falha em cada etapa depois das gravações anteriores: nada fica."""

    def lancar_com_falha(self, alvo):
        analise = self.nova_analise()
        antes = contagens()
        with com_modelo(), mock.patch(alvo, side_effect=RuntimeError("falha simulada")):
            with self.assertRaises(RuntimeError):
                self.lancar(analise, CRIAR, CRIAR)
        self.assert_nada_gravado(analise, antes)

    def test_falha_depois_dos_cadastros(self):
        self.lancar_com_falha("financeiro.lancamento_nota.registrar_movimento")

    def test_falha_depois_do_movimento(self):
        self.lancar_com_falha("financeiro.lancamento_nota.registrar_identidade_fiscal")

    def test_falha_ao_finalizar_a_analise(self):
        self.lancar_com_falha("documentos.analises._finalizar")

    def test_reativacao_desfeita(self):
        fornecedor, _ = cadastrar_pessoas()
        fornecedor.inativar()
        analise = self.nova_analise()
        with com_modelo(), mock.patch("financeiro.lancamento_nota.registrar_identidade_fiscal",
                                      side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.lancar(analise, DecisoesDaParte({Decisao.REATIVAR_PESSOA}))
        fornecedor.refresh_from_db()
        self.assertEqual(fornecedor.status, Status.INATIVO)


class EstadoDaAnaliseTests(LancamentoTestBase):
    def setUp(self):
        super().setUp()
        cadastrar_pessoas()

    def assert_analise_error(self, codigo, analise, **kwargs):
        antes = contagens()
        with com_modelo(), self.assertRaises(AnaliseError) as contexto:
            self.lancar(analise, **kwargs)
        self.assertEqual(contexto.exception.codigo, codigo)
        self.assertEqual(contagens(), antes)

    def test_correcoes_alteradas_depois_da_conferencia(self):
        analise = self.nova_analise()
        registrar_correcoes(self.sessao, analise.id, {"serie": 2}, 1)
        self.assert_analise_error("correcoes_desatualizadas", analise, versao=1)

    def test_expirada(self):
        analise = self.nova_analise()
        agora = timezone.now()
        AnalisePendente.objects.filter(pk=analise.id).update(
            criado_em=agora - timedelta(hours=1), expira_em=agora - timedelta(seconds=1)
        )
        self.assert_analise_error("analise_expirada", analise)
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.EXPIRADA)

    def test_cancelada(self):
        analise = self.nova_analise()
        cancelar_analise(self.sessao, analise.id)
        self.assert_analise_error("analise_cancelada", analise)

    def test_outra_sessao(self):
        analise = self.nova_analise()
        self.assert_analise_error("analise_nao_encontrada", analise, sessao=nova_sessao())

    def test_dentro_de_outra_transacao(self):
        analise = self.nova_analise()
        with transaction.atomic(), self.assertRaises(RuntimeError):
            self.lancar(analise)


class SolicitacaoTests(LancamentoTestBase):
    def test_solicitacao_invalida_nao_toca_a_analise(self):
        analise = self.nova_analise()
        casos = (
            (TypeError, {"fornecedor": {"decisoes": ["CRIAR_PESSOA"]}}),
            (TypeError, {"versao_correcoes": "1"}),
            (TypeError, {"versao_correcoes": True}),
            (TypeError, {"faturado": DecisoesDaParte("CRIAR_PESSOA")}),
            (ValueError, {"faturado": DecisoesDaParte(frozenset({"CRIAR_TUDO"}))}),
            (TypeError, {"faturado": DecisoesDaParte(pessoa_incompleta_id="1")}),
            (TypeError, {"faturado": DecisoesDaParte(pessoa_incompleta_id=True)}),
        )
        for erro, campos in casos:
            with self.subTest(campos=campos), self.assertRaises(erro):
                lancar_nota(self.sessao, analise.id, SolicitacaoLancamento(**{"versao_correcoes": 1, **campos}))
        with self.assertRaises(TypeError):
            lancar_nota(self.sessao, analise.id, {"versao_correcoes": 1})
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)

    def test_decisoes_em_texto(self):
        analise = self.nova_analise()
        with com_modelo():
            lancamento = self.lancar(analise, DecisoesDaParte(frozenset({"CRIAR_PESSOA"})), CRIAR)
        self.assertEqual(lancamento.fornecedor.acoes, (Decisao.CRIAR_PESSOA,))


class VersoesDosDadosTests(LancamentoTestBase):
    def test_v1_e_a_unica_versao_armazenada(self):
        analise = self.nova_analise()
        self.assertEqual(analise.versao_dados, 1)

    def test_json_v2_ainda_nao_e_aceito_pela_analise(self):
        # P-09 aprovada, mas a GR-43 ainda confere só as chaves da v1.
        resultado = resultado_da_nota()
        resultado["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        with self.assertRaises(AnaliseError) as contexto:
            criar_analise(self.sessao, resultado)
        self.assertEqual(contexto.exception.codigo, "dados_invalidos")

    def test_f3_ainda_nao_le_o_bloco_fiscal_v2(self):
        resultado = resultado_da_nota()
        resultado["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        nota = conferir_nota(resultado, {"serie": 1})
        self.assertIn(("identidade_fiscal", "identidade_fiscal_insuficiente"),
                      {(p.campo, p.codigo) for p in nota.problemas})


class ConcorrenciaTests(TransactionTestCase):
    """Conexões reais em paralelo: cada thread tem a própria conexão."""

    serialized_rollback = True

    def setUp(self):
        self.sessao = nova_sessao()

    def nova_analise(self):
        analise = criar_analise(self.sessao, resultado_da_nota())
        registrar_correcoes(self.sessao, analise.id, {"serie": 1}, 0)
        return analise

    def lancar(self, analise, esperar=None):
        if esperar is not None:
            esperar.wait(TEMPO_LIMITE)
        return lancar_nota(self.sessao, analise.id, SolicitacaoLancamento(1, CRIAR, CRIAR))

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
        with com_modelo():
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(TEMPO_LIMITE)
        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        return resultados, erros

    def codigo(self, erro):
        return getattr(erro, "codigo", None) or ",".join(codigos(erro))

    def segurar_gravacao(self, gravado, segurar=0.5):
        """Faz a primeira confirmação esperar antes do COMMIT, já com tudo gravado."""
        original = lancamento_nota.registrar_identidade_fiscal
        primeira = threading.Lock()

        def registrar(movimento, identidade):
            resultado = original(movimento, identidade)
            if primeira.acquire(blocking=False):
                gravado.set()
                time.sleep(segurar)
            return resultado

        return mock.patch.object(lancamento_nota, "registrar_identidade_fiscal", side_effect=registrar)

    def test_mesma_nota_em_duas_analises_simultaneas(self):
        primeira, segunda = self.nova_analise(), self.nova_analise()
        gravado = threading.Event()

        with self.segurar_gravacao(gravado) as registrar:
            resultados, erros = self.em_paralelo(
                lambda: self.lancar(primeira), lambda: self.lancar(segunda, esperar=gravado),
            )

        # A segunda passou pela F-3 e pela F-4 (a primeira ainda sem COMMIT) e
        # só foi barrada na identidade fiscal, com tudo desfeito.
        self.assertEqual(registrar.call_count, 2)
        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, self.codigo(e)) for i, e in erros], [(1, "nota_ja_lancada")])
        # Uma pessoa por documento: a segunda reutilizou ou desfez as suas.
        self.assertEqual(Pessoa.objects.count(), 2)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
        segunda.refresh_from_db()
        self.assertEqual(segunda.status, StatusAnalise.PENDENTE)

    def test_mesma_analise_confirmada_duas_vezes_ao_mesmo_tempo(self):
        analise = self.nova_analise()
        gravado = threading.Event()

        with self.segurar_gravacao(gravado) as registrar:
            resultados, erros = self.em_paralelo(
                lambda: self.lancar(analise), lambda: self.lancar(analise, esperar=gravado),
            )

        # A segunda esperou o bloqueio da análise e nem chamou o gravar.
        self.assertEqual(registrar.call_count, 1)
        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, self.codigo(e)) for i, e in erros], [(1, "analise_confirmada")])
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_resultado_so_depois_do_commit(self):
        analise = self.nova_analise()
        vistos = []

        def lancar_e_ler_de_outra_conexao():
            lancamento = self.lancar(analise)
            leitor = threading.Thread(target=lambda: (
                vistos.append(MovimentoConta.objects.filter(pk=lancamento.movimento.pk).exists()),
                connection.close(),
            ))
            leitor.start()
            leitor.join(TEMPO_LIMITE)
            return lancamento

        resultados, erros = self.em_paralelo(lancar_e_ler_de_outra_conexao)

        self.assertEqual(erros, [])
        self.assertEqual(vistos, [True])

    def test_varias_analises_simultaneas_lancam_uma(self):
        analises_da_nota = [self.nova_analise() for _ in range(4)]
        barreira = threading.Barrier(4)

        def lancar(analise):
            barreira.wait(TEMPO_LIMITE)
            return self.lancar(analise)

        resultados, erros = self.em_paralelo(*[lambda a=a: lancar(a) for a in analises_da_nota])

        self.assertEqual(len([r for r in resultados if r is not None]), 1)
        self.assertEqual(sorted(self.codigo(e) for _, e in erros), ["nota_ja_lancada"] * 3)
        self.assertEqual(Pessoa.objects.count(), 2)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
