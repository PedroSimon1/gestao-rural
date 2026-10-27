"""Correções da conferência: lista fechada de campos e validação de cada um (GR-22, F-2).

Campos autorizados pela D-02 (documentos, nomes, classificação, número,
série, data, valor total e parcelas) e pela D-03 (o documento de cada parte é
o escolhido pelo usuário, CPF ou CNPJ, sem tipo deduzido pelo papel). Chave de
acesso e modelo ficam fora (G-01, não aprovada).

Aqui cada campo é validado e normalizado sozinho. A combinação com os dados
extraídos e as regras entre campos (soma das parcelas, numeração, identidade
fiscal, papéis) são da F-3 e dos serviços financeiros, que revalidam tudo na
confirmação. Os erros citam só o nome do campo, nunca o valor recebido.
"""

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from cadastros.models import FORMATO_CODIGO
from cadastros.validators import normalizar_documento, validar_documento
from financeiro.models import LIMITE_VALOR, NUMERO_MAXIMO, SERIE_MAXIMA
from financeiro.servicos import MAXIMO_DE_PARCELAS

CENTAVO = Decimal("0.01")
# Limite antes do int(): o Python recusa textos de mais de 4300 dígitos com
# ValueError; 10 dígitos bastam para o maior campo (número da nota).
_DIGITOS = re.compile(r"[0-9]{1,10}")
_DATA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Valor com ponto decimal e sem separador de milhar: "1.250" seria R$ 1,25.
_VALOR = re.compile(r"[0-9]{1,10}(\.[0-9]{1,2})?")
# NUL e outros caracteres de controle (o PostgreSQL recusa NUL em jsonb) e
# surrogates isolados (não codificáveis em UTF-8).
_CATEGORIAS_PROIBIDAS = {"Cc", "Cs"}


class CampoInvalido(Exception):
    """Valor de correção inválido; a mensagem nunca traz o valor."""


def _documento(valor):
    if not isinstance(valor, str):
        raise CampoInvalido
    documento = normalizar_documento(valor)
    try:
        validar_documento(documento)
    except ValidationError:
        raise CampoInvalido from None
    return documento


def _nome(valor):
    if not isinstance(valor, str):
        raise CampoInvalido
    nome = " ".join(valor.split())
    if not nome or len(nome) > 255:
        raise CampoInvalido
    if any(unicodedata.category(caractere) in _CATEGORIAS_PROIBIDAS for caractere in nome):
        raise CampoInvalido
    return nome


def _codigo(valor):
    if not isinstance(valor, str):
        raise CampoInvalido
    codigo = valor.strip().upper()
    if len(codigo) > 60 or not re.fullmatch(FORMATO_CODIGO, codigo):
        raise CampoInvalido
    return codigo


def _inteiro(minimo, maximo):
    def validar(valor):
        # Texto com zeros à esquerda é aceito; bool não conta como número.
        if isinstance(valor, str) and _DIGITOS.fullmatch(valor.strip()):
            valor = int(valor.strip())
        if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
            raise CampoInvalido
        return valor
    return validar


def _data(valor):
    if not isinstance(valor, str) or not _DATA.fullmatch(valor):
        raise CampoInvalido
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        raise CampoInvalido from None


def _valor(valor):
    # Texto no formato _VALOR ou Decimal; float é recusado (arredondamento binário).
    if isinstance(valor, str):
        if not _VALOR.fullmatch(valor.strip()):
            raise CampoInvalido
        valor = valor.strip()
    elif not isinstance(valor, Decimal):
        raise CampoInvalido
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        raise CampoInvalido from None
    if not numero.is_finite() or not 0 < numero < LIMITE_VALOR:
        raise CampoInvalido
    if numero != numero.quantize(CENTAVO):
        raise CampoInvalido
    return str(numero.quantize(CENTAVO))


_numero_parcela = _inteiro(1, MAXIMO_DE_PARCELAS)


def _parcelas(valor):
    if not isinstance(valor, list) or not 1 <= len(valor) <= MAXIMO_DE_PARCELAS:
        raise CampoInvalido
    parcelas = []
    for item in valor:
        if not isinstance(item, dict) or set(item) != {"numero", "data_vencimento", "valor"}:
            raise CampoInvalido
        parcelas.append({
            "numero": _numero_parcela(item["numero"]),
            "data_vencimento": _data(item["data_vencimento"]),
            "valor": _valor(item["valor"]),
        })
    return parcelas


# Nome do campo (como fica em campos_corrigidos) → validador.
CAMPOS_CORRIGIVEIS = {
    "fornecedor.documento": _documento,
    "fornecedor.razao_social": _nome,
    "faturado.documento": _documento,
    "faturado.nome": _nome,
    "tipo_despesa": _codigo,
    "numero_nota": _inteiro(1, NUMERO_MAXIMO),
    "serie": _inteiro(0, SERIE_MAXIMA),
    "data_emissao": _data,
    "valor_total": _valor,
    "parcelas": _parcelas,
}


def validar_correcoes(correcoes):
    """(correções normalizadas, campos inválidos). Campo fora da lista conta
    como inválido, com o nome genérico "campo_nao_autorizado"."""
    normalizadas, invalidos = {}, []
    for campo, valor in correcoes.items():
        validar = CAMPOS_CORRIGIVEIS.get(campo)
        if validar is None:
            invalidos.append("campo_nao_autorizado")
            continue
        try:
            normalizadas[campo] = validar(valor)
        except CampoInvalido:
            invalidos.append(campo)
    return normalizadas, sorted(set(invalidos))
