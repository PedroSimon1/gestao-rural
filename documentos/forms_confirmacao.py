"""Decisões explícitas da tela; persistência é exclusivamente a F-5 oficial."""
from django import forms

from cadastros.resolucao import Decisao
from cadastros.pendentes import listar_incompletos
from financeiro.lancamento_nota import DecisoesDaParte, SolicitacaoLancamento

ROTULOS_DECISAO = {
    Decisao.REGULARIZAR: 'Regularizar o cadastro incompleto selecionado com o documento conferido',
    Decisao.CRIAR_PESSOA: 'Criar o cadastro se ainda não existir',
    Decisao.REATIVAR_PESSOA: 'Reativar o cadastro se estiver inativo',
    Decisao.ATRIBUIR_PAPEL: 'Atribuir o papel desta parte se estiver ausente',
    Decisao.REATIVAR_PAPEL: 'Reativar o papel desta parte se estiver inativo',
}
ESCOLHAS = [(d.value, ROTULOS_DECISAO[d]) for d in Decisao]


class ConfirmacaoLancamentoForm(forms.Form):
    versao_correcoes = forms.IntegerField(min_value=0, max_value=2147483647, widget=forms.HiddenInput)
    fornecedor_decisoes = forms.MultipleChoiceField(label='Autorizações para o fornecedor',
        choices=ESCOLHAS, required=False, widget=forms.CheckboxSelectMultiple)
    fornecedor_pessoa_incompleta_id = forms.TypedChoiceField(label='Cadastro incompleto do fornecedor (opcional)',
        coerce=int, empty_value=None, required=False, choices=())
    faturado_decisoes = forms.MultipleChoiceField(label='Autorizações para o faturado',
        choices=ESCOLHAS, required=False, widget=forms.CheckboxSelectMultiple)
    faturado_pessoa_incompleta_id = forms.TypedChoiceField(label='Cadastro incompleto do faturado (opcional)',
        coerce=int, empty_value=None, required=False, choices=())
    confirmar = forms.BooleanField(label='Conferi os dados salvos e confirmo este lançamento financeiro.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sem busca/associação por nome: a escolha envia o ID do registro.
        pendentes = listar_incompletos()
        for parte in ('fornecedor', 'faturado'):
            self.fields[f'{parte}_pessoa_incompleta_id'].choices = [('', 'Nenhum selecionado')] + [
                (p.id, f'ID {p.id} — {p.razao_social} — {p.status}') for p in pendentes]

    def solicitacao(self):
        if not self.is_valid():
            raise ValueError('A confirmação precisa ser validada.')
        def parte(nome):
            return DecisoesDaParte(
                decisoes=frozenset(Decisao(d) for d in self.cleaned_data[f'{nome}_decisoes']),
                pessoa_incompleta_id=self.cleaned_data[f'{nome}_pessoa_incompleta_id'])
        return SolicitacaoLancamento(versao_correcoes=self.cleaned_data['versao_correcoes'],
            fornecedor=parte('fornecedor'), faturado=parte('faturado'))
