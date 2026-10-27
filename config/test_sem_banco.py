"""Garantias estruturais do banco na N2 - Etapa 2 (GR-33 e GR-34).

O banco (Supabase PostgreSQL) está configurado e a Etapa 2 vai acrescentar
models e migrations. Estes testes não proíbem banco: garantem que ele não
guarde o PDF, documentos nem a chave Gemini, que os testes sem banco não se
conectem e que os testes com banco nunca alcancem o banco de DB_*.

Os testes de fluxo da Etapa 1 são todos SimpleTestCase: neles qualquer
consulta ao banco faria o teste falhar.
"""

import copy
import os
from pathlib import Path
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, models
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState
from django.test import SimpleTestCase
from django.test.testcases import DatabaseOperationForbidden
from django.test.utils import isolate_apps

from config.banco_de_teste import (
    ExecutorDeTestes, conexao_de_teste, configuracao_do_banco_de_teste,
)

RAIZ = Path(settings.BASE_DIR)
PASTAS_DO_PROJETO = ("agents", "cadastros", "config", "documentos", "financeiro", "usuarios")

# O PDF é lido só durante a requisição: nenhum campo guarda arquivo ou bytes.
CAMPOS_DE_ARQUIVO = (models.FileField, models.FilePathField, models.BinaryField)
NOMES_DE_CAMPOS_PROIBIDOS = (
    "api_key", "apikey", "chave_api", "chave_gemini", "gemini", "token",
    "senha", "password", "secret", "segredo",
)

AMBIENTE_TESTE_VALIDO = {
    "DB_NAME": "postgres",
    "DB_TEST_HOST": "127.0.0.1",
    "DB_TEST_NAME": "test_gestao_rural",
    "DB_TEST_USER": "usuario-teste",
}


def sem_variaveis_db_test():
    """Ambiente sem DB_TEST_*, mesmo que o .env local as defina."""
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("DB_TEST_")}
    return mock.patch.dict(os.environ, ambiente, clear=True)


def arquivos_python_de_producao():
    for pasta in PASTAS_DO_PROJETO:
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            if not arquivo.name.startswith("test"):
                yield arquivo


def arquivos_de_migration():
    for pasta in PASTAS_DO_PROJETO:
        for diretorio in (RAIZ / pasta).rglob("migrations"):
            yield from diretorio.glob("[0-9]*.py")


def problemas_do_model(model):
    """Campos que guardariam arquivo, bytes ou segredo no banco."""
    problemas = []
    for campo in model._meta.get_fields():
        if isinstance(campo, CAMPOS_DE_ARQUIVO):
            problemas.append(f"{campo.name}: {type(campo).__name__}")
        if any(proibido in campo.name.lower() for proibido in NOMES_DE_CAMPOS_PROIBIDOS):
            problemas.append(f"{campo.name}: nome de segredo")
    return problemas


class SemBancoTests(SimpleTestCase):
    def test_banco_postgresql_e_sem_conexao_nos_testes_sem_banco(self):
        conexao = connections["default"]

        # TLS e demais padrões de DB_* ficam em test_producao (processo novo).
        self.assertEqual(list(settings.DATABASES), ["default"])
        self.assertEqual(conexao.settings_dict["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(conexao.settings_dict["CONN_MAX_AGE"], 0)
        # SimpleTestCase recusa qualquer conexão: nenhum teste sem banco alcança o Supabase.
        with self.assertRaises(DatabaseOperationForbidden):
            conexao.ensure_connection()

    def test_apps_que_dependem_de_banco_nao_estao_instalados(self):
        # Login da demonstração e sessão em cookie assinado (Etapa 1).
        for app in (
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "rest_framework",
        ):
            with self.subTest(app=app):
                self.assertNotIn(app, settings.INSTALLED_APPS)

    def test_middleware_sem_autenticacao_nem_mensagens(self):
        for middleware in settings.MIDDLEWARE:
            with self.subTest(middleware=middleware):
                self.assertNotIn("contrib.auth", middleware)
                self.assertNotIn("contrib.messages", middleware)

    def test_sessao_em_cookie_assinado(self):
        self.assertEqual(
            settings.SESSION_ENGINE, "django.contrib.sessions.backends.signed_cookies"
        )

    def test_codigo_de_producao_nao_grava_arquivos(self):
        for arquivo in arquivos_python_de_producao():
            codigo = arquivo.read_text()
            with self.subTest(arquivo=str(arquivo.relative_to(RAIZ))):
                for proibido in ("MEDIA_ROOT", "default_storage", "storage.save"):
                    self.assertNotIn(proibido, codigo)

    def test_banco_so_postgresql_por_variaveis_db(self):
        settings_py = (RAIZ / "config" / "settings.py").read_text()
        exemplo = (RAIZ / ".env.example").read_text()
        requisitos = (RAIZ / "requirements.txt").read_text().lower()

        for variavel in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            with self.subTest(variavel=variavel):
                self.assertIn(f'"{variavel}"', settings_py)
                self.assertRegex(exemplo, rf"(?m)^{variavel}=")
        # Segredos nunca têm valor de exemplo.
        for variavel in ("DB_HOST", "DB_USER", "DB_PASSWORD"):
            with self.subTest(variavel=variavel):
                self.assertRegex(exemplo, rf"(?m)^{variavel}=$")
        self.assertRegex(requisitos, r"(?m)^psycopg\[binary\]==\d")
        for nome, texto in (("config/settings.py", settings_py), (".env.example", exemplo),
                            ("requirements.txt", requisitos)):
            with self.subTest(arquivo=nome):
                for proibido in ("sqlite", "DATABASE_URL", "dj-database-url",
                                 "djangorestframework", "supabase-py"):
                    self.assertNotIn(proibido, texto)

    def test_sem_armazenamento_de_media(self):
        self.assertEqual(settings.MEDIA_ROOT, "")
        self.assertNotIn("MEDIA_", (RAIZ / "config" / "settings.py").read_text())
        self.assertNotIn("media", (RAIZ / "config" / "urls.py").read_text())


class ModelsTests(SimpleTestCase):
    def test_models_nao_guardam_pdf_nem_segredos(self):
        for model in apps.get_models():
            with self.subTest(model=model._meta.label):
                self.assertEqual(problemas_do_model(model), [])

    @isolate_apps("documentos")
    def test_a_verificacao_detecta_arquivo_bytes_e_chave(self):
        class Proibido(models.Model):
            arquivo = models.FileField()
            conteudo = models.BinaryField()
            gemini_api_key = models.CharField(max_length=100)

            class Meta:
                app_label = "documentos"

        class Permitido(models.Model):
            # Chave de acesso da NF-e é dado do documento, não segredo.
            chave_acesso = models.CharField(max_length=44)
            valor_total = models.DecimalField(max_digits=12, decimal_places=2)

            class Meta:
                app_label = "documentos"

        self.assertEqual(problemas_do_model(Proibido), [
            "arquivo: FileField", "conteudo: BinaryField", "gemini_api_key: nome de segredo",
        ])
        self.assertEqual(problemas_do_model(Permitido), [])


class MigrationsTests(SimpleTestCase):
    def test_nenhuma_alteracao_de_model_sem_migration(self):
        # Mesmo cálculo do makemigrations, sem conexão com o banco. Os apps do
        # projeto são informados para que um app ainda sem pasta migrations
        # também acuse a migration inicial que falta.
        apps_do_projeto = {
            config.label for config in apps.get_app_configs()
            if Path(config.path).is_relative_to(RAIZ)
        }
        loader = MigrationLoader(None, ignore_no_migrations=True)
        mudancas = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
            NonInteractiveMigrationQuestioner(specified_apps=apps_do_projeto),
        ).changes(graph=loader.graph)

        self.assertEqual(mudancas, {}, "rode makemigrations e versione as migrations")

    def test_historico_de_migrations_sem_conflitos(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)

        self.assertEqual(loader.detect_conflicts(), {})

    def test_pastas_de_migrations_sao_pacotes(self):
        # Sem __init__.py, o Django ignora a pasta sem avisar.
        for pasta in PASTAS_DO_PROJETO:
            for diretorio in (RAIZ / pasta).rglob("migrations"):
                with self.subTest(pasta=str(diretorio.relative_to(RAIZ))):
                    self.assertTrue((diretorio / "__init__.py").is_file())

    def test_migrations_nao_criam_campos_de_arquivo(self):
        for arquivo in arquivos_de_migration():
            codigo = arquivo.read_text()
            with self.subTest(arquivo=str(arquivo.relative_to(RAIZ))):
                for proibido in ("FileField", "ImageField", "FilePathField", "BinaryField"):
                    self.assertNotIn(proibido, codigo)


class BancoDeTesteTests(SimpleTestCase):
    def test_executor_de_testes_protegido(self):
        self.assertEqual(settings.TEST_RUNNER, "config.banco_de_teste.ExecutorDeTestes")

    def test_configuracao_local_valida(self):
        configuracao = configuracao_do_banco_de_teste(AMBIENTE_TESTE_VALIDO)

        self.assertEqual(configuracao["HOST"], "127.0.0.1")
        self.assertEqual(configuracao["PORT"], "5432")
        self.assertEqual(configuracao["NAME"], "test_gestao_rural")
        self.assertEqual(configuracao["PASSWORD"], "")
        self.assertEqual(configuracao["CONN_MAX_AGE"], 0)
        self.assertEqual(configuracao["OPTIONS"], {"sslmode": "prefer", "connect_timeout": 10})

    def test_hosts_locais_aceitos(self):
        for host in ("localhost", "127.0.0.1", "::1"):
            with self.subTest(host=host):
                configuracao = configuracao_do_banco_de_teste(
                    {**AMBIENTE_TESTE_VALIDO, "DB_TEST_HOST": f" {host} "}
                )
                self.assertEqual(configuracao["HOST"], host)

    def test_socket_unix_conforme_plataforma(self):
        # Caminho Unix so e local onde o sistema o reconhece como absoluto.
        # No Windows, recusa-lo preserva a protecao do runner.
        host = "/var/run/postgresql"
        ambiente = {**AMBIENTE_TESTE_VALIDO, "DB_TEST_HOST": host}
        if os.name == "nt":
            with self.assertRaisesMessage(ImproperlyConfigured, "DB_TEST_HOST"):
                configuracao_do_banco_de_teste(ambiente)
        else:
            self.assertEqual(configuracao_do_banco_de_teste(ambiente)["HOST"], host)

    def test_sem_variaveis_db_test_nao_ha_banco_substituto(self):
        for variavel in ("DB_TEST_HOST", "DB_TEST_NAME", "DB_TEST_USER"):
            with self.subTest(variavel=variavel):
                with self.assertRaisesMessage(ImproperlyConfigured, variavel):
                    configuracao_do_banco_de_teste({**AMBIENTE_TESTE_VALIDO, variavel: " "})
        # As variáveis DB_* (homologação) nunca são usadas no lugar.
        with self.assertRaises(ImproperlyConfigured):
            configuracao_do_banco_de_teste({
                "DB_HOST": "aws-0-regiao.pooler.supabase.com", "DB_NAME": "postgres",
                "DB_USER": "postgres.projeto", "DB_PASSWORD": "senha",
            })

    def test_host_remoto_recusado(self):
        for host in ("aws-0-regiao.pooler.supabase.com", "db.projeto.supabase.co",
                     "10.0.0.5", "localhost.exemplo.com", "relativo/socket",
                     "/run/postgresql,db.projeto.supabase.co", "localhost,10.0.0.5",
                     "/tmp host=db.projeto.supabase.co", "[::1]"):
            with self.subTest(host=host):
                with self.assertRaisesMessage(ImproperlyConfigured, "DB_TEST_HOST"):
                    configuracao_do_banco_de_teste({**AMBIENTE_TESTE_VALIDO, "DB_TEST_HOST": host})

    def test_nome_sem_prefixo_ou_igual_ao_da_aplicacao_recusado(self):
        for nome in ("postgres", "gestao_rural", "test_", "teste_gestao"):
            with self.subTest(nome=nome):
                with self.assertRaisesMessage(ImproperlyConfigured, "DB_TEST_NAME"):
                    configuracao_do_banco_de_teste({**AMBIENTE_TESTE_VALIDO, "DB_TEST_NAME": nome})
        with self.assertRaisesMessage(ImproperlyConfigured, "diferente de DB_NAME"):
            configuracao_do_banco_de_teste(
                {**AMBIENTE_TESTE_VALIDO, "DB_NAME": "test_gestao_rural"}
            )

    def test_variaveis_do_libpq_que_redirecionam_recusadas(self):
        for variavel in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"):
            with self.subTest(variavel=variavel):
                with self.assertRaisesMessage(ImproperlyConfigured, variavel):
                    configuracao_do_banco_de_teste({**AMBIENTE_TESTE_VALIDO, variavel: "x"})

    def test_conexao_de_teste_troca_o_destino_e_preserva_o_resto(self):
        original = copy.deepcopy(connections["default"].settings_dict)

        local = conexao_de_teste(original, AMBIENTE_TESTE_VALIDO)

        self.assertEqual(original, connections["default"].settings_dict)
        self.assertEqual(local["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((local["HOST"], local["NAME"], local["USER"], local["PASSWORD"]),
                         ("127.0.0.1", "test_gestao_rural", "usuario-teste", ""))
        self.assertEqual(local["OPTIONS"], {"sslmode": "prefer", "connect_timeout": 10})
        # Chaves que o Django lê sem valor padrão ao criar o banco de teste.
        self.assertEqual(local["TEST"], {**original["TEST"], "NAME": "test_gestao_rural"})
        for chave in ("MIRROR", "MIGRATE", "CHARSET", "COLLATION"):
            self.assertIn(chave, local["TEST"])
        for chave in ("ATOMIC_REQUESTS", "AUTOCOMMIT", "TIME_ZONE"):
            self.assertEqual(local[chave], original[chave])

    def test_timeout_invalido_recusado(self):
        for timeout in ("abc", "0", "-1"):
            with self.subTest(timeout=timeout):
                with self.assertRaisesMessage(ImproperlyConfigured, "DB_TEST_CONNECT_TIMEOUT"):
                    configuracao_do_banco_de_teste(
                        {**AMBIENTE_TESTE_VALIDO, "DB_TEST_CONNECT_TIMEOUT": timeout}
                    )

    def test_executor_para_antes_de_conectar_sem_db_test(self):
        with sem_variaveis_db_test():
            antes = dict(connections["default"].settings_dict)
            with self.assertRaises(ImproperlyConfigured):
                ExecutorDeTestes(verbosity=0).setup_databases(aliases={"default"})

        self.assertEqual(dict(connections["default"].settings_dict), antes)

    def test_executor_sem_testes_de_banco_nao_exige_db_test(self):
        with sem_variaveis_db_test():
            self.assertEqual(ExecutorDeTestes(verbosity=0).setup_databases(aliases=set()), [])

    def conexoes_falsas(self):
        """Conexões simuladas com destino remoto: nada real é fechado ou alterado."""
        remota = {**copy.deepcopy(connections["default"].settings_dict),
                  "HOST": "banco-remoto.invalid", "NAME": "postgres"}
        falsa = mock.Mock(settings_dict=remota)
        return {"default": falsa}, falsa

    def test_executor_sem_aliases_para_antes_de_conectar_sem_db_test(self):
        falsas, falsa = self.conexoes_falsas()
        with sem_variaveis_db_test(), \
                mock.patch("config.banco_de_teste.connections", falsas), \
                mock.patch("django.test.runner.DiscoverRunner.setup_databases") as criar:
            with self.assertRaises(ImproperlyConfigured):
                ExecutorDeTestes(verbosity=0).setup_databases()

        criar.assert_not_called()
        falsa.close.assert_not_called()
        self.assertEqual(falsa.settings_dict["HOST"], "banco-remoto.invalid")

    def test_executor_sem_aliases_troca_todas_as_conexoes_para_o_banco_local(self):
        falsas, falsa = self.conexoes_falsas()
        destinos = []

        def criar(**kwargs):
            destinos.append((kwargs["aliases"], falsa.settings_dict["HOST"],
                             falsa.settings_dict["NAME"], falsa.close.called))
            return []

        with mock.patch.dict(os.environ, AMBIENTE_TESTE_VALIDO), \
                mock.patch("config.banco_de_teste.connections", falsas), \
                mock.patch("django.test.runner.DiscoverRunner.setup_databases",
                           side_effect=criar):
            ExecutorDeTestes(verbosity=0).setup_databases()

        self.assertEqual(destinos, [({"default"}, "127.0.0.1", "test_gestao_rural", True)])
