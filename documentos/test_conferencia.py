"""Combinação e revalidação de extraído + corrigido (GR-22, F-3) no PostgreSQL local.

TestCase: roda só com as variáveis DB_TEST_* (config/banco_de_teste.py).
Documentos fictícios, com DV calculado; nenhum dado real. As categorias
iniciais de DESPESA vêm da migration 0003 de cadastros.
"""

import copy
import uuid
from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from cadastros.consultas import Situacao
from cadastros.models import Classificacao, Papel, PapelPessoa, Pessoa
from financeiro.identidade_fiscal import (
    IdentidadeFiscal, identificar_nota, registrar_identidade_fiscal,
)
from financeiro.models import MovimentoConta, NotaFiscalLancada
from financeiro.servicos import (
    DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento, validar_parcelas,
)

from .analises import confirmar_analise, correcoes_da_confirmacao, criar_analise, registrar_correcoes
from .conferencia import Problema, conferir_nota
from .testing import CNPJ, CPF, nova_sessao, resultado_da_nota

CNPJ_ALFANUMERICO = "12ABC34501DE35"
IDENTIDADE = IdentidadeFiscal(emitente_cnpj=CNPJ, modelo="55", serie=1, numero=123)


def problemas(nota):
    return {(p.campo, p.codigo) for p in nota.problemas}


def cadastrar_pessoas():
    fornecedor = Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste Ltda")
    fornecedor.atribuir_papel(Papel.FORNECEDOR)
    faturado = Pessoa.objects.create(documento=CPF, razao_social="Produtor Teste")
    faturado.atribuir_papel(Papel.FATURADO)
    return fornecedor, faturado


class ValidarParcelasTests(SimpleTestCase):
    """Invólucro público das regras da GR-38 (sem duplicar)."""

    def test_mesmos_codigos_de_registrar_movimento(self):
        uma = (ItemParcela(1, date(2026, 11, 1), Decimal("150.00")),)
        validar_parcelas(Decimal("150.00"), uma)
        casos = {
            "sem_parcela": (Decimal("150.00"), ()),
            "parcela_soma": (Decimal("151.00"), uma),
            "parcela_numeracao": (Decimal("150.00"), (ItemParcela(2, date(2026, 11, 1), Decimal("150.00")),)),
            "parcela_vencimento": (Decimal("150.00"), (ItemParcela(1, None, Decimal("150.00")),)),
        }
        for codigo, (total, parcelas) in casos.items():
            with self.subTest(codigo), self.assertRaises(ValidationError) as contexto:
                validar_parcelas(total, parcelas)
            self.assertEqual(contexto.exception.code, codigo)


class ValidarParcelasSemListaTests(SimpleTestCase):
    def test_none_e_sem_parcela(self):
        with self.assertRaises(ValidationError) as contexto:
            validar_parcelas(Decimal("1.00"), None)
        self.assertEqual(contexto.exception.code, "sem_parcela")


class ConferirNotaTestBase(TestCase):
    def setUp(self):
        self.fornecedor, self.faturado = cadastrar_pessoas()


class CombinacaoTests(ConferirNotaTestBase):
    def test_sem_correcoes_usa_o_extraido(self):
        nota = conferir_nota(resultado_da_nota())

        self.assertEqual(nota.fornecedor.documento, CNPJ)
        self.assertEqual(nota.fornecedor.consulta.id, self.fornecedor.pk)
        self.assertEqual(nota.faturado.consulta.id, self.faturado.pk)
        self.assertEqual(nota.classificacao.codigo, "MANUTENCAO_E_OPERACAO")
        self.assertEqual(
            (nota.numero_nota, nota.serie, nota.data_emissao, nota.valor_total),
            (123, None, date(2026, 10, 1), Decimal("150.00")),
        )
        self.assertEqual(nota.parcelas, (ItemParcela(1, date(2026, 11, 1), Decimal("150.00")),))
        self.assertEqual(nota.campos_alterados, ())

    def test_json_v1_nunca_identifica_a_nota(self):
        # D-01: sem chave nem modelo (G-01 e JSON v2 pendentes), a identidade
        # é insuficiente, mesmo com a série corrigida.
        for correcoes in (None, {"serie": 1}):
            with self.subTest(correcoes=correcoes):
                nota = conferir_nota(resultado_da_nota(), correcoes)
                self.assertEqual(problemas(nota), {("identidade_fiscal", "identidade_fiscal_insuficiente")})
                self.assertIsNone(nota.identidade_fiscal)
                self.assertFalse(nota.sem_problemas)

    def test_correcoes_prevalecem_e_os_extraidos_nao_mudam(self):
        dados = resultado_da_nota()
        original = copy.deepcopy(dados)
        correcoes = {
            "fornecedor.razao_social": "Nome Corrigido",
            "valor_total": "300.00",
            "parcelas": [
                {"numero": 1, "data_vencimento": "2026-11-01", "valor": "150.00"},
                {"numero": 2, "data_vencimento": "2026-12-01", "valor": "150.00"},
            ],
            "tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES",
            "numero_nota": "123",  # igual ao extraído: não conta como alterado
        }

        nota = conferir_nota(dados, correcoes)

        self.assertEqual(dados, original)
        self.assertEqual(nota.fornecedor.nome, "Nome Corrigido")
        self.assertEqual(nota.valor_total, Decimal("300.00"))
        self.assertEqual(len(nota.parcelas), 2)
        self.assertEqual(nota.classificacao.codigo, "INFRAESTRUTURA_E_UTILIDADES")
        self.assertEqual(set(nota.campos_alterados),
                         {"fornecedor.razao_social", "valor_total", "parcelas", "tipo_despesa"})
        self.assertEqual(problemas(nota), {("identidade_fiscal", "identidade_fiscal_insuficiente")})

    def test_correcao_invalida_nao_volta_para_o_extraido(self):
        nota = conferir_nota(resultado_da_nota(), {"valor_total": "abc", "faturado.documento": "1"})

        self.assertIsNone(nota.valor_total)
        self.assertIsNone(nota.faturado.documento)
        # A consulta acompanha o problema: documento digitado errado é inválido, não ausente.
        self.assertEqual(nota.faturado.consulta.situacao, Situacao.DOCUMENTO_INVALIDO)
        self.assertTrue({("valor_total", "invalido"), ("faturado.documento", "invalido")} <= problemas(nota))

    def test_correcoes_vazias_equivalem_a_nenhuma(self):
        self.assertEqual(conferir_nota(resultado_da_nota(), {}), conferir_nota(resultado_da_nota()))

    def test_so_formatacao_nao_conta_como_alteracao(self):
        nota = conferir_nota(resultado_da_nota(), {"fornecedor.documento": "11.222.333/0001-81"})

        self.assertEqual(nota.campos_alterados, ())

    def test_extraido_que_nao_e_texto(self):
        dados = resultado_da_nota()
        dados["fornecedor"]["cnpj"] = 11222333000181
        dados["tipo_despesa"] = 7

        nota = conferir_nota(dados)

        self.assertTrue({("fornecedor.documento", "invalido"), ("tipo_despesa", "invalido")}
                        <= problemas(nota))
        self.assertEqual(nota.fornecedor.consulta.situacao, Situacao.DOCUMENTO_AUSENTE)

    def test_parcela_extraida_com_campo_a_mais(self):
        # JSON v2 (F-7) pode acrescentar campos à parcela.
        dados = resultado_da_nota()
        dados["parcelas"][0]["identificacao"] = "ÚNICA"

        self.assertNotIn("parcelas", {p.campo for p in conferir_nota(dados).problemas})

    def test_data_extraida_invalida_nao_bloqueia(self):
        # A data de emissão não é gravada no movimento; corrigida inválida, sim.
        dados = resultado_da_nota() | {"data_emissao": "01/10/2026"}

        nota = conferir_nota(dados)
        self.assertNotIn("data_emissao", {p.campo for p in nota.problemas})
        self.assertIsNone(nota.data_emissao)
        self.assertIn(("data_emissao", "invalido"),
                      problemas(conferir_nota(dados, {"data_emissao": "31/12/2026"})))

    def test_correcao_nao_autorizada_e_formato_errado(self):
        self.assertIn(("campo_nao_autorizado", "invalido"),
                      problemas(conferir_nota(resultado_da_nota(), {"documento_fiscal": {}})))
        self.assertIn(("correcoes", "invalido"),
                      problemas(conferir_nota(resultado_da_nota(), ["serie"])))

    def test_dados_mal_formados_nao_quebram(self):
        for dados in (None, {}, {"fornecedor": "x", "faturado": [], "parcelas": "x"}):
            with self.subTest(dados=dados):
                nota = conferir_nota(dados)
                self.assertIn(("fornecedor.documento", "ausente"), problemas(nota))
                self.assertFalse(nota.sem_problemas)


class DocumentosEPessoasTests(ConferirNotaTestBase):
    def test_documento_extraido_invalido(self):
        dados = resultado_da_nota()
        dados["fornecedor"]["cnpj"] = "11222333000182"

        nota = conferir_nota(dados)

        self.assertIn(("fornecedor.documento", "invalido"), problemas(nota))
        self.assertEqual(nota.fornecedor.consulta.situacao, Situacao.DOCUMENTO_INVALIDO)

    def test_documento_ausente(self):
        dados = resultado_da_nota()
        dados["faturado"]["cpf"] = None

        nota = conferir_nota(dados)

        self.assertIn(("faturado.documento", "ausente"), problemas(nota))
        self.assertEqual(nota.faturado.consulta.situacao, Situacao.DOCUMENTO_AUSENTE)

    def test_cpf_e_cnpj_extraidos_exigem_escolha(self):
        # D-03 (e GR-41 com o JSON v2): sem escolha automática.
        dados = resultado_da_nota()
        dados["faturado"]["cnpj"] = CNPJ_ALFANUMERICO

        nota = conferir_nota(dados)
        self.assertIn(("faturado.documento", "escolha_necessaria"), problemas(nota))
        self.assertIsNone(nota.faturado.documento)

        escolhida = conferir_nota(dados, {"faturado.documento": CNPJ_ALFANUMERICO})
        self.assertNotIn("faturado.documento", {p.campo for p in escolhida.problemas})
        self.assertEqual(escolhida.faturado.documento, CNPJ_ALFANUMERICO)
        self.assertEqual(escolhida.faturado.consulta.situacao, Situacao.NAO_EXISTE)

    def test_faturado_com_cnpj_por_correcao(self):
        nota = conferir_nota(resultado_da_nota(), {"faturado.documento": "11.222.333/0001-81"})

        # A mesma pessoa pode ser fornecedor e faturado (DQ-06); o papel é informado.
        self.assertEqual(nota.faturado.consulta.id, self.fornecedor.pk)
        self.assertEqual(nota.faturado.consulta.status_papel, "AUSENTE")

    def test_nome_so_e_exigido_para_pessoa_nova(self):
        dados = resultado_da_nota()
        dados["fornecedor"]["razao_social"] = None
        dados["faturado"]["nome"] = None
        self.assertEqual(problemas(conferir_nota(dados)),
                         {("identidade_fiscal", "identidade_fiscal_insuficiente")})

        nova = conferir_nota(dados, {"faturado.documento": CNPJ_ALFANUMERICO})
        self.assertIn(("faturado.nome", "ausente"), problemas(nova))

    def test_nome_extraido_invalido(self):
        dados = resultado_da_nota()
        dados["faturado"]["nome"] = "Nome\x00"

        # Pessoa existente: o nome extraído não é usado.
        self.assertNotIn("faturado.nome", {p.campo for p in conferir_nota(dados).problemas})
        # Pessoa nova: um só problema, invalido.
        nova = conferir_nota(dados, {"faturado.documento": CNPJ_ALFANUMERICO})
        self.assertEqual([p for p in nova.problemas if p.campo == "faturado.nome"],
                         [Problema("faturado.nome", "invalido")])

    def test_nome_corrigido_invalido_com_pessoa_nova(self):
        nota = conferir_nota(resultado_da_nota(),
                             {"faturado.documento": CNPJ_ALFANUMERICO, "faturado.nome": "   "})

        self.assertEqual([p for p in nota.problemas if p.campo == "faturado.nome"],
                         [Problema("faturado.nome", "invalido")])

    def test_inativos_nao_sao_problema_de_dado(self):
        # DQ-07: a decisão de reativar é da F-4; aqui só aparece na consulta.
        self.fornecedor.inativar()
        PapelPessoa.objects.get(pessoa=self.faturado).inativar()

        nota = conferir_nota(resultado_da_nota())

        self.assertEqual(nota.fornecedor.consulta.status, "INATIVO")
        self.assertEqual(nota.faturado.consulta.status_papel, "INATIVO")
        self.assertNotIn("fornecedor.documento", {p.campo for p in nota.problemas})
        self.fornecedor.refresh_from_db()
        self.assertEqual(self.fornecedor.status, "INATIVO")


class ClassificacaoTests(ConferirNotaTestBase):
    def test_classificacao_inconclusiva_gr42(self):
        nota = conferir_nota(resultado_da_nota() | {"tipo_despesa": None})

        self.assertIn(("tipo_despesa", "ausente"), problemas(nota))
        self.assertEqual(nota.classificacao.situacao, Situacao.CLASSIFICACAO_AUSENTE)
        corrigida = conferir_nota(resultado_da_nota() | {"tipo_despesa": None},
                                  {"tipo_despesa": "MANUTENCAO_E_OPERACAO"})
        self.assertNotIn("tipo_despesa", {p.campo for p in corrigida.problemas})

    def test_classificacao_inexistente_bloqueia(self):
        nota = conferir_nota(resultado_da_nota(), {"tipo_despesa": "INSUMOS"})

        self.assertIn(("tipo_despesa", "classificacao_inexistente"), problemas(nota))
        self.assertFalse(Classificacao.objects.filter(codigo="INSUMOS").exists())

    def test_classificacao_inativa_fica_para_a_f4(self):
        Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO").inativar()

        nota = conferir_nota(resultado_da_nota())

        self.assertEqual(nota.classificacao.status, "INATIVO")
        self.assertNotIn("tipo_despesa", {p.campo for p in nota.problemas})


class ValoresEParcelasTests(ConferirNotaTestBase):
    def parcelas(self, *itens):
        return [{"numero": n, "data_vencimento": d, "valor": v} for n, d, v in itens]

    def test_regras_da_gr38(self):
        casos = {
            "parcela_soma": self.parcelas((1, "2026-11-01", "100.00")),
            "parcela_numeracao": self.parcelas((1, "2026-11-01", "75.00"), (3, "2026-12-01", "75.00")),
            "parcela_repetida": self.parcelas((1, "2026-11-01", "75.00"), (1, "2026-12-01", "75.00")),
        }
        for codigo, parcelas in casos.items():
            with self.subTest(codigo):
                nota = conferir_nota(resultado_da_nota(), {"parcelas": parcelas})
                self.assertIn(("parcelas", codigo), problemas(nota))

    def test_parcelas_extraidas_sem_vencimento_ou_vazias(self):
        sem_vencimento = resultado_da_nota()
        sem_vencimento["parcelas"][0]["data_vencimento"] = None
        vazia = resultado_da_nota() | {"parcelas": [], "quantidade_parcelas": 0}

        self.assertIn(("parcelas", "invalido"), problemas(conferir_nota(sem_vencimento)))
        self.assertIn(("parcelas", "ausente"), problemas(conferir_nota(vazia)))
        # D-02: o usuário completa as parcelas na correção.
        corrigida = conferir_nota(vazia, {"parcelas": self.parcelas((1, "2026-11-01", "150.00"))})
        self.assertNotIn("parcelas", {p.campo for p in corrigida.problemas})

    def test_valor_total_invalido_nao_confere_a_soma(self):
        dados = resultado_da_nota() | {"valor_total": "-1"}

        nota = conferir_nota(dados)

        self.assertIn(("valor_total", "invalido"), problemas(nota))
        self.assertNotIn("parcelas", {p.campo for p in nota.problemas})

    def test_numero_impresso_com_separadores_exige_correcao(self):
        nota = conferir_nota(resultado_da_nota() | {"numero_nota": "000.123"})

        self.assertIn(("numero_nota", "invalido"), problemas(nota))
        self.assertNotIn("numero_nota", {p.campo for p in conferir_nota(
            resultado_da_nota() | {"numero_nota": "000.123"}, {"numero_nota": "123"}).problemas})

    def test_problemas_nao_trazem_valores(self):
        nota = conferir_nota(resultado_da_nota(), {"parcelas": self.parcelas((1, "2026-11-01", "987.65"))})

        for problema in nota.problemas:
            self.assertEqual(set(vars(problema)), {"campo", "codigo"})
            self.assertNotIn("987", f"{problema!r}")


class IdentidadeFiscalTests(ConferirNotaTestBase):
    def test_fornecedor_com_cpf_bloqueia(self):
        # Com o JSON v1 falta o modelo, e identificar_nota() acusa primeiro a
        # falta de dados; com o modelo, o código seria identidade_fiscal_nao_suportada (T-06).
        nota = conferir_nota(resultado_da_nota(), {"fornecedor.documento": CPF, "serie": 1})

        self.assertIn(("identidade_fiscal", "identidade_fiscal_insuficiente"), problemas(nota))
        self.assertIsNone(nota.identidade_fiscal)

    def test_identidade_completa_sem_problemas(self):
        # Simula a origem do modelo (JSON v2 ou G-01), ainda inexistente.
        with mock.patch("documentos.conferencia.identificar_nota", return_value=IDENTIDADE) as chamada:
            nota = conferir_nota(resultado_da_nota(), {"serie": 1})

        chamada.assert_called_once_with(
            chave_acesso=None, emitente_cnpj=CNPJ, modelo=None, serie=1, numero=123
        )
        self.assertTrue(nota.sem_problemas, nota.problemas)
        self.assertEqual(nota.identidade_fiscal, IDENTIDADE)

    def test_argumentos_reais_da_identidade(self):
        with mock.patch("documentos.conferencia.identificar_nota",
                        wraps=identificar_nota) as chamada:
            conferir_nota(resultado_da_nota(), {"serie": 7, "fornecedor.documento": CNPJ_ALFANUMERICO})

        chamada.assert_called_once_with(
            chave_acesso=None, emitente_cnpj=CNPJ_ALFANUMERICO, modelo=None, serie=7, numero=123
        )

    def test_nota_ja_lancada(self):
        with transaction.atomic():
            movimento, _ = registrar_movimento(DadosMovimento(
                tipo="APAGAR", origem="NOTA_FISCAL", contraparte=self.fornecedor,
                faturado=self.faturado, valor_total=Decimal("150.00"),
                classificacoes=(ItemClassificacao(
                    Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO"), principal=True),),
                analise_origem_id=uuid.uuid4(),
                parcelas=(ItemParcela(1, date(2026, 11, 1), Decimal("150.00")),),
            ))
            registrar_identidade_fiscal(movimento, IDENTIDADE)

        with mock.patch("documentos.conferencia.identificar_nota", return_value=IDENTIDADE):
            nota = conferir_nota(resultado_da_nota(), {"serie": 1})

        self.assertEqual(problemas(nota), {("identidade_fiscal", "nota_ja_lancada")})


class SomenteLeituraTests(ConferirNotaTestBase):
    def contagens(self):
        return tuple(m.objects.count() for m in (Pessoa, PapelPessoa, Classificacao, MovimentoConta,
                                                 NotaFiscalLancada))

    def test_so_executa_select(self):
        antes = self.contagens()
        correcoes = {"faturado.documento": CNPJ_ALFANUMERICO, "tipo_despesa": "INSUMOS"}

        with CaptureQueriesContext(connection) as consultas:
            conferir_nota(resultado_da_nota(), correcoes)

        self.assertTrue(consultas.captured_queries)
        for consulta in consultas.captured_queries:
            self.assertTrue(consulta["sql"].lstrip().upper().startswith("SELECT"), consulta["sql"])
        self.assertEqual(self.contagens(), antes)


class UsoNaConfirmacaoTests(ConferirNotaTestBase):
    """Como a F-5 usará: dentro do gravar, com correcoes_da_confirmacao()."""

    def test_dentro_da_confirmacao(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        registrar_correcoes(sessao, analise.id, {"serie": 1}, 0)

        def gravar(dados, analise_id):
            return conferir_nota(dados, correcoes_da_confirmacao(analise_id))

        nota = confirmar_analise(sessao, analise.id, gravar, versao_correcoes=1)

        self.assertEqual(nota.serie, 1)
        self.assertEqual(MovimentoConta.objects.count(), 0)
