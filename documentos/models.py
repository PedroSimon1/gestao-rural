from django.db import models

from usuarios.models import Titular


class Documento(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PROCESSANDO = "PROCESSANDO", "Processando"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        ERRO = "ERRO", "Erro"

    arquivo = models.FileField(upload_to="documentos/")
    nome_original = models.CharField(max_length=255)
    enviado_em = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDENTE,
    )
    titular = models.ForeignKey(
        Titular,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos",
    )
    resultado_estruturado = models.JSONField(default=dict, blank=True)
    metadados = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.nome_original