"""Correções da conferência em AnalisePendente (GR-22, F-2) no PostgreSQL local.

TestCase e TransactionTestCase: rodam só com as variáveis DB_TEST_*
(config/banco_de_teste.py). Documentos fictícios, com DV calculado; nenhum
dado real.
"""

import threading
import time
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from .analises import (
    CHAVE_DA_SESSAO, AnaliseError, cancelar_analise, confirmar_analise, correcoes_da_confirmacao,
    criar_analise, descartar_analises, expirar_analises, obter_analise, registrar_correcoes,
)
from .correcoes import CAMPOS_CORRIGIVEIS, validar_correcoes
from .models import AnalisePendente, StatusAnalise
from financeiro.test_identidade_fiscal import chave

from .test_analises import vencer
from .testing import nova_sessao, resultado_da_nota

CPF = "12345678909"
CNPJ_ALFANUMERICO = "12ABC34501DE35"
TEMPO_LIMITE = 20

CORRECOES = {
    "fornecedor.documento": "12.abc.345/01de-35",
    "fornecedor.razao_social": "  Fornecedor   Corrigido  ",
    "faturado.documento": "123.456.789-09",
    "faturado.nome": "Produtor Corrigido",
    "tipo_despesa": " infraestrutura_e_utilidades ",
    "numero_nota": "000123",
    "serie": "001",
    # G-01: chave como impressa (com espaços) e modelo.
    "chave_acesso": " ".join(chave()[i:i + 4] for i in range(0, 44, 4)),
    "modelo": " 55 ",
    "data_emissao": "2026-10-02",
    "valor_total": "300.5",
    "parcelas": [
        {"numero": 1, "data_vencimento": "2026-11-01", "valor": "150.25"},
        {"numero": "2", "data_vencimento": "2026-12-01", "valor": Decimal("150.25")},
    ],
}
NORMALIZADAS = {
    "fornecedor.documento": CNPJ_ALFANUMERICO,
    "fornecedor.razao_social": "Fornecedor Corrigido",
    "faturado.documento": CPF,
    "faturado.nome": "Produtor Corrigido",
    "tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES",
    "numero_nota": 123,
    "serie": 1,
    "chave_acesso": chave(),
    "modelo": "55",
    "data_emissao": "2026-10-02",
    "valor_total": "300.50",
    "parcelas": [
        {"numero": 1, "data_vencimento": "2026-11-01", "valor": "150.25"},
        {"numero": 2, "data_vencimento": "2026-12-01", "valor": "150.25"},
    ],
}


def assert_erro(teste, codigo, funcao, *args, **kwargs):
    with teste.assertRaises(AnaliseError) as contexto:
        funcao(*args, **kwargs)
    teste.assertEqual(contexto.exception.codigo, codigo)
    return contexto.exception


class ValidacaoDosCamposTests(SimpleTestCase):
    def test_lista_fechada_da_d02_d03_e_g01(self):
        self.assertEqual(set(CAMPOS_CORRIGIVEIS), set(NORMALIZADAS))
        for proibido in ("documento_fiscal", "emitente_cnpj", "itens", "validacoes", "fornecedor",
                         "dados"):
            self.assertNotIn(proibido, CAMPOS_CORRIGIVEIS)

    def test_normaliza_todos_os_campos(self):
        self.assertEqual(validar_correcoes(CORRECOES), (NORMALIZADAS, []))

    def test_documento_de_qualquer_tipo_em_qualquer_papel(self):
        # D-03: sem tipo deduzido pelo papel.
        normalizadas, invalidos = validar_correcoes({
            "fornecedor.documento": CPF, "faturado.documento": CNPJ_ALFANUMERICO,
        })
        self.assertEqual(invalidos, [])
        self.assertEqual(normalizadas["fornecedor.documento"], CPF)

    def test_valores_invalidos(self):
        casos = {
            "fornecedor.documento": ["12345678900", "", 12345678909, None],
            "faturado.nome": ["   ", "x" * 256, 1, "Nome\x00", "Nome\x07", "Nome\ud800"],
            "tipo_despesa": ["com espaço", "ÇÃO", "X" * 61, None],
            "numero_nota": [0, 1_000_000_000, "12a", True, 1.0, "²", "1" * 5000,
                            "0" * 5000 + "1"],
            "serie": [-1, 1000, "1-A", "9" * 5000],
            "chave_acesso": [chave()[:-1] + str((int(chave()[-1]) + 1) % 10), chave()[:43], "",
                             int(chave()), None, "x" * 5000],
            "modelo": ["5", "555", "5A", 55, None, ""],
            "data_emissao": ["01/10/2026", "2026-02-30", "2026-1-1", 20261001],
            "valor_total": ["0", "-1", "1.005", "abc", 150.0, "NaN", "Infinity", "10000000000",
                            "1e3", "1_000", "+5", "١٠", "150,25", "1.250", "1" * 5000],
            "parcelas": [
                [], {}, "x", [{"numero": 1, "valor": "1.00"}],
                [{"numero": 0, "data_vencimento": "2026-11-01", "valor": "1.00"}],
                [{"numero": 1, "data_vencimento": "2026-11-01", "valor": "1.00", "extra": 1}],
                [{"numero": 1, "data_vencimento": "2026-11-01", "valor": "1.00"}] * 121,
                [{"numero": "1" * 5000, "data_vencimento": "2026-11-01", "valor": "1.00"}],
            ],
        }
        for campo, valores in casos.items():
            for valor in valores:
                with self.subTest(campo=campo, valor=str(valor)[:30]):
                    self.assertEqual(validar_correcoes({campo: valor}), ({}, [campo]))

    def test_valores_no_formato_aceito(self):
        self.assertEqual(
            [validar_correcoes({"valor_total": v})[0]["valor_total"]
             for v in ("1250", "1250.5", " 1250.00 ", Decimal("1250.10"))],
            ["1250.00", "1250.50", "1250.00", "1250.10"],
        )

    def test_campo_nao_autorizado_nao_ecoa_o_nome(self):
        normalizadas, invalidos = validar_correcoes({
            "documento_fiscal": {"modelo": "55"}, "<script>": "x", "emitente_cnpj": "1",
        })
        self.assertEqual((normalizadas, invalidos), ({}, ["campo_nao_autorizado"]))


class RegistrarCorrecoesTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())

    def recarregar(self):
        self.analise.refresh_from_db()
        return self.analise

    def test_grava_separado_dos_dados_extraidos(self):
        sessao_antes = dict(self.sessao)

        atualizada = registrar_correcoes(self.sessao, self.analise.id, CORRECOES, 0)

        analise = self.recarregar()
        self.assertEqual(atualizada.versao_correcoes, 1)
        self.assertEqual(analise.correcoes, NORMALIZADAS)
        self.assertEqual(analise.campos_corrigidos, sorted(NORMALIZADAS))
        self.assertEqual(analise.versao_correcoes, 1)
        # Os dados extraídos não mudam, e nada vai para a sessão (cookie).
        self.assertEqual(analise.dados, resultado_da_nota())
        self.assertEqual(self.sessao, sessao_antes)

    def test_substitui_o_conjunto_inteiro(self):
        registrar_correcoes(self.sessao, self.analise.id, CORRECOES, 0)

        registrar_correcoes(self.sessao, self.analise.id, {"serie": 2}, 1)

        analise = self.recarregar()
        self.assertEqual(analise.correcoes, {"serie": 2})
        self.assertEqual(analise.campos_corrigidos, ["serie"])
        self.assertEqual(analise.versao_correcoes, 2)

    def test_dicionario_vazio_apaga_as_correcoes(self):
        registrar_correcoes(self.sessao, self.analise.id, CORRECOES, 0)

        registrar_correcoes(self.sessao, self.analise.id, {}, 1)

        analise = self.recarregar()
        self.assertIsNone(analise.correcoes)
        self.assertEqual(analise.campos_corrigidos, [])
        self.assertEqual(analise.versao_correcoes, 2)

    def test_obter_devolve_extraido_e_corrigido(self):
        registrar_correcoes(self.sessao, self.analise.id, {"serie": "3"}, 0)

        analise = obter_analise(self.sessao, self.analise.id)

        self.assertEqual((analise.dados, analise.correcoes), (resultado_da_nota(), {"serie": 3}))

    def test_versao_desatualizada_nao_grava(self):
        registrar_correcoes(self.sessao, self.analise.id, {"serie": 1}, 0)

        assert_erro(self, "correcoes_desatualizadas", registrar_correcoes,
                    self.sessao, self.analise.id, {"serie": 9}, 0)

        analise = self.recarregar()
        self.assertEqual((analise.correcoes, analise.versao_correcoes), ({"serie": 1}, 1))

    def test_versao_que_nao_e_inteiro(self):
        for versao in (None, "0", True, 0.0):
            with self.subTest(versao=versao), self.assertRaises(TypeError):
                registrar_correcoes(self.sessao, self.analise.id, {"serie": 1}, versao)
        self.assertEqual(self.recarregar().versao_correcoes, 0)

    def test_correcao_invalida_nao_grava_nem_ecoa_valores(self):
        erro = assert_erro(
            self, "correcao_invalida", registrar_correcoes, self.sessao, self.analise.id,
            {"faturado.documento": "12345678900", "serie": 1, "validacoes": "segredo"}, 0,
        )

        self.assertEqual(erro.campos, ("campo_nao_autorizado", "faturado.documento"))
        for texto in (str(erro), erro.mensagem, repr(erro.campos)):
            self.assertNotIn("12345678900", texto)
            self.assertNotIn("segredo", texto)
        analise = self.recarregar()
        self.assertEqual((analise.correcoes, analise.versao_correcoes), (None, 0))

    def test_entrada_que_nao_e_dicionario(self):
        for correcoes in (None, [], "serie=1"):
            with self.subTest(correcoes=correcoes):
                assert_erro(self, "correcao_invalida", registrar_correcoes,
                            self.sessao, self.analise.id, correcoes, 0)

    def test_outra_sessao_nao_corrige(self):
        for sessao in (nova_sessao(), {}, {CHAVE_DA_SESSAO: self.analise.dono_hash}):
            with self.subTest(sessao=sessao):
                assert_erro(self, "analise_nao_encontrada", registrar_correcoes,
                            sessao, self.analise.id, {"serie": 1}, 0)
        self.assertIsNone(self.recarregar().correcoes)

    def test_estados_finais_e_prazo(self):
        cancelar_analise(self.sessao, self.analise.id)
        assert_erro(self, "analise_cancelada", registrar_correcoes,
                    self.sessao, self.analise.id, {"serie": 1}, 0)

        vencida = criar_analise(self.sessao, resultado_da_nota())
        vencer(vencida)
        assert_erro(self, "analise_expirada", registrar_correcoes,
                    self.sessao, vencida.id, {"serie": 1}, 0)
        vencida.refresh_from_db()
        self.assertEqual(vencida.status, StatusAnalise.EXPIRADA)

    def test_dentro_de_outra_transacao_e_recusado(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            registrar_correcoes(self.sessao, self.analise.id, {"serie": 1}, 0)


class CicloDeVidaTests(TestCase):
    """T-03: na finalização, correções apagadas; ficam só os nomes dos campos."""

    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())
        registrar_correcoes(self.sessao, self.analise.id, {"serie": 1, "faturado.nome": "X"}, 0)

    def assert_finalizada(self, status):
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, status)
        self.assertIsNone(self.analise.dados)
        self.assertIsNone(self.analise.correcoes)
        self.assertEqual(self.analise.campos_corrigidos, ["faturado.nome", "serie"])
        self.assertEqual(self.analise.versao_correcoes, 1)

    def test_confirmar(self):
        confirmar_analise(self.sessao, self.analise.id, lambda *args: None)
        self.assert_finalizada(StatusAnalise.CONFIRMADA)

    def test_cancelar(self):
        cancelar_analise(self.sessao, self.analise.id)
        self.assert_finalizada(StatusAnalise.CANCELADA)

    def test_expirar_ao_acessar(self):
        vencer(self.analise)
        with self.assertRaises(AnaliseError):
            obter_analise(self.sessao, self.analise.id)
        self.assert_finalizada(StatusAnalise.EXPIRADA)

    def test_limpeza_em_massa(self):
        vencer(self.analise)
        self.assertEqual(expirar_analises(), 1)
        self.assert_finalizada(StatusAnalise.EXPIRADA)

    def test_logout(self):
        self.assertEqual(descartar_analises(self.sessao), 1)
        self.assert_finalizada(StatusAnalise.CANCELADA)

    def test_banco_recusa_correcoes_em_estado_final(self):
        agora = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnalisePendente.objects.filter(pk=self.analise.pk).update(
                status=StatusAnalise.CANCELADA, dados=None, finalizado_em=agora
            )


class ConfirmacaoComCorrecoesTests(TestCase):
    """G-03: `gravar(dados, analise_id)` não muda; as correções vêm de
    correcoes_da_confirmacao(), só dentro da confirmação."""

    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())
        registrar_correcoes(self.sessao, self.analise.id, CORRECOES, 0)

    def test_gravar_le_as_correcoes_sem_mudar_a_assinatura(self):
        vistos = []

        def gravar(dados, analise_id):
            vistos.append((dados, correcoes_da_confirmacao(analise_id)))
            return "ok"

        self.assertEqual(confirmar_analise(self.sessao, self.analise.id, gravar), "ok")
        self.assertEqual(vistos, [(resultado_da_nota(), NORMALIZADAS)])

    def test_sem_correcoes_devolve_dicionario_vazio(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())

        confirmar_analise(sessao, analise.id, lambda dados, i: self.assertEqual(
            correcoes_da_confirmacao(i), {}))

    def test_copia_nao_altera_a_analise(self):
        def gravar(dados, analise_id):
            correcoes_da_confirmacao(analise_id)["serie"] = 999
            return correcoes_da_confirmacao(analise_id)["serie"]

        self.assertEqual(confirmar_analise(self.sessao, self.analise.id, gravar), 1)

    def test_fora_da_confirmacao_ou_de_outra_analise(self):
        with self.assertRaises(RuntimeError):
            correcoes_da_confirmacao(self.analise.id)
        outra = criar_analise(self.sessao, resultado_da_nota())

        def gravar(dados, analise_id):
            correcoes_da_confirmacao(outra.id)

        with self.assertRaises(RuntimeError):
            confirmar_analise(self.sessao, self.analise.id, gravar)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)
        # Depois de uma falha, o contexto da confirmação não fica preso.
        with self.assertRaises(RuntimeError):
            correcoes_da_confirmacao(self.analise.id)

    def test_versao_conferida_na_confirmacao(self):
        assert_erro(
            self, "correcoes_desatualizadas", confirmar_analise, self.sessao, self.analise.id,
            lambda *args: self.fail("gravar não deveria ser chamado"), versao_correcoes=0,
        )
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)

        self.assertEqual(
            confirmar_analise(self.sessao, self.analise.id, lambda *a: 1, versao_correcoes=1), 1
        )

    def test_versao_em_texto_e_recusada(self):
        # A view precisa converter para int (contrato GR-51, 4.3).
        with self.assertRaises(TypeError):
            confirmar_analise(self.sessao, self.analise.id, lambda *a: None, versao_correcoes="1")
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)

    def test_chamada_antiga_continua_valendo(self):
        # Compatibilidade com a GR-43: sem versao_correcoes, como antes.
        self.assertEqual(confirmar_analise(self.sessao, self.analise.id, lambda d, i: d), resultado_da_nota())


class ConcorrenciaTests(TransactionTestCase):
    serialized_rollback = True

    def em_paralelo(self, *chamadas):
        resultados, erros = [None] * len(chamadas), []

        def executar(indice, chamada):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                resultados[indice] = chamada()
            except BaseException as erro:
                erros.append((indice, erro))
            finally:
                connection.close()

        threads = [threading.Thread(target=executar, args=(i, c), daemon=True)
                   for i, c in enumerate(chamadas)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TEMPO_LIMITE)
        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        return resultados, erros

    def test_duas_abas_com_a_mesma_versao(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        barreira = threading.Barrier(2)

        def corrigir(serie):
            barreira.wait(TEMPO_LIMITE)
            return registrar_correcoes(dict(sessao), analise.id, {"serie": serie}, 0).versao_correcoes

        resultados, erros = self.em_paralelo(lambda: corrigir(1), lambda: corrigir(2))

        self.assertEqual([r for r in resultados if r is not None], [1])
        self.assertEqual([e.codigo for _, e in erros], ["correcoes_desatualizadas"])
        analise.refresh_from_db()
        self.assertEqual(analise.versao_correcoes, 1)
        self.assertIn(analise.correcoes["serie"], (1, 2))

    def test_correcao_durante_a_confirmacao(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        gravando = threading.Event()

        def gravar(dados, analise_id):
            gravando.set()
            time.sleep(0.3)
            return correcoes_da_confirmacao(analise_id)

        esperou = []

        def corrigir():
            gravando.wait(TEMPO_LIMITE)
            inicio = time.monotonic()
            try:
                registrar_correcoes(dict(sessao), analise.id, {"serie": 5}, 0)
            finally:
                esperou.append(time.monotonic() - inicio)

        resultados, erros = self.em_paralelo(
            lambda: confirmar_analise(dict(sessao), analise.id, gravar), corrigir
        )

        # A correção espera o bloqueio e encontra a análise já confirmada;
        # a confirmação usou o conjunto que existia (nenhum).
        self.assertEqual(resultados[0], {})
        self.assertEqual([(i, e.codigo) for i, e in erros], [(1, "analise_confirmada")])
        # Esperou o bloqueio da confirmação (que dormiu 0,3 s depois do sinal).
        self.assertGreater(esperou[0], 0.15)
        analise.refresh_from_db()
        self.assertEqual((analise.status, analise.correcoes), (StatusAnalise.CONFIRMADA, None))

    def test_logout_durante_a_correcao_na_confirmacao(self):
        # O descarte do logout espera o bloqueio e não desfaz o que foi gravado.
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        registrar_correcoes(sessao, analise.id, {"serie": 1}, 0)
        gravando = threading.Event()

        def gravar(dados, analise_id):
            gravando.set()
            time.sleep(0.3)
            return correcoes_da_confirmacao(analise_id)

        def descartar():
            gravando.wait(TEMPO_LIMITE)
            return descartar_analises(dict(sessao))

        resultados, erros = self.em_paralelo(
            lambda: confirmar_analise(dict(sessao), analise.id, gravar), descartar
        )

        self.assertEqual((resultados, erros), ([{"serie": 1}, 0], []))
        analise.refresh_from_db()
        self.assertEqual((analise.status, analise.correcoes, analise.campos_corrigidos),
                         (StatusAnalise.CONFIRMADA, None, ["serie"]))

    def test_confirmacao_com_versao_antiga_depois_de_outra_aba_corrigir(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        registrar_correcoes(sessao, analise.id, {"serie": 1}, 0)
        registrar_correcoes(sessao, analise.id, {"serie": 2}, 1)  # outra aba

        with self.assertRaises(AnaliseError) as contexto:
            confirmar_analise(sessao, analise.id, lambda *a: None, versao_correcoes=1)

        self.assertEqual(contexto.exception.codigo, "correcoes_desatualizadas")
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)
