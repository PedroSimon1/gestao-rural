"""Orquestração stateless do processamento de uma nota fiscal em PDF.

Fluxo: bytes do PDF + Gemini API Key → GeminiClient → AgentExtrator →
AgentClassificador → JSON final.
Nada é gravado: o PDF, a chave e o resultado existem só durante a requisição.
"""

import logging
from dataclasses import dataclass

from django.views.decorators.debug import sensitive_variables

from agents.classificador.agent import AgentClassificador, ClassificadorError
from agents.extrator.agent import AgentExtrator, ExtratorError
from agents.gemini_client import GeminiClient, GeminiConfiguracaoError

logger = logging.getLogger(__name__)

MENSAGEM_ERRO_INTERNO = "Erro inesperado ao processar o documento."
MENSAGEM_GEMINI_NAO_CONFIGURADO = "Serviço de IA indisponível no momento."


class ProcessamentoError(Exception):
    """Falha do processamento. `mensagem` é segura para exibir na tela."""

    def __init__(self, etapa, codigo, mensagem):
        super().__init__(mensagem)
        self.etapa = etapa
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class ResultadoProcessamento:
    resultado: dict
    justificativa: str


def montar_resultado(nota, classificacao):
    """Monta o JSON final da atividade.

    Parte do dump JSON da extração (dinheiro como string, datas ISO,
    validacoes incluído) e acrescenta quantidade_parcelas e tipo_despesa.
    documento_e_nota_fiscal fica de fora: é sempre true quando se chega aqui.
    """
    extracao = nota.model_dump(mode="json")
    parcelas = extracao["parcelas"]

    return {
        "fornecedor": extracao["fornecedor"],
        "faturado": extracao["faturado"],
        "numero_nota": extracao["numero_nota"],
        "data_emissao": extracao["data_emissao"],
        "itens": extracao["itens"],
        "quantidade_parcelas": len(parcelas),
        "parcelas": parcelas,
        "valor_total": extracao["valor_total"],
        "tipo_despesa": classificacao.model_dump(mode="json")["tipo_despesa"],
        "validacoes": extracao["validacoes"],
    }


def _erro(etapa, exc):
    # Só o código e a mensagem fixa da exceção; nunca __cause__ ou traceback,
    # que podem conter dados da nota ou detalhes da API.
    logger.warning("Processamento falhou (%s/%s).", etapa, exc.codigo)
    return ProcessamentoError(etapa, exc.codigo, str(exc))


@sensitive_variables("gemini_api_key")
def _criar_cliente(gemini_api_key):
    """Um único GeminiClient com a chave da requisição, compartilhado pelos Agents."""
    try:
        return GeminiClient(api_key=gemini_api_key)
    except GeminiConfiguracaoError:
        # A mensagem da exceção nunca contém a chave, mas não é repassada.
        logger.warning("Processamento falhou (configuracao/servico_indisponivel).")
        raise ProcessamentoError(
            "configuracao", "servico_indisponivel", MENSAGEM_GEMINI_NAO_CONFIGURADO
        ) from None


@sensitive_variables("gemini_api_key")
def _executar(pdf_bytes, gemini_api_key, extrator, classificador):
    if extrator is None or classificador is None:
        cliente = _criar_cliente(gemini_api_key)
        if extrator is None:
            extrator = AgentExtrator(cliente=cliente)
        if classificador is None:
            classificador = AgentClassificador(cliente=cliente)

    try:
        nota = extrator.extrair(pdf_bytes)
    except ExtratorError as exc:
        raise _erro("extracao", exc) from None

    try:
        classificacao = classificador.classificar(nota)
    except ClassificadorError as exc:
        raise _erro("classificacao", exc) from None

    return ResultadoProcessamento(
        resultado=montar_resultado(nota, classificacao),
        justificativa=classificacao.justificativa,
    )


@sensitive_variables("gemini_api_key")
def processar_pdf(pdf_bytes, gemini_api_key, *, extrator=None, classificador=None):
    """Processa os bytes de um PDF e devolve o JSON final e a justificativa.

    `gemini_api_key` é a chave informada na tela: vai direto para um único
    GeminiClient usado pelo Extrator e pelo Classificador e é descartada ao
    fim da chamada. Nunca é gravada, logada nem devolvida.
    `extrator` e `classificador` só são injetados em testes.

    Toda falha (configuração, extração, classificação ou inesperada) vira
    ProcessamentoError com etapa, código e mensagem seguros.
    """
    try:
        return _executar(pdf_bytes, gemini_api_key, extrator, classificador)
    except ProcessamentoError:
        raise
    except Exception:
        logger.exception("Erro inesperado ao processar o documento.")
        raise ProcessamentoError(
            "processamento", "erro_interno", MENSAGEM_ERRO_INTERNO
        ) from None
