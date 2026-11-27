"""Resumos da nota para a tela: ficha (etapas 2 a 4) e resumo do lançamento concluído.

Só apresentação: lê a nota já conferida e não consulta nem grava nada.
"""
from types import SimpleNamespace

from financeiro.templatetags.moeda import SEM_VALOR, moeda


def ficha_da_nota(nota):
    """Nota, fornecedor, faturado, total e parcelas ("2 × R$ 920,00" ou "3 parcelas") em uma linha."""
    parcelas = nota.parcelas
    valores = {parcela.valor for parcela in parcelas}
    if not parcelas:
        texto = SEM_VALOR
    elif len(valores) == 1:
        texto = f"{len(parcelas)} × {moeda(next(iter(valores)))}"
    else:
        texto = f"{len(parcelas)} parcela{'s' if len(parcelas) != 1 else ''}"
    return SimpleNamespace(
        numero=nota.numero_nota, fornecedor=nota.fornecedor.nome, faturado=nota.faturado.nome,
        valor_total=nota.valor_total, parcelas=texto, quantidade_parcelas=len(parcelas),
    )


def resumo_do_lancamento(nota):
    """Dados mostrados na tela de concluído: valor, número de parcelas e o primeiro vencimento."""
    return SimpleNamespace(
        valor_total=nota.valor_total, quantidade_parcelas=len(nota.parcelas),
        primeiro_vencimento=min((parcela.data_vencimento for parcela in nota.parcelas), default=None),
    )
