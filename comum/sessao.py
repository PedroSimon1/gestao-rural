"""Código que identifica o dono das análises e dos formulários de uma sessão (GR-43).

O cookie assinado da sessão guarda só um código aleatório por login; análises e formulários
guardam apenas um hash dele. Fica aqui, fora dos apps, porque `documentos` (análises) e
`financeiro` (formulário manual) usam o mesmo código e não devem depender um do outro por isso.
"""
import secrets

CHAVE_DA_SESSAO = "analise_dono"


def garantir_dono(session):
    """Dá à sessão um código novo (chamado no login, usuarios/demo.py).

    O código nasce no login, e não numa requisição longa de processamento: com
    cookie assinado, a resposta regrava a sessão inteira e poderia desfazer um
    logout feito em outra aba nesse meio tempo. Um código novo a cada login
    impede que o código de uma sessão não autenticada seja reaproveitado; não
    protege contra quem planta um cookie já autenticado.
    """
    session[CHAVE_DA_SESSAO] = secrets.token_urlsafe(32)


def codigo_do_dono(session):
    """Código da sessão, ou None se ela não tem um (cookie anterior à GR-43)."""
    codigo = session.get(CHAVE_DA_SESSAO)
    if not isinstance(codigo, str) or not codigo:
        return None
    return codigo
