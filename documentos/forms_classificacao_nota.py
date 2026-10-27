"""FLU-07: reaproveita o cadastro administrativo, restrito a DESPESA."""
from django import forms

from cadastros.forms_classificacoes import NovaClassificacaoForm
from cadastros.models import TipoClassificacao


class ClassificacaoNaNotaForm(NovaClassificacaoForm):
    tipo = forms.ChoiceField(choices=[(TipoClassificacao.DESPESA, "Despesa")],
        initial=TipoClassificacao.DESPESA, widget=forms.HiddenInput)
    confirmar = forms.BooleanField(label="Confirmo o cadastro desta classificação de despesa")
