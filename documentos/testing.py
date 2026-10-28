"""Apoio aos testes que precisam de uma análise de nota (GR-43).

Documentos fictícios, com DV calculado; nenhum dado real.
"""

import secrets

from .analises import CHAVE_DA_SESSAO

CNPJ = "11222333000181"
CPF = "12345678909"


def nova_sessao():
    """Sessão como a do login: já com o código das análises."""
    return {CHAVE_DA_SESSAO: secrets.token_urlsafe(32)}


def resultado_da_nota(valor="150.00"):
    """JSON final no formato de montar_resultado (ContextoProjeto 17.3)."""
    return {
        "fornecedor": {"razao_social": "Fornecedor Teste Ltda", "nome_fantasia": None, "cnpj": CNPJ},
        "faturado": {"nome": "Produtor Teste", "cpf": CPF},
        "numero_nota": "123",
        "data_emissao": "2026-10-01",
        "itens": [{"descricao": "Óleo", "quantidade": "1", "valor_unitario": valor, "valor_total": valor}],
        "quantidade_parcelas": 1,
        "parcelas": [{"numero": 1, "data_vencimento": "2026-11-01", "valor": valor}],
        "valor_total": valor,
        "tipo_despesa": "MANUTENCAO_E_OPERACAO",
        "validacoes": {
            "fornecedor_cnpj": {"status": "valido", "motivo": None},
            "faturado_cpf": {"status": "valido", "motivo": None},
        },
    }
