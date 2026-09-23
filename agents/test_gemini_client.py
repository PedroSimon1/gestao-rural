import os
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings
from google.genai import errors

from .gemini_client import (
    GeminiAPIError,
    GeminiClient,
    GeminiConfiguracaoError,
    GeminiError,
    GeminiRespostaInvalidaError,
    GeminiTimeoutError,
)

CHAVE_TESTE = "chave-secreta-teste-gr9"

CONFIGURACAO_PADRAO = {
    "GEMINI_API_KEY": CHAVE_TESTE,
    "GEMINI_MODEL": "modelo-teste",
    "GEMINI_TIMEOUT_SEGUNDOS": "60",
    "GEMINI_MAX_TENTATIVAS": "3",
}


def erro_api(classe, codigo, status):
    return classe(
        codigo,
        {
            "error": {
                "code": codigo,
                "message": f"Falha usando a chave {CHAVE_TESTE}",
                "status": status,
            }
        },
    )


@override_settings(**CONFIGURACAO_PADRAO)
class GeminiClientTestBase(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch("agents.gemini_client.genai.Client")
        self.sdk_client_classe = patcher.start()
        self.addCleanup(patcher.stop)
        self.sdk_client = self.sdk_client_classe.return_value
        self.generate_content = self.sdk_client.models.generate_content

    def argumentos_do_sdk(self):
        return self.sdk_client_classe.call_args.kwargs

    def definir_resposta(self, texto):
        self.generate_content.return_value = mock.Mock(text=texto)


class GeminiClientConfiguracaoTests(GeminiClientTestBase):
    @override_settings(GEMINI_API_KEY=None)
    def test_chave_ausente_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

        self.sdk_client_classe.assert_not_called()

    @override_settings(GEMINI_API_KEY="")
    def test_chave_vazia_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    @override_settings(GEMINI_API_KEY="   ")
    def test_chave_so_com_espacos_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    @override_settings(GEMINI_MODEL=None)
    def test_modelo_ausente_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    def test_chave_valida_e_passada_explicitamente_ao_sdk(self):
        cliente = GeminiClient()

        argumentos = self.argumentos_do_sdk()
        self.assertEqual(argumentos["api_key"], CHAVE_TESTE)
        self.assertIs(argumentos["vertexai"], False)
        self.assertEqual(cliente.modelo, "modelo-teste")

    @override_settings(GEMINI_API_KEY=None)
    def test_google_api_key_nao_substitui_gemini_api_key_ausente(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "outra-chave"}):
            with self.assertRaises(GeminiConfiguracaoError):
                GeminiClient()

        self.sdk_client_classe.assert_not_called()

    def test_google_api_key_nao_substitui_gemini_api_key_configurada(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "outra-chave"}):
            GeminiClient()

        self.assertEqual(self.argumentos_do_sdk()["api_key"], CHAVE_TESTE)

    def test_parametros_explicitos_sobrescrevem_settings(self):
        cliente = GeminiClient(
            api_key="chave-explicita",
            modelo="modelo-explicito",
            timeout_segundos=10,
            max_tentativas=5,
        )

        argumentos = self.argumentos_do_sdk()
        self.assertEqual(argumentos["api_key"], "chave-explicita")
        self.assertEqual(cliente.modelo, "modelo-explicito")
        self.assertEqual(argumentos["http_options"].timeout, 10_000)
        self.assertEqual(
            argumentos["http_options"].retry_options.attempts, 5
        )

    def test_timeout_e_configurado_em_milissegundos(self):
        cliente = GeminiClient()

        self.assertEqual(cliente.timeout_segundos, 60)
        self.assertEqual(self.argumentos_do_sdk()["http_options"].timeout, 60_000)

    @override_settings(GEMINI_TIMEOUT_SEGUNDOS=None, GEMINI_MAX_TENTATIVAS=None)
    def test_timeout_e_tentativas_usam_padrao_quando_ausentes(self):
        cliente = GeminiClient()

        self.assertEqual(cliente.timeout_segundos, 60)
        self.assertEqual(cliente.max_tentativas, 3)

    @override_settings(GEMINI_TIMEOUT_SEGUNDOS="abc")
    def test_timeout_invalido_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    def test_tentativas_usam_retry_nativo_do_sdk(self):
        cliente = GeminiClient()

        retry = self.argumentos_do_sdk()["http_options"].retry_options
        self.assertEqual(cliente.max_tentativas, 3)
        self.assertEqual(retry.attempts, 3)

    @override_settings(GEMINI_MAX_TENTATIVAS="0")
    def test_tentativas_menor_que_um_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    def test_repr_nao_expoe_chave(self):
        cliente = GeminiClient()

        self.assertNotIn(CHAVE_TESTE, repr(cliente))
        self.assertNotIn(CHAVE_TESTE, str(cliente))


class GeminiClientChamadaTests(GeminiClientTestBase):
    def test_chamada_com_sucesso_retorna_texto(self):
        self.definir_resposta("resposta do modelo")

        texto = GeminiClient().gerar_conteudo(
            "Classifique este lançamento",
            instrucao_sistema="Você é um classificador.",
            temperatura=0.1,
        )

        self.assertEqual(texto, "resposta do modelo")
        argumentos = self.generate_content.call_args.kwargs
        self.assertEqual(argumentos["model"], "modelo-teste")
        self.assertEqual(argumentos["contents"], "Classifique este lançamento")
        self.assertEqual(argumentos["config"].temperature, 0.1)
        self.assertIsNone(argumentos["config"].response_mime_type)

    def test_aceita_conteudo_multimodal(self):
        self.definir_resposta("ok")
        conteudo = ["Extraia os dados", mock.sentinel.parte_pdf]

        GeminiClient().gerar_conteudo(conteudo)

        self.assertEqual(
            self.generate_content.call_args.kwargs["contents"], conteudo
        )

    def test_json_valido_e_convertido(self):
        self.definir_resposta('{"categoria": "insumos", "valor": 10.5}')
        schema = {
            "type": "OBJECT",
            "properties": {"categoria": {"type": "STRING"}},
        }

        resultado = GeminiClient().gerar_json(
            "Classifique", schema_resposta=schema
        )

        self.assertEqual(resultado, {"categoria": "insumos", "valor": 10.5})
        config = self.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertIsNotNone(config.response_schema)

    def test_json_invalido_gera_resposta_invalida(self):
        self.definir_resposta("isto não é json")

        with self.assertRaises(GeminiRespostaInvalidaError):
            GeminiClient().gerar_json("Classifique")

    def test_resposta_vazia_gera_resposta_invalida(self):
        for texto in (None, "", "   "):
            with self.subTest(texto=texto):
                self.definir_resposta(texto)

                with self.assertRaises(GeminiRespostaInvalidaError):
                    GeminiClient().gerar_conteudo("Olá")


class GeminiClientFalhasTests(GeminiClientTestBase):
    def test_timeout_gera_gemini_timeout_error(self):
        self.generate_content.side_effect = httpx.ReadTimeout("timeout")

        with self.assertLogs("agents.gemini_client", "WARNING"):
            with self.assertRaises(GeminiTimeoutError) as contexto:
                GeminiClient().gerar_conteudo("Olá")

        self.assertIsInstance(contexto.exception.__cause__, httpx.ReadTimeout)

    def test_erro_de_rede_gera_gemini_api_error(self):
        self.generate_content.side_effect = httpx.ConnectError("sem rede")

        with self.assertLogs("agents.gemini_client", "WARNING"):
            with self.assertRaises(GeminiAPIError) as contexto:
                GeminiClient().gerar_conteudo("Olá")

        self.assertIsNone(contexto.exception.status_code)

    def test_erro_da_api_gera_gemini_api_error_com_status(self):
        casos = (
            (errors.ClientError, 403, "PERMISSION_DENIED"),
            (errors.ClientError, 429, "RESOURCE_EXHAUSTED"),
            (errors.ServerError, 503, "UNAVAILABLE"),
        )
        for classe, codigo, status in casos:
            with self.subTest(codigo=codigo):
                erro = erro_api(classe, codigo, status)
                self.generate_content.side_effect = erro

                with self.assertLogs("agents.gemini_client", "WARNING"):
                    with self.assertRaises(GeminiAPIError) as contexto:
                        GeminiClient().gerar_conteudo("Olá")

                self.assertEqual(contexto.exception.status_code, codigo)
                self.assertIs(contexto.exception.__cause__, erro)

    def test_todas_as_excecoes_herdam_gemini_error(self):
        for classe in (
            GeminiConfiguracaoError,
            GeminiTimeoutError,
            GeminiAPIError,
            GeminiRespostaInvalidaError,
        ):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(issubclass(classe, GeminiError))

    def test_chave_nao_aparece_em_excecoes_nem_logs(self):
        falhas = (
            httpx.ReadTimeout(f"timeout {CHAVE_TESTE}"),
            httpx.ConnectError(f"sem rede {CHAVE_TESTE}"),
            erro_api(errors.ClientError, 401, "UNAUTHENTICATED"),
            erro_api(errors.ServerError, 500, "INTERNAL"),
        )
        for falha in falhas:
            with self.subTest(falha=type(falha).__name__):
                self.generate_content.side_effect = falha

                with self.assertLogs("agents.gemini_client") as logs:
                    with self.assertRaises(GeminiError) as contexto:
                        GeminiClient().gerar_conteudo("Olá")

                self.assertNotIn(CHAVE_TESTE, str(contexto.exception))
                self.assertNotIn(CHAVE_TESTE, repr(contexto.exception))
                self.assertNotIn(CHAVE_TESTE, "\n".join(logs.output))

    def test_chave_nao_aparece_em_erros_de_resposta(self):
        self.generate_content.side_effect = None
        for texto in (None, "json inválido"):
            with self.subTest(texto=texto):
                self.definir_resposta(texto)

                with self.assertRaises(GeminiRespostaInvalidaError) as contexto:
                    GeminiClient().gerar_json("Olá")

                self.assertNotIn(CHAVE_TESTE, str(contexto.exception))

    @override_settings(GEMINI_MODEL=None)
    def test_chave_nao_aparece_em_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError) as contexto:
            GeminiClient()

        self.assertNotIn(CHAVE_TESTE, str(contexto.exception))


@override_settings(**CONFIGURACAO_PADRAO)
class GeminiClientSdkRealTests(SimpleTestCase):
    """Usa o genai.Client real, sem chamadas de rede."""

    def test_sdk_real_usa_gemini_api_key_mesmo_com_google_api_key(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "outra-chave"}):
            cliente = GeminiClient()

        self.assertEqual(cliente._client._api_client.api_key, CHAVE_TESTE)
        self.assertNotIn(CHAVE_TESTE, repr(cliente))
