"""Banco dos testes automatizados, separado do banco da aplicação (GR-34).

Os testes que usam banco (TestCase, TransactionTestCase) nunca usam as
variáveis DB_*, que podem apontar para o Supabase de homologação. Eles exigem
as variáveis DB_TEST_*, que só aceitam um PostgreSQL local, e o nome do banco
precisa começar com "test_": com --noinput, o Django apaga sem perguntar um
banco de teste que já existe. Sem configuração válida, a execução para antes
de abrir qualquer conexão; não há banco substituto.

Testes que não usam banco (SimpleTestCase) não dependem de nada disso.

setup_databases() chamado sem aliases (fora do `manage.py test`) também troca
todas as conexões para o banco local antes de conectar: em 27/10/2026, um
script auxiliar que fez essa chamada criou um banco de teste no servidor de
DB_* (ContextoProjeto.md, 15.1.20 e 15.1.21).
"""

import os

from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.test.runner import DiscoverRunner

# Loopback ou diretório do socket Unix (caminho absoluto, ex.: /run/postgresql).
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
PREFIXO_DO_NOME = "test_"
# Variáveis do libpq que redirecionariam a conexão para outro endereço.
VARIAVEIS_LIBPQ_PROIBIDAS = ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")


def configuracao_do_banco_de_teste(ambiente):
    """Conexão do banco de teste a partir das variáveis DB_TEST_* de `ambiente`."""
    valor = {
        nome: (ambiente.get(f"DB_TEST_{nome}") or "").strip()
        for nome in ("HOST", "PORT", "NAME", "USER", "PASSWORD", "CONNECT_TIMEOUT")
    }

    faltando = [f"DB_TEST_{nome}" for nome in ("HOST", "NAME", "USER") if not valor[nome]]
    if faltando:
        raise ImproperlyConfigured(
            "Testes com banco exigem um PostgreSQL local de teste. "
            "Variáveis ausentes: " + ", ".join(faltando)
        )
    # Vírgula e espaço recusados: o libpq aceita vários hosts em um só valor.
    host_local = valor["HOST"] in HOSTS_LOCAIS or (
        os.path.isabs(valor["HOST"]) and not any(c in valor["HOST"] for c in ", \t")
    )
    if not host_local:
        raise ImproperlyConfigured(
            "DB_TEST_HOST deve ser local (localhost, 127.0.0.1, ::1 ou o diretório "
            "do socket do PostgreSQL). Bancos remotos não são usados nos testes."
        )
    if not valor["NAME"].startswith(PREFIXO_DO_NOME) or valor["NAME"] == PREFIXO_DO_NOME:
        raise ImproperlyConfigured(
            f'DB_TEST_NAME deve começar com "{PREFIXO_DO_NOME}": o banco é criado e '
            "apagado a cada execução dos testes."
        )
    if valor["NAME"] == (ambiente.get("DB_NAME") or "").strip():
        raise ImproperlyConfigured("DB_TEST_NAME deve ser diferente de DB_NAME.")
    definidas = [nome for nome in VARIAVEIS_LIBPQ_PROIBIDAS if ambiente.get(nome)]
    if definidas:
        raise ImproperlyConfigured(
            "Remova do ambiente antes de rodar os testes com banco: " + ", ".join(definidas)
        )

    timeout = valor["CONNECT_TIMEOUT"] or "10"
    if not timeout.isdigit() or int(timeout) < 1:
        raise ImproperlyConfigured(
            "DB_TEST_CONNECT_TIMEOUT deve ser um inteiro positivo (segundos)."
        )

    return {
        "HOST": valor["HOST"],
        "PORT": valor["PORT"] or "5432",
        "NAME": valor["NAME"],
        "USER": valor["USER"],
        "PASSWORD": valor["PASSWORD"],
        "CONN_MAX_AGE": 0,
        # Conexão local: TLS se o servidor oferecer (no socket Unix não se aplica).
        "OPTIONS": {"sslmode": "prefer", "connect_timeout": int(timeout)},
    }


def conexao_de_teste(settings_dict, ambiente):
    """settings_dict da conexão com o banco local no lugar do de DB_*."""
    configuracao = configuracao_do_banco_de_teste(ambiente)
    # TEST mantém as chaves que o Django preenche (MIRROR, MIGRATE, CHARSET...).
    teste = {**settings_dict.get("TEST", {}), "NAME": configuracao["NAME"]}
    return {**settings_dict, **configuracao, "TEST": teste}


class ExecutorDeTestes(DiscoverRunner):
    """DiscoverRunner que só cria banco de teste no PostgreSQL local de DB_TEST_*."""

    def setup_databases(self, **kwargs):
        aliases = kwargs.get("aliases")
        if aliases is None:
            # Chamada sem aliases (script auxiliar, por exemplo): o Django
            # prepararia todas as conexões com as DB_*, que podem ser remotas.
            # Todas passam pelo banco local; sem DB_TEST_* válidas, para aqui.
            aliases = kwargs["aliases"] = set(connections)
        if aliases:
            for alias in aliases:
                conexao = connections[alias]
                # Valida tudo antes de alterar; close() garante que a próxima
                # conexão já use o banco local.
                local = conexao_de_teste(conexao.settings_dict, os.environ)
                conexao.close()
                conexao.settings_dict.update(local)
        return super().setup_databases(**kwargs)
