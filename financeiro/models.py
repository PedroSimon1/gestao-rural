"""Movimentos financeiros, classificações (ENT-03, GR-37) e parcelas (ENT-04, GR-38).

Um movimento só existe depois da confirmação do usuário (Q-02): nasce
CONFIRMADO e não há rascunho. Tipo, origem, status, pessoas, valor e
analise_origem_id não mudam depois de gravados; o cancelamento será uma
operação própria, ainda não implementada. Movimentos e vínculos nunca são
excluídos, e as FKs são PROTECT, o que preserva o histórico.

As regras entre entidades (papéis vigentes, pessoas completas e ativas,
classificação compatível e exatamente uma principal) ficam em
financeiro/servicos.py, que grava tudo em uma transação.

Parcelas: um movimento CONFIRMADO tem pelo menos uma parcela ATIVA, e a soma
das parcelas ATIVAS é igual ao valor_total. Uma parcela isolada não é um
lançamento completo, então a regra não cabe numa constraint por linha: o
serviço a valida antes de gravar, e um gatilho diferido do PostgreSQL
(migration 0002) a confere de novo no COMMIT, para qualquer caminho de escrita.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from cadastros.models import Classificacao, ExclusaoNaoPermitida, Pessoa

# Mesmo teto do Extrator (agents/extrator/schemas.py, LIMITE_VALOR_MONETARIO).
LIMITE_VALOR = 10_000_000_000


class TipoMovimento(models.TextChoices):
    APAGAR = "APAGAR", "A pagar"
    ARECEBER = "ARECEBER", "A receber"


class OrigemMovimento(models.TextChoices):
    NOTA_FISCAL = "NOTA_FISCAL", "Nota fiscal"
    MANUAL = "MANUAL", "Manual"


class StatusMovimento(models.TextChoices):
    CONFIRMADO = "CONFIRMADO", "Confirmado"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusParcela(models.TextChoices):
    ATIVA = "ATIVA", "Ativa"
    CANCELADA = "CANCELADA", "Cancelada"


class ExclusaoDeMovimentoNaoPermitida(ExclusaoNaoPermitida):
    """Movimentos e seus vínculos não são excluídos (RN-01)."""


class AlteracaoNaoPermitida(ValidationError):
    """Campo essencial de um registro financeiro já gravado."""


def _recusar_exclusao():
    raise ExclusaoDeMovimentoNaoPermitida(
        "Movimentos financeiros não podem ser excluídos."
    )


class SemExclusaoNemAlteracaoQuerySet(models.QuerySet):
    def delete(self):
        _recusar_exclusao()

    def _campos_imutaveis(self):
        # Fonte única: a lista do model, com o nome e a coluna de cada campo.
        campos = set()
        for nome in self.model.campos_imutaveis:
            field = self.model._meta.get_field(nome)
            campos.update({field.name, field.attname})
        return campos

    def _recusar_imutaveis(self, campos):
        proibidos = sorted(set(campos) & self._campos_imutaveis())
        if proibidos:
            raise AlteracaoNaoPermitida(
                "Campos que não podem ser alterados: " + ", ".join(proibidos) + ".",
                code="campo_imutavel",
            )

    def update(self, **campos):
        # O save() usa _update() e não passa por aqui.
        self._recusar_imutaveis(campos)
        return super().update(**campos)

    def bulk_update(self, objs, fields, batch_size=None):
        # Antes do atomic(savepoint=False) do Django: recusar lá dentro deixaria
        # a transação de quem chamou marcada para rollback. tuple(): um gerador
        # seria consumido aqui e chegaria vazio ao Django; sem campos, o
        # Django levanta o ValueError de sempre.
        fields = tuple(fields or ())
        self._recusar_imutaveis(fields)
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(
        self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
        update_fields=None, unique_fields=None,
    ):
        # Upsert (update_conflicts) alteraria registros gravados sem o save().
        # Assinatura explícita: argumentos posicionais também passam por aqui.
        if update_conflicts:
            update_fields = tuple(update_fields or ())
            self._recusar_imutaveis(update_fields)
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields,
            unique_fields=unique_fields,
        )


# Os gerenciadores reversos (pessoa.movimentos_como_faturado,
# movimento.classificacoes...) são subclasses criadas pelo Django a partir deste
# manager. Neles, add/remove/clear/set só trocam a FK, que é imutável; recusar
# antes do atomic(savepoint=False) do Django mantém usável a transação de quem
# chamou. As versões assíncronas (aadd...) chamam estas. Vale para qualquer
# subclasse: um futuro ManyToMany para estes models também seria recusado.
METODOS_QUE_TROCAM_A_FK = ("add", "remove", "clear", "set")


def _recusar_troca_de_vinculo(self, *args, **kwargs):
    raise AlteracaoNaoPermitida(
        "Os vínculos de um registro financeiro não podem ser trocados.",
        code="campo_imutavel",
    )


# Como nos métodos originais: templates não chamam métodos que alteram dados.
_recusar_troca_de_vinculo.alters_data = True


class SemExclusaoNemAlteracaoManager(models.Manager):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for nome in METODOS_QUE_TROCAM_A_FK:
            if nome in vars(cls):
                setattr(cls, nome, _recusar_troca_de_vinculo)


class RegistroFinanceiro(models.Model):
    """Base: sem exclusão e com campos essenciais imutáveis após a gravação."""

    campos_imutaveis = ()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        _recusar_exclusao()

    def _validar_imutaveis(self):
        # pk, e não _state.adding: um objeto novo com pk de um registro
        # existente faria UPDATE sem passar por esta verificação.
        if self.pk is None:
            return
        atual = type(self)._base_manager.filter(pk=self.pk).values(*self.campos_imutaveis).first()
        if atual is None:
            return
        if self._state.adding:
            # Objeto novo com a pk de um registro gravado: o save() faria UPDATE.
            raise AlteracaoNaoPermitida(
                "Já existe um registro com este identificador.", code="registro_existente"
            )
        alterados = [
            campo for campo in self.campos_imutaveis
            if atual[campo] != self._valor_normalizado(campo)
        ]
        if alterados:
            raise AlteracaoNaoPermitida(
                "Campos que não podem ser alterados: " + ", ".join(alterados) + ".",
                code="campo_imutavel",
            )

    def _valor_normalizado(self, campo):
        # "150.00" e Decimal("150.00"), ou um UUID em texto, não são alteração.
        field = self._meta.get_field(campo)
        valor = getattr(self, field.attname)
        try:
            return field.target_field.to_python(valor) if field.is_relation else field.to_python(valor)
        except ValidationError:
            return valor

    def save(self, *args, **kwargs):
        self._validar_imutaveis()
        super().save(*args, **kwargs)


class MovimentoQuerySet(SemExclusaoNemAlteracaoQuerySet):
    def confirmados(self):
        return self.filter(status=StatusMovimento.CONFIRMADO)


class MovimentoConta(RegistroFinanceiro):
    # Status entra na lista até existir a operação de cancelamento.
    campos_imutaveis = (
        "tipo", "origem", "status", "contraparte", "faturado", "valor_total",
        "analise_origem_id", "criado_em",
    )

    tipo = models.CharField(max_length=8, choices=TipoMovimento)
    origem = models.CharField(max_length=11, choices=OrigemMovimento)
    status = models.CharField(
        max_length=10, choices=StatusMovimento, default=StatusMovimento.CONFIRMADO
    )
    # Fornecedor (APAGAR) ou cliente (ARECEBER); o papel é conferido no serviço.
    contraparte = models.ForeignKey(
        Pessoa, on_delete=models.PROTECT, related_name="movimentos_como_contraparte"
    )
    # Obrigatório no APAGAR (FLU-08).
    faturado = models.ForeignKey(
        Pessoa, on_delete=models.PROTECT, null=True, blank=True,
        related_name="movimentos_como_faturado",
    )
    valor_total = models.DecimalField(max_digits=12, decimal_places=2)
    # Análise que originou o lançamento; também impede lançá-la duas vezes.
    analise_origem_id = models.UUIDField(null=True, blank=True, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = SemExclusaoNemAlteracaoManager.from_queryset(MovimentoQuerySet)()

    class Meta:
        db_table = "movimentos_contas"
        # _base_manager também recusa exclusão e alteração dos campos essenciais.
        base_manager_name = "objects"
        ordering = ["-criado_em", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tipo__in=TipoMovimento.values),
                name="movimento_tipo_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(origem__in=OrigemMovimento.values),
                name="movimento_origem_valida",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=StatusMovimento.values),
                name="movimento_status_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_total__gt=0, valor_total__lt=LIMITE_VALOR),
                name="movimento_valor_total_positivo",
                violation_error_message=(
                    "O valor total deve ser maior que zero e menor que R$ 10 bilhões."
                ),
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(tipo=TipoMovimento.APAGAR) | models.Q(faturado__isnull=False)
                ),
                name="movimento_apagar_com_faturado",
                violation_error_message="Conta a pagar exige o faturado.",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} #{self.pk} — R$ {self.valor_total}"


class MovimentoClassificacaoQuerySet(SemExclusaoNemAlteracaoQuerySet):
    pass


class MovimentoClassificacao(RegistroFinanceiro):
    """Uma das classificações do movimento (RN-04); exatamente uma é a principal."""

    campos_imutaveis = ("movimento", "classificacao", "principal")

    movimento = models.ForeignKey(
        MovimentoConta, on_delete=models.PROTECT, related_name="classificacoes"
    )
    classificacao = models.ForeignKey(
        Classificacao, on_delete=models.PROTECT, related_name="movimentos"
    )
    principal = models.BooleanField(default=False)

    objects = SemExclusaoNemAlteracaoManager.from_queryset(MovimentoClassificacaoQuerySet)()

    class Meta:
        db_table = "movimentos_classificacoes"
        base_manager_name = "objects"
        ordering = ["movimento_id", "-principal", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["movimento", "classificacao"],
                name="movimento_classificacao_unica",
                violation_error_message="Esta classificação já está no movimento.",
            ),
            # No máximo uma principal no banco; "exatamente uma" fica no serviço.
            models.UniqueConstraint(
                fields=["movimento"],
                condition=models.Q(principal=True),
                name="movimento_uma_classificacao_principal",
                violation_error_message="O movimento já tem uma classificação principal.",
            ),
        ]

    def __str__(self):
        marca = " (principal)" if self.principal else ""
        return f"Movimento #{self.movimento_id}: {self.classificacao}{marca}"


class ParcelaContaQuerySet(SemExclusaoNemAlteracaoQuerySet):
    def ativas(self):
        return self.filter(status=StatusParcela.ATIVA)


class ParcelaConta(RegistroFinanceiro):
    """Parcela de um movimento (ENT-04, RN-06), com vencimento e valor próprios.

    A "Identificacao" do professor ("ÚNICA" quando há uma só) é apresentação;
    o registro guarda o número. A situação de pagamento e o cancelamento
    ainda não têm contrato aprovado: o status nasce ATIVA e não muda.
    """

    # Status entra na lista até existir a operação de cancelamento.
    campos_imutaveis = (
        "identificador", "movimento", "numero", "data_vencimento", "valor", "status",
        "criado_em",
    )

    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    movimento = models.ForeignKey(
        MovimentoConta, on_delete=models.PROTECT, related_name="parcelas"
    )
    numero = models.PositiveSmallIntegerField()
    data_vencimento = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=9, choices=StatusParcela, default=StatusParcela.ATIVA
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = SemExclusaoNemAlteracaoManager.from_queryset(ParcelaContaQuerySet)()

    class Meta:
        db_table = "parcelas_contas"
        base_manager_name = "objects"
        ordering = ["movimento_id", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["movimento", "numero"],
                name="parcela_numero_unico_no_movimento",
                violation_error_message="Este número de parcela já existe no movimento.",
            ),
            models.CheckConstraint(
                condition=models.Q(numero__gte=1),
                name="parcela_numero_positivo",
                violation_error_message="O número da parcela deve ser maior que zero.",
            ),
            models.CheckConstraint(
                condition=models.Q(valor__gt=0, valor__lt=LIMITE_VALOR),
                name="parcela_valor_positivo",
                violation_error_message=(
                    "O valor da parcela deve ser maior que zero e menor que R$ 10 bilhões."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=StatusParcela.values),
                name="parcela_status_valido",
            ),
        ]

    def __str__(self):
        return f"Parcela {self.numero} do movimento #{self.movimento_id} — R$ {self.valor}"
