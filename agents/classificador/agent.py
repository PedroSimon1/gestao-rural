"""Agent responsável pela classificação da despesa da nota fiscal."""

import json
import logging

from pydantic import ValidationError

from agents.gemini_client import (
    GeminiClient,
    GeminiError,
    GeminiRespostaInvalidaError,
)
from agents.extrator.schemas import NotaFiscalExtraida

from .schemas import ClassificacaoDespesa


logger = logging.getLogger(__name__)


INSTRUCAO_SISTEMA = """\
Você é um classificador de despesas de notas fiscais rurais.

Sua tarefa é analisar os itens da nota fiscal e classificar a despesa em uma
das categorias disponíveis no MVP.

Categorias permitidas:

1. MANUTENCAO_E_OPERACAO
   Use para despesas relacionadas à manutenção e operação de máquinas,
   equipamentos e veículos.
   Exemplos: óleo diesel, óleo lubrificante, peças e materiais de manutenção.

2. INFRAESTRUTURA_E_UTILIDADES
   Use para despesas relacionadas à infraestrutura da propriedade e utilidades.
   Exemplos: materiais hidráulicos, materiais elétricos e materiais de construção.

Regras:
- Escolha somente uma das categorias permitidas.
- Não crie categorias novas.
- Baseie a decisão principalmente na descrição dos itens.
- Não invente informações que não estejam nos dados recebidos.
- Se nenhuma categoria for adequada, use null em tipo_despesa.
- A justificativa deve ser curta e explicar quais itens motivaram a decisão.
"""


INSTRUCAO_CLASSIFICACAO = (
    "Classifique a despesa usando exclusivamente as categorias definidas."
)


class ClassificadorError(Exception):
    """Erro base do Agent Classificador."""

    codigo = "erro_classificacao"
    mensagem_padrao = "Não foi possível classificar a despesa."

    def __init__(self, mensagem=None):
        super().__init__(mensagem or self.mensagem_padrao)


class ClassificacaoIndisponivelError(ClassificadorError):
    codigo = "servico_indisponivel"
    mensagem_padrao = "Serviço de classificação indisponível no momento."


class ClassificacaoInvalidaError(ClassificadorError):
    codigo = "classificacao_invalida"
    mensagem_padrao = "A classificação retornada não é válida."


class ClassificacaoInconclusivaError(ClassificadorError):
    codigo = "classificacao_inconclusiva"
    mensagem_padrao = (
        "A despesa não se encaixa nas categorias disponíveis no MVP."
    )


def _campos_invalidos(erro):
    """Retorna somente caminhos de campos inválidos, nunca seus valores."""
    caminhos = {
        ".".join(str(parte) for parte in detalhe["loc"]) or "<raiz>"
        for detalhe in erro.errors(include_input=False, include_url=False)
    }
    return ", ".join(sorted(caminhos))


def _montar_contexto(nota):
    """Seleciona somente os dados necessários para a classificação."""
    return {
        "fornecedor": {
            "razao_social": nota.fornecedor.razao_social,
            "nome_fantasia": nota.fornecedor.nome_fantasia,
        },
        "itens": [
            {
                "descricao": item.descricao,
                "quantidade": (
                    str(item.quantidade)
                    if item.quantidade is not None
                    else None
                ),
                "valor_total": (
                    str(item.valor_total)
                    if item.valor_total is not None
                    else None
                ),
            }
            for item in nota.itens
        ],
        "valor_total": str(nota.valor_total),
    }


class AgentClassificador:
    """Classifica o TipoDespesa a partir de uma NotaFiscalExtraida."""

    def __init__(self, cliente=None):
        # O cliente padrão só é criado quando a primeira classificação ocorrer.
        self._cliente = cliente

    @property
    def modelo(self):
        """Modelo Gemini em uso ou None antes da criação do cliente."""
        return getattr(self._cliente, "modelo", None)

    def classificar(self, nota):
        if not isinstance(nota, NotaFiscalExtraida):
            raise ClassificacaoInvalidaError(
                "Os dados recebidos para classificação são inválidos."
            )

        if not nota.documento_e_nota_fiscal or not nota.itens:
            raise ClassificacaoInvalidaError(
                "A nota fiscal não possui dados suficientes para classificação."
            )

        contexto = _montar_contexto(nota)

        conteudo = [
            INSTRUCAO_CLASSIFICACAO,
            json.dumps(contexto, ensure_ascii=False),
        ]

        try:
            if self._cliente is None:
                self._cliente = GeminiClient()

            dados = self._cliente.gerar_json(
                conteudo,
                instrucao_sistema=INSTRUCAO_SISTEMA,
                schema_resposta=ClassificacaoDespesa,
                temperatura=0,
            )

        except GeminiRespostaInvalidaError as exc:
            logger.warning("Resposta inválida do Gemini na classificação.")
            raise ClassificacaoInvalidaError() from exc

        except GeminiError as exc:
            logger.warning(
                "Classificação indisponível (%s, status=%s).",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            raise ClassificacaoIndisponivelError() from exc

        try:
            classificacao = ClassificacaoDespesa.model_validate(dados)
        except ValidationError as exc:
            logger.warning(
                "Resposta da classificação fora do schema (campos: %s).",
                _campos_invalidos(exc),
            )
            raise ClassificacaoInvalidaError() from exc

        if classificacao.tipo_despesa is None:
            logger.warning(
                "Despesa fora das categorias disponíveis no MVP."
            )
            raise ClassificacaoInconclusivaError()

        return classificacao