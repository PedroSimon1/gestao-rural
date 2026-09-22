from django.db import models

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