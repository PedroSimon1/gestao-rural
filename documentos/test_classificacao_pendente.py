"""GR-42: extração preservada, sem banco, sessão de análise ou rede real."""

from unittest import mock

from django.test import SimpleTestCase

from agents.classificador.agent import (
    AgentClassificador, ClassificacaoInconclusivaError, ClassificacaoIndisponivelError,
    ClassificacaoInvalidaError,
)
from agents.classificador.schemas import ClassificacaoDespesa
from agents.extrator.agent import AgentExtrator
from agents.gemini_client import GeminiClient
from usuarios.demo import SESSAO_DEMO

from .processamento import ProcessamentoError, processar_pdf
from .test_processamento import nota_extraida, classificacao, PDF
from .test_interface import InterfaceTestBase, processamento


class ProcessamentoPendenteTests(SimpleTestCase):
    def executar(self, excecao):
        extrator = mock.Mock(spec=AgentExtrator)
        extrator.extrair.return_value = nota_extraida()
        classificador = mock.Mock(spec=AgentClassificador)
        classificador.classificar.side_effect = excecao
        retorno = processar_pdf(PDF, "chave-teste", extrator=extrator, classificador=classificador)
        extrator.extrair.assert_called_once_with(PDF)
        classificador.classificar.assert_called_once_with(extrator.extrair.return_value)
        return retorno

    def test_inconclusao_preserva_todos_os_dados_extraidos(self):
        categoria = ClassificacaoDespesa(tipo_despesa=None, justificativa="Revisar categoria.")
        retorno = self.executar(ClassificacaoInconclusivaError(classificacao=categoria))
        esperado = nota_extraida().model_dump(mode="json")
        for campo in ("fornecedor", "faturado", "numero_nota", "data_emissao", "itens", "parcelas", "valor_total", "validacoes"):
            self.assertEqual(retorno.resultado[campo], esperado[campo])
        self.assertIsNone(retorno.resultado["tipo_despesa"])
        self.assertEqual(retorno.resultado["quantidade_parcelas"], len(esperado["parcelas"]))
        self.assertEqual(retorno.situacao, "AGUARDANDO_CLASSIFICACAO")
        self.assertEqual(retorno.justificativa, "Revisar categoria.")

    def test_inconclusao_sem_payload_usa_mensagem_fixa(self):
        retorno = self.executar(ClassificacaoInconclusivaError("detalhe não confiável"))
        self.assertIsNone(retorno.resultado["tipo_despesa"])
        self.assertNotIn("detalhe não confiável", retorno.justificativa)
        self.assertEqual(retorno.situacao, "AGUARDANDO_CLASSIFICACAO")

    def test_classificador_real_preserva_justificativa_validada(self):
        cliente = mock.Mock(spec=GeminiClient)
        cliente.gerar_json.return_value = {"tipo_despesa": None, "justificativa": "Categoria indefinida."}
        with self.assertRaises(ClassificacaoInconclusivaError) as contexto:
            AgentClassificador(cliente=cliente).classificar(nota_extraida())
        self.assertIsNone(contexto.exception.classificacao.tipo_despesa)
        self.assertEqual(contexto.exception.classificacao.justificativa, "Categoria indefinida.")

    def test_rede_e_resposta_invalida_continuam_erros_distintos(self):
        for excecao in (ClassificacaoIndisponivelError(), ClassificacaoInvalidaError()):
            with self.subTest(tipo=type(excecao).__name__):
                with self.assertRaises(ProcessamentoError) as contexto:
                    self.executar(excecao)
                self.assertEqual(contexto.exception.codigo, excecao.codigo)

    def test_categoria_conclusiva_mantem_comportamento(self):
        extrator = mock.Mock(spec=AgentExtrator)
        extrator.extrair.return_value = nota_extraida()
        classificador = mock.Mock(spec=AgentClassificador)
        classificador.classificar.return_value = classificacao()
        retorno = processar_pdf(PDF, "chave-teste", extrator=extrator, classificador=classificador)
        self.assertEqual(retorno.situacao, "CLASSIFICADA")
        self.assertEqual(retorno.resultado["tipo_despesa"], "MANUTENCAO_E_OPERACAO")


class InterfacePendenteTests(InterfaceTestBase):
    def test_exibe_dados_pendentes_sem_armazenar_na_sessao(self):
        resposta, _ = self.enviar(retorno=processamento(tipo_despesa=None))
        self.assertContains(resposta, "Aguardando classificação")
        self.assertContains(resposta, "JSON final")
        self.assertContains(resposta, "Pecas Exemplo Ltda")
        self.assertContains(resposta, "Nenhum lançamento financeiro foi realizado.")
        self.assertNotContains(resposta, "não foi concluído")
        self.assertEqual(dict(self.client.session.items()), {SESSAO_DEMO: True})

    def test_nova_visita_nao_simula_persistencia_da_analise(self):
        self.enviar(retorno=processamento(tipo_despesa=None))
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, "JSON final")
        self.assertNotContains(resposta, "Aguardando classificação")

    def test_justificativa_escapada_e_chave_nao_exposta(self):
        resposta, _ = self.enviar(retorno=processamento(
            tipo_despesa=None, justificativa='<script>alert("teste")</script>'
        ))
        self.assertNotContains(resposta, '<script>alert("teste")</script>')
        self.assertContains(resposta, "&lt;script&gt;")
        self.assertNotContains(resposta, "CHAVE_CORRETA_DO_TESTE-n2-9f3a")
