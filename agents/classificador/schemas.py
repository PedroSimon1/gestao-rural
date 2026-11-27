"""Schemas do Agent Classificador de despesas.

O Classificador recebe os dados estruturados produzidos pelo Agent Extrator
e interpreta o TipoDespesa com base principalmente nos itens da nota fiscal.

No MVP atual existem somente duas categorias de despesa.
"""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator


VERSAO_SCHEMA = 1


class TipoDespesa(str, Enum):
    """Categorias de despesa permitidas no MVP."""

    MANUTENCAO_E_OPERACAO = "MANUTENCAO_E_OPERACAO"
    INFRAESTRUTURA_E_UTILIDADES = "INFRAESTRUTURA_E_UTILIDADES"


class ClassificacaoDespesa(BaseModel):
    """Resultado estruturado produzido pelo Agent Classificador."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    tipo_despesa: TipoDespesa | None = Field(
        description=(
            "Categoria da despesa. Use null quando os itens não permitirem "
            "classificar com segurança em nenhuma categoria disponível."
        ),
    )

    justificativa: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Explicação curta da classificação baseada nos itens da nota fiscal."
        ),
    )

    @field_validator("justificativa")
    @classmethod
    def limpar_justificativa(cls, valor):
        return " ".join(valor.split())


@dataclass(frozen=True)
class CategoriaDespesa:
    """Uma classificação de despesa que o Classificador pode escolher.

    Vem do cadastro do sistema (classificações ativas de DESPESA); o Agent não acessa o banco.
    """

    codigo: str
    descricao: str


@lru_cache(maxsize=32)
def _modelo_para(codigos):
    return create_model(
        "ClassificacaoDespesaDinamica",
        __base__=ClassificacaoDespesa,
        tipo_despesa=(
            Literal[codigos] | None,
            Field(description=(
                "Código da categoria da despesa, exatamente como na lista permitida. Use null quando "
                "os itens não permitirem classificar com segurança em nenhuma categoria."
            )),
        ),
    )


def classificacao_para(categorias):
    """Modelo de resposta cujo `tipo_despesa` só aceita os códigos de `categorias` (ou null).

    É também o `response_schema` enviado ao Gemini (enum fechado) e a validação da resposta.
    """
    return _modelo_para(tuple(categoria.codigo for categoria in categorias))
