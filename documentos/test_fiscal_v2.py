"""JSON fiscal v2 e correções fiscais (P-09 e G-01) no PostgreSQL local.

GR-43 (versões de `dados`), F-2 (chave de acesso e modelo corrigíveis) e F-3
(combinação com a identidade fiscal oficial). TestCase: roda só com as
variáveis DB_TEST_* (config/banco_de_teste.py). Documentos fictícios, com DV
calculado; nenhum dado real.
"""

import copy

from django.test import TestCase

from cadastros.models import Papel, Pessoa
from financeiro.test_identidade_fiscal import chave

from .analises import (
    CHAVES_POR_VERSAO, AnaliseError, criar_analise, obter_analise, registrar_correcoes,
)
from .conferencia import conferir_nota
from .test_analises import vencer
from .testing import CNPJ, CPF, nova_sessao, resultado_da_nota

CNPJ_ALFANUMERICO = "12ABC34501DE35"


def resultado_v2(chave_acesso=None, modelo="55", serie="1", fornecedor_cpf=None, cnpj=CNPJ):
    """JSON final v2 (docs/contratos/JSONFiscalV2.schema.json), a partir da v1."""
    resultado = resultado_da_nota()
    resultado["fornecedor"]["cnpj"] = cnpj
    resultado["fornecedor"]["cpf"] = fornecedor_cpf
    resultado["faturado"]["cnpj"] = None
    resultado["validacoes"].update({
        "faturado_cnpj": {"status": "ausente", "motivo": None},
        "fornecedor_cpf": {"status": "ausente", "motivo": None},
        "chave_acesso": {"status": "ausente", "motivo": None},
    })
    resultado["documento_fiscal"] = {"chave_acesso": chave_acesso, "modelo": modelo, "serie": serie}
    return resultado


def problemas(nota):
    return {(p.campo, p.codigo) for p in nota.problemas}


def identidade(nota):
    i = nota.identidade_fiscal
    return i and (i.emitente_cnpj, i.modelo, i.serie, i.numero, i.chave_acesso)


class VersoesDaAnaliseTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()

    def test_versao_reconhecida_pelas_chaves(self):
        v1 = criar_analise(self.sessao, resultado_da_nota())
        v2 = criar_analise(self.sessao, resultado_v2())
        for analise in (v1, v2):
            analise.refresh_from_db()

        self.assertEqual((v1.versao_dados, v2.versao_dados), (1, 2))
        self.assertEqual(v2.dados, resultado_v2())
        self.assertEqual(set(v2.dados), set(CHAVES_POR_VERSAO[2]))
        self.assertNotIn("versao", v2.dados)

    def test_estrutura_invalida_e_versao_desconhecida(self):
        def com(**mudancas):
            resultado = resultado_v2()
            for chave_, valor in mudancas.items():
                if valor is ...:
                    del resultado[chave_]
                else:
                    resultado[chave_] = valor
            return resultado

        fiscal = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        casos = {
            "bloco não é objeto": com(documento_fiscal="55"),
            "bloco sem chave": com(documento_fiscal={"modelo": "55", "serie": "1"}),
            "bloco com chave a mais": com(documento_fiscal={**fiscal, "numero": "123"}),
            "valor não textual": com(documento_fiscal={**fiscal, "modelo": 55}),
            "versão futura": com(versao=3),
            "v2 sem chave da v1": com(itens=...),
        }
        for nome, resultado in casos.items():
            with self.subTest(nome), self.assertRaises(AnaliseError) as contexto:
                criar_analise(self.sessao, resultado)
            self.assertEqual(contexto.exception.codigo, "dados_invalidos")

    def test_v2_com_as_mesmas_protecoes(self):
        analise = criar_analise(self.sessao, resultado_v2())

        with self.assertRaises(AnaliseError) as outra:
            obter_analise(nova_sessao(), analise.id)
        vencer(analise)
        with self.assertRaises(AnaliseError) as vencida:
            obter_analise(self.sessao, analise.id)

        self.assertEqual(outra.exception.codigo, "analise_nao_encontrada")
        self.assertEqual(vencida.exception.codigo, "analise_expirada")

    def test_v1_continua_v1_com_correcoes_fiscais(self):
        analise = criar_analise(self.sessao, resultado_da_nota())

        registrar_correcoes(self.sessao, analise.id, {"modelo": "55", "serie": "001"}, 0)

        analise.refresh_from_db()
        self.assertEqual(analise.versao_dados, 1)
        self.assertEqual(analise.correcoes, {"modelo": "55", "serie": 1})
        self.assertNotIn("documento_fiscal", analise.dados)

    def test_correcao_de_chave_invalida_nao_grava(self):
        analise = criar_analise(self.sessao, resultado_da_nota())
        invalida = chave()[:-1] + str((int(chave()[-1]) + 1) % 10)

        with self.assertRaises(AnaliseError) as contexto:
            registrar_correcoes(self.sessao, analise.id, {"chave_acesso": invalida}, 0)

        self.assertEqual(contexto.exception.campos, ("chave_acesso",))
        self.assertNotIn(invalida, str(contexto.exception))
        analise.refresh_from_db()
        self.assertIsNone(analise.correcoes)


class CombinacaoFiscalTests(TestCase):
    def setUp(self):
        fornecedor = Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste Ltda")
        fornecedor.atribuir_papel(Papel.FORNECEDOR)
        faturado = Pessoa.objects.create(documento=CPF, razao_social="Produtor Teste")
        faturado.atribuir_papel(Papel.FATURADO)

    def test_v2_completo_sem_chave(self):
        nota = conferir_nota(resultado_v2())
        self.assertTrue(nota.sem_problemas, nota.problemas)
        self.assertEqual(identidade(nota), (CNPJ, "55", 1, 123, None))
        self.assertEqual(nota.campos_alterados, ())

    def test_v2_com_chave_coerente_ou_so_com_a_chave(self):
        for modelo, serie in (("55", "001"), (None, None)):
            with self.subTest(modelo=modelo):
                nota = conferir_nota(resultado_v2(chave_acesso=chave(), modelo=modelo, serie=serie))
                self.assertTrue(nota.sem_problemas, nota.problemas)
                self.assertEqual(identidade(nota), (CNPJ, "55", 1, 123, chave()))

    def test_v2_sem_modelo_nem_chave_e_insuficiente(self):
        nota = conferir_nota(resultado_v2(modelo=None))
        self.assertEqual(problemas(nota), {("identidade_fiscal", "identidade_fiscal_insuficiente")})

        corrigida = conferir_nota(resultado_v2(modelo=None), {"modelo": "55"})
        self.assertTrue(corrigida.sem_problemas, corrigida.problemas)
        self.assertEqual(corrigida.campos_alterados, ("modelo",))

    def test_chave_extraida_invalida_bloqueia_ate_ser_corrigida(self):
        invalida = chave()[:-1] + str((int(chave()[-1]) + 1) % 10)
        dados = resultado_v2(chave_acesso=invalida)
        original = copy.deepcopy(dados)

        self.assertIn(("chave_acesso", "invalido"), problemas(conferir_nota(dados)))
        nota = conferir_nota(dados, {"chave_acesso": chave()})

        self.assertTrue(nota.sem_problemas, nota.problemas)
        self.assertEqual(identidade(nota)[4], chave())
        self.assertEqual(dados, original)

    def test_chave_divergente(self):
        for dados, correcoes in (
            (resultado_v2(chave_acesso=chave(numero=999)), None),
            (resultado_da_nota(), {"chave_acesso": chave(serie=2), "serie": 1}),
            (resultado_v2(chave_acesso=chave()), {"modelo": "65"}),
        ):
            with self.subTest(correcoes=correcoes):
                self.assertIn(("identidade_fiscal", "identidade_fiscal_divergente"),
                              problemas(conferir_nota(dados, correcoes)))

    def test_modelo_nao_suportado_ou_invalido(self):
        self.assertIn(("identidade_fiscal", "identidade_fiscal_nao_suportada"),
                      problemas(conferir_nota(resultado_v2(modelo="57"))))
        self.assertIn(("modelo", "invalido"), problemas(conferir_nota(resultado_v2(modelo="5A"))))
        self.assertIn(("serie", "invalido"), problemas(conferir_nota(resultado_v2(serie="A1"))))

    def test_v1_com_correcoes_g01(self):
        casos = (
            ({"serie": 1, "modelo": "55"}, (CNPJ, "55", 1, 123, None)),
            ({"chave_acesso": chave()}, (CNPJ, "55", 1, 123, chave())),
        )
        for correcoes, esperada in casos:
            with self.subTest(correcoes=correcoes):
                nota = conferir_nota(resultado_da_nota(), correcoes)
                self.assertTrue(nota.sem_problemas, nota.problemas)
                self.assertEqual(identidade(nota), esperada)

    def test_v1_so_com_a_serie_continua_insuficiente(self):
        self.assertIn(("identidade_fiscal", "identidade_fiscal_insuficiente"),
                      problemas(conferir_nota(resultado_da_nota(), {"serie": 1})))

    def test_emitente_com_cpf_ou_documento_ambiguo(self):
        so_cpf = conferir_nota(resultado_v2(cnpj=None, fornecedor_cpf=CPF))
        self.assertIn(("identidade_fiscal", "identidade_fiscal_nao_suportada"), problemas(so_cpf))

        ambiguo = resultado_v2(fornecedor_cpf=CPF)
        self.assertIn(("fornecedor.documento", "escolha_necessaria"),
                      problemas(conferir_nota(ambiguo)))
        escolhido = conferir_nota(ambiguo, {"fornecedor.documento": CNPJ})
        self.assertTrue(escolhido.sem_problemas, escolhido.problemas)

    def test_chave_com_cnpj_alfanumerico(self):
        Pessoa.objects.create(documento=CNPJ_ALFANUMERICO, razao_social="Emitente Alfa").atribuir_papel(
            Papel.FORNECEDOR
        )
        dados = resultado_v2(chave_acesso=chave(cnpj=CNPJ_ALFANUMERICO), cnpj=CNPJ_ALFANUMERICO)
        nota = conferir_nota(dados)
        self.assertTrue(nota.sem_problemas, nota.problemas)
        self.assertEqual(identidade(nota)[0], CNPJ_ALFANUMERICO)
