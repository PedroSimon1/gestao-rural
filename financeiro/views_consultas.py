"""GR-49 parcial: somente leitura pelos serviços oficiais de P08."""
from functools import wraps
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from usuarios.demo import demo_login_required
from .forms_consultas import FiltroContasForm
from .manual import MOVIMENTO_INEXISTENTE, consultar_movimento, listar_movimentos
from .models import OrigemMovimento, StatusMovimento, StatusParcela, TipoMovimento


def _erros_de_banco(view):
    @wraps(view)
    def consultar(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except DatabaseError:
            # Inclui falhas ao validar/renderizar os seletores de filtros.
            return render(request, "financeiro/conta_detalhe.html", {
                "erro": "Não foi possível consultar as contas agora. Tente novamente.",
            }, status=503)
    return consultar


def _resumo(item):
    return {
        "dados": item, "tipo": TipoMovimento(item.tipo).label,
        "origem": OrigemMovimento(item.origem).label,
        "status": StatusMovimento(item.status).label,
    }


@never_cache
@demo_login_required
@require_GET
@_erros_de_banco
def contas(request):
    modo = request.GET.get("modo")
    form = FiltroContasForm(request.GET if modo == "buscar" else None)
    contexto = {"form": form, "pesquisou": modo in {"buscar", "todos"}, "linhas": []}
    filtros = None
    if modo == "todos":
        # CONFIRMADO é estado financeiro, não status administrativo ATIVO.
        filtros = {"status": StatusMovimento.CONFIRMADO}
        try:
            pagina = int(request.GET.get("pagina", "1"))
            if not 1 <= pagina <= 10**9:
                raise ValueError
            filtros["pagina"] = pagina
        except (ValueError, TypeError):
            contexto["erro"] = "Página inválida. Volte à pesquisa."
            filtros = None
    elif modo == "buscar" and form.is_valid():
        d = form.cleaned_data
        filtros = {
            "tipo": d["tipo"] or None, "origem": d["origem"] or None,
            "status": None if d["status"] == "TODOS" else (d["status"] or StatusMovimento.CONFIRMADO),
            "contraparte_id": d["contraparte"].pk if d["contraparte"] else None,
            "classificacao_id": d["classificacao"].pk if d["classificacao"] else None,
            "pagina": d["pagina"] or 1, "por_pagina": int(d["por_pagina"] or 30),
        }
    if filtros is not None:
        pagina = listar_movimentos(**filtros)
        contexto.update(pagina=pagina, linhas=[_resumo(item) for item in pagina.itens],
            anterior=pagina.pagina - 1 if pagina.pagina > 1 else None,
            proxima=pagina.pagina + 1 if pagina.pagina < pagina.total_paginas else None)
    params = request.GET.copy()
    params.pop("pagina", None)
    contexto["filtros"] = params.urlencode()
    return render(request, "financeiro/contas.html", contexto)


@never_cache
@demo_login_required
@require_GET
@_erros_de_banco
def conta_detalhe(request, movimento_id):
    try:
        detalhe = consultar_movimento(movimento_id)
    except ValidationError as erro:
        if erro.code == MOVIMENTO_INEXISTENTE:
            return render(request, "financeiro/conta_detalhe.html", {
                "erro": "Conta não encontrada.",
            }, status=404)
        raise
    return render(request, "financeiro/conta_detalhe.html", {
        **_resumo(detalhe), "detalhe": detalhe,
        "parcelas": [{"dados": p, "status": StatusParcela(p.status).label} for p in detalhe.parcelas],
    })
