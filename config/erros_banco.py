"""Resposta 503 em português quando o banco falha durante uma tela."""
import logging
from functools import wraps

from django.db import Error
from django.shortcuts import render

logger = logging.getLogger(__name__)


def erros_de_banco(template, mensagem):
    """Decorador de view: falha do banco renderiza `template` com `erro=mensagem` (503).

    A falha pode vir da consulta, de uma gravação ou da renderização de um
    seletor preguiçoso. Nada do erro original chega ao usuário nem ao log
    (pode conter SQL ou dados pessoais); o log só registra a view afetada.
    Erros de validação e `IntegrityError` tratados dentro da view continuam
    como estão, pois são capturados antes de chegar aqui.
    """

    def decorador(view):
        @wraps(view)
        def protegida(request, *args, **kwargs):
            try:
                return view(request, *args, **kwargs)
            except Error:
                logger.warning("Falha do banco na view %s.", view.__name__)
                return render(request, template, {"erro": mensagem}, status=503)

        return protegida

    return decorador
