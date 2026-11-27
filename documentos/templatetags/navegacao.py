"""Indica em qual seção do menu a página atual está (para `aria-current="page"`)."""
from django import template

register = template.Library()

SECOES = {
    "contas": {"contas", "conta_detalhe", "conta_manual_nova", "parcela_pagamento"},
    "nota": {
        "documento_inicio", "analise_criar", "analise_conferencia", "analise_conferencia_salva",
        "analise_cancelar", "analise_confirmar",
    },
    "pessoas": {
        "pessoas", "pessoa_nova", "pessoa_detalhe", "pessoa_editar", "pessoa_atribuir_papel",
        "pessoa_regularizar", "pessoa_status", "papel_status",
    },
    "classificacoes": {"classificacoes", "classificacao_nova", "classificacao_editar", "classificacao_status"},
    "consulta": {"consulta", "consulta_indice"},
}


@register.simple_tag(takes_context=True)
def secao_atual(context):
    """Nome da seção da rota atual; vazio em páginas fora do menu (404, login, sair)."""
    request = context.get("request")
    nome = getattr(getattr(request, "resolver_match", None), "url_name", None)
    return next((secao for secao, nomes in SECOES.items() if nome in nomes), "")
