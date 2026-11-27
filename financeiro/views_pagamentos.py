"""Baixa de parcela pela tela da conta (D1): marcar como paga/recebida e desfazer."""
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from usuarios.demo import demo_login_required
from .forms_pagamentos import DESFAZER, PagamentoParcelaForm
from .models import ParcelaConta
from .pagamentos import desfazer_pagamento, registrar_pagamento
from .views_consultas import _erros_de_banco, renderizar_detalhe

CAMPOS = {"acao", "data_pagamento", "csrfmiddlewaretoken"}


@never_cache
@demo_login_required
@require_POST
@_erros_de_banco
def parcela_pagamento(request, parcela_id):
    movimento_id = ParcelaConta.objects.filter(pk=parcela_id).values_list("movimento_id", flat=True).first()
    if movimento_id is None:
        return render(request, "financeiro/conta_detalhe.html", {"erro": "Parcela não encontrada."}, status=404)

    form = PagamentoParcelaForm(request.POST)
    erro = None
    if set(request.POST) - CAMPOS or any(len(request.POST.getlist(c)) > 1 for c in request.POST):
        erro = "Pedido inválido. Recarregue a página e tente de novo."
    elif not form.is_valid():
        erro = next(iter(form.errors.values()))[0]
    else:
        try:
            if form.cleaned_data["acao"] == DESFAZER:
                desfazer_pagamento(parcela_id)
            else:
                registrar_pagamento(parcela_id, form.cleaned_data["data_pagamento"])
        except ValidationError as falha:
            erro = falha.messages[0]
        else:
            return redirect("conta_detalhe", movimento_id=movimento_id)
    return renderizar_detalhe(request, movimento_id, status=400, erro_pagamento=erro)
