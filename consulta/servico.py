"""Consulta em linguagem natural: recupera movimentos, monta o contexto e pede a resposta ao Gemini.

Nada é gravado. A pergunta, o contexto e a chave existem só durante a chamada
e nunca vão para logs; os registros daqui trazem apenas o código do erro.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from agents.gemini_client import (
    GeminiAPIError, GeminiClient, GeminiConfiguracaoError, GeminiError,
    GeminiRespostaInvalidaError, GeminiTimeoutError,
)
from agents.rag.agent import AgenteRag
from financeiro.models import MovimentoConta, TipoMovimento
from financeiro.templatetags.moeda import moeda

from . import recuperacao_simples
from .fontes import Fonte
from .texto import carregar_movimentos, montar_contexto

logger = logging.getLogger(__name__)

MODO_SIMPLES = "simples"
MODO_SEMANTICO = "semantico"

_STATUS_CHAVE_RECUSADA = frozenset({400, 401, 403})
_STATUS_LIMITE = 429

MENSAGENS = {
    "modo_invalido": "Escolha uma forma de busca válida.",
    "pergunta_vazia": "Digite a pergunta.",
    "configuracao": "A consulta está indisponível por um problema de configuração. Avise a equipe.",
    "sem_dados": "Ainda não há contas cadastradas para consultar.",
    "chave_invalida": "A Gemini API Key foi recusada. Confira se ela está correta e tem permissão de uso.",
    "limite_excedido": "O limite de uso da Gemini API Key foi atingido. Aguarde um pouco e tente novamente.",
    "tempo_esgotado": "O Gemini demorou demais para responder. Tente novamente.",
    "servico_indisponivel": "Não foi possível falar com o Gemini agora. Tente novamente mais tarde.",
    "resposta_invalida": "O Gemini devolveu uma resposta inutilizável. Tente novamente.",
}


class ConsultaError(Exception):
    """Falha da consulta. `mensagem` é segura para exibir na tela."""

    def __init__(self, codigo, mensagem=None):
        mensagem = mensagem or MENSAGENS[codigo]
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class FonteExibida:
    movimento_id: int
    rotulo: str
    pontuacao: float | None
    motivo: str


@dataclass(frozen=True)
class RespostaConsulta:
    modo: str
    pergunta: str
    resposta: str
    fontes: tuple[FonteExibida, ...]
    aviso: str | None


@dataclass(frozen=True)
class Modo:
    rotulo: str
    # (pergunta, limite, cliente) -> fontes; o cliente só serve às buscas que chamam o Gemini.
    recuperar: Callable[[str, int, GeminiClient], list[Fonte]]
    # (fontes) -> aviso a exibir junto da resposta, ou None.
    aviso: Callable[[list[Fonte]], str | None]


def _recuperar_simples(pergunta, limite, cliente):
    return recuperacao_simples.recuperar(pergunta, limite)


def _aviso_simples(fontes):
    if fontes and all(fonte.pontuacao == 0 for fonte in fontes):
        return (
            "Nenhuma conta citou os termos da pergunta; a resposta usa as contas mais "
            "recentes e pode não cobrir o que você procura."
        )
    return None


# A Etapa 2.5 acrescenta MODO_SEMANTICO aqui; o fluxo de `consultar` não muda.
MODOS = {
    MODO_SIMPLES: Modo("Busca simples (palavras da pergunta)", _recuperar_simples, _aviso_simples),
}


def _falha(codigo):
    logger.warning("Consulta falhou (%s).", codigo)
    return ConsultaError(codigo)


def _limite_de_fontes():
    try:
        limite = int(str(settings.RAG_TOP_K).strip())
    except (AttributeError, TypeError, ValueError):
        limite = 0
    if limite < 1:
        raise _falha("configuracao")
    return limite


def _codigo_do_erro_gemini(exc):
    if isinstance(exc, GeminiTimeoutError):
        return "tempo_esgotado"
    if isinstance(exc, GeminiRespostaInvalidaError):
        return "resposta_invalida"
    if isinstance(exc, GeminiAPIError):
        if exc.status_code in _STATUS_CHAVE_RECUSADA:
            return "chave_invalida"
        if exc.status_code == _STATUS_LIMITE:
            return "limite_excedido"
    # Inclui GeminiConfiguracaoError (modelo não configurado) e falhas de rede.
    return "servico_indisponivel"


def _rotulo(movimento):
    tipo = "Conta a pagar" if movimento.tipo == TipoMovimento.APAGAR else "Conta a receber"
    return f"{tipo} #{movimento.pk} — {movimento.contraparte.razao_social} — {moeda(movimento.valor_total)}"


@sensitive_variables("api_key")
def _criar_cliente(api_key):
    try:
        return GeminiClient(api_key=api_key)
    except GeminiConfiguracaoError:
        # A mensagem da exceção nunca contém a chave, mas não é repassada.
        raise _falha("servico_indisponivel") from None


@sensitive_variables("api_key")
def consultar(pergunta: str, modo: str, api_key: str) -> RespostaConsulta:
    """Responde à pergunta com base nos movimentos recuperados pelo `modo` escolhido."""
    estrategia = MODOS.get(modo)
    if estrategia is None:
        raise _falha("modo_invalido")
    pergunta = (pergunta or "").strip()
    if not pergunta:
        raise _falha("pergunta_vazia")
    limite = _limite_de_fontes()
    if not MovimentoConta.objects.exists():
        # Sem dados, não há o que perguntar ao Gemini (nem chave a gastar).
        raise _falha("sem_dados")

    try:
        cliente = _criar_cliente(api_key)
        fontes = estrategia.recuperar(pergunta, limite, cliente)
        movimentos = carregar_movimentos([fonte.movimento_id for fonte in fontes])
        if not movimentos:
            raise _falha("sem_dados")
        texto = AgenteRag(cliente).responder(pergunta, montar_contexto(movimentos))
    except ConsultaError:
        raise
    except GeminiError as exc:
        # Só o tipo e o status; nunca a mensagem nem a causa, que podem trazer detalhes da API.
        logger.warning(
            "Consulta indisponível (%s, status=%s).",
            type(exc).__name__, getattr(exc, "status_code", None),
        )
        raise ConsultaError(_codigo_do_erro_gemini(exc)) from None

    rotulos = {movimento.pk: _rotulo(movimento) for movimento in movimentos}
    exibidas = tuple(
        FonteExibida(fonte.movimento_id, rotulos[fonte.movimento_id], fonte.pontuacao, fonte.motivo)
        for fonte in fontes if fonte.movimento_id in rotulos
    )
    return RespostaConsulta(
        modo=modo, pergunta=pergunta, resposta=texto, fontes=exibidas,
        aviso=estrategia.aviso(fontes),
    )
