import logging

from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from . import limite
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
MENSAGEM_MUITAS_TENTATIVAS = (
    "Muitas tentativas de login. Aguarde alguns minutos e tente novamente."
)


@sensitive_post_parameters("senha")
@require_http_methods(["GET", "POST"])
def login_demo(request):
    """Tela de login da demonstração (credenciais do ambiente, sem tabela de usuários)."""
    if demo_autenticado(request):
        return redirect("documento_inicio")

    erro = None
    if request.method == "POST":
        form = LoginDemoForm(request.POST)
        if not credenciais_configuradas():
            # Só o nome das variáveis no log; nunca valores.
            logger.warning("Login da demonstração sem DEMO_LOGIN/DEMO_PASSWORD configurados.")
            erro = MENSAGEM_LOGIN_INDISPONIVEL
        elif limite.bloqueado(request):
            # Recusa antes de comparar: com a senha certa também, até a janela acabar.
            logger.warning("Login da demonstração bloqueado por excesso de tentativas.")
            return render(
                request, "usuarios/login.html",
                {"form": LoginDemoForm(), "erro": MENSAGEM_MUITAS_TENTATIVAS}, status=429,
            )
        elif form.is_valid() and credenciais_validas(
            form.cleaned_data["login"], form.cleaned_data["senha"]
        ):
            limite.limpar_falhas_da_origem(request)
            iniciar_sessao_demo(request)
            return redirect("documento_inicio")
        else:
            limite.registrar_falha(request)
            erro = MENSAGEM_CREDENCIAIS_INVALIDAS
    else:
        form = LoginDemoForm()

    return render(request, "usuarios/login.html", {"form": form, "erro": erro})


@require_http_methods(["GET", "POST"])
def logout_demo(request):
    # GET não pode cancelar análises por um link externo ou prefetch.
    if request.method == "GET":
        return render(request, "usuarios/logout.html")
    encerrar_sessao_demo(request)
    return redirect("login")
