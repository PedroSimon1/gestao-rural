"""GR-45: validação da conferência, sem gravação ou autorização de lançamento."""

from decimal import Decimal
from copy import deepcopy

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from cadastros.models import Classificacao, Status, TipoClassificacao
from cadastros.validators import normalizar_documento, tipo_do_documento, validar_documento
from financeiro.servicos import MAXIMO_DE_PARCELAS
from .forms_fiscais import CamposFiscaisForm


def documento_corrigido(valor):
    documento = normalizar_documento(valor)
    validar_documento(documento)
    return documento


class ConferenciaForm(forms.Form):
    fornecedor_nome = forms.CharField(label="Nome ou razão social do fornecedor", max_length=255)
    fornecedor_documento = forms.CharField(label="CPF/CNPJ do fornecedor", max_length=30)
    faturado_nome = forms.CharField(label="Nome ou razão social do faturado", max_length=255)
    faturado_cpf = forms.CharField(label="CPF do faturado", max_length=25, required=False)
    faturado_cnpj = forms.CharField(label="CNPJ do faturado", max_length=30, required=False)
    documento_faturado = forms.ChoiceField(
        label="Documento do faturado a utilizar", required=False,
        choices=(("CPF", "CPF"), ("CNPJ", "CNPJ")), widget=forms.RadioSelect,
        help_text="Se ambos estiverem preenchidos, escolha explicitamente o documento correto.",
    )
    classificacao = forms.ModelChoiceField(
        label="Classificação da despesa", queryset=Classificacao.objects.none(),
        empty_label="Selecione uma classificação ativa",
    )
    numero_nota = forms.CharField(label="Número da nota", max_length=60, required=False)
    serie_nota = forms.CharField(label="Série da nota", max_length=20, required=False)
    chave_acesso = deepcopy(CamposFiscaisForm.base_fields['chave_acesso'])
    modelo = deepcopy(CamposFiscaisForm.base_fields['modelo'])
    data_emissao = forms.DateField(label="Data de emissão", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    valor_total = forms.DecimalField(label="Valor total", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["classificacao"].queryset = Classificacao.objects.filter(
            tipo=TipoClassificacao.DESPESA, status=Status.ATIVO
        ).order_by("descricao", "pk")
        for campo in self.fields.values():
            if not isinstance(campo.widget, forms.RadioSelect):
                campo.widget.attrs["class"] = "formulario__campo"

    def clean_fornecedor_documento(self):
        return documento_corrigido(self.cleaned_data["fornecedor_documento"])

    def clean(self):
        dados = super().clean()
        cpf = dados.get("faturado_cpf", "")
        cnpj = dados.get("faturado_cnpj", "")
        escolha = dados.get("documento_faturado")
        if cpf and cnpj and not escolha:
            self.add_error("documento_faturado", "Escolha CPF ou CNPJ; a seleção não é automática.")
            return dados
        if not escolha:
            escolha = "CPF" if cpf else "CNPJ" if cnpj else None
        selecionado = cpf if escolha == "CPF" else cnpj if escolha == "CNPJ" else ""
        if not selecionado:
            self.add_error("documento_faturado", "Informe e selecione o documento do faturado.")
            return dados
        try:
            documento = documento_corrigido(selecionado)
            if tipo_do_documento(documento) != escolha:
                raise ValidationError("O documento não corresponde ao tipo selecionado.")
        except ValidationError as erro:
            self.add_error("faturado_cpf" if escolha == "CPF" else "faturado_cnpj", erro)
        else:
            dados["faturado_documento_escolhido"] = documento
            dados["documento_faturado"] = escolha
        return dados


class ParcelaConferenciaForm(forms.Form):
    data_vencimento = forms.DateField(label="Vencimento", widget=forms.DateInput(attrs={"type": "date", "class": "formulario__campo"}, format="%Y-%m-%d"))
    valor = forms.DecimalField(label="Valor", max_digits=12, decimal_places=2, min_value=Decimal("0.01"), widget=forms.NumberInput(attrs={"class": "formulario__campo", "step": "0.01"}))


class BaseParcelasConferencia(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if any(not form.cleaned_data for form in self.forms):
            raise ValidationError("Preencha vencimento e valor de todas as parcelas.")


ParcelasConferenciaFormSet = formset_factory(
    ParcelaConferenciaForm, formset=BaseParcelasConferencia,
    extra=0, min_num=1, validate_min=True, max_num=MAXIMO_DE_PARCELAS,
    validate_max=True, absolute_max=MAXIMO_DE_PARCELAS,
)
