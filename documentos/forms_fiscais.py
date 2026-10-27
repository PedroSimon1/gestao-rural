"""GR-45/G-01: componente fiscal preparado, ainda não conectado às rotas.

Validação delegada à identidade oficial da GR-22. Não guarda correções nem
substitui revalidação, autorização ou transação da confirmação.
"""
from django import forms
from django.core.exceptions import ValidationError

from financeiro.identidade_fiscal import identificar_nota


MENSAGENS_FISCAIS = {
    'chave_acesso_invalida': 'A chave de acesso tem formato ou dígito verificador inválido. Confira o documento.',
    'identidade_fiscal_divergente': 'A chave de acesso diverge dos dados informados. Confira emitente, modelo, série e número.',
    'identidade_fiscal_insuficiente': 'Informe a chave de acesso ou complete CNPJ do emitente, modelo, série e número.',
    'identidade_fiscal_nao_suportada': 'São aceitas NF-e (55) e NFC-e (65), de emitente com CNPJ.',
    'emitente_invalido': 'Confira o CNPJ do emitente selecionado na conferência.',
    'serie_invalida': 'Confira a série da nota.',
    'numero_invalido': 'Confira o número da nota.',
    'nota_ja_lancada': 'Esta nota fiscal já foi lançada. Confira o registro existente.',
}


def mensagem_fiscal(codigo):
    """Mensagem fixa: não refletir exceções, documentos ou valores recebidos."""
    return MENSAGENS_FISCAIS.get(codigo, 'Não foi possível validar a identificação fiscal. Revise os dados.')


class CamposFiscaisForm(forms.Form):
    chave_acesso = forms.CharField(label='Chave de acesso', required=False, max_length=200,
        help_text='Copie a chave impressa. Ela será validada novamente pelo servidor.')
    modelo = forms.CharField(label='Modelo da nota', required=False, max_length=20,
        help_text='55 para NF-e; 65 para NFC-e. Informe apenas o que consta no documento.')
    serie = forms.CharField(label='Série da nota', required=False, max_length=20)
    numero_nota = forms.CharField(label='Número da nota', required=False, max_length=60)

    def __init__(self, *args, emitente_cnpj=None, **kwargs):
        super().__init__(*args, **kwargs)
        # O chamador passa o documento escolhido; este componente não escolhe CPF/CNPJ.
        self.emitente_cnpj = emitente_cnpj
        self.identidade = None
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'formulario__campo'

    def clean(self):
        dados = super().clean()
        if self.errors:
            return dados
        try:
            self.identidade = identificar_nota(
                chave_acesso=dados.get('chave_acesso'), emitente_cnpj=self.emitente_cnpj,
                modelo=dados.get('modelo'), serie=dados.get('serie'), numero=dados.get('numero_nota'),
            )
        except ValidationError as erro:
            campo = {'chave_acesso_invalida': 'chave_acesso', 'serie_invalida': 'serie',
                     'numero_invalido': 'numero_nota'}.get(erro.code)
            self.add_error(campo, mensagem_fiscal(erro.code))
        return dados

    def proposta_correcoes(self):
        """Somente valores preenchidos; não transportar derivados da chave como extraídos.

        Nomes planos são proposta G-01: validar com o contrato final de Simon
        antes de registrar. Ausência não decide apagar correção existente.
        """
        if not self.is_valid():
            raise ValueError('Valide os campos fiscais antes de preparar correções.')
        return {campo: valor for campo, valor in self.cleaned_data.items() if valor not in ('', None)}


def preparar_campos_fiscais(original, correcoes=None):
    """Leitura de v1 e da v2 proposta, sem converter/mutar o JSON original.

    Sem inferir modelo/série da chave, sem escolher o documento do emitente.
    correcoes devem vir da análise autorizada no servidor.
    """
    fiscal = original.get('documento_fiscal') or {}
    initial = {campo: fiscal.get(campo) for campo in ('chave_acesso', 'modelo', 'serie')}
    initial['numero_nota'] = original.get('numero_nota')
    for campo in initial:
        if correcoes is not None and campo in correcoes:
            initial[campo] = correcoes[campo]
    return CamposFiscaisForm(initial=initial, prefix='fiscal')
