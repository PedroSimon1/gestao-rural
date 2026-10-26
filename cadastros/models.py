"""Pessoas (ENT-01) e os papéis de cada pessoa (GR-35).

Uma pessoa é identificada pelo CPF ou CNPJ normalizado, único no banco. A
mesma pessoa pode ser FORNECEDOR, CLIENTE e FATURADO sem ser duplicada: cada
papel é um PapelPessoa próprio (Q-11). Pessoa e papéis são inativados e
reativados de forma independente, sempre de modo explícito (T-05), e nunca
excluídos (RN-01 a RN-03), o que preserva os vínculos históricos.

Cadastro incompleto (C-02): sem CPF/CNPJ válido, a pessoa pode ser gravada com
situacao_documental INCOMPLETO e documento NULL, e depois regularizada no
mesmo registro. Nenhum documento fictício ou inválido é guardado.

O banco garante a estrutura do documento e a coerência com a situação. Os
dígitos verificadores são conferidos no save() e no full_clean(). Fixtures
controladas de QA e testes (loaddata) não passam pelo save() e podem conter
documentos com DV inválido; esses registros só podem ser inativados e
reativados, porque qualquer outro save() revalida o documento. bulk_create() e
QuerySet.update() também não passam pelo save(): a aplicação não os usa para
gravar documentos.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from .validators import (
    FORMATO_CNPJ, FORMATO_CPF, TIPO_CNPJ, TIPO_CPF, normalizar_documento,
    tipo_do_documento, validar_documento,
)


class Status(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    INATIVO = "INATIVO", "Inativo"


class TipoDocumento(models.TextChoices):
    CPF = TIPO_CPF, "CPF"
    CNPJ = TIPO_CNPJ, "CNPJ"


class Papel(models.TextChoices):
    FORNECEDOR = "FORNECEDOR", "Fornecedor"
    CLIENTE = "CLIENTE", "Cliente"
    FATURADO = "FATURADO", "Faturado"


class ExclusaoNaoPermitida(Exception):
    """Cadastros não são excluídos: são inativados (RN-01, RN-02)."""


class SemExclusaoQuerySet(models.QuerySet):
    def delete(self):
        raise ExclusaoNaoPermitida("Cadastros não podem ser excluídos; inative o registro.")

    def ativos(self):
        return self.filter(status=Status.ATIVO)


class ComStatus(models.Model):
    status = models.CharField(max_length=7, choices=Status, default=Status.ATIVO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def ativo(self):
        return self.status == Status.ATIVO

    def inativar(self):
        self._mudar_status(Status.INATIVO)

    def reativar(self):
        self._mudar_status(Status.ATIVO)

    def _mudar_status(self, status):
        if self.status != status:
            self.status = status
            self.save(update_fields=["status", "atualizado_em"])

    def delete(self, *args, **kwargs):
        raise ExclusaoNaoPermitida("Cadastros não podem ser excluídos; inative o registro.")


class SituacaoDocumental(models.TextChoices):
    COMPLETO = "COMPLETO", "Completo"
    # Sem CPF/CNPJ válido; aguarda correção (C-02). Não tem relação com o status.
    INCOMPLETO = "INCOMPLETO", "Pendente de correção"


class PessoaQuerySet(SemExclusaoQuerySet):
    def por_documento(self, documento):
        documento = normalizar_documento(documento)
        return self.filter(documento=documento) if documento else self.none()

    def incompletas(self):
        return self.filter(situacao_documental=SituacaoDocumental.INCOMPLETO)


class Pessoa(ComStatus):
    # Derivado do documento; a constraint do banco garante a coerência.
    tipo_documento = models.CharField(
        max_length=4, choices=TipoDocumento, editable=False, null=True, blank=True
    )
    # CPF: 11 dígitos. CNPJ: 14 caracteres, numérico ou alfanumérico. NULL só no
    # cadastro incompleto; o índice único do PostgreSQL ignora NULLs.
    documento = models.CharField(max_length=14, unique=True, null=True, blank=True)
    # Padrão COMPLETO: o cadastro só fica incompleto quando isso é pedido de forma
    # explícita (a confirmação do usuário pertence ao fluxo de conferência).
    situacao_documental = models.CharField(
        max_length=10, choices=SituacaoDocumental, default=SituacaoDocumental.COMPLETO
    )
    razao_social = models.CharField(max_length=255)

    objects = PessoaQuerySet.as_manager()

    class Meta:
        db_table = "pessoas"
        ordering = ["razao_social", "id"]
        constraints = [
            # IS NOT NULL explícito: no PostgreSQL, CHECK com resultado NULL passa.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        situacao_documental=SituacaoDocumental.COMPLETO,
                        documento__isnull=False, tipo_documento__isnull=False,
                        tipo_documento=TIPO_CPF, documento__regex=FORMATO_CPF,
                    )
                    | models.Q(
                        situacao_documental=SituacaoDocumental.COMPLETO,
                        documento__isnull=False, tipo_documento__isnull=False,
                        tipo_documento=TIPO_CNPJ, documento__regex=FORMATO_CNPJ,
                    )
                    | models.Q(
                        situacao_documental=SituacaoDocumental.INCOMPLETO,
                        documento__isnull=True, tipo_documento__isnull=True,
                    )
                ),
                name="pessoa_documento_coerente_com_situacao",
                violation_error_message=(
                    "Cadastro completo exige CPF ou CNPJ normalizado; "
                    "cadastro incompleto não tem documento."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(razao_social__regex=r"\S"),
                name="pessoa_razao_social_preenchida",
                violation_error_message="Informe a razão social ou o nome.",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values),
                name="pessoa_status_valido",
            ),
        ]

    def __str__(self):
        if not self.documento:
            return f"{self.razao_social} (documento pendente)"
        # CPF é dado pessoal: só os 4 últimos dígitos aparecem em logs e erros.
        documento = self.documento
        if self.tipo_documento == TIPO_CPF:
            documento = "*******" + documento[-4:]
        return f"{self.razao_social} ({self.tipo_documento} {documento})"

    @property
    def documentacao_completa(self):
        return self.situacao_documental == SituacaoDocumental.COMPLETO

    def _normalizar(self):
        self.documento = normalizar_documento(self.documento) or None
        self.razao_social = " ".join((self.razao_social or "").split())
        self.tipo_documento = tipo_do_documento(self.documento) if self.documento else None

    def _validar_documento(self):
        if self.situacao_documental == SituacaoDocumental.INCOMPLETO:
            # Documento inválido não é guardado: o incompleto fica sem documento.
            if self.documento:
                raise ValidationError({"documento": ValidationError(
                    "Cadastro incompleto não guarda documento; use regularizar().",
                    code="incompleto_com_documento",
                )})
            return
        try:
            validar_documento(self.documento or "")
        except ValidationError as erro:
            raise ValidationError({"documento": erro})

    def clean_fields(self, exclude=None):
        # Normaliza antes do max_length: "12.345.678/0001-95" tem 18 caracteres.
        self._normalizar()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        self._validar_documento()

    def save(self, *args, **kwargs):
        # Caminho normal da aplicação: documento com DV inválido é recusado.
        # Inativar e reativar (update_fields só com status) não revalidam.
        update_fields = kwargs.get("update_fields")
        campos_validados = {"documento", "razao_social", "situacao_documental"}
        if update_fields is None or campos_validados & set(update_fields):
            self._normalizar()
            self._validar_documento()
            if update_fields is not None and {"documento", "situacao_documental"} & set(update_fields):
                # Documento, tipo e situação são gravados juntos: o que foi
                # validado em memória é o que vai para o banco.
                kwargs["update_fields"] = {
                    *update_fields, "documento", "tipo_documento", "situacao_documental",
                }
        super().save(*args, **kwargs)

    def regularizar(self, documento):
        """Completa o cadastro incompleto no mesmo registro, preservando os
        vínculos (C-02). O documento é validado e não pode pertencer a outra
        pessoa; em caso de erro, nada muda."""
        if self.pk is None:
            raise ValueError("Salve a pessoa antes de regularizar o cadastro.")
        if self.documentacao_completa:
            raise ValidationError("O cadastro já está completo.", code="ja_completo")
        normalizado = normalizar_documento(documento)
        try:
            validar_documento(normalizado)
        except ValidationError as erro:
            raise ValidationError({"documento": erro})
        if Pessoa.objects.filter(documento=normalizado).exclude(pk=self.pk).exists():
            raise ValidationError({"documento": ValidationError(
                "Já existe uma pessoa com este documento.", code="unique"
            )})

        campos = ("documento", "tipo_documento", "situacao_documental", "atualizado_em")
        anterior = {campo: getattr(self, campo) for campo in campos}
        self.documento = normalizado
        self.situacao_documental = SituacaoDocumental.COMPLETO
        try:
            # O índice único ainda decide em caso de cadastro concorrente.
            with transaction.atomic():
                self.save(update_fields=["documento", "situacao_documental", "atualizado_em"])
        except Exception as erro:
            for campo, valor in anterior.items():
                setattr(self, campo, valor)
            if isinstance(erro, IntegrityError):
                raise ValidationError({"documento": ValidationError(
                    "Já existe uma pessoa com este documento.", code="unique"
                )}) from erro
            raise

    def atribuir_papel(self, papel):
        """(PapelPessoa, criado) do get_or_create. Não muda o status de um papel
        existente: a reativação é sempre explícita (T-05)."""
        return PapelPessoa.objects.get_or_create(pessoa=self, papel=papel)


class PapelPessoaQuerySet(SemExclusaoQuerySet):
    def vigentes(self):
        """Papéis ativos de pessoas ativas."""
        return self.filter(status=Status.ATIVO, pessoa__status=Status.ATIVO)


class PapelPessoa(ComStatus):
    # PROTECT: a pessoa com papéis nunca some do banco.
    pessoa = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="papeis")
    papel = models.CharField(max_length=10, choices=Papel)

    objects = PapelPessoaQuerySet.as_manager()

    class Meta:
        db_table = "papeis_pessoa"
        ordering = ["pessoa_id", "papel"]
        constraints = [
            # Um registro por papel: inativar e reativar mudam o status dele.
            models.UniqueConstraint(
                fields=["pessoa", "papel"],
                name="papel_pessoa_unico",
                violation_error_message="Esta pessoa já possui este papel.",
            ),
            models.CheckConstraint(
                condition=models.Q(papel__in=Papel.values),
                name="papel_pessoa_papel_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values),
                name="papel_pessoa_status_valido",
            ),
        ]

    def __str__(self):
        return f"{self.pessoa.razao_social}: {self.papel}"


class TipoClassificacao(models.TextChoices):
    DESPESA = "DESPESA", "Despesa"
    RECEITA = "RECEITA", "Receita"


# Código estável em maiúsculas, como os valores do Enum do Classificador
# (ex.: MANUTENCAO_E_OPERACAO).
FORMATO_CODIGO = r"^[A-Z0-9]+(_[A-Z0-9]+)*$"


class ClassificacaoQuerySet(SemExclusaoQuerySet):
    def por_codigo(self, tipo, codigo):
        """Busca em qualquer status: um registro INATIVO é identificado, não recriado."""
        return self.filter(tipo=tipo, codigo=(codigo or "").strip().upper())


class Classificacao(ComStatus):
    """Tipos de despesa e de receita (ENT-02, GR-36).

    tipo e codigo identificam a classificação e não mudam depois de criados,
    para não alterar o significado de registros que já a usam; a descrição é o
    texto legível e pode ser corrigida. Inativação e reativação são explícitas
    e não há exclusão (RN-01 a RN-03). QuerySet.update() e fixtures (loaddata,
    que não chamam o save()) não passam por essa proteção: a aplicação não os
    usa para mudar tipo ou código.
    """

    tipo = models.CharField(max_length=7, choices=TipoClassificacao)
    codigo = models.CharField(max_length=60)
    descricao = models.CharField(max_length=255)

    objects = ClassificacaoQuerySet.as_manager()

    class Meta:
        db_table = "classificacoes"
        ordering = ["tipo", "descricao", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "codigo"],
                name="classificacao_tipo_codigo_unico",
                violation_error_message="Já existe uma classificação com este tipo e código.",
            ),
            models.CheckConstraint(
                condition=models.Q(tipo__in=TipoClassificacao.values),
                name="classificacao_tipo_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(codigo__regex=FORMATO_CODIGO),
                name="classificacao_codigo_valido",
                violation_error_message=(
                    "Use letras maiúsculas sem acento, números e sublinhado no "
                    "código (ex.: MANUTENCAO_E_OPERACAO)."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(descricao__regex=r"\S"),
                name="classificacao_descricao_preenchida",
                violation_error_message="Informe a descrição.",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values),
                name="classificacao_status_valido",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.descricao}"

    def _normalizar(self):
        self.codigo = (self.codigo or "").strip().upper()
        self.descricao = " ".join((self.descricao or "").split())

    def _validar_identidade(self):
        """tipo e codigo de uma classificação gravada não mudam."""
        # pk, e não _state.adding: um objeto novo com pk explícita de um
        # registro existente faria UPDATE sem passar por esta verificação.
        if self.pk is None:
            return
        original = (
            Classificacao.objects.filter(pk=self.pk).values_list("tipo", "codigo").first()
        )
        if original and original != (self.tipo, self.codigo):
            raise ValidationError(
                "O tipo e o código de uma classificação não podem ser alterados; "
                "crie outra classificação e inative esta.",
                code="identidade_imutavel",
            )

    def clean_fields(self, exclude=None):
        self._normalizar()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        self._validar_identidade()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None or {"tipo", "codigo", "descricao"} & set(update_fields):
            self._normalizar()
            self._validar_identidade()
        super().save(*args, **kwargs)
