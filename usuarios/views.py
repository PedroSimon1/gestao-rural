import logging

from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .demo import (
    credenciais_configuradas,
    credenciais_validas,
    demo_autenticado,
    encerrar_sessao_demo,
    iniciar_sessao_demo,
)
from .forms import LoginDemoForm

logger = logging.getLogger(__name__)

MENSAGEM_CREDENCIAIS_INVALIDAS = "Login ou senha inválidos."
MENSAGEM_LOGIN_INDISPONIVEL = (
    "Login indisponível no momento. Avise o responsável pelo sistema."
)


@sensitive_post_parameters("senha")
@require_http_methods(["GET", "POST"])
def login_demo(request):
    """Tela de login da demonstração (credenciais do ambiente, sem banco)."""
    if demo_autenticado(request):
        return redirect("documento_inicio")

    erro = None
    if request.method == "POST":
        form = LoginDemoForm(request.POST)
        if not credenciais_configuradas():
            # Só o nome das variáveis no log; nunca valores.
            logger.warning("Login da demonstração sem DEMO_LOGIN/DEMO_PASSWORD configurados.")
            erro = MENSAGEM_LOGIN_INDISPONIVEL
        elif form.is_valid() and credenciais_validas(
            form.cleaned_data["login"], form.cleaned_data["senha"]
        ):
            iniciar_sessao_demo(request)
            return redirect("documento_inicio")
        else:
            erro = MENSAGEM_CREDENCIAIS_INVALIDAS
    else:
        form = LoginDemoForm()

    return render(request, "usuarios/login.html", {"form": form, "erro": erro})


@require_http_methods(["GET", "POST"])
def logout_demo(request):
    encerrar_sessao_demo(request)
    return redirect("login")
