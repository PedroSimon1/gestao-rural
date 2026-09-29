"""Autenticação da demonstração (apresentação da N2 - Etapa 1).

Login e senha vêm de settings.DEMO_LOGIN e settings.DEMO_PASSWORD (lidos do
ambiente). Não há usuários nem banco: a autenticação existe só na sessão do
Django (cookie assinado, ver SESSION_ENGINE), na chave SESSAO_DEMO.
"""

from functools import wraps

from django.conf import settings
from django.shortcuts import redirect
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

SESSAO_DEMO = "demo_autenticado"


def _configurado(valor):
    return isinstance(valor, str) and bool(valor.strip())


def credenciais_configuradas():
    return _configurado(getattr(settings, "DEMO_LOGIN", None)) and _configurado(
        getattr(settings, "DEMO_PASSWORD", None)
    )


@sensitive_variables("senha", "senha_esperada")
def credenciais_validas(login, senha):
    """Compara com o ambiente em tempo constante. Sem configuração, recusa."""
    if not credenciais_configuradas():
        return False
    login_esperado = settings.DEMO_LOGIN
    senha_esperada = settings.DEMO_PASSWORD
    # "&" em vez de "and": as duas comparações sempre acontecem.
    return constant_time_compare(login, login_esperado) & constant_time_compare(
        senha, senha_esperada
    )


def demo_autenticado(request):
    # Sem configuração, nem uma sessão antiga libera o acesso.
    return request.session.get(SESSAO_DEMO) is True and credenciais_configuradas()


def iniciar_sessao_demo(request):
    # Com cookie assinado não há chave no servidor para fixar: o cookie
    # inteiro é regravado quando a sessão muda.
    request.session[SESSAO_DEMO] = True


def encerrar_sessao_demo(request):
    request.session.flush()


def demo_login_required(view):
    """Exige a sessão da demonstração; sem ela, redireciona para /login/."""

    @wraps(view)
    def verificar(request, *args, **kwargs):
        if not demo_autenticado(request):
            return redirect("login")
        return view(request, *args, **kwargs)

    return verificar
