"""Valores em reais para exibição: `R$ 1.234,56`."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()

SEM_VALOR = "—"


@register.filter
def moeda(valor):
    """Formata em reais, com milhar e vírgula, sempre com centavos. Sem valor, devolve um travessão."""
    if valor is None or valor == "":
        return SEM_VALOR
    try:
        numero = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return SEM_VALOR
    if not numero.is_finite():
        return SEM_VALOR
    texto = f"{abs(numero):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if numero < 0 else ''}R$ {texto}"
