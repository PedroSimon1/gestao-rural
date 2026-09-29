import base64
import json
import logging
from decimal import Decimal
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings
from google.genai import types

from agents.gemini_client import (
    GeminiAPIError,
    GeminiClient,
    GeminiConfiguracaoError,
    GeminiError,
    GeminiRespostaInvalidaError,
    GeminiTimeoutError,
)

from .agent import (
    INSTRUCAO_SISTEMA,
    AgentExtrator,
    DocumentoIlegivelError,
    ExtracaoIndisponivelError,
    ExtracaoInvalidaError,
    ExtratorError,
)
from .schemas import NotaFiscalExtraida
from .test_schemas import (
    CNPJ_VALIDO,
    CPF_FICTICIO_DV_INVALIDO,
    CPF_VALIDO,
    nota_valida,
)

PDF = b"%PDF-1.4\nconteudo de teste\n%%EOF\n"
DETALHE_INTERNO = "detalhe-interno-xyz"


# GEMINI_API_KEY ausente: mesmo que algo escape dos mocks, não há como autenticar.
@override_settings(GEMINI_API_KEY=None, GEMINI_MODEL="modelo-teste")
class AgentExtratorTestBase(SimpleTestCase):
    def setUp(self):
        # Rede de segurança: qualquer criação do SDK real falha o teste.
        patcher = mock.patch(
            "agents.gemini_client.genai.Client",
            side_effect=AssertionError("O SDK real do Gemini não deve ser usado."),
        )
        self.sdk_client_classe = patcher.start()
        self.addCleanup(patcher.stop)

        self.cliente = mock.Mock(spec=GeminiClient)
        self.cliente.modelo = "modelo-teste"
        self.cliente.gerar_json.return_value = nota_valida()
        self.agent = AgentExtrator(cliente=self.cliente)

    def argumentos_gerar_json(self):
        self.cliente.gerar_json.assert_called_once()
        return self.cliente.gerar_json.call_args

    def resposta(self, **alteracoes):
        dados = nota_valida()
        dados.update(alteracoes)
        return dados


class ExtracaoComSucessoTests(AgentExtratorTestBase):
    def test_retorna_nota_fiscal_extraida(self):
        nota = self.agent.extrair(PDF)

        self.assertIsInstance(nota, NotaFiscalExtraida)
        self.assertEqual(nota.valor_total, Decimal("1500.00"))
        self.assertEqual(nota.fornecedor.cnpj, "11222333000181")
        self.assertEqual(len(nota.itens), 1)
        self.assertEqual(len(nota.parcelas), 2)

    def test_gerar_json_chamado_uma_vez_com_schema_e_temperatura_zero(self):
        self.agent.extrair(PDF)

        argumentos = self.argumentos_gerar_json().kwargs
        self.assertIs(argumentos["schema_resposta"], NotaFiscalExtraida)
        self.assertEqual(argumentos["temperatura"], 0)
        self.assertEqual(argumentos["instrucao_sistema"], INSTRUCAO_SISTEMA)
        self.assertTrue(argumentos["instrucao_sistema"].strip())

    def test_conteudo_multimodal_envia_o_pdf_recebido(self):
        self.agent.extrair(PDF)

        conteudo = self.argumentos_gerar_json().args[0]
        self.assertEqual(len(conteudo), 2)
        self.assertIsInstance(conteudo[0], str)
        parte_pdf = conteudo[1]
        self.assertIsInstance(parte_pdf, types.Part)
        self.assertEqual(parte_pdf.inline_data.mime_type, "application/pdf")
        self.assertEqual(parte_pdf.inline_data.data, PDF)

    def test_gerar_conteudo_nunca_e_chamado(self):
        self.agent.extrair(PDF)

        self.cliente.gerar_conteudo.assert_not_called()

    def test_propriedade_modelo(self):
        self.assertEqual(self.agent.modelo, "modelo-teste")

    def test_extracao_nao_cria_o_sdk_real(self):
        self.agent.extrair(PDF)

        self.sdk_client_classe.assert_not_called()


class EntradaInvalidaTests(AgentExtratorTestBase):
    def test_entrada_invalida_nao_chama_o_gemini(self):
        casos = (
            b"",
            b"texto qualquer",
            b" %PDF-1.4",
            b"%PDF",
            "%PDF-1.4 em texto",
            bytearray(PDF),
            None,
        )
        for entrada in casos:
            with self.subTest(entrada=entrada):
                with self.assertRaises(DocumentoIlegivelError):
                    self.agent.extrair(entrada)

        self.cliente.gerar_json.assert_not_called()


class DocumentoComDvInvalidoTests(AgentExtratorTestBase):
    def test_cpf_ficticio_com_dv_invalido_e_aceito_e_sinalizado(self):
        resposta = self.resposta()
        resposta["faturado"]["cpf"] = CPF_FICTICIO_DV_INVALIDO
        self.cliente.gerar_json.return_value = resposta

        nota = self.agent.extrair(PDF)

        self.assertIsInstance(nota, NotaFiscalExtraida)
        self.assertEqual(nota.faturado.cpf, "99999999999")
        self.assertEqual(nota.validacoes.faturado_cpf.status, "invalido")
        self.assertEqual(
            nota.validacoes.faturado_cpf.motivo, "digitos_verificadores_invalidos"
        )
        self.assertEqual(nota.validacoes.fornecedor_cnpj.status, "valido")
        self.cliente.gerar_json.assert_called_once()

    def test_cnpj_com_dv_invalido_e_aceito_e_sinalizado(self):
        resposta = self.resposta()
        resposta["fornecedor"]["cnpj"] = "11.222.333/0001-82"
        self.cliente.gerar_json.return_value = resposta

        nota = self.agent.extrair(PDF)

        self.assertEqual(nota.fornecedor.cnpj, "11222333000182")
        self.assertEqual(nota.validacoes.fornecedor_cnpj.status, "invalido")
        self.cliente.gerar_json.assert_called_once()


class RespostaInvalidaTests(AgentExtratorTestBase):
    def assert_resposta_invalida(self, resposta):
        self.cliente.gerar_json.return_value = resposta

        with self.assertLogs("agents.extrator.agent", "WARNING"):
            with self.assertRaises(ExtracaoInvalidaError) as contexto:
                self.agent.extrair(PDF)

        return contexto.exception

    def test_resposta_fora_do_schema(self):
        casos = {
            "tipo_errado": self.resposta(valor_total="muito"),
            "item_sem_descricao": self.resposta(itens=[{"valor_total": 10}]),
            "cnpj_estrutura_impossivel": self.resposta(
                fornecedor={"cnpj": "11.222.333/0001"}
            ),
            "objeto_vazio": {},
        }
        for nome, resposta in casos.items():
            with self.subTest(caso=nome):
                excecao = self.assert_resposta_invalida(resposta)
                self.assertIsNotNone(excecao.__cause__)

    def test_lista_em_vez_de_objeto(self):
        self.assert_resposta_invalida([nota_valida()])

    def test_documento_que_nao_e_nota_fiscal(self):
        excecao = self.assert_resposta_invalida(
            self.resposta(documento_e_nota_fiscal=False)
        )

        self.assertIn("nota fiscal", str(excecao))

    def test_sem_itens(self):
        self.assert_resposta_invalida(self.resposta(itens=[]))

    def test_sem_valor_total(self):
        sem_campo = self.resposta()
        del sem_campo["valor_total"]
        casos = {"null": self.resposta(valor_total=None), "ausente": sem_campo}
        for nome, resposta in casos.items():
            with self.subTest(caso=nome):
                self.assert_resposta_invalida(resposta)


class FalhasDoGeminiTests(AgentExtratorTestBase):
    def test_falhas_de_servico_viram_extracao_indisponivel(self):
        casos = (
            GeminiTimeoutError(f"timeout {DETALHE_INTERNO}"),
            GeminiAPIError(f"erro 503 {DETALHE_INTERNO}", status_code=503),
            GeminiAPIError(f"quota {DETALHE_INTERNO}", status_code=429),
            GeminiAPIError(f"sem rede {DETALHE_INTERNO}", status_code=None),
            GeminiConfiguracaoError(f"sem chave {DETALHE_INTERNO}"),
        )
        for erro in casos:
            with self.subTest(erro=type(erro).__name__, status=getattr(erro, "status_code", None)):
                self.cliente.gerar_json.side_effect = erro

                with self.assertLogs("agents.extrator.agent", "WARNING"):
                    with self.assertRaises(ExtracaoIndisponivelError) as contexto:
                        self.agent.extrair(PDF)

                self.assertIs(contexto.exception.__cause__, erro)

    def test_status_code_aparece_no_log(self):
        for status in (429, 503):
            with self.subTest(status=status):
                self.cliente.gerar_json.side_effect = GeminiAPIError(
                    "x", status_code=status
                )

                with self.assertLogs("agents.extrator.agent", "WARNING") as logs:
                    with self.assertRaises(ExtracaoIndisponivelError):
                        self.agent.extrair(PDF)

                self.assertIn(f"status={status}", "\n".join(logs.output))

    def test_quota_excedida_429_vira_extracao_indisponivel(self):
        erro = GeminiAPIError("Erro da API do Gemini (status 429).", status_code=429)
        self.cliente.gerar_json.side_effect = erro

        with self.assertLogs("agents.extrator.agent", "WARNING"):
            with self.assertRaises(ExtracaoIndisponivelError) as contexto:
                self.agent.extrair(PDF)

        self.assertEqual(contexto.exception.codigo, "servico_indisponivel")
        self.assertIs(contexto.exception.__cause__, erro)
        self.assertEqual(contexto.exception.__cause__.status_code, 429)
        self.cliente.gerar_json.assert_called_once()

    def test_resposta_invalida_do_gemini_vira_extracao_invalida(self):
        erro = GeminiRespostaInvalidaError(f"json inválido {DETALHE_INTERNO}")
        self.cliente.gerar_json.side_effect = erro

        with self.assertLogs("agents.extrator.agent", "WARNING"):
            with self.assertRaises(ExtracaoInvalidaError) as contexto:
                self.agent.extrair(PDF)

        self.assertIs(contexto.exception.__cause__, erro)


class ExcecoesTests(SimpleTestCase):
    def test_hierarquia(self):
        for classe in (
            DocumentoIlegivelError,
            ExtracaoIndisponivelError,
            ExtracaoInvalidaError,
        ):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(issubclass(classe, ExtratorError))
                self.assertFalse(issubclass(classe, GeminiError))

    def test_codigos_estaveis(self):
        self.assertEqual(ExtratorError.codigo, "erro_extracao")
        self.assertEqual(DocumentoIlegivelError.codigo, "documento_ilegivel")
        self.assertEqual(ExtracaoIndisponivelError.codigo, "servico_indisponivel")
        self.assertEqual(ExtracaoInvalidaError.codigo, "resposta_invalida")

    def test_mensagem_padrao_nao_e_vazia(self):
        for classe in (
            ExtratorError,
            DocumentoIlegivelError,
            ExtracaoIndisponivelError,
            ExtracaoInvalidaError,
        ):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(str(classe()).strip())


class SigiloTests(AgentExtratorTestBase):
    """Mensagens e logs não podem expor detalhes internos nem dados da nota."""

    DADOS_SENSIVEIS = (
        DETALHE_INTERNO,
        "52998224725",
        CPF_VALIDO,
        "11222333000181",
        CNPJ_VALIDO,
        "1500",
        "Agro Insumos",
        "Produtor Teste",
    )

    def assert_sem_vazamento(self, excecao, logs):
        texto = "\n".join([str(excecao), repr(excecao), *logs.output])
        for dado in self.DADOS_SENSIVEIS:
            self.assertNotIn(dado, texto)

    def test_erros_do_gemini_nao_vazam_detalhes(self):
        for erro in (
            GeminiTimeoutError(DETALHE_INTERNO),
            GeminiAPIError(DETALHE_INTERNO, status_code=500),
            GeminiConfiguracaoError(DETALHE_INTERNO),
            GeminiRespostaInvalidaError(DETALHE_INTERNO),
        ):
            with self.subTest(erro=type(erro).__name__):
                self.cliente.gerar_json.side_effect = erro

                with self.assertLogs("agents.extrator.agent") as logs:
                    with self.assertRaises(ExtratorError) as contexto:
                        self.agent.extrair(PDF)

                self.assert_sem_vazamento(contexto.exception, logs)

    def test_validacao_nao_vaza_valores_da_resposta(self):
        resposta = self.resposta(
            faturado={"nome": "Produtor Teste", "cpf": "529.982.247-2X"},
            valor_total=-1500,
        )
        resposta["itens"] = [{"descricao": "", "valor_total": 1500}]
        resposta["observacao"] = DETALHE_INTERNO
        self.cliente.gerar_json.return_value = resposta

        with self.assertLogs("agents.extrator.agent") as logs:
            with self.assertRaises(ExtracaoInvalidaError) as contexto:
                self.agent.extrair(PDF)

        self.assert_sem_vazamento(contexto.exception, logs)
        self.assertNotIn("529.982.247-2X", "\n".join(logs.output))
        # Os caminhos dos campos inválidos podem (e devem) aparecer.
        saida = "\n".join(logs.output)
        self.assertIn("faturado.cpf", saida)
        self.assertIn("valor_total", saida)
        self.assertIn("itens.0.descricao", saida)

    def test_nota_rejeitada_por_regra_nao_vaza_dados(self):
        for resposta in (
            self.resposta(documento_e_nota_fiscal=False),
            self.resposta(itens=[]),
        ):
            with self.subTest():
                self.cliente.gerar_json.return_value = resposta

                with self.assertLogs("agents.extrator.agent") as logs:
                    with self.assertRaises(ExtracaoInvalidaError) as contexto:
                        self.agent.extrair(PDF)

                self.assert_sem_vazamento(contexto.exception, logs)


class CriacaoPreguicosaDoClienteTests(AgentExtratorTestBase):
    def test_instanciar_sem_cliente_nao_exige_api_key(self):
        with mock.patch("agents.extrator.agent.GeminiClient") as classe_cliente:
            agent = AgentExtrator()

        classe_cliente.assert_not_called()
        self.assertIsNone(agent.modelo)

    def test_cliente_padrao_e_criado_na_primeira_extracao_e_reutilizado(self):
        with mock.patch("agents.extrator.agent.GeminiClient") as classe_cliente:
            classe_cliente.return_value = self.cliente
            agent = AgentExtrator()

            agent.extrair(PDF)
            agent.extrair(PDF)

        classe_cliente.assert_called_once_with()
        self.assertEqual(self.cliente.gerar_json.call_count, 2)
        self.assertEqual(agent.modelo, "modelo-teste")

    def test_cliente_nao_e_criado_para_pdf_invalido(self):
        with mock.patch("agents.extrator.agent.GeminiClient") as classe_cliente:
            with self.assertRaises(DocumentoIlegivelError):
                AgentExtrator().extrair(b"")

        classe_cliente.assert_not_called()

    def test_sem_api_key_vira_extracao_indisponivel(self):
        # GeminiClient real, com GEMINI_API_KEY=None (settings da classe base).
        agent = AgentExtrator()

        with self.assertLogs("agents.extrator.agent", "WARNING"):
            with self.assertRaises(ExtracaoIndisponivelError) as contexto:
                agent.extrair(PDF)

        self.assertIsInstance(contexto.exception.__cause__, GeminiConfiguracaoError)
        self.sdk_client_classe.assert_not_called()


@override_settings(GEMINI_API_KEY=None)
class PayloadEnviadoAoGeminiTests(SimpleTestCase):
    """Usa o SDK real, mas substitui o envio HTTP: nada sai da máquina."""

    def test_payload_real_do_sdk(self):
        requisicoes = []
        resposta = nota_valida()
        resposta["faturado"]["cpf"] = CPF_FICTICIO_DV_INVALIDO
        corpo_resposta = {
            "candidates": [{
                "content": {"role": "model", "parts": [{"text": json.dumps(resposta)}]},
                "finishReason": "STOP",
            }]
        }

        def enviar(cliente_http, requisicao, **kwargs):
            requisicoes.append(requisicao)
            return httpx.Response(200, json=corpo_resposta, request=requisicao)

        with (
            mock.patch.object(httpx.Client, "send", new=enviar),
            # Aviso informativo do SDK sobre AFC; só polui a saída do teste.
            mock.patch.object(logging.getLogger("google_genai.models"), "disabled", True),
        ):
            cliente = GeminiClient(api_key="chave-falsa-teste", modelo="modelo-teste")
            nota = AgentExtrator(cliente=cliente).extrair(PDF)

        self.assertEqual(len(requisicoes), 1)
        requisicao = requisicoes[0]
        self.assertTrue(
            requisicao.url.path.endswith("/models/modelo-teste:generateContent")
        )
        corpo = json.loads(requisicao.content)

        parte_pdf = corpo["contents"][0]["parts"][1]["inlineData"]
        self.assertEqual(parte_pdf["mimeType"], "application/pdf")
        self.assertEqual(base64.b64decode(parte_pdf["data"]), PDF)

        configuracao = corpo["generationConfig"]
        self.assertEqual(configuracao["responseMimeType"], "application/json")
        self.assertEqual(configuracao["temperature"], 0)
        self.assertEqual(
            list(configuracao["responseSchema"]["properties"]),
            ["documento_e_nota_fiscal", "fornecedor", "faturado", "numero_nota",
             "data_emissao", "itens", "parcelas", "valor_total"],
        )
        self.assertNotIn("validacoes", json.dumps(corpo))
        self.assertIn("systemInstruction", corpo)

        self.assertEqual(nota.validacoes.faturado_cpf.status, "invalido")
