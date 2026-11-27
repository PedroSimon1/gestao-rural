from django.shortcuts import render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required

from .forms import ConsultaForm
from .servico import MODOS, ConsultaError, consultar


@sensitive_post_parameters("gemini_api_key")
@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_variables("form", "dados", "chave")
def consulta(request):
    """Pergunta em linguagem natural; a chave vale só nesta requisição e nunca vai ao contexto."""
    contexto = {"resposta": None, "erro": None}
    if request.method == "POST":
        form = ConsultaForm(request.POST)
        valido = form.is_valid()
        # O formulário vai ao template: a chave sai dele antes, mesmo com erros de validação.
        chave = form.cleaned_data.pop("gemini_api_key", None) if valido else None
        form.data = form.data.copy()
        form.data.pop("gemini_api_key", None)
        if valido:
            dados = form.cleaned_data
            try:
                contexto["resposta"] = consultar(dados["pergunta"], dados["modo"], chave)
            except ConsultaError as exc:
                contexto["erro"] = exc.mensagem
            else:
                contexto["modo_rotulo"] = MODOS[contexto["resposta"].modo].rotulo
    else:
        form = ConsultaForm()
    contexto["form"] = form
    return render(request, "consulta/consulta.html", contexto)
