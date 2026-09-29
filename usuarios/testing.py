"""Apoio aos testes que precisam da sessão da demonstração.

Credenciais fictícias, usadas só com override_settings; nunca as reais.
"""

from django.conf import settings

from .demo import SESSAO_DEMO

CREDENCIAIS_TESTE = {
    "DEMO_LOGIN": "login-de-teste",
    "DEMO_PASSWORD": "senha-de-teste",
}


def autenticar_demo(client):
    """Grava no client de teste o cookie de sessão autenticado na demonstração."""
    session = client.session
    session[SESSAO_DEMO] = True
    session.save()
    # Com cookie assinado, a "chave" da sessão é o próprio conteúdo assinado.
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
