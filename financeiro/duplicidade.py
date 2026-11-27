"""Aviso de possível duplicidade (2C): contas já registradas que parecem ser a que está sendo lançada.

Só leitura e só aviso: nada aqui bloqueia o lançamento. Uma conta "parece" a mesma quando tem a
mesma contraparte, o mesmo valor total e o mesmo primeiro vencimento e está CONFIRMADA, qualquer
que seja a origem (nota fiscal ou manual). Isso cobre o caso que a identidade fiscal não vê: a
mesma compra lançada à mão e por nota, ou duas vezes à mão com chaves diferentes.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Min, Q

from .models import MovimentoConta, StatusMovimento, StatusParcela

LIMITE = 5


@dataclass(frozen=True)
class MovimentoParecido:
    id: int
    tipo: str
    origem: str
    valor_total: Decimal
    primeiro_vencimento: date | None
    criado_em: datetime


def movimentos_parecidos(contraparte_id, valor_total, primeiro_vencimento=None, limite=LIMITE, excluir_chave=None):
    """Até `limite` movimentos CONFIRMADOS com a mesma contraparte, valor e primeiro vencimento.

    `primeiro_vencimento` None: só contraparte e valor. `excluir_chave`: chave de idempotência
    da solicitação em andamento (a conta manual que ela já registrou não é "outra"). Mais recentes primeiro.
    """
    if isinstance(contraparte_id, bool) or not isinstance(contraparte_id, int):
        raise TypeError("contraparte_id deve ser um inteiro.")
    if not isinstance(valor_total, Decimal):
        raise TypeError("valor_total deve ser um Decimal.")
    movimentos = (
        MovimentoConta.objects
        .filter(contraparte_id=contraparte_id, valor_total=valor_total, status=StatusMovimento.CONFIRMADO)
        .annotate(
            primeiro_vencimento=Min("parcelas__data_vencimento", filter=Q(parcelas__status=StatusParcela.ATIVA))
        )
    )
    if excluir_chave is not None:
        movimentos = movimentos.exclude(chave_idempotencia=excluir_chave)
    if primeiro_vencimento is not None:
        movimentos = movimentos.filter(primeiro_vencimento=primeiro_vencimento)
    return tuple(
        MovimentoParecido(m.pk, m.tipo, m.origem, m.valor_total, m.primeiro_vencimento, m.criado_em)
        for m in movimentos.order_by("-criado_em", "-id")[:limite]
    )
