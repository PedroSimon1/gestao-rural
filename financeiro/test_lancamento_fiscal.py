"""Lançamento (F-5) com a identidade fiscal real: JSON v1 + correções G-01 e JSON v2.

Sem simulação da origem do modelo: a identidade vem da análise (P-09) ou das
correções (G-01) e é revalidada por identificar_nota() e
registrar_identidade_fiscal(). TestCase e TransactionTestCase: rodam só com
as variáveis DB_TEST_* (config/banco_de_teste.py). Documentos fictícios.
"""

import threading
import time
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase

from cadastros.models import Pessoa
from documentos.analises import criar_analise, registrar_correcoes
from documentos.models import StatusAnalise
from documentos.test_fiscal_v2 import resultado_v2
from documentos.testing import CNPJ, nova_sessao, resultado_da_nota

from . import lancamento_nota
from .lancamento_nota import SolicitacaoLancamento, lancar_nota
from .models import MovimentoConta, NotaFiscalLancada
from .test_identidade_fiscal import chave
from .test_lancamento_nota import CRIAR, TEMPO_LIMITE, cadastrar_pessoas, codigos, contagens


class LancamentoFiscalTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()

    def analise(self, resultado, correcoes=None):
        analise = criar_analise(self.sessao, resultado)
        versao = 0
        if correcoes:
            registrar_correcoes(self.sessao, analise.id, correcoes, 0)
            versao = 1
        return analise, versao

    def lancar(self, analise, versao, fornecedor=CRIAR, faturado=CRIAR):
        return lancar_nota(self.sessao, analise.id, SolicitacaoLancamento(versao, fornecedor, faturado))

    def assert_lanca(self, resultado, correcoes, esperada):
        analise, versao = self.analise(resultado, correcoes)
        lancamento = self.lancar(analise, versao)
        nota = lancamento.nota_fiscal
        self.assertEqual(
            (nota.emitente_cnpj, nota.modelo, nota.serie, nota.numero, nota.chave_acesso), esperada
        )
        self.assertEqual(lancamento.movimento.analise_origem_id, analise.id)
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.CONFIRMADA)
        return lancamento

    def assert_recusa(self, codigo, resultado, correcoes=None):
        analise, versao = self.analise(resultado, correcoes)
        antes = contagens()
        with self.assertRaises(ValidationError) as contexto:
            self.lancar(analise, versao)
        self.assertIn(codigo, codigos(contexto.exception))
        self.assertEqual(contagens(), antes)
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)

    def test_v1_com_modelo_e_serie_corrigidos(self):
        self.assert_lanca(resultado_da_nota(), {"modelo": "55", "serie": 1}, (CNPJ, "55", 1, 123, None))

    def test_v1_com_chave_corrigida(self):
        self.assert_lanca(resultado_da_nota(), {"chave_acesso": chave()}, (CNPJ, "55", 1, 123, chave()))

    def test_v2_sem_correcoes(self):
        lancamento = self.assert_lanca(resultado_v2(), None, (CNPJ, "55", 1, 123, None))
        self.assertEqual(Pessoa.objects.count(), 2)
        self.assertEqual(lancamento.movimento.parcelas.count(), 1)

    def test_v2_com_chave(self):
        self.assert_lanca(resultado_v2(chave_acesso=chave()), None, (CNPJ, "55", 1, 123, chave()))

    def test_recusas_fiscais(self):
        casos = (
            ("identidade_fiscal_insuficiente", resultado_da_nota(), {"serie": 1}),
            ("identidade_fiscal_insuficiente", resultado_v2(modelo=None), None),
            ("identidade_fiscal_divergente", resultado_v2(chave_acesso=chave(numero=999)), None),
            ("identidade_fiscal_nao_suportada", resultado_v2(modelo="57"), None),
            ("invalido", resultado_v2(chave_acesso=chave()[:43] + "X"), None),
        )
        for codigo, resultado, correcoes in casos:
            with self.subTest(codigo=codigo):
                self.assert_recusa(codigo, resultado, correcoes)
        self.assertEqual(Pessoa.objects.count(), 0)

    def test_mesma_nota_por_v1_corrigida_e_por_v2(self):
        self.assert_lanca(resultado_da_nota(), {"modelo": "55", "serie": 1}, (CNPJ, "55", 1, 123, None))
        # Outra análise com a chave: mesmos emitente, modelo, série e número.
        self.assert_recusa("nota_ja_lancada", resultado_v2(chave_acesso=chave()))
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_rollback_depois_do_movimento(self):
        analise, versao = self.analise(resultado_v2())
        antes = contagens()
        with mock.patch.object(lancamento_nota, "registrar_identidade_fiscal", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.lancar(analise, versao)
        self.assertEqual(contagens(), antes)
        analise.refresh_from_db()
        self.assertEqual((analise.status, analise.versao_dados), (StatusAnalise.PENDENTE, 2))


class ConcorrenciaFiscalTests(TransactionTestCase):
    """A mesma nota por uma análise v1 corrigida e por uma v2, ao mesmo tempo."""

    serialized_rollback = True

    def test_um_movimento_e_uma_identidade(self):
        cadastrar_pessoas()
        sessao = nova_sessao()
        v1 = criar_analise(sessao, resultado_da_nota())
        registrar_correcoes(sessao, v1.id, {"modelo": "55", "serie": 1}, 0)
        v2 = criar_analise(sessao, resultado_v2(chave_acesso=chave()))
        gravado = threading.Event()
        original = lancamento_nota.registrar_identidade_fiscal
        primeira = threading.Lock()
        resultados, erros = {}, []

        def registrar(movimento, identidade):
            resultado = original(movimento, identidade)
            if primeira.acquire(blocking=False):
                gravado.set()
                time.sleep(0.5)
            return resultado

        def lancar(nome, analise, versao, esperar=None):
            try:
                if esperar is not None:
                    esperar.wait(TEMPO_LIMITE)
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                resultados[nome] = lancar_nota(sessao, analise.id, SolicitacaoLancamento(versao))
            except BaseException as erro:
                erros.append((nome, erro))
            finally:
                connection.close()

        with mock.patch.object(lancamento_nota, "registrar_identidade_fiscal", side_effect=registrar):
            threads = [
                threading.Thread(target=lancar, args=("v1", v1, 1), daemon=True),
                threading.Thread(target=lancar, args=("v2", v2, 0, gravado), daemon=True),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(TEMPO_LIMITE)

        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        self.assertEqual(list(resultados), ["v1"])
        self.assertEqual([(nome, codigos(e)) for nome, e in erros], [("v2", ["nota_ja_lancada"])])
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
        v2.refresh_from_db()
        self.assertEqual(v2.status, StatusAnalise.PENDENTE)
