"""Manutenção de Pessoas/Papéis (GR-46), usando os métodos oficiais."""
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required

from .forms import (
    ConfirmacaoForm, NovaPessoaForm, PapelForm, PesquisaPessoaForm,
    PessoaForm, RegularizacaoForm,
)
from .models import PapelPessoa, Pessoa, Status
from .pendentes import regularizar_cadastro_pendente
from .resolucao import Decisao, ParteNota, resolver_partes
from .validators import normalizar_documento


def _entrada_valida(form, request):
    valida = form.is_valid()
    # Recusa campos externos ao formulário e campos escalares repetidos.
    extras = set(request.POST) - set(form.fields) - {"csrfmiddlewaretoken"}
    repetidos = any(len(request.POST.getlist(c)) > 1 for c in request.POST if c != "papeis")
    if extras or repetidos:
        form.add_error(None, "Pedido inválido. Recarregue o formulário e tente novamente.")
        return False
    return valida


def _erro(form, erro):
    # Não expor SQL, documentos pessoais nem detalhes de infraestrutura.
    if isinstance(erro, IntegrityError):
        form.add_error(None, "O documento já está em uso. Recarregue e confira o cadastro existente.")
    elif hasattr(erro, "message_dict"):
        for campo, mensagens in erro.message_dict.items():
            form.add_error(campo if campo in form.fields else None, mensagens)
    else:
        form.add_error(None, erro)


@demo_login_required
@require_http_methods(["GET"])
def pessoas(request):
    modo = request.GET.get("modo")
    form = PesquisaPessoaForm(request.GET if modo == "buscar" else None)
    encontrados = []
    pesquisou = modo in {"buscar", "todos"}
    if modo == "todos":
        encontrados = Pessoa.objects.ativos()
    elif modo == "buscar" and form.is_valid():
        dados = form.cleaned_data
        if not any(dados.get(c) for c in ("busca", "papel")) and dados.get("status") in {None, "", Status.ATIVO}:
            form.add_error(None, "Informe nome, documento ou papel; ou use TODOS (ativos).")
        else:
            encontrados = Pessoa.objects.all()
            for termo in dados["busca"].split():
                condicao = Q(razao_social__icontains=termo)
                documento = normalizar_documento(termo)
                if documento:
                    condicao |= Q(documento__icontains=documento)
                encontrados = encontrados.filter(condicao)
            if dados["papel"]:
                encontrados = encontrados.filter(papeis__papel=dados["papel"])
            status = dados["status"] or Status.ATIVO
            if status != "TODOS":
                encontrados = encontrados.filter(status=status)
    ordem = request.GET.get("ordem", "nome")
    campos = {"nome": "razao_social", "documento": "documento", "status": "status"}
    chave = ordem.removeprefix("-")
    if chave not in campos:
        ordem, chave = "nome", "nome"
    if hasattr(encontrados, "order_by"):
        encontrados = encontrados.order_by(("-" if ordem.startswith("-") else "") + campos[chave], "id").prefetch_related("papeis")
    pagina = Paginator(encontrados, 30).get_page(request.GET.get("pagina"))
    cabecalhos = []
    for campo, rotulo in (("nome", "Nome / razão social"), ("documento", "Documento"), ("status", "Situação")):
        params = request.GET.copy()
        params.pop("pagina", None)
        params["ordem"] = "-" + campo if ordem == campo else campo
        cabecalhos.append({"rotulo": rotulo, "query": params.urlencode()})
    params = request.GET.copy()
    params.pop("pagina", None)
    return render(request, "cadastros/pessoas.html", {
        "form": form, "pagina": pagina, "pesquisou": pesquisou,
        "cabecalhos": cabecalhos, "filtros": params.urlencode(),
    })


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def pessoa_nova(request):
    form = NovaPessoaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and _entrada_valida(form, request):
        dados = form.cleaned_data
        try:
            resolvidas = resolver_partes([
                ParteNota(papel=papel, documento=dados["documento"], nome=dados["razao_social"],
                          decisoes=frozenset({Decisao.CRIAR_PESSOA, Decisao.ATRIBUIR_PAPEL}))
                for papel in dados["papeis"]
            ])
        except (ValidationError, IntegrityError) as erro:
            _erro(form, erro)
        else:
            return redirect("pessoa_detalhe", pessoa_id=resolvidas[0].pessoa.pk)
    return render(request, "cadastros/pessoa_form.html", {"form": form, "titulo": "Cadastrar pessoa"})


@demo_login_required
@require_http_methods(["GET"])
def pessoa_detalhe(request, pessoa_id):
    pessoa = get_object_or_404(Pessoa.objects.prefetch_related("papeis"), pk=pessoa_id)
    return render(request, "cadastros/pessoa_detalhe.html", {"pessoa": pessoa, "papel_form": PapelForm()})


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def pessoa_editar(request, pessoa_id):
    pessoa = get_object_or_404(Pessoa, pk=pessoa_id)
    form = PessoaForm(request.POST if request.method == "POST" else None, instance=pessoa)
    if request.method == "POST" and _entrada_valida(form, request):
        try:
            form.save()
        except (ValidationError, IntegrityError) as erro:
            _erro(form, erro)
        else:
            return redirect("pessoa_detalhe", pessoa_id=pessoa.pk)
    return render(request, "cadastros/pessoa_form.html", {"form": form, "pessoa": pessoa, "titulo": "Editar pessoa"})


@demo_login_required
@require_http_methods(["POST"])
@sensitive_post_parameters()
def pessoa_atribuir_papel(request, pessoa_id):
    pessoa = get_object_or_404(Pessoa.objects.prefetch_related("papeis"), pk=pessoa_id)
    form = PapelForm(request.POST)
    aviso = None
    if _entrada_valida(form, request):
        vinculo, criado = pessoa.atribuir_papel(form.cleaned_data["papel"])
        if criado:
            return redirect("pessoa_detalhe", pessoa_id=pessoa.pk)
        aviso = "Este papel já existe. Se estiver inativo, use a ação Reativar do próprio papel."
    return render(request, "cadastros/pessoa_detalhe.html", {"pessoa": pessoa, "papel_form": form, "aviso": aviso})


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def pessoa_status(request, pessoa_id, acao, papel_id=None):
    if acao not in {"inativar", "reativar"}:
        raise Http404
    pessoa = get_object_or_404(Pessoa, pk=pessoa_id)
    alvo = pessoa if papel_id is None else get_object_or_404(PapelPessoa, pk=papel_id, pessoa=pessoa)
    form = ConfirmacaoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and _entrada_valida(form, request):
        getattr(alvo, acao)()
        return redirect("pessoa_detalhe", pessoa_id=pessoa.pk)
    titulo = f"{acao.capitalize()} " + ("pessoa" if papel_id is None else alvo.get_papel_display())
    return render(request, "cadastros/pessoa_form.html", {
        "form": form, "pessoa": pessoa, "titulo": titulo,
        "aviso": "Esta ação altera somente o status selecionado. Pessoa e papéis têm status independentes; vínculos históricos serão preservados.",
    })


@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def pessoa_regularizar(request, pessoa_id):
    pessoa = get_object_or_404(Pessoa, pk=pessoa_id)
    if pessoa.documentacao_completa:
        return redirect("pessoa_detalhe", pessoa_id=pessoa.pk)
    form = RegularizacaoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and _entrada_valida(form, request):
        try:
            regularizar_cadastro_pendente(pessoa.pk, form.cleaned_data["documento"])
        except (ValidationError, IntegrityError) as erro:
            _erro(form, erro)
        else:
            return redirect("pessoa_detalhe", pessoa_id=pessoa.pk)
    return render(request, "cadastros/pessoa_form.html", {
        "form": form, "pessoa": pessoa, "titulo": "Regularizar documento",
        "aviso": "O documento será validado no cadastro existente, preservando os papéis e vínculos.",
    })
