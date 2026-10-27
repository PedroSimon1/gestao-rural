"""GR-47: manutenção autenticada sem alterar serviços ou modelos de domínio."""
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required

from .forms import ConfirmacaoForm
from .forms_classificacoes import DescricaoClassificacaoForm, NovaClassificacaoForm, PesquisaClassificacaoForm
from .models import Classificacao, Status
from .views import _entrada_valida


def _erro(form, erro):
    if isinstance(erro, IntegrityError):
        form.add_error(None, "Já existe uma classificação com este tipo e código. Pesquise também os inativos; a reativação é uma ação separada.")
    elif hasattr(erro, "message_dict"):
        for campo, mensagens in erro.message_dict.items():
            form.add_error(campo if campo in form.fields else None, mensagens)
    else:
        form.add_error(None, erro)


@demo_login_required
@require_http_methods(["GET"])
def classificacoes(request):
    modo = request.GET.get("modo")
    form = PesquisaClassificacaoForm(request.GET if modo == "buscar" else None)
    encontrados = []
    if modo == "todos":
        encontrados = Classificacao.objects.ativos()
    elif modo == "buscar" and form.is_valid():
        dados = form.cleaned_data
        if not dados["busca"] and not dados["tipo"] and dados["status"] in {None, "", Status.ATIVO}:
            form.add_error(None, "Informe código, descrição ou tipo; ou use TODOS (ativos).")
        else:
            encontrados = Classificacao.objects.all()
            for termo in dados["busca"].split():
                encontrados = encontrados.filter(Q(codigo__icontains=termo) | Q(descricao__icontains=termo))
            if dados["tipo"]:
                encontrados = encontrados.filter(tipo=dados["tipo"])
            status = dados["status"] or Status.ATIVO
            if status != "TODOS":
                encontrados = encontrados.filter(status=status)
    ordem = request.GET.get("ordem", "descricao")
    campos = {"tipo", "codigo", "descricao", "status"}
    if ordem.removeprefix("-") not in campos:
        ordem = "descricao"
    if hasattr(encontrados, "order_by"):
        encontrados = encontrados.order_by(ordem, "id")
    pagina = Paginator(encontrados, 30).get_page(request.GET.get("pagina"))
    cabecalhos = []
    for campo, rotulo in (("tipo", "Tipo"), ("codigo", "Código"), ("descricao", "Descrição"), ("status", "Situação")):
        params = request.GET.copy()
        params.pop("pagina", None)
        params["ordem"] = "-" + campo if ordem == campo else campo
        cabecalhos.append({"rotulo": rotulo, "query": params.urlencode()})
    params = request.GET.copy()
    params.pop("pagina", None)
    return render(request, "cadastros/classificacoes.html", {
        "form": form, "pagina": pagina, "pesquisou": modo in {"buscar", "todos"},
        "cabecalhos": cabecalhos, "filtros": params.urlencode(),
    })


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def classificacao_nova(request):
    form = NovaClassificacaoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and _entrada_valida(form, request):
        try:
            # Savepoint apenas do cadastro: trata disputa no índice único sem
            # deixar a conexão quebrada. Nenhuma transação financeira aqui.
            with transaction.atomic():
                classificacao = form.save()
        except (ValidationError, IntegrityError) as erro:
            _erro(form, erro)
        else:
            return redirect("classificacao_editar", classificacao_id=classificacao.pk)
    return render(request, "cadastros/classificacao_form.html", {"form": form, "titulo": "Cadastrar classificação"})


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def classificacao_editar(request, classificacao_id):
    classificacao = get_object_or_404(Classificacao, pk=classificacao_id)
    form = DescricaoClassificacaoForm(request.POST if request.method == "POST" else None, instance=classificacao)
    if request.method == "POST" and _entrada_valida(form, request):
        try:
            form.save()
        except ValidationError as erro:
            _erro(form, erro)
        else:
            return redirect("classificacao_editar", classificacao_id=classificacao.pk)
    return render(request, "cadastros/classificacao_form.html", {
        "form": form, "titulo": "Editar classificação", "classificacao": classificacao,
    })


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def classificacao_status(request, classificacao_id, acao):
    if acao not in {"inativar", "reativar"}:
        raise Http404
    classificacao = get_object_or_404(Classificacao, pk=classificacao_id)
    form = ConfirmacaoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and _entrada_valida(form, request):
        getattr(classificacao, acao)()
        return redirect("classificacao_editar", classificacao_id=classificacao.pk)
    return render(request, "cadastros/classificacao_form.html", {
        "form": form, "titulo": f"{acao.capitalize()} classificação", "classificacao": classificacao,
        "aviso": "Somente a situação será alterada. Os vínculos e movimentos financeiros existentes serão preservados.",
    })
