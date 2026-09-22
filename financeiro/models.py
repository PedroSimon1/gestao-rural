from decimal import Decimal

from django.db import models
from django.db.models import Sum

from usuarios.models import Titular


class LancamentoFinanceiro(models.Model):
    class Categoria(models.TextChoices):
        DESPESA = "DESPESA", "Despesa"
        RECEITA = "RECEITA", "Receita"

    titular = models.ForeignKey(
        Titular,
        on_delete=models.CASCADE,
        related_name="lancamentos",
    )

    categoria = models.CharField(
        max_length=10,
        choices=Categoria.choices,
    )

    subcategoria = models.CharField(
        max_length=100,
        blank=True,
    )

    descricao = models.CharField(
        max_length=255,
    )

    valor_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    data_lancamento = models.DateField()

    criado_em = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.get_categoria_display()} - {self.descricao} - R$ {self.valor_total}"


class Parcela(models.Model):
    lancamento = models.ForeignKey(
        LancamentoFinanceiro,
        on_delete=models.CASCADE,
        related_name="parcelas",
    )

    numero = models.PositiveIntegerField()

    valor_nominal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    data_vencimento = models.DateField()

    class Meta:
        ordering = ["numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["lancamento", "numero"],
                name="unique_numero_parcela_por_lancamento",
            )
        ]

    def __str__(self):
        return (
            f"Parcela {self.numero} - "
            f"{self.lancamento.descricao} - "
            f"R$ {self.valor_nominal}"
        )

    @property
    def total_pago(self):
        total = self.amortizacoes.aggregate(total=Sum("valor_pago"))["total"]
        return total if total is not None else Decimal("0.00")

    @property
    def saldo_restante(self):
        saldo = self.valor_nominal - self.total_pago
        return max(saldo, Decimal("0.00"))

    @property
    def quitada(self):
        return self.saldo_restante == Decimal("0.00")


class Amortizacao(models.Model):
    parcela = models.ForeignKey(
        Parcela,
        on_delete=models.CASCADE,
        related_name="amortizacoes",
    )

    valor_pago = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    data_pagamento = models.DateField()

    criado_em = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return (
            f"Amortização da parcela {self.parcela.numero} - "
            f"R$ {self.valor_pago}"
        )
