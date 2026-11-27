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
- A origem vem de X-Forwarded-For contando PROXIES_CONFIAVEIS valores do fim
  (DJANGO_PROXIES_CONFIAVEIS, padrão 1). Se o número real de proxies da
  plataforma for outro, a origem de todos os usuários pode virar o mesmo
  endereço (todos no mesmo limite) ou um valor forjável.
"""
import hashlib

from django.conf import settings
from django.core.cache import cache

TENTATIVAS_POR_ORIGEM = 5
TENTATIVAS_GLOBAIS = 30
JANELA_EM_SEGUNDOS = 15 * 60

CHAVE_GLOBAL = "login-falhas:global"


def _origem(request):
    # Com N proxies confiáveis (settings.PROXIES_CONFIAVEIS) na frente, cada um
    # acrescenta ao fim de X-Forwarded-For o endereço que viu; o cliente é o
    # N-ésimo valor contado do fim, e os anteriores podem ser forjados por ele.
    # Com 0 (app alcançável sem proxy), o cabeçalho é ignorado: o cliente o controla.
    saltos = settings.PROXIES_CONFIAVEIS
    if saltos > 0:
        valores = [v.strip() for v in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
        valores = [v for v in valores if v]
        if valores:
            return valores[-saltos:][0]
    return request.META.get("REMOTE_ADDR", "")


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
