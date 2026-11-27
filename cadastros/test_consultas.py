"""Consultas de existência (GR-40) no PostgreSQL local de teste.

TestCase: rodam só com as variáveis DB_TEST_* (config/banco_de_teste.py).
Documentos fictícios, com DV calculado; nenhum dado real. As categorias
iniciais (0003_categorias_iniciais) já existem em cada teste.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .consultas import (
    PAPEL_AUSENTE, ConsultaPessoa, Situacao, consultar_classificacao, consultar_pessoa,
)
from .models import Classificacao, Papel, PapelPessoa, Pessoa, SituacaoDocumental, Status
from .test_models import (
    CNPJ, CNPJ_ALFANUMERICO, CNPJ_DV_INVALIDO, CNPJ_FORMATADO, CPF, CPF_DV_INVALIDO,
    CPF_FORMATADO, criar_incompleta, criar_pessoa,
)

FORNECEDOR = Papel.FORNECEDOR
FATURADO = Papel.FATURADO


def fornecedor(documento=CNPJ, razao_social="Agropecuária Teste Ltda"):
    pessoa = criar_pessoa(documento, razao_social)
    pessoa.atribuir_papel(FORNECEDOR)
    return pessoa


class PessoaExistenteTests(TestCase):
    def test_existe_com_id_e_papel_ativo(self):
        pessoa = fornecedor()

        consulta = consultar_pessoa(CNPJ, FORNECEDOR, nome="  Agropecuária   Teste Ltda ")

        self.assertEqual(consulta, ConsultaPessoa(
            papel=FORNECEDOR, situacao=Situacao.EXISTE, nome="Agropecuária Teste Ltda",
            documento=CNPJ, tipo_documento="CNPJ", id=pessoa.pk,
            razao_social="Agropecuária Teste Ltda", status=Status.ATIVO,
            status_papel=Status.ATIVO,
        ))
        self.assertTrue(consulta.existe)

    def test_documento_formatado_e_normalizado_antes_da_busca(self):
        pessoa = criar_pessoa(CPF)

        consulta = consultar_pessoa(f"  {CPF_FORMATADO} ", FATURADO)

        self.assertEqual((consulta.situacao, consulta.id), (Situacao.EXISTE, pessoa.pk))
        self.assertEqual((consulta.documento, consulta.tipo_documento), (CPF, "CPF"))

    def test_cnpj_alfanumerico_em_minusculas(self):
        pessoa = fornecedor(CNPJ_ALFANUMERICO)

        consulta = consultar_pessoa("12.abc.345/01de-35", FORNECEDOR)

        self.assertEqual((consulta.situacao, consulta.id), (Situacao.EXISTE, pessoa.pk))
        self.assertEqual(consulta.documento, CNPJ_ALFANUMERICO)

    def test_razao_social_cadastrada_e_a_da_nota_ficam_separadas(self):
        fornecedor(razao_social="Nome Cadastrado")

        consulta = consultar_pessoa(CNPJ, FORNECEDOR, nome="Nome Na Nota")

        self.assertEqual((consulta.nome, consulta.razao_social), ("Nome Na Nota", "Nome Cadastrado"))


class PessoaInexistenteTests(TestCase):
    def test_nao_existe_sem_id(self):
        consulta = consultar_pessoa(CNPJ, FORNECEDOR, nome="Empresa Nova")

        self.assertEqual(consulta, ConsultaPessoa(
            papel=FORNECEDOR, situacao=Situacao.NAO_EXISTE, nome="Empresa Nova",
            documento=CNPJ, tipo_documento="CNPJ",
        ))
        self.assertFalse(consulta.existe)

    def test_outro_documento_cadastrado_nao_conta(self):
        fornecedor(CNPJ)

        self.assertEqual(consultar_pessoa(CPF, FATURADO).situacao, Situacao.NAO_EXISTE)

    def test_sem_busca_pela_razao_social(self):
        # Q-03: só o documento identifica a pessoa.
        criar_pessoa(CPF, "Produtor Teste")
        criar_incompleta("Produtor Teste")

        consulta = consultar_pessoa(CNPJ, FORNECEDOR, nome="Produtor Teste")

        self.assertEqual(consulta.situacao, Situacao.NAO_EXISTE)


class DocumentoAusenteOuInvalidoTests(TestCase):
    def test_documento_ausente_nao_consulta_o_banco(self):
        criar_incompleta("Produtor Teste")

        for documento in (None, "", "   ", " . - / "):
            with self.subTest(documento=documento), self.assertNumQueries(0):
                consulta = consultar_pessoa(documento, FATURADO, nome="Produtor Teste")
            self.assertEqual(consulta.situacao, Situacao.DOCUMENTO_AUSENTE)
            self.assertIsNone(consulta.documento)
            self.assertIsNone(consulta.id)
            self.assertEqual(consulta.nome, "Produtor Teste")

    def test_documento_invalido_nao_consulta_o_banco(self):
        for documento in (CPF_DV_INVALIDO, CNPJ_DV_INVALIDO, "11111111111", "123", "ABC"):
            with self.subTest(documento=documento), self.assertNumQueries(0):
                consulta = consultar_pessoa(documento, FORNECEDOR)
            self.assertEqual(consulta.situacao, Situacao.DOCUMENTO_INVALIDO)
            self.assertIsNone(consulta.id)

    def test_documento_invalido_de_fixture_nao_e_encontrado(self):
        # Fixtures de QA (sem save()) podem ter DV inválido; a consulta não os busca.
        Pessoa.objects.bulk_create([Pessoa(
            documento=CPF_DV_INVALIDO, tipo_documento="CPF", razao_social="Fixture"
        )])

        consulta = consultar_pessoa(CPF_DV_INVALIDO, FATURADO)

        self.assertEqual(consulta.situacao, Situacao.DOCUMENTO_INVALIDO)
        self.assertEqual((consulta.documento, consulta.tipo_documento), (CPF_DV_INVALIDO, "CPF"))

    def test_documento_que_nao_e_texto_e_recusado(self):
        with self.assertRaises(TypeError):
            consultar_pessoa(12345678909, FATURADO)


class StatusEPapelTests(TestCase):
    """T-05: inativos são identificados, nunca reativados; o papel não é atribuído."""

    def test_pessoa_inativa_existe_e_continua_inativa(self):
        pessoa = fornecedor()
        pessoa.inativar()

        consulta = consultar_pessoa(CNPJ, FORNECEDOR)

        self.assertEqual((consulta.situacao, consulta.id), (Situacao.EXISTE, pessoa.pk))
        self.assertEqual((consulta.status, consulta.status_papel), (Status.INATIVO, Status.ATIVO))
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.INATIVO)

    def test_papel_inativo(self):
        pessoa = criar_pessoa(CPF)
        papel, _ = pessoa.atribuir_papel(FATURADO)
        papel.inativar()

        consulta = consultar_pessoa(CPF, FATURADO)

        self.assertEqual((consulta.status, consulta.status_papel), (Status.ATIVO, Status.INATIVO))
        papel.refresh_from_db()
        self.assertEqual(papel.status, Status.INATIVO)

    def test_pessoa_sem_o_papel_pedido(self):
        pessoa = criar_pessoa(CNPJ)
        pessoa.atribuir_papel(Papel.CLIENTE)

        consulta = consultar_pessoa(CNPJ, FORNECEDOR)

        self.assertEqual((consulta.situacao, consulta.id), (Situacao.EXISTE, pessoa.pk))
        self.assertEqual(consulta.status_papel, PAPEL_AUSENTE)
        self.assertFalse(PapelPessoa.objects.filter(pessoa=pessoa, papel=FORNECEDOR).exists())

    def test_papel_de_cada_consulta_e_o_pedido(self):
        pessoa = fornecedor(CPF)

        self.assertEqual(consultar_pessoa(CPF, FORNECEDOR).status_papel, Status.ATIVO)
        self.assertEqual(consultar_pessoa(CPF, FATURADO).status_papel, PAPEL_AUSENTE)
        self.assertEqual(consultar_pessoa(CPF, Papel.CLIENTE).status_papel, PAPEL_AUSENTE)
        self.assertEqual(pessoa.papeis.count(), 1)

    def test_papel_desconhecido_e_recusado(self):
        with self.assertRaises(ValueError):
            consultar_pessoa(CPF, "CLIENTE-FORNECEDOR")


class ClassificacaoTests(TestCase):
    def test_categoria_inicial_existe(self):
        esperada = Classificacao.objects.get(tipo="DESPESA", codigo="MANUTENCAO_E_OPERACAO")

        consulta = consultar_classificacao("MANUTENCAO_E_OPERACAO")

        self.assertEqual(consulta.situacao, Situacao.EXISTE)
        self.assertTrue(consulta.existe)
        self.assertEqual(
            (consulta.tipo, consulta.codigo, consulta.id, consulta.descricao, consulta.status),
            ("DESPESA", "MANUTENCAO_E_OPERACAO", esperada.pk, "MANUTENÇÃO E OPERAÇÃO", Status.ATIVO),
        )

    def test_codigo_normalizado(self):
        consulta = consultar_classificacao("  infraestrutura_e_utilidades ")

        self.assertEqual(consulta.situacao, Situacao.EXISTE)
        self.assertEqual(consulta.codigo, "INFRAESTRUTURA_E_UTILIDADES")

    def test_inativa_existe_e_continua_inativa(self):
        classificacao = Classificacao.objects.get(codigo="MANUTENCAO_E_OPERACAO")
        classificacao.inativar()

        consulta = consultar_classificacao("MANUTENCAO_E_OPERACAO")

        self.assertEqual((consulta.situacao, consulta.status), (Situacao.EXISTE, Status.INATIVO))
        classificacao.refresh_from_db()
        self.assertEqual(classificacao.status, Status.INATIVO)

    def test_inexistente(self):
        consulta = consultar_classificacao("INSUMOS")

        self.assertEqual((consulta.situacao, consulta.codigo, consulta.id), (Situacao.NAO_EXISTE, "INSUMOS", None))
        self.assertFalse(Classificacao.objects.filter(codigo="INSUMOS").exists())

    def test_mesmo_codigo_de_receita_nao_conta_como_despesa(self):
        Classificacao.objects.create(tipo="RECEITA", codigo="ARRENDAMENTO", descricao="Arrendamento")

        self.assertEqual(consultar_classificacao("ARRENDAMENTO").situacao, Situacao.NAO_EXISTE)
        self.assertEqual(consultar_classificacao("ARRENDAMENTO", "RECEITA").situacao, Situacao.EXISTE)

    def test_codigo_ausente_nao_consulta_o_banco(self):
        for codigo in (None, "", "  "):
            with self.subTest(codigo=codigo), self.assertNumQueries(0):
                consulta = consultar_classificacao(codigo)
            self.assertEqual(consulta.situacao, Situacao.CLASSIFICACAO_AUSENTE)
            self.assertIsNone(consulta.codigo)

    def test_tipo_desconhecido_e_recusado(self):
        with self.assertRaises(ValueError):
            consultar_classificacao("MANUTENCAO_E_OPERACAO", "APAGAR")


class SomenteLeituraTests(TestCase):
    """A consulta não grava nada (P03, critério 2)."""

    def contagens(self):
        return (
            Pessoa.objects.count(), PapelPessoa.objects.count(), Classificacao.objects.count(),
            Pessoa.objects.filter(situacao_documental=SituacaoDocumental.INCOMPLETO).count(),
        )

    def consultar_tudo(self, fornecedor_doc, faturado_doc, codigo):
        return (
            consultar_pessoa(fornecedor_doc, FORNECEDOR),
            consultar_pessoa(faturado_doc, FATURADO),
            consultar_classificacao(codigo),
        )

    def test_so_executa_select(self):
        fornecedor()
        criar_pessoa(CPF).atribuir_papel(FATURADO)

        for dados in ((CNPJ, CPF, "MANUTENCAO_E_OPERACAO"), (CNPJ_ALFANUMERICO, None, "INSUMOS")):
            with self.subTest(fornecedor=dados[0]):
                antes = self.contagens()
                with CaptureQueriesContext(connection) as consultas:
                    self.consultar_tudo(*dados)

                self.assertTrue(consultas.captured_queries)
                for consulta in consultas.captured_queries:
                    self.assertTrue(consulta["sql"].lstrip().upper().startswith("SELECT"), consulta["sql"])
                self.assertEqual(self.contagens(), antes)

    def test_numero_de_consultas(self):
        fornecedor()
        criar_pessoa(CPF).atribuir_papel(FATURADO)

        # Pessoa e papel para cada pessoa encontrada, mais a classificação.
        with self.assertNumQueries(5):
            self.consultar_tudo(CNPJ, CPF, "MANUTENCAO_E_OPERACAO")
