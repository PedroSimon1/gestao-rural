"""Formulários administrativos; regras de documento permanecem no domínio."""
import unicodedata

from django import forms

from .models import Papel, Pessoa, Status
from .validators import normalizar_documento, validar_documento


class PessoaForm(forms.ModelForm):
    documento = forms.CharField(label="CPF ou CNPJ", max_length=30)

    class Meta:
        model = Pessoa
        fields = ("razao_social", "documento")
        labels = {"razao_social": "Nome / razão social"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.incompleta = bool(self.instance.pk and not self.instance.documentacao_completa)
        if self.incompleta:
            self.fields["documento"].disabled = True
            self.fields["documento"].required = False
            self.fields["documento"].help_text = "Use Regularizar documento para completar este cadastro."

    def clean_razao_social(self):
        nome = " ".join(self.cleaned_data["razao_social"].split())
        if any(unicodedata.category(c) in {"Cc", "Cs"} for c in nome):
            raise forms.ValidationError("Informe um nome sem caracteres de controle.")
        return nome

    def clean_documento(self):
        if self.incompleta:
            return None
        documento = normalizar_documento(self.cleaned_data["documento"])
        validar_documento(documento)
        return documento

    def save(self, commit=True):
        pessoa = super().save(commit=False)
        if commit:
            # Editar nome/documento não pode restaurar um status lido antes de
            # uma inativação concorrente, nem sobrescrever uma regularização.
            campos = ["razao_social", "atualizado_em"]
            if not self.incompleta:
                campos.append("documento")
            pessoa.save(update_fields=campos)
        return pessoa


class NovaPessoaForm(PessoaForm):
    papeis = forms.MultipleChoiceField(
        label="Papéis a atribuir", choices=Papel.choices,
        widget=forms.CheckboxSelectMultiple,
    )


class PapelForm(forms.Form):
    papel = forms.ChoiceField(label="Papel a atribuir", choices=Papel.choices)


class ConfirmacaoForm(forms.Form):
    confirmar = forms.BooleanField(label="Confirmo esta alteração")


class RegularizacaoForm(ConfirmacaoForm):
    documento = forms.CharField(label="CPF ou CNPJ", max_length=30)

    def clean_documento(self):
        documento = normalizar_documento(self.cleaned_data["documento"])
        validar_documento(documento)
        return documento


class PesquisaPessoaForm(forms.Form):
    busca = forms.CharField(label="Nome ou documento", required=False, max_length=255)
    papel = forms.ChoiceField(label="Papel", required=False, choices=[("", "Qualquer papel"), *Papel.choices])
    status = forms.ChoiceField(
        label="Situação da pessoa", required=False, initial=Status.ATIVO,
        choices=[*Status.choices, ("TODOS", "Ativos e inativos")],
    )
