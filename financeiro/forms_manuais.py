"""Entrada da interface P08; persistência e regras financeiras são do serviço."""
from decimal import Decimal
import re

from django import forms
from django.forms import BaseFormSet, formset_factory

from cadastros.models import Classificacao, Papel, Pessoa, SituacaoDocumental, Status, TipoClassificacao
from .models import LIMITE_VALOR, TipoMovimento
from .servicos import MAXIMO_DE_PARCELAS


class ValorManualField(forms.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(min_value=Decimal("0.01"), max_value=Decimal(LIMITE_VALOR) - Decimal("0.01"),
            max_digits=12, decimal_places=2,
            widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "150,00"}), **kwargs)

    def to_python(self, value):
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if not re.fullmatch(r"[0-9]+(?:[.,][0-9]{1,2})?", value):
                raise forms.ValidationError("Use até duas casas decimais, sem separador de milhar.")
            value = value.replace(",", ".")
        return super().to_python(value)


class ContaManualForm(forms.Form):
    tipo = forms.ChoiceField(choices=TipoMovimento.choices, widget=forms.HiddenInput)
    chave_idempotencia = forms.UUIDField(widget=forms.HiddenInput)
    solicitacao = forms.CharField(max_length=512, widget=forms.HiddenInput)
    contraparte = forms.ModelChoiceField(label="Fornecedor / cliente", queryset=Pessoa.objects.none())
    faturado = forms.ModelChoiceField(label="Faturado", required=False, queryset=Pessoa.objects.none())
    valor_total = ValorManualField(label="Valor total", help_text="Use vírgula ou ponto para centavos, sem separador de milhar.")
    classificacoes = forms.ModelMultipleChoiceField(label="Classificações", queryset=Classificacao.objects.none(), widget=forms.CheckboxSelectMultiple)
    principal = forms.ModelChoiceField(label="Classificação principal", queryset=Classificacao.objects.none())
    confirmar = forms.BooleanField(label="Conferi os dados e confirmo o registro desta conta")

    def __init__(self, *args, tipo, **kwargs):
        super().__init__(*args, **kwargs)
        if tipo not in TipoMovimento.values:
            return
        pagar = tipo == TipoMovimento.APAGAR
        pessoas = Pessoa.objects.filter(status=Status.ATIVO, situacao_documental=SituacaoDocumental.COMPLETO)
        self.fields["contraparte"].queryset = pessoas.filter(papeis__papel=Papel.FORNECEDOR if pagar else Papel.CLIENTE, papeis__status=Status.ATIVO).distinct()
        self.fields["contraparte"].label = "Fornecedor" if pagar else "Cliente"
        self.fields["faturado"].queryset = pessoas.filter(papeis__papel=Papel.FATURADO, papeis__status=Status.ATIVO).distinct()
        self.fields["faturado"].required = pagar
        self.fields["faturado"].help_text = "Obrigatório para contas a pagar." if pagar else "Opcional; se informado, deve ter o papel Faturado ativo."
        classificacoes = Classificacao.objects.filter(status=Status.ATIVO, tipo=TipoClassificacao.DESPESA if pagar else TipoClassificacao.RECEITA)
        self.fields["classificacoes"].queryset = classificacoes
        self.fields["principal"].queryset = classificacoes

    def clean(self):
        dados = super().clean()
        principal, escolhidas = dados.get("principal"), dados.get("classificacoes")
        if principal is not None and escolhidas is not None and principal not in escolhidas:
            self.add_error("principal", "A principal deve estar entre as classificações selecionadas.")
        return dados


class ParcelaManualForm(forms.Form):
    data_vencimento = forms.DateField(label="Vencimento", input_formats=["%Y-%m-%d"], widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    valor = ValorManualField(label="Valor da parcela")


class BaseParcelasManuais(BaseFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields["DELETE"].label = "Remover esta parcela antes de registrar"


ParcelasManuaisFormSet = formset_factory(ParcelaManualForm, formset=BaseParcelasManuais,
    extra=0, min_num=1, validate_min=True, max_num=MAXIMO_DE_PARCELAS,
    validate_max=True, absolute_max=MAXIMO_DE_PARCELAS, can_delete=True)
