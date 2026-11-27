"""Baixa de parcela: marcar como paga (a pagar) ou recebida (a receber), e desfazer (D1).

A parcela guarda só a data (`pago_em`); valor, vencimento e número continuam imutáveis, e o
status segue ATIVA, então o gatilho da soma das parcelas (migration 0002) não muda. Cada
operação relê a parcela com bloqueio: duas baixas simultâneas da mesma parcela não passam.

Erros (ValidationError, code): parcela_inexistente, parcela_cancelada, movimento_cancelado,
pagamento_ja_registrado, pagamento_nao_registrado, data_invalida, data_futura.
"""

from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ParcelaConta, StatusMovimento, StatusParcela

MENSAGENS = {
    "parcela_inexistente": "Parcela não encontrada.",
    "parcela_cancelada": "Parcela cancelada não recebe baixa.",
    "movimento_cancelado": "Lançamento cancelado não recebe baixa.",
    "pagamento_ja_registrado": "Esta parcela já tem baixa registrada. Desfaça a baixa antes de registrar outra.",
    "pagamento_nao_registrado": "Esta parcela não tem baixa para desfazer.",
    "data_invalida": "Informe a data do pagamento.",
    "data_futura": "A data do pagamento não pode ser futura.",
}


def _erro(codigo):
    return ValidationError(MENSAGENS[codigo], code=codigo)


def _parcela_bloqueada(parcela_id):
    """Parcela ATIVA de movimento CONFIRMADO, bloqueada até o fim da transação."""
    if isinstance(parcela_id, bool) or not isinstance(parcela_id, int):
        raise TypeError("parcela_id deve ser um inteiro.")
    parcela = (
        ParcelaConta.objects.select_for_update(of=("self",)).select_related("movimento")
        .filter(pk=parcela_id).first()
    )
    if parcela is None:
        raise _erro("parcela_inexistente")
    if parcela.status != StatusParcela.ATIVA:
        raise _erro("parcela_cancelada")
    if parcela.movimento.status != StatusMovimento.CONFIRMADO:
        raise _erro("movimento_cancelado")
    return parcela


def registrar_pagamento(parcela_id, data_pagamento):
    """Marca a parcela como paga/recebida em `data_pagamento`; devolve a ParcelaConta."""
    if isinstance(data_pagamento, datetime) or not isinstance(data_pagamento, date):
        raise _erro("data_invalida")
    if data_pagamento > timezone.localdate():
        raise _erro("data_futura")
    with transaction.atomic():
        parcela = _parcela_bloqueada(parcela_id)
        if parcela.pago_em is not None:
            raise _erro("pagamento_ja_registrado")
        parcela.pago_em = data_pagamento
        parcela.save(update_fields=["pago_em", "atualizado_em"])
    return parcela


def desfazer_pagamento(parcela_id):
    """Volta a parcela para em aberto; devolve a ParcelaConta."""
    with transaction.atomic():
        parcela = _parcela_bloqueada(parcela_id)
        if parcela.pago_em is None:
            raise _erro("pagamento_nao_registrado")
        parcela.pago_em = None
        parcela.save(update_fields=["pago_em", "atualizado_em"])
    return parcela
