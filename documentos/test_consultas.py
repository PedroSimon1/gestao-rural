"""GR-51: adaptação sem banco e consultas no TEST PostgreSQL local."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from cadastros import consultas as consultas_cadastros

from agents.classificador.schemas import ClassificacaoDespesa
from agents.extrator.schemas import NotaFiscalExtraida
from cadastros.models import Classificacao, Papel, PapelPessoa, Pessoa, Status, TipoClassificacao
from financeiro.models import MovimentoConta, ParcelaConta

from .adaptador_financeiro import adaptar_resultado
from .consultas import consultar_resultado
from .processamento import montar_resultado


def resultado():
    # Mesmo contrato real da orquestração; documentos fictícios usados na suíte.
    nota = NotaFiscalExtraida.model_validate({
        "documento_e_nota_fiscal": True,
        "fornecedor": {"razao_social": "Fornecedor Teste", "cnpj": "11.222.333/0001-81"},
        "faturado": {"nome": "Faturado Teste", "cpf": "123.456.789-09"},
        "numero_nota": "00123", "data_emissao": "2026-10-27", "itens": [],
        "valor_total": "150.00",
        "parcelas": [{"numero": 1, "data_vencimento": "2026-11-27", "valor": "150.00"}],
    })
    categoria = ClassificacaoDespesa(
        tipo_despesa="MANUTENCAO_E_OPERACAO", justificativa="Manutenção."
    )
    return montar_resultado(nota, categoria)


class AdaptadorTests(SimpleTestCase):
    def test_contrato_real_convertido_sem_mutar_resultado(self):
        original = resultado()
        antes = deepcopy(original)
        nota = adaptar_resultado(original)
        self.assertEqual(original, antes)
        self.assertEqual(nota.valor_total, Decimal("150.00"))
        self.assertIsInstance(nota.valor_total, Decimal)
        self.assertEqual(nota.data_emissao, date(2026, 10, 27))
        self.assertEqual(nota.parcelas[0].data_vencimento, date(2026, 11, 27))
        self.assertEqual(nota.parcelas[0].valor, Decimal("150.00"))
        self.assertEqual(nota.fornecedor.documento, "11222333000181")
        self.assertEqual(nota.numero_nota, "00123")
        self.assertEqual(nota.pendencias, ())

    def test_cnpj_alfanumerico_normalizado(self):
        dados = resultado()
        dados["fornecedor"]["cnpj"] = "12.abc.345/01de-35"
        self.assertEqual(adaptar_resultado(dados).fornecedor.documento, "12ABC34501DE35")

    def test_recalcula_documento_sem_confiar_no_aviso_recebido(self):
        dados = resultado()
        dados["faturado"]["cpf"] = "12345678900"
        self.assertEqual(dados["validacoes"]["faturado_cpf"]["status"], "valido")
        nota = adaptar_resultado(dados)
        self.assertIsNone(nota.faturado.documento)
        self.assertIn("faturado_documento_invalido", nota.pendencias)

    def test_papel_nao_restringe_tipo_de_documento(self):
        dados = resultado()
        dados["fornecedor"]["cnpj"] = "12345678909"
        self.assertEqual(adaptar_resultado(dados).fornecedor.situacao_documento, "valido")

    def test_ausentes_preservados_sem_inventar(self):
        dados = resultado()
        dados["fornecedor"] = {"razao_social": None, "nome_fantasia": None, "cnpj": None}
        dados["data_emissao"] = None
        dados["numero_nota"] = None
        dados["parcelas"][0]["data_vencimento"] = None
        dados["parcelas"][0]["numero"] = None
        dados["tipo_despesa"] = None
        nota = adaptar_resultado(dados)
        self.assertIsNone(nota.fornecedor.documento)
        self.assertIsNone(nota.data_emissao)
        self.assertIsNone(nota.numero_nota)
        self.assertIsNone(nota.parcelas[0].numero)
        self.assertIsNone(nota.parcelas[0].data_vencimento)
        self.assertIn("fornecedor_documento_ausente", nota.pendencias)
        self.assertIn("fornecedor_nome_ausente", nota.pendencias)
        self.assertIn("classificacao_ausente", nota.pendencias)
        self.assertIn("parcela_vencimento", nota.pendencias)
        self.assertIn("parcela_numeracao", nota.pendencias)

    def test_sem_parcelas_nao_cria_parcela_unica(self):
        dados = resultado()
        dados.update(parcelas=[], quantidade_parcelas=0)
        nota = adaptar_resultado(dados)
        self.assertEqual(nota.parcelas, ())
        self.assertIn("sem_parcela", nota.pendencias)

    def test_soma_divergente_sinalizada_sem_corrigir_valores(self):
        dados = resultado()
        dados["parcelas"][0]["valor"] = "149.99"
        nota = adaptar_resultado(dados)
        self.assertEqual(nota.parcelas[0].valor, Decimal("149.99"))
        self.assertIn("parcela_soma", nota.pendencias)

    def test_numeracao_com_lacuna_ou_repetida_sinalizada(self):
        for numeros in ((1, 3), (1, 1)):
            with self.subTest(numeros=numeros):
                dados = resultado()
                dados.update(quantidade_parcelas=2, parcelas=[
                    {"numero": n, "data_vencimento": "2026-11-27", "valor": "75.00"}
                    for n in numeros
                ])
                self.assertIn("parcela_numeracao", adaptar_resultado(dados).pendencias)

    def test_limite_de_120_parcelas(self):
        dados = resultado()
        dados.update(valor_total="121.00", quantidade_parcelas=121, parcelas=[
            {"numero": n, "data_vencimento": "2026-11-27", "valor": "1.00"}
            for n in range(1, 122)
        ])
        self.assertIn("parcela_quantidade", adaptar_resultado(dados).pendencias)

    def test_dinheiro_invalido_recusado_sem_arredondamento(self):
        for valor in (True, 150.0, "NaN", "Infinity", "0", "-1", "1.001", "10000000000"):
            with self.subTest(valor=valor):
                dados = resultado()
                dados["valor_total"] = valor
                with self.assertRaises(ValidationError):
                    adaptar_resultado(dados)

    def test_estrutura_e_tipos_invalidos_recusados(self):
        for alteracao in (
            {"fornecedor": None}, {"parcelas": None}, {"quantidade_parcelas": True},
            {"quantidade_parcelas": 2}, {"tipo_despesa": "DESCONHECIDA"},
            {"data_emissao": "20261027"}, {"numero_nota": 123},
        ):
            with self.subTest(alteracao=alteracao):
                dados = resultado()
                dados.update(alteracao)
                with self.assertRaises(ValidationError):
                    adaptar_resultado(dados)
        for dados in (None, {}, []):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                adaptar_resultado(dados)


class ConsultasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fornecedor = Pessoa.objects.create(documento="11222333000181", razao_social="Empresa")
        cls.fornecedor.atribuir_papel(Papel.FORNECEDOR)
        cls.faturado = Pessoa.objects.create(documento="12345678909", razao_social="Produtor")
        cls.faturado.atribuir_papel(Papel.FATURADO)
        cls.despesa = Classificacao.objects.get(
            tipo=TipoClassificacao.DESPESA, codigo="MANUTENCAO_E_OPERACAO"
        )

    def test_existentes_retornam_ids_e_papeis(self):
        consulta = consultar_resultado(resultado())
        self.assertEqual(consulta.fornecedor.id, self.fornecedor.pk)
        self.assertEqual(consulta.fornecedor.razao_social, "Empresa")
        self.assertEqual(consulta.fornecedor.nome, "Fornecedor Teste")
        self.assertEqual(consulta.fornecedor.status_papel, Status.ATIVO)
        self.assertEqual(consulta.faturado.id, self.faturado.pk)
        self.assertEqual(consulta.classificacao.id, self.despesa.pk)
        self.assertEqual(consulta.classificacao.situacao, "EXISTE")

    def test_inativos_identificados_sem_reativacao(self):
        self.fornecedor.inativar()
        papel = PapelPessoa.objects.get(pessoa=self.faturado, papel=Papel.FATURADO)
        papel.inativar()
        self.despesa.inativar()
        consulta = consultar_resultado(resultado())
        self.assertEqual(consulta.fornecedor.situacao, "EXISTE")
        self.assertEqual(consulta.fornecedor.status, Status.INATIVO)
        self.assertEqual(consulta.faturado.status_papel, Status.INATIVO)
        self.assertEqual(consulta.classificacao.status, Status.INATIVO)
        self.fornecedor.refresh_from_db()
        papel.refresh_from_db()
        self.despesa.refresh_from_db()
        self.assertEqual(self.fornecedor.status, Status.INATIVO)
        self.assertEqual(papel.status, Status.INATIVO)
        self.assertEqual(self.despesa.status, Status.INATIVO)

    def test_papel_ausente_nao_criado(self):
        dados = resultado()
        # Pessoa já existe com o CPF, mas não possui papel FORNECEDOR.
        # O fornecedor do contrato usa CNPJ; retirar esse papel testa o caso.
        papel = PapelPessoa.objects.get(pessoa=self.fornecedor, papel=Papel.FORNECEDOR)
        papel.inativar()
        consulta = consultar_resultado(dados)
        self.assertEqual(consulta.fornecedor.status_papel, Status.INATIVO)
        self.assertEqual(PapelPessoa.objects.filter(pessoa=self.fornecedor).count(), 1)

    def test_pessoa_existente_sem_papel_exigido(self):
        pessoa = Pessoa.objects.create(documento="12ABC34501DE35", razao_social="Outra")
        pessoa.atribuir_papel(Papel.CLIENTE)
        dados = resultado()
        dados["fornecedor"]["cnpj"] = "12ABC34501DE35"
        consulta = consultar_resultado(dados)
        self.assertEqual(consulta.fornecedor.id, pessoa.pk)
        self.assertEqual(consulta.fornecedor.situacao, "EXISTE")
        self.assertEqual(consulta.fornecedor.status_papel, "AUSENTE")
        self.assertFalse(PapelPessoa.objects.filter(pessoa=pessoa, papel=Papel.FORNECEDOR).exists())

    def test_nome_igual_nao_substitui_documento(self):
        dados = resultado()
        dados["fornecedor"]["cnpj"] = "12ABC34501DE35"
        dados["fornecedor"]["razao_social"] = self.fornecedor.razao_social
        consulta = consultar_resultado(dados)
        self.assertEqual(consulta.fornecedor.situacao, "NAO_EXISTE")
        self.assertIsNone(consulta.fornecedor.id)

    def test_documentos_ausentes_invalidos_nao_consultam_pessoas(self):
        dados = resultado()
        dados["fornecedor"]["cnpj"] = None
        dados["faturado"]["cpf"] = "12345678900"
        with self.assertNumQueries(1):  # apenas classificação
            consulta = consultar_resultado(dados)
        self.assertEqual(consulta.fornecedor.situacao, "DOCUMENTO_AUSENTE")
        self.assertEqual(consulta.faturado.situacao, "DOCUMENTO_INVALIDO")
        self.assertIsNone(consulta.faturado.id)

    def test_classificacao_nao_confunde_receita_com_despesa(self):
        codigo = "MANUTENCAO_E_OPERACAO"
        Classificacao.objects.filter(pk=self.despesa.pk).update(codigo="OUTRA_DESPESA")
        Classificacao.objects.create(tipo=TipoClassificacao.RECEITA, codigo=codigo, descricao="Receita")
        consulta = consultar_resultado(resultado())
        self.assertEqual(consulta.classificacao.situacao, "NAO_EXISTE")
        self.assertIsNone(consulta.classificacao.id)

    def test_classificacao_inconclusiva_nao_e_inexistente(self):
        dados = resultado()
        dados["tipo_despesa"] = None
        self.assertEqual(consultar_resultado(dados).classificacao.situacao, "CLASSIFICACAO_AUSENTE")

    def test_consulta_executa_apenas_select_e_nao_cria_lancamento(self):
        antes = (Pessoa.objects.count(), PapelPessoa.objects.count(), Classificacao.objects.count())
        with CaptureQueriesContext(connection) as consultas:
            consultar_resultado(resultado())
        self.assertTrue(consultas)
        for consulta in consultas:
            self.assertTrue(consulta["sql"].lstrip().upper().startswith("SELECT"), consulta["sql"])
        self.assertEqual(antes, (Pessoa.objects.count(), PapelPessoa.objects.count(), Classificacao.objects.count()))
        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertEqual(ParcelaConta.objects.count(), 0)

    def test_entrada_invalida_falha_antes_do_banco(self):
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            consultar_resultado({})

    def test_faturado_pj_numerico_usa_servico_oficial(self):
        self.fornecedor.atribuir_papel(Papel.FATURADO)
        dados = resultado()
        dados["faturado"] = {"nome": "Faturado PJ", "cpf": None, "cnpj": "11.222.333/0001-81"}
        consulta = consultar_resultado(dados)
        self.assertIsInstance(consulta, consultas_cadastros.ResultadoConsultas)
        self.assertEqual(consulta.faturado.id, self.fornecedor.pk)
        self.assertEqual(consulta.faturado.tipo_documento, "CNPJ")
        self.assertEqual(consulta.faturado.status_papel, Status.ATIVO)

    def test_faturado_pj_alfanumerico(self):
        pj = Pessoa.objects.create(documento="12ABC34501DE35", razao_social="Empresa PJ")
        pj.atribuir_papel(Papel.FATURADO)
        dados = resultado()
        dados["faturado"] = {"nome": "Empresa Extraída", "cnpj": "12.abc.345/01de-35"}
        consulta = consultar_resultado(dados)
        self.assertEqual(consulta.faturado.id, pj.pk)
        self.assertEqual(consulta.faturado.documento, "12ABC34501DE35")
        self.assertEqual(consulta.faturado.nome, "Empresa Extraída")
        self.assertEqual(consulta.faturado.razao_social, "Empresa PJ")

    def test_cpf_e_cnpj_juntos_exigem_revisao_antes_de_qualquer_query(self):
        dados = resultado()
        dados["faturado"]["cnpj"] = "12ABC34501DE35"
        with self.assertNumQueries(0), self.assertRaises(ValidationError) as contexto:
            consultar_resultado(dados)
        self.assertEqual(contexto.exception.code, "faturado_documento_ambiguo")

    def test_cnpj_invalido_nao_vira_documento_ausente(self):
        dados = resultado()
        dados["faturado"] = {"nome": "PJ inválida", "cpf": None, "cnpj": "12ABC34501DE36"}
        consulta = consultar_resultado(dados)
        self.assertEqual(consulta.faturado.situacao, consultas_cadastros.Situacao.DOCUMENTO_INVALIDO)
        self.assertIsNone(consulta.faturado.id)

    def test_documento_em_branco_nao_cria_ambiguidade(self):
        dados = resultado()
        dados["faturado"]["cnpj"] = "  "
        self.assertEqual(consultar_resultado(dados).faturado.id, self.faturado.pk)

    def test_delega_as_tres_consultas_sem_reimplementar_orm(self):
        with mock.patch.object(consultas_cadastros, "consultar_pessoa", wraps=consultas_cadastros.consultar_pessoa) as pessoa, mock.patch.object(
            consultas_cadastros, "consultar_classificacao", wraps=consultas_cadastros.consultar_classificacao
        ) as categoria:
            consultar_resultado(resultado())
        self.assertEqual(pessoa.call_count, 2)
        categoria.assert_called_once_with("MANUTENCAO_E_OPERACAO")

    def test_fornecedor_pode_ter_cpf_sem_regra_por_papel(self):
        self.faturado.atribuir_papel(Papel.FORNECEDOR)
        dados = resultado()
        dados["fornecedor"]["cnpj"] = "12345678909"
        consulta = consultar_resultado(dados)
        self.assertEqual(consulta.fornecedor.id, self.faturado.pk)
        self.assertEqual(consulta.fornecedor.tipo_documento, "CPF")
