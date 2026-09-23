"""Schemas do Agent Classificador de despesas.

O Classificador recebe os dados estruturados produzidos pelo Agent Extrator
e interpreta o TipoDespesa com base principalmente nos itens da nota fiscal.

No MVP atual existem somente duas categorias de despesa.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
