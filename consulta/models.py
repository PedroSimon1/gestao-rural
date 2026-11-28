"""Índice derivado e regravável; nunca modifica os movimentos financeiros."""

import math

from django.core.exceptions import ValidationError
from django.db import models

from financeiro.models import MovimentoConta


class EmbeddingMovimento(models.Model):
    movimento = models.ForeignKey(
        MovimentoConta, on_delete=models.PROTECT, related_name="embeddings",
    )
    modelo = models.CharField(max_length=100)
    dimensao = models.PositiveIntegerField()
    vetor = models.JSONField()
    hash_texto = models.CharField(max_length=64)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "embeddings_movimentos"
        constraints = [
            models.UniqueConstraint(
                fields=["movimento", "modelo"], name="embedding_movimento_modelo_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(modelo__regex=r"\S"), name="embedding_modelo_obrigatorio",
            ),
            models.CheckConstraint(
                condition=models.Q(dimensao__gte=1), name="embedding_dimensao_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(hash_texto__regex=r"^[0-9a-f]{64}$"),
                name="embedding_hash_sha256_valido",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            not isinstance(self.vetor, list)
            or len(self.vetor) != self.dimensao
            or any(
                isinstance(valor, bool) or not isinstance(valor, (int, float))
                or not math.isfinite(valor)
                for valor in self.vetor
            )
        ):
            raise ValidationError({
                "vetor": "Informe uma lista de números finitos com a dimensão indicada.",
            })
