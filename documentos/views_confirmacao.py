"""GR-51: interface da confirmação; a F-5 é a única transação financeira."""
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required
from cadastros.resolucao import ParteNota, avaliar_partes
from financeiro.lancamento_nota import lancar_nota
from .analises import AnaliseError, obter_analise
from .conferencia import conferir_nota
from .forms_confirmacao import ConfirmacaoLancamentoForm, ROTULOS_DECISAO
from .forms_fiscais import MENSAGENS_FISCAIS, mensagem_fiscal
from .views_analises import _erro_analise, _falha

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


def pendencias_da_nota(nota):
    return [f"{ROTULOS_CAMPO.get(p.campo, 'Dados da nota')}: {mensagem_validacao(p.codigo)}" for p in nota.problemas]


def _avaliacoes(nota):
    partes = (nota.fornecedor, nota.faturado)
    resultado = avaliar_partes([ParteNota(papel=p.papel, documento=p.documento, nome=p.nome) for p in partes])
    return [{'rotulo': rotulo, 'acoes': [ROTULOS_DECISAO[d] for d in ROTULOS_DECISAO if d in avaliacao.decisoes_necessarias],
             'bloqueio': mensagem_validacao(avaliacao.bloqueio) if avaliacao.bloqueio else None}
            for rotulo, avaliacao in zip(('Fornecedor', 'Faturado'), resultado)]


@sensitive_post_parameters()
@demo_login_required
@require_http_methods(['GET', 'POST'])
def analise_confirmar(request, analise_id):
    try:
        analise = obter_analise(request.session, analise_id)
        nota = conferir_nota(analise.dados, analise.correcoes)
        status = 200
        if request.method == 'POST':
            permitidos = set(ConfirmacaoLancamentoForm.base_fields) | {'csrfmiddlewaretoken'}
            if set(request.POST) - permitidos:
                return _falha(request, 'A confirmação contém campos não autorizados.', 400)
            form = ConfirmacaoLancamentoForm(request.POST)
            if form.is_valid():
                try:
                    resultado = lancar_nota(request.session, analise.id, form.solicitacao())
                except ValidationError as erro:
                    # Ler códigos da F-5, nunca mensagens arbitrárias com valores.
                    for mensagem in dict.fromkeys(mensagem_validacao(e.code) for e in erro.error_list):
                        form.add_error(None, mensagem)
                    status = 400
                else:
                    # lancar_nota só retorna depois do COMMIT oficial.
                    return render(request, 'documentos/lancamento_sucesso.html', {
                        'movimento_id': resultado.movimento.pk, 'nota_fiscal_id': resultado.nota_fiscal.pk})
            else:
                status = 400
        else:
            form = ConfirmacaoLancamentoForm(initial={'versao_correcoes': analise.versao_correcoes})
        return render(request, 'documentos/confirmacao.html', {
            'analise_id': analise.id, 'form_confirmacao': form, 'nota': nota,
            'pendencias': pendencias_da_nota(nota), 'avaliacoes': _avaliacoes(nota),
        }, status=status)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, 'Não foi possível confirmar o lançamento agora. Recarregue a análise e confira seu estado antes de tentar novamente.', 503)
