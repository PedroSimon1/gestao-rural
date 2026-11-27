"""Persistência tolerante dos itens extraídos, independente da análise por IA."""

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext

from django.db import transaction

from .models import ItemNotaFiscal, NotaFiscalLancada


def _numero(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)):
        return None
    try:
        numero = Decimal(str(valor))
        limite = Decimal(10) ** (campo.max_digits - campo.decimal_places)
        if not numero.is_finite() or numero < 0 or numero >= limite:
            return None
        with localcontext() as contexto:
            contexto.prec = campo.max_digits + 2
            numero = numero.quantize(Decimal(1).scaleb(-campo.decimal_places), rounding=ROUND_HALF_UP)
        return numero if numero < limite else None
    except (DecimalException, ValueError):
        return None


@transaction.atomic
def registrar_itens_nota(nota_fiscal, itens):
    """Grava uma vez, na ordem recebida; dados ilegíveis tornam-se ausentes.

    O bloqueio da nota serializa chamadas simultâneas, inclusive quando ainda
    não existe item para bloquear. Falhas de banco não são erros de extração.
    """
    nota = NotaFiscalLancada.objects.select_for_update().get(pk=nota_fiscal.pk)
    existentes = list(nota.itens.all())
    if existentes:
        return existentes
    if not isinstance(itens, (list, tuple)):
        return []
    limite_descricao = ItemNotaFiscal._meta.get_field("descricao").max_length
    campos = {nome: ItemNotaFiscal._meta.get_field(nome) for nome in (
        "quantidade", "valor_unitario", "valor_total",
    )}
    registros = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        descricao = item.get("descricao")
        if not isinstance(descricao, str) or not descricao.strip():
            continue
        registros.append(ItemNotaFiscal(
            nota_fiscal=nota,
            ordem=len(registros) + 1,
            descricao=descricao.strip()[:limite_descricao],
            **{nome: _numero(item.get(nome), campo) for nome, campo in campos.items()},
        ))
    return ItemNotaFiscal.objects.bulk_create(registros)
