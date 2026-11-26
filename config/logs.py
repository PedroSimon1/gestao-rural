"""Formatação de logs que não vaza dados pelas exceções."""
import logging
import traceback


class FormatadorSemMensagemDaExcecao(logging.Formatter):
    """Imprime o rastreio e o tipo da exceção, sem a mensagem dela.

    A mensagem de uma exceção pode carregar SQL, valores de colunas (CPF/CNPJ,
    valores financeiros) ou trechos de resposta de terceiros. O rastreio traz só
    arquivos, linhas e o código-fonte; variáveis locais não entram.
    """

    def formatException(self, exc_info):
        tipo, _, rastreio = exc_info
        return "Rastreio (mensagem omitida):\n" + "".join(traceback.format_tb(rastreio)) + tipo.__qualname__
