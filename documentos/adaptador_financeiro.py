"""Dados tipados para conferência (GR-51), sem banco ou persistência.

Consome o JSON de montar_resultado; preserva os Agents e não decide como
guardar a análise, editar a nota ou confirmar o lançamento.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from agents.classificador.schemas import TipoDespesa
from cadastros.validators import normalizar_documento, validar_documento


@dataclass(frozen=True)
class PessoaExtraida:
    nome: str | None
    documento: str | None
    situacao_documento: str


@dataclass(frozen=True)
class ParcelaParaConferencia:
    numero: int | None
    data_vencimento: date | None
    valor: Decimal | None


@dataclass(frozen=True)
class NotaParaConferencia:
    fornecedor: PessoaExtraida
    faturado: PessoaExtraida
    numero_nota: str | None
    data_emissao: date | None
    valor_total: Decimal | None
    codigo_despesa: str | None
    parcelas: tuple[ParcelaParaConferencia, ...]
    pendencias: tuple[str, ...]


def _erro():
    return ValidationError("Resultado do processamento inválido.", code="resultado_invalido")


def _texto(valor):
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise _erro()
    return " ".join(valor.split()) or None


def _dinheiro(valor, permitir_ausente=False):
    # O JSON final usa strings; não arredondar nem aceitar float/bool.
    if valor is None and permitir_ausente:
        return None
    if not isinstance(valor, (str, Decimal)):
        raise _erro()
    try:
        numero = Decimal(valor)
        if not numero.is_finite() or not 0 < numero < Decimal("10000000000"):
            raise _erro()
        if numero != numero.quantize(Decimal("0.01")):
            raise _erro()
    except (InvalidOperation, ValueError):
        raise _erro() from None
    return numero


def _data(valor):
    if valor is None or type(valor) is date:
        return valor
    if not isinstance(valor, str):
        raise _erro()
    try:
        resultado = date.fromisoformat(valor)
    except ValueError:
        raise _erro() from None
    if resultado.isoformat() != valor:
        raise _erro()
    return resultado


def _pessoa(nome, documento):
    nome = _texto(nome)
    if documento is not None and not isinstance(documento, str):
        raise _erro()
    documento = normalizar_documento(documento)
    if not documento:
        return PessoaExtraida(nome, None, "ausente")
    try:
        validar_documento(documento)
    except ValidationError:
        # Não transportar documento inválido como identificador de busca.
        return PessoaExtraida(nome, None, "invalido")
    return PessoaExtraida(nome, documento, "valido")


def documento_faturado(faturado):
    """Seleciona o único documento informado, sem priorizar CPF ou CNPJ.

    Dois documentos exigem seleção explícita na conferência (D-03 aprovada). Não descartar silenciosamente nem recorrer ao outro em caso de DV inválido.
    """
    return documento_da_parte(faturado, 'faturado')


def documento_da_parte(parte, rotulo):
    if not isinstance(parte, dict):
        raise _erro()
    cpf = _texto(parte.get("cpf"))
    cnpj = _texto(parte.get("cnpj"))
    if cpf and cnpj:
        raise ValidationError(
            "Há CPF e CNPJ informados para a mesma parte; escolha o documento na conferência.",
            code=f"{rotulo}_documento_ambiguo",
        )
    return cpf or cnpj


def adaptar_resultado(resultado):
    """Converte o dict final, sem alterá-lo ou inventar dados ausentes.

Pendências descrevem incompatibilidades com o serviço atual de movimentos;
não autorizam gravação nem substituem sua validação na confirmação.
"""
    if not isinstance(resultado, dict):
        raise _erro()
    try:
        fornecedor = resultado["fornecedor"]
        faturado = resultado["faturado"]
        fornecedor = _pessoa(
            fornecedor["razao_social"] or fornecedor["nome_fantasia"], documento_da_parte(fornecedor, 'fornecedor')
        )
        faturado = _pessoa(faturado["nome"], documento_faturado(faturado))
        v2 = 'documento_fiscal' in resultado
        total = _dinheiro(resultado["valor_total"], permitir_ausente=v2)
        codigo = resultado["tipo_despesa"]
        if codigo is not None:
            codigo = TipoDespesa(codigo).value
        origem = resultado["parcelas"]
        if not isinstance(origem, list):
            raise _erro()
        quantidade = resultado["quantidade_parcelas"]
        if type(quantidade) is not int or quantidade != len(origem):
            raise _erro()
        parcelas = []
        for item in origem:
            numero = item["numero"]
            if numero is not None and (type(numero) is not int or numero < 1):
                raise _erro()
            parcelas.append(ParcelaParaConferencia(
                numero, _data(item["data_vencimento"]), _dinheiro(item["valor"], permitir_ausente=v2)
            ))
        numero_nota = _texto(resultado["numero_nota"])
        emissao = _data(resultado["data_emissao"])
    except (KeyError, TypeError, ValueError):
        raise _erro() from None

    pendencias = []
    if total is None:
        pendencias.append('valor_total_ausente')
    for rotulo, pessoa in (("fornecedor", fornecedor), ("faturado", faturado)):
        if pessoa.situacao_documento != "valido":
            pendencias.append(f"{rotulo}_documento_{pessoa.situacao_documento}")
        if pessoa.nome is None:
            pendencias.append(f"{rotulo}_nome_ausente")
    if codigo is None:
        pendencias.append("classificacao_ausente")
    if not parcelas:
        pendencias.append("sem_parcela")
    else:
        if len(parcelas) > 120:
            pendencias.append("parcela_quantidade")
        numeros = [p.numero for p in parcelas]
        if any(n is None for n in numeros) or sorted(numeros) != list(range(1, len(parcelas) + 1)):
            pendencias.append("parcela_numeracao")
        if any(p.data_vencimento is None for p in parcelas):
            pendencias.append("parcela_vencimento")
        if any(p.valor is None for p in parcelas):
            pendencias.append('parcela_valor_ausente')
        elif total is not None and sum(p.valor for p in parcelas) != total:
            pendencias.append("parcela_soma")
    return NotaParaConferencia(
        fornecedor, faturado, numero_nota, emissao, total, codigo, tuple(parcelas), tuple(pendencias)
    )
