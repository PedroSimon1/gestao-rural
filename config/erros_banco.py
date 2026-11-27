"""Falha do banco durante uma tela: mensagem em português, resposta 503 e checagem prévia."""
import logging
from functools import wraps

from django.db import Error, connection
from django.shortcuts import render

logger = logging.getLogger(__name__)


def mensagem_de_banco(acao, orientacao="Tente novamente em instantes."):
    """Texto único para qualquer tela cujo banco não respondeu (ex.: projeto do Supabase pausado).

    `acao` completa "Não foi possível ... agora"; `orientacao` diz o que fazer em seguida.
    Nunca recebe o erro original, que pode trazer SQL ou dados pessoais.
    """
    return (
        f"Não foi possível {acao} agora: o banco de dados não está respondendo. {orientacao} "
        "Se o problema continuar, avise o responsável pelo sistema."
    )


def verificar_banco():
    """Levanta django.db.Error se o banco não responde (um SELECT 1).

    Usada antes de gastar a chamada ao Gemini e a chave do usuário num processamento
    cujo resultado não poderia ser guardado, e pela rota /saude/.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


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
