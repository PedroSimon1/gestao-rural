"""Análise de nota fiscal aguardando a conferência do usuário (GR-43, T-04).

Entre o processamento e a confirmação, o resultado da análise fica no
servidor, e não no cookie da sessão. Cada análise pertence a uma sessão: o
cookie assinado guarda só um código aleatório, e aqui fica só o hash SHA-256
desse código (dono_hash).

O PDF e a Gemini API Key nunca são guardados. Os dados da nota só existem
enquanto a análise está PENDENTE: ao confirmar, cancelar ou expirar, `dados`
é apagado e ficam só o estado e as datas, para rastreabilidade.

Correções da conferência (GR-22, F-2): ficam em `correcoes`, separadas de
`dados`, que nunca muda. São apagadas junto com `dados`; depois da finalização
fica só `campos_corrigidos`, com os nomes dos campos corrigidos e sem valores
(T-03). `versao_correcoes` conta as gravações (controle otimista, T-02).
"""

import uuid

from django.db import models
from django.utils import timezone


class StatusAnalise(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    CONFIRMADA = "CONFIRMADA", "Confirmada"
    CANCELADA = "CANCELADA", "Cancelada"
    EXPIRADA = "EXPIRADA", "Expirada"


ESTADOS_FINAIS = (StatusAnalise.CONFIRMADA, StatusAnalise.CANCELADA, StatusAnalise.EXPIRADA)


class AnalisePendente(models.Model):
    # O mesmo UUID vira o analise_origem_id do movimento (idempotência da GR-37).
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dono_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=10, choices=StatusAnalise, default=StatusAnalise.PENDENTE
    )
    # Versão do formato de `dados` (documentos/analises.py, VERSAO_DADOS).
    versao_dados = models.PositiveSmallIntegerField()
    # JSON final do processamento (ContextoProjeto 17.3); NULL fora de PENDENTE.
    dados = models.JSONField(null=True, blank=True)
    # Correções da conferência (documentos/correcoes.py); NULL sem correção e
    # sempre NULL fora de PENDENTE.
    correcoes = models.JSONField(null=True, blank=True)
    versao_correcoes = models.PositiveIntegerField(default=0)
    # Só os nomes dos campos corrigidos; fica depois da finalização (T-03).
    campos_corrigidos = models.JSONField(default=list, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)
    expira_em = models.DateTimeField()
    finalizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "analises_pendentes"
        ordering = ["criado_em"]
        indexes = [
            # Limpeza das vencidas (expirar_analises).
            models.Index(fields=["status", "expira_em"], name="analise_status_expira_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=StatusAnalise.values),
                name="analise_status_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(dono_hash__regex=r"^[0-9a-f]{64}$"),
                name="analise_dono_hash_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(expira_em__gt=models.F("criado_em")),
                name="analise_expira_depois_de_criada",
            ),
            # Dados só enquanto pendente; estado final sempre com a data.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=StatusAnalise.PENDENTE,
                        dados__isnull=False, finalizado_em__isnull=True,
                    )
                    | models.Q(
                        status__in=ESTADOS_FINAIS,
                        dados__isnull=True, finalizado_em__isnull=False,
                    )
                ),
                name="analise_dados_coerentes_com_status",
            ),
            # Correções só enquanto pendente, como os dados.
            models.CheckConstraint(
                condition=(
                    models.Q(status=StatusAnalise.PENDENTE)
                    | models.Q(status__in=ESTADOS_FINAIS, correcoes__isnull=True)
                ),
                name="analise_correcoes_so_pendente",
            ),
        ]

    def __str__(self):
        return f"Análise {self.id} ({self.status})"

    def vencida(self, agora=None):
        return self.expira_em <= (agora or timezone.now())
