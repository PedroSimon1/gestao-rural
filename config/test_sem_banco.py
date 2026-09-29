"""Garantias estruturais do MVP stateless da N2 - Etapa 1: nenhum banco de dados.

Complementa os testes de fluxo, que são todos SimpleTestCase: neles qualquer
consulta ao banco faria o teste falhar.
"""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)
PASTAS_DO_PROJETO = ("agents", "config", "documentos", "usuarios")


def arquivos_python_de_producao():
    for pasta in PASTAS_DO_PROJETO:
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            if not arquivo.name.startswith("test"):
                yield arquivo


class SemBancoTests(SimpleTestCase):
    def test_nenhum_banco_configurado(self):
        conexao = connections["default"]

        self.assertEqual(conexao.settings_dict["ENGINE"], "django.db.backends.dummy")
        # O backend dummy recusa qualquer conexão.
        with self.assertRaises(ImproperlyConfigured):
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
            with self.subTest(arquivo=str(arquivo.relative_to(RAIZ))):
                for proibido in ("django.db", ".objects.", "MEDIA_ROOT", "default_storage", "storage.save"):
                    self.assertNotIn(proibido, codigo)

    def test_sem_variaveis_de_banco_nem_postgresql(self):
        textos = {
            "config/settings.py": (RAIZ / "config" / "settings.py").read_text(),
            ".env.example": (RAIZ / ".env.example").read_text(),
            "requirements.txt": (RAIZ / "requirements.txt").read_text().lower(),
        }
        for nome, texto in textos.items():
            with self.subTest(arquivo=nome):
                for proibido in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT",
                                 "postgresql", "psycopg", "sqlite", "djangorestframework"):
                    self.assertNotIn(proibido, texto)

    def test_sem_armazenamento_de_media(self):
        self.assertEqual(settings.MEDIA_ROOT, "")
        self.assertNotIn("MEDIA_", (RAIZ / "config" / "settings.py").read_text())
        self.assertNotIn("media", (RAIZ / "config" / "urls.py").read_text())
