"""CPF e CNPJ: limpeza e dígitos verificadores.

Usado pelos Agents (validação da extração), pelos cadastros e pela identidade
fiscal. Fica fora dos apps para que nenhum deles dependa de outro só por esta regra.

O CNPJ é numérico ou alfanumérico (IN RFB 2.229/2024): 12 posições [0-9A-Z]
seguidas de 2 dígitos verificadores numéricos. DV válido significa apenas que o
número é bem formado, não que o documento existe.
"""

import re

SEPARADORES_DOCUMENTO = re.compile(r"[.\-/\s]")
FORMATO_CPF = re.compile(r"\d{11}")
FORMATO_CNPJ = re.compile(r"[0-9A-Z]{12}\d{2}")

_PESOS_CNPJ_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_DV2 = (6, *_PESOS_CNPJ_DV1)


def digito_verificador(base, pesos):
    # ord(c) - 48 vale para dígitos (0-9) e letras (A=17 ... Z=42),
    # como define a regra do CNPJ alfanumérico; para CPF e CNPJ numérico
    # é o próprio valor do dígito. Também serve à chave de acesso (44 posições).
    soma = sum((ord(caractere) - 48) * peso for caractere, peso in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def limpar_cpf(valor):
    return SEPARADORES_DOCUMENTO.sub("", valor)


def limpar_cnpj(valor):
    return SEPARADORES_DOCUMENTO.sub("", valor).upper()


def cpf_dv_valido(cpf):
    """Indica se o CPF tem estrutura e dígitos verificadores válidos.

    Sequências repetidas (ex.: 999.999.999-99) fecham a conta do DV, mas
    são tratadas como inválidas, como faz a Receita Federal.
    """
    cpf = limpar_cpf(cpf)
    if not FORMATO_CPF.fullmatch(cpf) or len(set(cpf)) == 1:
        return False
    dv1 = digito_verificador(cpf[:9], range(10, 1, -1))
    dv2 = digito_verificador(cpf[:9] + dv1, range(11, 1, -1))
    return cpf[9:] == dv1 + dv2


def cnpj_dv_valido(cnpj):
    """Indica se o CNPJ (numérico ou alfanumérico) tem DV válido."""
    cnpj = limpar_cnpj(cnpj)
    if not FORMATO_CNPJ.fullmatch(cnpj) or len(set(cnpj)) == 1:
        return False
    dv1 = digito_verificador(cnpj[:12], _PESOS_CNPJ_DV1)
    dv2 = digito_verificador(cnpj[:12] + dv1, _PESOS_CNPJ_DV2)
    return cnpj[12:] == dv1 + dv2
