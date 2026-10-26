"""Normalização e validação de CPF e CNPJ dos cadastros.

A regra do dígito verificador é a mesma do Agent Extrator, incluindo o CNPJ
alfanumérico (IN RFB 2.229/2024). DV válido significa apenas que o número é
bem formado, não que o documento existe.
"""

import re

from django.core.exceptions import ValidationError

from agents.extrator.schemas import cnpj_dv_valido, cpf_dv_valido

TIPO_CPF = "CPF"
TIPO_CNPJ = "CNPJ"

_SEPARADORES = re.compile(r"[.\-/\s]")
# Formatos normalizados; também usados nas constraints do banco.
FORMATO_CPF = r"^[0-9]{11}$"
# 12 posições [0-9A-Z] seguidas de 2 dígitos verificadores numéricos.
FORMATO_CNPJ = r"^[0-9A-Z]{12}[0-9]{2}$"


def normalizar_documento(valor):
    """Remove pontos, traços, barras e espaços e põe as letras em maiúsculas."""
    return _SEPARADORES.sub("", valor or "").upper()


def tipo_do_documento(documento):
    """CPF ou CNPJ conforme a estrutura do documento normalizado; None se nenhum."""
    if re.fullmatch(FORMATO_CPF, documento):
        return TIPO_CPF
    if re.fullmatch(FORMATO_CNPJ, documento):
        return TIPO_CNPJ
    return None


def validar_documento(documento):
    """Exige CPF ou CNPJ normalizado com dígitos verificadores válidos."""
    tipo = tipo_do_documento(documento)
    if tipo is None:
        raise ValidationError(
            "Informe um CPF (11 dígitos) ou um CNPJ (14 caracteres).", code="formato"
        )
    valido = cpf_dv_valido(documento) if tipo == TIPO_CPF else cnpj_dv_valido(documento)
    if not valido:
        raise ValidationError(f"{tipo} inválido.", code="dv")
