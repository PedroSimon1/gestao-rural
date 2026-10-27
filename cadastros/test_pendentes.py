"""Cadastro pendente (GR-22, F-6) no PostgreSQL local de teste.

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

from documentos.analises import criar_analise, registrar_correcoes
from documentos.models import StatusAnalise
from documentos.test_fiscal_v2 import resultado_v2
from documentos.testing import CNPJ as CNPJ_DA_NOTA, CPF as CPF_DA_NOTA, nova_sessao
from financeiro.lancamento_nota import DecisoesDaParte, SolicitacaoLancamento, lancar_nota
from financeiro.models import MovimentoConta
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

from .models import Classificacao, Papel, PapelPessoa, Pessoa, SituacaoDocumental, Status
from .pendentes import (
    CadastroPendente, listar_incompletos, regularizar_cadastro_pendente, salvar_cadastro_pendente,
)
from .resolucao import Decisao
from .test_models import (
    CNPJ, CNPJ_ALFANUMERICO, CNPJ_DV_INVALIDO, CPF, CPF_DV_INVALIDO, CPF_FORMATADO, criar_pessoa,
)

FORNECEDOR = Papel.FORNECEDOR
FATURADO = Papel.FATURADO
TEMPO_LIMITE = 30


def salvar(nome="Produtor Sem Documento", papel=FATURADO, **extra):
    return salvar_cadastro_pendente(nome, papel, consentimento=True, **extra)


class PendenteTestBase(TestCase):
    def assert_codigo(self, codigo, funcao, *args, **kwargs):
        with self.assertRaises(ValidationError) as contexto:
            funcao(*args, **kwargs)
        self.assertEqual(contexto.exception.code, codigo)
        return contexto.exception

    def contagens(self):
        return Pessoa.objects.count(), PapelPessoa.objects.count()


class SalvarTests(PendenteTestBase):
    def test_salva_incompleto_com_o_papel_escolhido(self):
        cadastro = salvar("  Produtor   Sem Documento ", FATURADO, documento_extraido=CPF_DV_INVALIDO)

        pessoa = Pessoa.objects.get()
        self.assertIsInstance(cadastro, CadastroPendente)
        self.assertEqual(cadastro, CadastroPendente(
            pessoa.pk, "Produtor Sem Documento", Status.ATIVO, ((FATURADO, Status.ATIVO),)
        ))
        self.assertEqual(pessoa.situacao_documental, SituacaoDocumental.INCOMPLETO)
        self.assertIsNone(pessoa.documento)
        self.assertIsNone(pessoa.tipo_documento)

    def test_documento_ausente_ou_invalido_nunca_e_guardado(self):
        for documento in (None, "", "  ", CPF_DV_INVALIDO, CNPJ_DV_INVALIDO, "123"):
            with self.subTest(documento=documento):
                salvar(documento_extraido=documento)
        self.assertFalse(Pessoa.objects.exclude(documento=None).exists())
        self.assertEqual(Pessoa.objects.incompletas().count(), 6)

    def test_sem_consentimento_nada_e_gravado(self):
        for consentimento in (False, None, "true", 1, "sim"):
            with self.subTest(consentimento=consentimento):
                self.assert_codigo("consentimento_ausente", salvar_cadastro_pendente,
                                   "Produtor", FATURADO, consentimento=consentimento)
        with self.assertRaises(TypeError):
            salvar_cadastro_pendente("Produtor", FATURADO)
        self.assertEqual(self.contagens(), (0, 0))

    def test_documento_valido_exige_cadastro_completo(self):
        criar_pessoa(CPF, "Já Cadastrado")
        for documento in (CPF, CPF_FORMATADO, CNPJ, CNPJ_ALFANUMERICO):
            with self.subTest(documento=documento):
                self.assert_codigo("documento_valido", salvar, documento_extraido=documento)
        self.assertEqual(Pessoa.objects.incompletas().count(), 0)

    def test_mesmo_nome_nao_identifica_pessoa(self):
        # Sem mesclagem por nome (D-04): o usuário escolhe na listagem.
        primeiro = salvar("Produtor Repetido")
        segundo = salvar("Produtor Repetido")

        self.assertNotEqual(primeiro.id, segundo.id)
        self.assertEqual([c.id for c in listar_incompletos()], [primeiro.id, segundo.id])

    def test_nome_invalido(self):
        for nome, codigo in ((None, "nome_ausente"), ("   ", "nome_ausente"),
                             ("x" * 256, "nome_invalido"), ("Nome\x00", "nome_invalido"),
                             ("Nome\ud800", "nome_invalido")):
            with self.subTest(codigo=codigo, nome=repr(nome)[:20]):
                self.assert_codigo(codigo, salvar, nome)
        self.assertEqual(self.contagens(), (0, 0))

    def test_entradas_mal_formadas(self):
        with self.assertRaises(ValueError):
            salvar(papel="SOCIO")
        with self.assertRaises(TypeError):
            salvar(nome=123)
        with self.assertRaises(TypeError):
            salvar(documento_extraido=12345678909)
        self.assertEqual(self.contagens(), (0, 0))

    def test_falha_ao_atribuir_o_papel_desfaz_a_pessoa(self):
        with mock.patch.object(Pessoa, "atribuir_papel", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                salvar()
        self.assertEqual(self.contagens(), (0, 0))

    def test_nao_toca_a_analise_nem_o_financeiro(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_v2())

        salvar()

        analise.refresh_from_db()
        self.assertEqual((analise.status, analise.versao_correcoes), (StatusAnalise.PENDENTE, 0))
        self.assertEqual(analise.dados, resultado_v2())
        self.assertEqual(MovimentoConta.objects.count(), 0)


class ListarTests(PendenteTestBase):
    def test_so_incompletos_em_ordem_de_nome_com_papeis_e_status(self):
        criar_pessoa(CPF, "Aaa Completo")
        b = salvar("Bbb Pendente", FORNECEDOR)
        a = salvar("Abc Pendente", FATURADO)
        Pessoa.objects.get(pk=a.id).atribuir_papel(FORNECEDOR)
        inativo = salvar("Ccc Inativo", FATURADO)
        Pessoa.objects.get(pk=inativo.id).inativar()

        lista = listar_incompletos()

        self.assertEqual([c.id for c in lista], [a.id, b.id, inativo.id])
        self.assertEqual(lista[0].papeis, ((FATURADO, Status.ATIVO), (FORNECEDOR, Status.ATIVO)))
        self.assertEqual(lista[2].status, Status.INATIVO)
        self.assertEqual([c.id for c in listar_incompletos(FORNECEDOR)], [a.id, b.id])
        self.assertEqual([c.id for c in listar_incompletos(FATURADO)], [a.id, inativo.id])

    def test_regularizado_sai_da_lista(self):
        cadastro = salvar()
        regularizar_cadastro_pendente(cadastro.id, CPF)
        self.assertEqual(listar_incompletos(), ())

    def test_numero_fixo_de_consultas(self):
        for i in range(5):
            salvar(f"Pendente {i}")
        with CaptureQueriesContext(connection) as consultas:
            listar_incompletos(FATURADO)
        self.assertEqual(len(consultas), 2)

    def test_papel_desconhecido(self):
        with self.assertRaises(ValueError):
            listar_incompletos("SOCIO")


class RegularizarTests(PendenteTestBase):
    def test_completa_o_mesmo_registro_preservando_os_papeis(self):
        cadastro = salvar()

        pessoa = regularizar_cadastro_pendente(cadastro.id, CPF_FORMATADO)

        pessoa.refresh_from_db()
        self.assertEqual(pessoa.pk, cadastro.id)
        self.assertEqual((pessoa.documento, pessoa.situacao_documental), (CPF, SituacaoDocumental.COMPLETO))
        self.assertEqual(list(pessoa.papeis.values_list("papel", flat=True)), [FATURADO])
        self.assertEqual(Pessoa.objects.count(), 1)

    def test_documento_ausente_ou_invalido(self):
        cadastro = salvar()
        for documento, codigo in ((None, "documento_ausente"), (" ", "documento_ausente"),
                                  (CPF_DV_INVALIDO, "documento_invalido"), ("123", "documento_invalido")):
            with self.subTest(documento=documento):
                self.assert_codigo(codigo, regularizar_cadastro_pendente, cadastro.id, documento)
        self.assertIsNone(Pessoa.objects.get(pk=cadastro.id).documento)

    def test_documento_de_outra_pessoa(self):
        criar_pessoa(CPF, "Dono do CPF")
        cadastro = salvar()

        self.assert_codigo("documento_em_uso", regularizar_cadastro_pendente, cadastro.id, CPF)

        pessoa = Pessoa.objects.get(pk=cadastro.id)
        self.assertEqual(pessoa.situacao_documental, SituacaoDocumental.INCOMPLETO)

    def test_selecao_invalida(self):
        completa = criar_pessoa(CPF, "Completa")
        cadastro = salvar()
        regularizar_cadastro_pendente(cadastro.id, CNPJ)
        for pessoa_id in (completa.pk, cadastro.id, 999999):
            with self.subTest(pessoa_id=pessoa_id):
                self.assert_codigo("selecao_invalida", regularizar_cadastro_pendente, pessoa_id, CNPJ_ALFANUMERICO)
        with self.assertRaises(TypeError):
            regularizar_cadastro_pendente(str(cadastro.id), CPF)


class BloqueioDoLancamentoTests(PendenteTestBase):
    """O incompleto salvo pela F-6 não entra em lançamento até a regularização."""

    def setUp(self):
        self.fornecedor = criar_pessoa(CNPJ_DA_NOTA, "Fornecedor Teste Ltda")
        self.fornecedor.atribuir_papel(FORNECEDOR)

    def test_registrar_movimento_recusa(self):
        pendente = Pessoa.objects.get(pk=salvar().id)
        classificacao = Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO")

        self.assert_codigo("pessoa_incompleta", registrar_movimento, DadosMovimento(
            tipo="APAGAR", origem="NOTA_FISCAL", contraparte=self.fornecedor, faturado=pendente,
            valor_total=Decimal("10.00"),
            classificacoes=(ItemClassificacao(classificacao, principal=True),),
            analise_origem_id=uuid.uuid4(),
            parcelas=(ItemParcela(1, date(2026, 11, 1), Decimal("10.00")),),
        ))
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_selecao_no_lancamento_so_com_regularizacao(self):
        # Nota v2 com o CPF do faturado ilegível; o usuário corrige o CPF e
        # seleciona o cadastro pendente salvo antes (F-4/F-5, sem mudança).
        cadastro = salvar("Produtor Teste")
        sessao = nova_sessao()
        resultado = resultado_v2()
        resultado["faturado"]["cpf"] = CPF_DV_INVALIDO
        analise = criar_analise(sessao, resultado)
        registrar_correcoes(sessao, analise.id, {"faturado.documento": CPF_DA_NOTA}, 0)

        def lancar(decisoes):
            return lancar_nota(sessao, analise.id, SolicitacaoLancamento(
                1, faturado=DecisoesDaParte(frozenset(decisoes), pessoa_incompleta_id=cadastro.id),
            ))

        with self.assertRaises(ValidationError) as contexto:
            lancar(set())
        self.assertEqual([e.code for e in contexto.exception.error_list], ["pessoa_incompleta"])
        self.assertEqual(MovimentoConta.objects.count(), 0)

        lancamento = lancar({Decisao.REGULARIZAR})
        self.assertEqual(lancamento.movimento.faturado_id, cadastro.id)
        self.assertEqual(Pessoa.objects.get(pk=cadastro.id).documento, CPF_DA_NOTA)

    def test_regularizado_antes_e_encontrado_pelo_documento(self):
        cadastro = salvar("Produtor Teste")
        regularizar_cadastro_pendente(cadastro.id, CPF_DA_NOTA)
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_v2())

        lancamento = lancar_nota(sessao, analise.id, SolicitacaoLancamento(0))

        self.assertEqual(lancamento.faturado.pessoa.pk, cadastro.id)
        self.assertEqual(lancamento.faturado.acoes, ())


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

    def regularizar(self, pessoa_id, gravado=None, esperar=None):
        if esperar is not None:
            esperar.wait(TEMPO_LIMITE)
        # A primeira segura o COMMIT para a segunda chegar com ela em aberto.
        with transaction.atomic():
            pessoa = regularizar_cadastro_pendente(pessoa_id, CPF)
            if gravado is not None:
                gravado.set()
                time.sleep(0.5)
        return pessoa

    def test_mesmo_cadastro_regularizado_duas_vezes(self):
        cadastro = salvar()
        gravado = threading.Event()

        resultados, erros = self.em_paralelo(
            lambda: self.regularizar(cadastro.id, gravado=gravado),
            lambda: self.regularizar(cadastro.id, esperar=gravado),
        )

        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, e.code) for i, e in erros], [(1, "selecao_invalida")])
        self.assertEqual(Pessoa.objects.get(pk=cadastro.id).documento, CPF)

    def test_dois_cadastros_com_o_mesmo_documento(self):
        primeiro, segundo = salvar("Primeiro"), salvar("Segundo")
        gravado = threading.Event()

        resultados, erros = self.em_paralelo(
            lambda: self.regularizar(primeiro.id, gravado=gravado),
            lambda: self.regularizar(segundo.id, esperar=gravado),
        )

        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, e.code) for i, e in erros], [(1, "documento_em_uso")])
        self.assertEqual(list(Pessoa.objects.filter(documento=CPF).values_list("pk", flat=True)),
                         [primeiro.id])
        self.assertIsNone(Pessoa.objects.get(pk=segundo.id).documento)
