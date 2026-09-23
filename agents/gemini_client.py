import json
import logging

import httpx
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

TIMEOUT_PADRAO_SEGUNDOS = 60
MAX_TENTATIVAS_PADRAO = 3


class GeminiError(Exception):
    """Erro base do cliente Gemini. Os agents devem capturar somente esta."""


class GeminiConfiguracaoError(GeminiError):
    pass


class GeminiTimeoutError(GeminiError):
    pass


class GeminiAPIError(GeminiError):
    def __init__(self, mensagem, status_code=None):
        super().__init__(mensagem)
        self.status_code = status_code


class GeminiRespostaInvalidaError(GeminiError):
    pass


def _texto_ou_none(valor):
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def _inteiro_positivo(valor, padrao, nome):
    if valor is None or valor == "":
        return padrao
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise GeminiConfiguracaoError(
            f"{nome} deve ser um número inteiro."
        ) from exc
    if numero < 1:
        raise GeminiConfiguracaoError(f"{nome} deve ser maior que zero.")
    return numero


class GeminiClient:
    """Cliente compartilhado do Gemini usado pelos agents.

    A configuração vem de django.conf.settings, mas pode ser sobrescrita
    por parâmetros explícitos. O SDK é criado somente quando esta classe
    é instanciada.
    """

    @sensitive_variables("api_key", "chave")
    def __init__(
        self,
        *,
        api_key=None,
        modelo=None,
        timeout_segundos=None,
        max_tentativas=None,
    ):
        chave = _texto_ou_none(
            api_key if api_key is not None
            else getattr(settings, "GEMINI_API_KEY", None)
        )
        if chave is None:
            raise GeminiConfiguracaoError("GEMINI_API_KEY não configurada.")

        self.modelo = _texto_ou_none(
            modelo if modelo is not None
            else getattr(settings, "GEMINI_MODEL", None)
        )
        if self.modelo is None:
            raise GeminiConfiguracaoError("GEMINI_MODEL não configurado.")

        self.timeout_segundos = _inteiro_positivo(
            timeout_segundos if timeout_segundos is not None
            else getattr(settings, "GEMINI_TIMEOUT_SEGUNDOS", None),
            TIMEOUT_PADRAO_SEGUNDOS,
            "GEMINI_TIMEOUT_SEGUNDOS",
        )
        self.max_tentativas = _inteiro_positivo(
            max_tentativas if max_tentativas is not None
            else getattr(settings, "GEMINI_MAX_TENTATIVAS", None),
            MAX_TENTATIVAS_PADRAO,
            "GEMINI_MAX_TENTATIVAS",
        )

        # api_key e vertexai explícitos impedem que o SDK use GOOGLE_API_KEY
        # ou troque de backend a partir de variáveis de ambiente.
        self._client = genai.Client(
            api_key=chave,
            vertexai=False,
            http_options=types.HttpOptions(
                timeout=self.timeout_segundos * 1000,
                retry_options=types.HttpRetryOptions(
                    attempts=self.max_tentativas,
                ),
            ),
        )

    def __repr__(self):
        return (
            f"GeminiClient(modelo={self.modelo!r}, "
            f"timeout_segundos={self.timeout_segundos}, "
            f"max_tentativas={self.max_tentativas})"
        )

    def gerar_conteudo(
        self,
        conteudo,
        *,
        instrucao_sistema=None,
        schema_resposta=None,
        tipo_resposta=None,
        temperatura=None,
    ):
        """Envia o conteúdo ao Gemini e retorna o texto da resposta.

        `conteudo` pode ser texto ou uma lista de partes do SDK
        (ex.: types.Part.from_bytes(data=..., mime_type="application/pdf")).
        """
        config = types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            response_mime_type=tipo_resposta,
            response_schema=schema_resposta,
            temperature=temperatura,
        )

        try:
            resposta = self._client.models.generate_content(
                model=self.modelo,
                contents=conteudo,
                config=config,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Timeout na chamada ao Gemini (modelo=%s).", self.modelo)
            raise GeminiTimeoutError(
                "Tempo limite excedido na chamada ao Gemini."
            ) from exc
        except errors.APIError as exc:
            logger.warning(
                "Erro da API do Gemini (modelo=%s, status=%s).",
                self.modelo,
                exc.code,
            )
            raise GeminiAPIError(
                f"Erro da API do Gemini (status {exc.code}).",
                status_code=exc.code,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede na chamada ao Gemini (modelo=%s).", self.modelo)
            raise GeminiAPIError(
                "Falha de comunicação com o Gemini."
            ) from exc

        try:
            texto = resposta.text
        except (AttributeError, ValueError) as exc:
            raise GeminiRespostaInvalidaError(
                "Resposta do Gemini sem conteúdo de texto."
            ) from exc

        if not texto or not texto.strip():
            raise GeminiRespostaInvalidaError("Resposta do Gemini vazia.")

        return texto

    def gerar_json(
        self,
        conteudo,
        *,
        instrucao_sistema=None,
        schema_resposta=None,
        temperatura=None,
    ):
        """Solicita saída JSON ao Gemini e retorna a estrutura Python."""
        texto = self.gerar_conteudo(
            conteudo,
            instrucao_sistema=instrucao_sistema,
            schema_resposta=schema_resposta,
            tipo_resposta="application/json",
            temperatura=temperatura,
        )

        try:
            return json.loads(texto)
        except json.JSONDecodeError as exc:
            raise GeminiRespostaInvalidaError(
                "Resposta do Gemini não é um JSON válido."
            ) from exc
