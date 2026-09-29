"""Orquestração stateless do processamento de uma nota fiscal em PDF.

Fluxo: bytes do PDF → AgentExtrator → AgentClassificador → JSON final.
Nada é gravado: o PDF e o resultado existem só durante a requisição.
"""

import logging
from dataclasses import dataclass

from agents.classificador.agent import AgentClassificador, ClassificadorError
from agents.extrator.agent import AgentExtrator, ExtratorError

logger = logging.getLogger(__name__)

MENSAGEM_ERRO_INTERNO = "Erro inesperado ao processar o documento."


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


def _executar(pdf_bytes, extrator, classificador):
    if extrator is None:
        extrator = AgentExtrator()
    if classificador is None:
        classificador = AgentClassificador()

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


def processar_pdf(pdf_bytes, *, extrator=None, classificador=None):
    """Processa os bytes de um PDF e devolve o JSON final e a justificativa.

    Toda falha (extração, classificação ou inesperada) vira
    ProcessamentoError com etapa, código e mensagem seguros.
    """
    try:
        return _executar(pdf_bytes, extrator, classificador)
    except ProcessamentoError:
        raise
    except Exception:
        logger.exception("Erro inesperado ao processar o documento.")
        raise ProcessamentoError(
            "processamento", "erro_interno", MENSAGEM_ERRO_INTERNO
        ) from None
