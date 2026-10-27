"""Evita armazenamento de respostas dinâmicas com dados da demonstração."""
from django.utils.cache import add_never_cache_headers


class RespostasPrivadasMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        # WhiteNoise atende estáticos antes deste middleware. As respostas
        # dinâmicas, inclusive redirects e erros, não devem ficar em cache.
        add_never_cache_headers(resposta)
        return resposta
