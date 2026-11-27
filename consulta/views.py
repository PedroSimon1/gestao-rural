from django.shortcuts import render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required

from .forms import ConsultaForm, IndiceForm
from .servico import (
    MODOS, ConsultaError, atualizar_indice_com_chave, consultar, descrever_atualizacao,
    situacao_do_indice,
)


def _retirar_chave(form):
    """O formulário vai ao template: a chave sai dele antes, mesmo com erros de validação."""
    chave = form.cleaned_data.pop("gemini_api_key", None) if form.is_valid() else None
    form.data = form.data.copy()
    form.data.pop("gemini_api_key", None)
    return chave


def _pagina(request, contexto):
    contexto.setdefault("form", ConsultaForm())
    contexto.setdefault("indice_form", IndiceForm())
    contexto.setdefault("indice", situacao_do_indice())
    return render(request, "consulta/consulta.html", contexto)


@sensitive_post_parameters("gemini_api_key")
@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_variables("form", "dados", "chave")
def consulta(request):
    """Pergunta em linguagem natural; a chave vale só nesta requisição e nunca vai ao contexto."""
    contexto = {"resposta": None, "erro": None}
    if request.method == "POST":
        form = ConsultaForm(request.POST)
        chave = _retirar_chave(form)
        if form.is_valid():
            dados = form.cleaned_data
            try:
                contexto["resposta"] = consultar(dados["pergunta"], dados["modo"], chave)
            except ConsultaError as exc:
                contexto["erro"] = exc.mensagem
            else:
                contexto["modo_rotulo"] = MODOS[contexto["resposta"].modo].rotulo
        contexto["form"] = form
    return _pagina(request, contexto)


@sensitive_post_parameters("gemini_api_key")
@demo_login_required
@require_http_methods(["POST"])
@sensitive_variables("form", "chave")
def consulta_indice(request):
    """Indexa um lote de movimentos; a chave vale só nesta requisição e nunca vai ao contexto."""
    contexto = {"resposta": None, "erro": None, "indice_mensagem": None, "indice_erro": None}
    form = IndiceForm(request.POST)
    chave = _retirar_chave(form)
    if form.is_valid():
        antes = situacao_do_indice()
        try:
            depois = atualizar_indice_com_chave(chave)
        except ConsultaError as exc:
            contexto["indice_erro"] = exc.mensagem
        else:
            contexto["indice"] = depois
            contexto["indice_mensagem"] = descrever_atualizacao(antes, depois)
    contexto["indice_form"] = form
    return _pagina(request, contexto)
