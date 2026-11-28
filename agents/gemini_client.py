import json
import logging
import math

import httpx
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

TIMEOUT_PADRAO_SEGUNDOS = 60
MAX_TENTATIVAS_PADRAO = 3

TAREFA_DOCUMENTO = "RETRIEVAL_DOCUMENT"
TAREFA_CONSULTA = "RETRIEVAL_QUERY"
TAREFAS_EMBEDDING = (TAREFA_DOCUMENTO, TAREFA_CONSULTA)
# O gemini-embedding-2 agrega várias entradas em UM vetor; o lote perderia a
# correspondência entre texto e vetor.
PREFIXO_MODELO_EMBEDDING_AGREGADOR = "gemini-embedding-2"


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


def _normalizar(valores, dimensao):
    if not valores or len(valores) != dimensao:
        raise GeminiRespostaInvalidaError(
            "Resposta do Gemini com embedding vazio ou de tamanho inesperado."
        )
    try:
        norma = math.hypot(*valores)
    except TypeError as exc:
        raise GeminiRespostaInvalidaError(
            "Resposta do Gemini com embedding não numérico."
        ) from exc
    if not math.isfinite(norma) or norma == 0:
        raise GeminiRespostaInvalidaError("Resposta do Gemini com embedding inválido.")
    return [valor / norma for valor in valores]


class GeminiClient:
    """Cliente compartilhado do Gemini usado pelos agents.

    A chave é sempre explícita (`api_key`): vem do formulário da tela e só
    existe durante a requisição. Não há fallback para settings nem para
    variáveis de ambiente. Modelo, timeout e tentativas vêm de
    django.conf.settings, mas podem ser sobrescritos por parâmetros.
    O SDK é criado somente quando esta classe é instanciada.
    """

    @sensitive_variables("api_key", "chave")
    def __init__(
        self,
        *,
        api_key=None,
        modelo=None,
        timeout_segundos=None,
        max_tentativas=None,
        modelo_embedding=None,
        dimensao_embedding=None,
    ):
        chave = _texto_ou_none(api_key)
        if chave is None:
            raise GeminiConfiguracaoError("Gemini API Key não informada.")

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

        self._modelo_embedding = _texto_ou_none(
            modelo_embedding if modelo_embedding is not None
            else getattr(settings, "GEMINI_MODELO_EMBEDDING", None)
        )
        # Validados só em gerar_embeddings: quem apenas gera texto não depende
        # da configuração de embeddings.
        self._dimensao_embedding = (
            dimensao_embedding if dimensao_embedding is not None
            else getattr(settings, "GEMINI_DIMENSAO_EMBEDDING", None)
        )

        # api_key e vertexai explícitos impedem que o SDK use GOOGLE_API_KEY
        # ou GEMINI_API_KEY do ambiente, ou troque de backend a partir dele.
        # A chave fica só dentro do SDK; esta classe não guarda cópia.
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

        resposta = self._chamar_sdk(
            self.modelo,
            lambda: self._client.models.generate_content(
                model=self.modelo,
                contents=conteudo,
                config=config,
            ),
        )

        try:
            texto = resposta.text
        except (AttributeError, ValueError) as exc:
            raise GeminiRespostaInvalidaError(
                "Resposta do Gemini sem conteúdo de texto."
            ) from exc

        if not texto or not texto.strip():
            raise GeminiRespostaInvalidaError("Resposta do Gemini vazia.")

        return texto

    @staticmethod
    def _chamar_sdk(modelo, chamada):
        """Executa a chamada ao SDK traduzindo as falhas para GeminiError."""
        try:
            return chamada()
        except httpx.TimeoutException as exc:
            logger.warning("Timeout na chamada ao Gemini (modelo=%s).", modelo)
            raise GeminiTimeoutError(
                "Tempo limite excedido na chamada ao Gemini."
            ) from exc
        except errors.APIError as exc:
            logger.warning(
                "Erro da API do Gemini (modelo=%s, status=%s).",
                modelo,
                exc.code,
            )
            raise GeminiAPIError(
                f"Erro da API do Gemini (status {exc.code}).",
                status_code=exc.code,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede na chamada ao Gemini (modelo=%s).", modelo)
            raise GeminiAPIError(
                "Falha de comunicação com o Gemini."
            ) from exc

    def gerar_embeddings(self, textos, *, tarefa):
        """Gera um vetor normalizado (L2) por texto, na mesma ordem.

        `tarefa` é TAREFA_DOCUMENTO (indexação) ou TAREFA_CONSULTA (pergunta).
        A normalização é feita aqui porque a API só normaliza a saída de 3072
        dimensões.
        """
        if tarefa not in TAREFAS_EMBEDDING:
            raise GeminiConfiguracaoError("Tarefa de embedding inválida.")
        if self._modelo_embedding is None:
            raise GeminiConfiguracaoError("GEMINI_MODELO_EMBEDDING não configurado.")
        if self._modelo_embedding.startswith(PREFIXO_MODELO_EMBEDDING_AGREGADOR):
            raise GeminiConfiguracaoError(
                "O modelo de embedding informado agrega o lote em um único vetor "
                "e não é suportado; use o gemini-embedding-001."
            )
        dimensao = _inteiro_positivo(
            self._dimensao_embedding, None, "GEMINI_DIMENSAO_EMBEDDING"
        )
        if dimensao is None:
            raise GeminiConfiguracaoError("GEMINI_DIMENSAO_EMBEDDING não configurado.")

        textos = list(textos)
        if not textos:
            raise GeminiConfiguracaoError("Nenhum texto informado para gerar embeddings.")
        if any(not isinstance(texto, str) or not texto.strip() for texto in textos):
            raise GeminiConfiguracaoError("Texto vazio informado para gerar embeddings.")

        config = types.EmbedContentConfig(
            task_type=tarefa,
            output_dimensionality=dimensao,
        )
        resposta = self._chamar_sdk(
            self._modelo_embedding,
            lambda: self._client.models.embed_content(
                model=self._modelo_embedding,
                contents=textos,
                config=config,
            ),
        )

        embeddings = getattr(resposta, "embeddings", None)
        if not isinstance(embeddings, (list, tuple)) or len(embeddings) != len(textos):
            raise GeminiRespostaInvalidaError(
                "Resposta do Gemini com quantidade de embeddings diferente da enviada."
            )
        return [
            _normalizar(getattr(embedding, "values", None), dimensao)
            for embedding in embeddings
        ]

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
