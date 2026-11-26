"""Limite de tentativas de login (auditoria M-01).

Conta as falhas por origem e no total, numa janela fixa que começa na primeira
falha. Passado o teto, o login recusa qualquer tentativa (inclusive com a senha
certa) até a janela acabar.

Limites conhecidos:
- O contador fica no cache do Django (memória do processo, `LocMemCache`).
  Cada worker do Gunicorn conta à parte e um reinício zera tudo; com
  `WEB_CONCURRENCY` = N, o teto efetivo por origem chega a N vezes o definido.
- O teto global protege contra tentativas espalhadas por vários endereços, mas
  também permite que alguém bloqueie o login legítimo durante a janela. Com um
  login único e compartilhado, esse custo foi aceito.
- Os endereços só entram no cache como hash.
"""
import hashlib

from django.core.cache import cache

TENTATIVAS_POR_ORIGEM = 5
TENTATIVAS_GLOBAIS = 30
JANELA_EM_SEGUNDOS = 15 * 60

CHAVE_GLOBAL = "login-falhas:global"


def _origem(request):
    # Atrás do proxy da plataforma, o último valor de X-Forwarded-For é o endereço
    # que o próprio proxy viu; valores anteriores podem ser forjados pelo cliente.
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ultimo = encaminhado.split(",")[-1].strip()
    return ultimo or request.META.get("REMOTE_ADDR", "")


def _chave_da_origem(request):
    resumo = hashlib.sha256(_origem(request).encode()).hexdigest()[:32]
    return f"login-falhas:origem:{resumo}"


def _incrementar(chave):
    # `add` define a janela só na primeira falha; `incr` preserva o prazo.
    cache.add(chave, 0, JANELA_EM_SEGUNDOS)
    try:
        cache.incr(chave)
    except ValueError:
        # Expirou entre o add e o incr.
        cache.set(chave, 1, JANELA_EM_SEGUNDOS)


def bloqueado(request):
    return (
        cache.get(_chave_da_origem(request), 0) >= TENTATIVAS_POR_ORIGEM
        or cache.get(CHAVE_GLOBAL, 0) >= TENTATIVAS_GLOBAIS
    )


def registrar_falha(request):
    _incrementar(_chave_da_origem(request))
    _incrementar(CHAVE_GLOBAL)


def limpar_falhas_da_origem(request):
    cache.delete(_chave_da_origem(request))
