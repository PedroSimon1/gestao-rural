"""Schema da extração de notas fiscais.

As mesmas classes servem de `response_schema` para o Gemini e de validação
da resposta. Valores e datas usam tipos anotados com `WithJsonSchema` para que
o schema enviado ao Gemini tenha apenas NUMBER e STRING simples.

CPF e CNPJ são normalizados e preservados como extraídos; a checagem dos
dígitos verificadores é separada e informada em `NotaFiscalExtraida.validacoes`.
DV válido significa apenas que o número é bem formado, não que o documento
existe.
"""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    computed_field,
    field_validator,
    model_validator,
)

VERSAO_SCHEMA = 1

CENTAVO = Decimal("0.01")
# Teto de sanidade para valores extraídos: até 12 dígitos com 2 casas decimais
# (menor que 10 bilhões). Acima disso o valor é tratado como leitura inválida.
LIMITE_VALOR_MONETARIO = Decimal("10000000000")

_SEPARADORES_DOCUMENTO = re.compile(r"[.\-/\s]")
_FORMATO_CPF = re.compile(r"\d{11}")
# CNPJ numérico ou alfanumérico (IN RFB 2.229/2024): 12 posições [0-9A-Z]
# seguidas de 2 dígitos verificadores numéricos.
_FORMATO_CNPJ = re.compile(r"[0-9A-Z]{12}\d{2}")
_FORMATO_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")

_PESOS_CNPJ_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_DV2 = (6, *_PESOS_CNPJ_DV1)


def _digito_verificador(base, pesos):
    # ord(c) - 48 vale para dígitos (0-9) e letras (A=17 ... Z=42),
    # como define a regra do CNPJ alfanumérico; para CPF e CNPJ numérico
    # é o próprio valor do dígito.
    soma = sum((ord(caractere) - 48) * peso for caractere, peso in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def _limpar_cpf(valor):
    return _SEPARADORES_DOCUMENTO.sub("", valor)


def _limpar_cnpj(valor):
    return _SEPARADORES_DOCUMENTO.sub("", valor).upper()


def _normalizar_cpf(valor):
    # Só a estrutura é exigida; o DV é checado à parte em cpf_dv_valido.
    cpf = _limpar_cpf(valor)
    if not _FORMATO_CPF.fullmatch(cpf):
        raise ValueError("CPF com estrutura inválida.")
    return cpf


def _normalizar_cnpj(valor):
    # Só a estrutura é exigida; o DV é checado à parte em cnpj_dv_valido.
    cnpj = _limpar_cnpj(valor)
    if not _FORMATO_CNPJ.fullmatch(cnpj):
        raise ValueError("CNPJ com estrutura inválida.")
    return cnpj


def cpf_dv_valido(cpf):
    """Indica se o CPF tem estrutura e dígitos verificadores válidos.

    Sequências repetidas (ex.: 999.999.999-99) fecham a conta do DV, mas
    são tratadas como inválidas, como faz a Receita Federal.
    """
    cpf = _limpar_cpf(cpf)
    if not _FORMATO_CPF.fullmatch(cpf) or len(set(cpf)) == 1:
        return False
    dv1 = _digito_verificador(cpf[:9], range(10, 1, -1))
    dv2 = _digito_verificador(cpf[:9] + dv1, range(11, 1, -1))
    return cpf[9:] == dv1 + dv2


def cnpj_dv_valido(cnpj):
    """Indica se o CNPJ (numérico ou alfanumérico) tem DV válido."""
    cnpj = _limpar_cnpj(cnpj)
    if not _FORMATO_CNPJ.fullmatch(cnpj) or len(set(cnpj)) == 1:
        return False
    dv1 = _digito_verificador(cnpj[:12], _PESOS_CNPJ_DV1)
    dv2 = _digito_verificador(cnpj[:12] + dv1, _PESOS_CNPJ_DV2)
    return cnpj[12:] == dv1 + dv2


def _converter_data(valor):
    if type(valor) is date:  # datetime (subclasse de date) não é aceito
        return valor
    if not isinstance(valor, str) or not _FORMATO_DATA.fullmatch(valor):
        raise ValueError("Data deve estar no formato AAAA-MM-DD.")
    return date.fromisoformat(valor)


def _recusar_booleano(valor):
    # Sem isto o Pydantic aceitaria True/False como 1/0.
    if isinstance(valor, bool):
        raise ValueError("Valor numérico inválido.")
    return valor


def _nao_negativo(valor):
    if valor < 0:
        raise ValueError("O valor não pode ser negativo.")
    return valor


def _valor_monetario(valor):
    # O limite é checado antes do quantize, que falharia com expoentes enormes.
    if abs(valor) >= LIMITE_VALOR_MONETARIO:
        raise ValueError("Valor monetário acima do limite suportado.")
    return _nao_negativo(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP))


def _positivo(valor):
    if valor <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    return valor


_SCHEMA_NUMERO = {"type": "number"}

Cpf = Annotated[str, AfterValidator(_normalizar_cpf)]
Cnpj = Annotated[str, AfterValidator(_normalizar_cnpj)]
Data = Annotated[
    date,
    BeforeValidator(_converter_data),
    WithJsonSchema({"type": "string", "description": "Data no formato AAAA-MM-DD."}),
]
Quantidade = Annotated[
    Decimal,
    BeforeValidator(_recusar_booleano),
    AfterValidator(_nao_negativo),
    WithJsonSchema(_SCHEMA_NUMERO),
]
ValorMonetario = Annotated[
    Decimal,
    BeforeValidator(_recusar_booleano),
    AfterValidator(_valor_monetario),
    WithJsonSchema(_SCHEMA_NUMERO),
]
ValorMonetarioPositivo = Annotated[ValorMonetario, AfterValidator(_positivo)]


class _ModeloExtracao(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _limpar_texto(cls, valor):
        # Junta espaços repetidos/quebras de linha e trata texto vazio como ausente.
        if isinstance(valor, str):
            return " ".join(valor.split()) or None
        return valor


class Fornecedor(_ModeloExtracao):
    razao_social: str | None = Field(
        default=None, description="Razão social do emitente/prestador."
    )
    nome_fantasia: str | None = Field(
        default=None, description="Nome fantasia do emitente/prestador."
    )
    cnpj: Cnpj | None = Field(
        default=None,
        description="CNPJ do emitente/prestador, exatamente como impresso.",
    )


class Faturado(_ModeloExtracao):
    nome: str | None = Field(
        default=None, description="Nome do destinatário/tomador."
    )
    cpf: Cpf | None = Field(
        default=None,
        description=(
            "CPF do destinatário/tomador, exatamente como impresso. "
            "null se não houver CPF."
        ),
    )


class Item(_ModeloExtracao):
    descricao: str = Field(
        min_length=1, description="Descrição do produto ou serviço."
    )
    quantidade: Quantidade | None = None
    valor_unitario: ValorMonetario | None = None
    valor_total: ValorMonetario | None = None


class ParcelaExtraida(_ModeloExtracao):
    numero: int | None = Field(
        default=None, description="Número da parcela (1, 2, 3...)."
    )
    data_vencimento: Data | None = None
    valor: ValorMonetarioPositivo

    @field_validator("numero")
    @classmethod
    def _numero_positivo(cls, numero):
        if numero is not None and numero < 1:
            raise ValueError("O número da parcela deve ser maior que zero.")
        return numero


class ValidacaoDocumento(BaseModel):
    status: Literal["valido", "invalido", "ausente"]
    motivo: Literal["digitos_verificadores_invalidos"] | None = None


class Validacoes(BaseModel):
    # Somente o resultado; os números ficam em fornecedor/faturado.
    fornecedor_cnpj: ValidacaoDocumento
    faturado_cpf: ValidacaoDocumento


def _validar_documento(numero, dv_valido):
    if numero is None:
        return ValidacaoDocumento(status="ausente")
    if dv_valido(numero):
        return ValidacaoDocumento(status="valido")
    return ValidacaoDocumento(
        status="invalido", motivo="digitos_verificadores_invalidos"
    )


class NotaFiscalExtraida(_ModeloExtracao):
    documento_e_nota_fiscal: bool = Field(
        description="true somente se o documento for uma nota fiscal."
    )
    # Blocos e listas são obrigatórios para o Gemini sempre devolver a
    # estrutura completa; os campos internos é que podem ser null.
    fornecedor: Fornecedor
    faturado: Faturado
    numero_nota: str | None = Field(
        default=None, description="Número da nota fiscal, como impresso."
    )
    data_emissao: Data | None = None
    itens: list[Item]
    parcelas: list[ParcelaExtraida] = Field(
        description="Parcelas/duplicatas. Lista vazia se não houver."
    )
    valor_total: ValorMonetarioPositivo = Field(
        description="Valor total da nota fiscal."
    )

    # computed_field entra no model_dump, mas não no schema de validação
    # (model_json_schema), que é o enviado ao Gemini: ele não preenche isto.
    @computed_field
    @property
    def validacoes(self) -> Validacoes:
        return Validacoes(
            fornecedor_cnpj=_validar_documento(self.fornecedor.cnpj, cnpj_dv_valido),
            faturado_cpf=_validar_documento(self.faturado.cpf, cpf_dv_valido),
        )

    @model_validator(mode="after")
    def _validar_numeracao_das_parcelas(self):
        numeros = [parcela.numero for parcela in self.parcelas]

        if all(numero is None for numero in numeros):
            for posicao, parcela in enumerate(self.parcelas, start=1):
                parcela.numero = posicao
        elif None in numeros:
            raise ValueError("Numeração das parcelas incompleta.")
        elif len(set(numeros)) != len(numeros):
            raise ValueError("Números de parcela repetidos.")

        return self
