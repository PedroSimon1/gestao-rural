"""Rota de saúde para o health check da plataforma (Render): sem login e sem dado sensível."""
import logging

from django.db import Error
from django.http import JsonResponse
from django.views.decorators.http import require_safe

from .erros_banco import verificar_banco

logger = logging.getLogger(__name__)


@require_safe
def saude(request):
    """200 com o banco respondendo; 503 sem ele. Só o estado, nunca o erro do banco."""
    try:
        verificar_banco()
    except Error:
        logger.warning("Health check: o banco não está respondendo.")
        return JsonResponse({"status": "indisponivel"}, status=503)
    return JsonResponse({"status": "ok"})
