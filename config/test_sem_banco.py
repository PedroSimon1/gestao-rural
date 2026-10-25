"""Garantias estruturais do MVP da N2 - Etapa 1 com o PostgreSQL da GR-33.

O banco (Supabase PostgreSQL) está configurado, mas ainda não há models,
migrations nem código que o use. Os testes de fluxo são todos SimpleTestCase:
neles qualquer consulta ao banco faria o teste falhar.
"""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import connections
from django.test import SimpleTestCase
from django.test.testcases import DatabaseOperationForbidden

RAIZ = Path(settings.BASE_DIR)
PASTAS_DO_PROJETO = ("agents", "config", "documentos", "usuarios")


def arquivos_python_de_producao():
    for pasta in PASTAS_DO_PROJETO:
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            if not arquivo.name.startswith("test"):
                yield arquivo


class SemBancoTests(SimpleTestCase):
    def test_banco_postgresql_com_tls_e_sem_conexao_nos_testes(self):
        conexao = connections["default"]

        self.assertEqual(list(settings.DATABASES), ["default"])
        self.assertEqual(conexao.settings_dict["ENGINE"], "django.db.backends.postgresql")
        self.assertIn(conexao.settings_dict["OPTIONS"]["sslmode"],
                      {"require", "verify-ca", "verify-full"})
        self.assertEqual(conexao.settings_dict["CONN_MAX_AGE"], 0)
        # SimpleTestCase recusa qualquer conexão: nenhum teste alcança o Supabase.
        with self.assertRaises(DatabaseOperationForbidden):
            conexao.ensure_connection()

    def test_nenhum_model_registrado(self):
        self.assertEqual(apps.get_models(), [])

    def test_apps_que_dependem_de_banco_nao_estao_instalados(self):
        for app in (
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "rest_framework",
            "financeiro",
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

    def test_sem_migrations_nem_app_financeiro(self):
        self.assertFalse((RAIZ / "financeiro").exists())
        for pasta in PASTAS_DO_PROJETO:
            with self.subTest(pasta=pasta):
                self.assertEqual(list((RAIZ / pasta).rglob("migrations")), [])

    def test_codigo_de_producao_nao_usa_banco(self):
        for arquivo in arquivos_python_de_producao():
            codigo = arquivo.read_text()
            if arquivo == RAIZ / "config" / "settings.py":
                # Única referência permitida: o backend PostgreSQL do DATABASES.
                codigo = codigo.replace('"django.db.backends.postgresql"', "", 1)
            with self.subTest(arquivo=str(arquivo.relative_to(RAIZ))):
                for proibido in ("django.db", ".objects.", "MEDIA_ROOT", "default_storage", "storage.save"):
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
