"""Schema fiscal v2 alinhado Simon/Lopes; legado preservado em schemas.py.

VERSAO_SCHEMA=3 do Extrator é independente de VERSAO_DADOS=2 da GR-43.
Valores ausentes são corrigíveis, nunca substituídos por valores fictícios.
"""
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .schemas import (
    Cpf, Fornecedor, NotaFiscalExtraida, ParcelaExtraida, Validacoes, ValidacaoDocumento,
    ValorMonetarioPositivo, _ModeloExtracao, _validar_documento, cpf_dv_valido,
)

VERSAO_SCHEMA = 3


class DocumentoFiscal(_ModeloExtracao):
    chave_acesso: str | None = Field(default=None, max_length=200,
        description='Chave de acesso como impressa. Não corrigir DV nem completar caracteres; null se ausente.')
    modelo: str | None = Field(default=None, max_length=20,
        description='Modelo impresso (ex.: 55 ou 65); não presumir modelo.')
    serie: str | None = Field(default=None, max_length=20, description='Série como impressa; null se ausente.')


class FornecedorV2(Fornecedor):
    cpf: Cpf | None = Field(default=None, description='CPF do emitente como impresso; não escolher entre CPF e CNPJ.')


class ParcelaExtraidaV2(ParcelaExtraida):
    valor: ValorMonetarioPositivo | None = Field(default=None,
        description='Valor da parcela; null se não identificado, nunca inventar.')


class ValidacaoChave(BaseModel):
    status: Literal['valido', 'invalido', 'ausente']
    motivo: Literal['chave_acesso_invalida'] | None = None


class ValidacoesV2(Validacoes):
    fornecedor_cpf: ValidacaoDocumento
    chave_acesso: ValidacaoChave


def _validar_chave(chave):
    if chave is None:
        return ValidacaoChave(status='ausente')
    # Importação tardia evita ciclo: GR-22 usa validadores documentais do legado.
    from django.core.exceptions import ValidationError
    from financeiro.identidade_fiscal import validar_chave_acesso
    try:
        validar_chave_acesso(chave)
    except ValidationError:
        return ValidacaoChave(status='invalido', motivo='chave_acesso_invalida')
    return ValidacaoChave(status='valido')


class NotaFiscalExtraidaV2(NotaFiscalExtraida):
    fornecedor: FornecedorV2
    documento_fiscal: DocumentoFiscal
    parcelas: list[ParcelaExtraidaV2]
    valor_total: ValorMonetarioPositivo | None = Field(default=None,
        description='Total impresso; null se não identificado, nunca calcular para completar.')

    @computed_field
    @property
    def validacoes(self) -> ValidacoesV2:
        legado = super().validacoes.model_dump()
        return ValidacoesV2(**legado,
            fornecedor_cpf=_validar_documento(self.fornecedor.cpf, cpf_dv_valido),
            chave_acesso=_validar_chave(self.documento_fiscal.chave_acesso))
