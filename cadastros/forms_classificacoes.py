"""Formulários da GR-47; identidade e restrições pertencem a Classificacao."""
import unicodedata

from django import forms

from .models import Classificacao, Status, TipoClassificacao


class DescricaoClassificacaoForm(forms.ModelForm):
    class Meta:
        model = Classificacao
        fields = ("descricao",)
        labels = {"descricao": "Descrição"}

    def clean_descricao(self):
        texto = " ".join(self.cleaned_data["descricao"].split())
        if any(unicodedata.category(c) in {"Cc", "Cs"} for c in texto):
            raise forms.ValidationError("Informe uma descrição sem caracteres de controle.")
        return texto

    def save(self, commit=True):
        classificacao = super().save(commit=False)
        if commit:
            # Não restaura status antigo nem regrava a identidade ao editar.
            classificacao.save(update_fields=["descricao", "atualizado_em"])
        return classificacao


class NovaClassificacaoForm(DescricaoClassificacaoForm):
    class Meta(DescricaoClassificacaoForm.Meta):
        fields = ("tipo", "codigo", "descricao")
        labels = {"tipo": "Tipo", "codigo": "Código", "descricao": "Descrição"}
        help_texts = {"codigo": "Código estável: letras sem acento, números e sublinhado. Tipo e código não poderão ser alterados. A combinação é única, inclusive entre inativos."}

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()

    def save(self, commit=True):
        # Criação normal pelo ModelForm/model, sem serviço paralelo de domínio.
        return forms.ModelForm.save(self, commit=commit)


class PesquisaClassificacaoForm(forms.Form):
    busca = forms.CharField(label="Código ou descrição", required=False, max_length=255)
    tipo = forms.ChoiceField(label="Tipo", required=False, choices=[("", "Receitas e despesas"), *TipoClassificacao.choices])
    status = forms.ChoiceField(
        label="Situação", required=False, initial=Status.ATIVO,
        choices=[*Status.choices, ("TODOS", "Ativos e inativos")],
    )
