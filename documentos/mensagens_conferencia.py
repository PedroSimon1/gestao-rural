"""Textos da conferência e da confirmação: mensagem por código e rótulo por campo.

Os códigos vêm da F-3 (conferir_nota), da F-4 (resolver_partes) e de registrar_movimento;
nunca se mostra a mensagem original de uma exceção, que pode trazer valores.
"""
from .forms_fiscais import MENSAGENS_FISCAIS, mensagem_fiscal

MENSAGENS = {
    'pessoa_inexistente': 'Autorize a criação do cadastro que ainda não existe.',
    'pessoa_inativa': 'O cadastro está inativo. Autorize a reativação se desejar utilizá-lo.',
    'papel_ausente': 'Autorize atribuir o papel necessário ao cadastro.',
    'papel_inativo': 'Autorize a reativação do papel necessário.',
    'pessoa_incompleta': 'Selecione um cadastro incompleto e autorize sua regularização com documento válido.',
    'documento_ausente': 'Informe o documento da parte na conferência.',
    'documento_invalido': 'Corrija o documento da parte na conferência.',
    'nome_ausente': 'Preencha o nome para o novo cadastro.',
    'nomes_divergentes': 'O mesmo documento está associado a nomes diferentes. Revise os dados.',
    'documento_em_uso': 'O documento já pertence a outro cadastro. Revise a seleção.',
    'selecao_invalida': 'O cadastro incompleto selecionado não está disponível.',
    'cadastro_concorrente': 'Os cadastros mudaram durante a confirmação. Recarregue e confira novamente.',
    'classificacao_inativa': 'A classificação está inativa. Selecione uma classificação ativa.',
    'classificacao_incompativel': 'A classificação não pode ser usada neste lançamento.',
    'classificacao_inexistente': 'Selecione uma classificação cadastrada.',
    'escolha_necessaria': 'Escolha explicitamente o documento correto na conferência.',
    'parcela_soma': 'A soma das parcelas deve ser igual ao total da nota.',
    'parcela_vencimento': 'Complete os vencimentos das parcelas.',
    'parcela_numeracao': 'Confira a numeração das parcelas.',
    'sem_parcela': 'Informe pelo menos uma parcela com valor e vencimento.',
    'ausente': 'Complete o campo indicado na conferência.',
    'invalido': 'Corrija o campo indicado na conferência.',
}
ROTULOS_CAMPO = {'identidade_fiscal': 'Identificação fiscal', 'chave_acesso': 'Chave de acesso',
    'modelo': 'Modelo', 'serie': 'Série', 'numero_nota': 'Número da nota',
    'fornecedor.documento': 'Documento do fornecedor', 'fornecedor.razao_social': 'Nome do fornecedor',
    'faturado.documento': 'Documento do faturado', 'faturado.nome': 'Nome do faturado',
    'valor_total': 'Valor total', 'parcelas': 'Parcelas', 'tipo_despesa': 'Classificação'}


def mensagem_validacao(codigo):
    if codigo in MENSAGENS_FISCAIS:
        return mensagem_fiscal(codigo)
    return MENSAGENS.get(codigo, 'Os dados não permitem confirmar o lançamento. Revise a conferência.')
