"""Entrada da baixa de parcela (D1); as regras estão em financeiro/pagamentos.py."""
from django import forms

REGISTRAR = "registrar"
DESFAZER = "desfazer"


class PagamentoParcelaForm(forms.Form):
    acao = forms.ChoiceField(choices=[(REGISTRAR, "Registrar"), (DESFAZER, "Desfazer")])
    data_pagamento = forms.DateField(
        required=False, input_formats=["%Y-%m-%d"],
        error_messages={"invalid": "Informe a data no formato dia/mês/ano."},
    )

    def clean(self):
        dados = super().clean()
        if dados.get("acao") == REGISTRAR and not dados.get("data_pagamento") and "data_pagamento" not in self.errors:
            self.add_error("data_pagamento", "Informe a data do pagamento.")
        return dados
