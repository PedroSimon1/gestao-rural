"""GR-51: interface da confirmação; a F-5 é a única transação financeira."""
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from config.erros_banco import mensagem_de_banco
from usuarios.demo import demo_login_required
from cadastros.resolucao import ParteNota, avaliar_partes
from financeiro.duplicidade import movimentos_parecidos
from financeiro.lancamento_nota import lancar_nota
from .analises import AnaliseError, obter_analise
from .conferencia import conferir_nota
from .forms_confirmacao import ConfirmacaoLancamentoForm, ROTULOS_DECISAO
from .mensagens_conferencia import ROTULOS_CAMPO, mensagem_validacao
from .resumo_nota import ficha_da_nota, resumo_do_lancamento
from .views_analises import _erro_analise, _falha


def pendencias_da_nota(nota):
    return [f"{ROTULOS_CAMPO.get(p.campo, 'Dados da nota')}: {mensagem_validacao(p.codigo)}" for p in nota.problemas]


def _avaliacoes(nota):
    partes = (nota.fornecedor, nota.faturado)
    resultado = avaliar_partes([ParteNota(papel=p.papel, documento=p.documento, nome=p.nome) for p in partes])
    return [{'rotulo': rotulo, 'acoes': [ROTULOS_DECISAO[d] for d in ROTULOS_DECISAO if d in avaliacao.decisoes_necessarias],
             'bloqueio': mensagem_validacao(avaliacao.bloqueio) if avaliacao.bloqueio else None}
            for rotulo, avaliacao in zip(('Fornecedor', 'Faturado'), resultado)]


def _duplicidades(nota):
    """Contas já registradas parecidas com esta nota (só aviso: a identidade fiscal é a trava de verdade)."""
    contraparte_id = nota.fornecedor.consulta.id
    if contraparte_id is None or nota.valor_total is None:
        return ()
    return movimentos_parecidos(
        contraparte_id, nota.valor_total, min((p.data_vencimento for p in nota.parcelas), default=None),
    )


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
                        'movimento_id': resultado.movimento.pk, 'nota_fiscal_id': resultado.nota_fiscal.pk,
                        'ficha': ficha_da_nota(nota), 'resumo': resumo_do_lancamento(nota)})
            else:
                status = 400
        else:
            form = ConfirmacaoLancamentoForm(initial={'versao_correcoes': analise.versao_correcoes})
        return render(request, 'documentos/confirmacao.html', {
            'analise_id': analise.id, 'form_confirmacao': form, 'nota': nota, 'ficha': ficha_da_nota(nota),
            'pendencias': pendencias_da_nota(nota), 'avaliacoes': _avaliacoes(nota),
            'duplicidades': _duplicidades(nota),
        }, status=status)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, mensagem_de_banco(
            'confirmar o lançamento',
            'Recarregue a análise e confira o estado dela antes de tentar novamente.'), 503)
