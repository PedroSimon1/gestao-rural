from unittest import mock

from django.test import SimpleTestCase, override_settings

from agents.extrator.schemas import NotaFiscalExtraida
from agents.gemini_client import (
    GeminiAPIError,
    GeminiClient,
    GeminiConfiguracaoError,
    GeminiRespostaInvalidaError,
    GeminiTimeoutError,
)

from .agent import (
    AgentClassificador,
    ClassificacaoInconclusivaError,
    ClassificacaoIndisponivelError,
    ClassificacaoInvalidaError,
    ClassificadorError,
)
from .schemas import ClassificacaoDespesa, TipoDespesa


def nota_valida(descricao="Óleo diesel S10"):
    return NotaFiscalExtraida.model_validate(
        {
            "documento_e_nota_fiscal": True,
            "fornecedor": {
                "razao_social": "Fornecedor Teste Ltda",
                "nome_fantasia": "Fornecedor Teste",
                "cnpj": "11.222.333/0001-81",
            },
            "faturado": {
                "nome": "Produtor Teste",
                "cpf": "529.982.247-25",
            },
            "numero_nota": "123",
            "data_emissao": "2026-09-23",
            "itens": [
                {
                    "descricao": descricao,
                    "quantidade": 1,
                    "valor_total": 100,
                }
            ],
            "parcelas": [],
            "valor_total": 100,
        }
    )


@override_settings(GEMINI_API_KEY=None, GEMINI_MODEL="modelo-teste")
class AgentClassificadorTestBase(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch(
            "agents.gemini_client.genai.Client",
            side_effect=AssertionError(
                "O SDK real do Gemini não deve ser usado nos testes."
            ),
        )
        self.sdk_client = patcher.start()
        self.addCleanup(patcher.stop)

        self.cliente = mock.Mock(spec=GeminiClient)
        self.cliente.modelo = "modelo-teste"
        self.cliente.gerar_json.return_value = {
            "tipo_despesa": "MANUTENCAO_E_OPERACAO",
            "justificativa": "A nota contém óleo diesel.",
        }

        self.agent = AgentClassificador(cliente=self.cliente)


class ClassificacaoComSucessoTests(AgentClassificadorTestBase):
    def test_classifica_manutencao_e_operacao(self):
        resultado = self.agent.classificar(nota_valida("Óleo diesel S10"))

        self.assertIsInstance(resultado, ClassificacaoDespesa)
        self.assertEqual(
            resultado.tipo_despesa,
            TipoDespesa.MANUTENCAO_E_OPERACAO,
        )

    def test_classifica_infraestrutura_e_utilidades(self):
        self.cliente.gerar_json.return_value = {
            "tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES",
            "justificativa": "A nota contém material hidráulico.",
        }

        resultado = self.agent.classificar(
            nota_valida("Tubo hidráulico PVC")
        )

        self.assertEqual(
            resultado.tipo_despesa,
            TipoDespesa.INFRAESTRUTURA_E_UTILIDADES,
        )

    def test_gemini_recebe_schema_e_temperatura_zero(self):
        self.agent.classificar(nota_valida())

        self.cliente.gerar_json.assert_called_once()

        argumentos = self.cliente.gerar_json.call_args.kwargs

        self.assertIs(
            argumentos["schema_resposta"],
            ClassificacaoDespesa,
        )
        self.assertEqual(argumentos["temperatura"], 0)
        self.assertTrue(argumentos["instrucao_sistema"])

    def test_modelo_do_cliente(self):
        self.assertEqual(self.agent.modelo, "modelo-teste")


class EntradaInvalidaTests(AgentClassificadorTestBase):
    def test_rejeita_objeto_que_nao_e_nota_extraida(self):
        with self.assertRaises(ClassificacaoInvalidaError):
            self.agent.classificar({"itens": []})

        self.cliente.gerar_json.assert_not_called()

    def test_rejeita_nota_sem_itens(self):
        dados = nota_valida().model_dump()
        dados["itens"] = []

        nota = NotaFiscalExtraida.model_validate(dados)

        with self.assertRaises(ClassificacaoInvalidaError):
            self.agent.classificar(nota)

        self.cliente.gerar_json.assert_not_called()


class RespostaInvalidaTests(AgentClassificadorTestBase):
    def test_categoria_nao_permitida_e_rejeitada(self):
        self.cliente.gerar_json.return_value = {
            "tipo_despesa": "COMBUSTIVEL",
            "justificativa": "Categoria criada pelo modelo.",
        }

        with self.assertRaises(ClassificacaoInvalidaError):
            self.agent.classificar(nota_valida())

    def test_resposta_sem_justificativa_e_rejeitada(self):
        self.cliente.gerar_json.return_value = {
            "tipo_despesa": "MANUTENCAO_E_OPERACAO",
        }

        with self.assertRaises(ClassificacaoInvalidaError):
            self.agent.classificar(nota_valida())

    def test_classificacao_inconclusiva(self):
        self.cliente.gerar_json.return_value = {
            "tipo_despesa": None,
            "justificativa": (
                "Os itens não pertencem às categorias disponíveis."
            ),
        }

        with self.assertRaises(ClassificacaoInconclusivaError):
            self.agent.classificar(
                nota_valida("Semente de milho")
            )


class FalhasDoGeminiTests(AgentClassificadorTestBase):
    def test_timeout_vira_classificacao_indisponivel(self):
        self.cliente.gerar_json.side_effect = GeminiTimeoutError(
            "timeout interno"
        )

        with self.assertRaises(ClassificacaoIndisponivelError):
            self.agent.classificar(nota_valida())

    def test_erro_api_vira_classificacao_indisponivel(self):
        self.cliente.gerar_json.side_effect = GeminiAPIError(
            "erro externo",
            status_code=503,
        )

        with self.assertRaises(ClassificacaoIndisponivelError):
            self.agent.classificar(nota_valida())

    def test_erro_configuracao_vira_classificacao_indisponivel(self):
        self.cliente.gerar_json.side_effect = GeminiConfiguracaoError(
            "sem chave"
        )

        with self.assertRaises(ClassificacaoIndisponivelError):
            self.agent.classificar(nota_valida())

    def test_resposta_invalida_do_gemini(self):
        self.cliente.gerar_json.side_effect = (
            GeminiRespostaInvalidaError("json inválido")
        )

        with self.assertRaises(ClassificacaoInvalidaError):
            self.agent.classificar(nota_valida())


class ExcecoesTests(SimpleTestCase):
    def test_hierarquia(self):
        for classe in (
            ClassificacaoIndisponivelError,
            ClassificacaoInvalidaError,
            ClassificacaoInconclusivaError,
        ):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(
                    issubclass(classe, ClassificadorError)
                )

    def test_codigos(self):
        self.assertEqual(
            ClassificadorError.codigo,
            "erro_classificacao",
        )
        self.assertEqual(
            ClassificacaoIndisponivelError.codigo,
            "servico_indisponivel",
        )
        self.assertEqual(
            ClassificacaoInvalidaError.codigo,
            "classificacao_invalida",
        )
        self.assertEqual(
            ClassificacaoInconclusivaError.codigo,
            "classificacao_inconclusiva",
        )