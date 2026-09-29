"""Configuração de produção (Render): hosts, CSRF, HTTPS, cookies e static.

settings.py é avaliado no import. Por isso cada cenário roda em um processo
Python novo, com as variáveis de ambiente controladas. Todas as variáveis que
o settings lê são definidas explicitamente (vazias quando for o caso): o
load_dotenv() não sobrescreve variáveis já presentes, então o .env local não
interfere no cenário.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)

# Valores fictícios, só para os subprocessos.
SECRET_TESTE = "chave-de-teste-producao-" + "x9Q2m7Lk4Rt8Vw1Zp6Hs3Jd5Nb0Fc" * 2

AMBIENTE_BASE = {
    "DJANGO_SECRET_KEY": SECRET_TESTE,
    "DJANGO_DEBUG": "False",
    "DJANGO_ALLOWED_HOSTS": "",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "",
    "RENDER_EXTERNAL_HOSTNAME": "",
    "DEMO_LOGIN": "login-ficticio",
    "DEMO_PASSWORD": "senha-ficticia",
    "GEMINI_MODEL": "modelo-teste",
}

SCRIPT_SETTINGS = """
import json
import django
from django.conf import settings
django.setup()
from django.db import connections
print(json.dumps({
    "DEBUG": settings.DEBUG,
    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    "CSRF_TRUSTED_ORIGINS": settings.CSRF_TRUSTED_ORIGINS,
    "SECURE_PROXY_SSL_HEADER": list(settings.SECURE_PROXY_SSL_HEADER),
    "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,
    "SESSION_COOKIE_HTTPONLY": settings.SESSION_COOKIE_HTTPONLY,
    "CSRF_COOKIE_SECURE": settings.CSRF_COOKIE_SECURE,
    "STATIC_ROOT": str(settings.STATIC_ROOT),
    "STORAGES": settings.STORAGES,
    "DATABASE_ENGINE": connections["default"].settings_dict["ENGINE"],
    "TEM_GEMINI_API_KEY": hasattr(settings, "GEMINI_API_KEY"),
}))
"""


def ambiente(**alteracoes):
    env = {
        chave: valor for chave, valor in os.environ.items()
        if chave not in {"DATABASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
    }
    env.update(AMBIENTE_BASE)
    env.update(alteracoes)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    return env


def executar(argumentos, **alteracoes):
    return subprocess.run(
        [sys.executable, "-B", *argumentos],
        cwd=RAIZ,
        env=ambiente(**alteracoes),
        capture_output=True,
        text=True,
        timeout=60,
    )


def settings_com(**alteracoes):
    processo = executar(["-c", SCRIPT_SETTINGS], **alteracoes)
    if processo.returncode != 0:
        raise AssertionError(processo.stderr)
    return json.loads(processo.stdout)


class HostsECsrfTests(SimpleTestCase):
    def test_render_external_hostname_entra_em_allowed_hosts_e_csrf(self):
        config = settings_com(RENDER_EXTERNAL_HOSTNAME="app-teste.onrender.com")

        self.assertEqual(config["ALLOWED_HOSTS"], ["app-teste.onrender.com"])
        self.assertEqual(config["CSRF_TRUSTED_ORIGINS"], ["https://app-teste.onrender.com"])

    def test_varios_hosts_com_espacos_itens_vazios_e_duplicados(self):
        config = settings_com(
            DJANGO_ALLOWED_HOSTS=" localhost, 127.0.0.1,,app-teste.onrender.com , localhost ",
            RENDER_EXTERNAL_HOSTNAME=" app-teste.onrender.com ",
        )

        self.assertEqual(
            config["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "app-teste.onrender.com"]
        )

    def test_varias_origens_csrf_sem_duplicar_a_do_render(self):
        config = settings_com(
            DJANGO_CSRF_TRUSTED_ORIGINS="https://exemplo.com.br, ,https://app-teste.onrender.com",
            RENDER_EXTERNAL_HOSTNAME="app-teste.onrender.com",
        )

        self.assertEqual(
            config["CSRF_TRUSTED_ORIGINS"],
            ["https://exemplo.com.br", "https://app-teste.onrender.com"],
        )

    def test_sem_variaveis_as_listas_ficam_vazias(self):
        config = settings_com()

        self.assertEqual(config["ALLOWED_HOSTS"], [])
        self.assertEqual(config["CSRF_TRUSTED_ORIGINS"], [])

    def test_nenhum_dominio_fixo_no_settings(self):
        codigo = (RAIZ / "config" / "settings.py").read_text()

        self.assertNotIn("onrender.com", codigo)


class HttpsECookiesTests(SimpleTestCase):
    def test_proxy_https_do_render(self):
        config = settings_com()

        self.assertEqual(config["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_cookies_seguros_em_producao(self):
        config = settings_com(DJANGO_DEBUG="False")

        self.assertIs(config["DEBUG"], False)
        self.assertIs(config["SESSION_COOKIE_SECURE"], True)
        self.assertIs(config["CSRF_COOKIE_SECURE"], True)
        self.assertIs(config["SESSION_COOKIE_HTTPONLY"], True)

    def test_cookies_nao_quebram_o_desenvolvimento(self):
        config = settings_com(DJANGO_DEBUG="True")

        self.assertIs(config["DEBUG"], True)
        self.assertIs(config["SESSION_COOKIE_SECURE"], False)
        self.assertIs(config["CSRF_COOKIE_SECURE"], False)
        self.assertIs(config["SESSION_COOKIE_HTTPONLY"], True)


class ArquivosEstaticosTests(SimpleTestCase):
    def test_whitenoise_logo_apos_o_security_middleware(self):
        self.assertEqual(
            settings.MIDDLEWARE[:2],
            [
                "django.middleware.security.SecurityMiddleware",
                "whitenoise.middleware.WhiteNoiseMiddleware",
            ],
        )

    def test_static_root_configurado_e_nao_versionado(self):
        self.assertEqual(Path(settings.STATIC_ROOT), RAIZ / "staticfiles")
        ignorados = (RAIZ / ".gitignore").read_text().splitlines()
        self.assertIn("staticfiles/", ignorados)

    def test_storage_de_producao_e_de_desenvolvimento(self):
        casos = (
            ("False", "whitenoise.storage.CompressedManifestStaticFilesStorage"),
            ("True", "django.contrib.staticfiles.storage.StaticFilesStorage"),
        )
        for debug, backend in casos:
            with self.subTest(debug=debug):
                storages = settings_com(DJANGO_DEBUG=debug)["STORAGES"]

                self.assertEqual(storages["staticfiles"]["BACKEND"], backend)
                self.assertEqual(
                    storages["default"]["BACKEND"], "django.core.files.storage.FileSystemStorage"
                )


class SemBancoNemChaveEmProducaoTests(SimpleTestCase):
    def test_producao_sem_banco_sem_database_url_e_sem_gemini_api_key(self):
        config = settings_com(RENDER_EXTERNAL_HOSTNAME="app-teste.onrender.com")

        self.assertEqual(config["DATABASE_ENGINE"], "django.db.backends.dummy")
        self.assertIs(config["TEM_GEMINI_API_KEY"], False)

    def test_check_deploy_so_com_avisos_delegados_ao_render(self):
        processo = executar(
            ["manage.py", "check", "--deploy"],
            RENDER_EXTERNAL_HOSTNAME="app-teste.onrender.com",
        )
        saida = processo.stdout + processo.stderr

        self.assertEqual(processo.returncode, 0, saida)
        # HSTS e redirecionamento HTTPS são decisões delegadas à plataforma.
        self.assertEqual(sorted(set(re.findall(r"security\.W\d{3}", saida))),
                         ["security.W004", "security.W008"])


class ScriptsDeDeployTests(SimpleTestCase):
    def ler(self, nome):
        return (RAIZ / nome).read_text()

    def test_scripts_existem_e_sao_executaveis(self):
        for nome in ("build.sh", "start.sh"):
            with self.subTest(nome=nome):
                self.assertTrue(os.access(RAIZ / nome, os.X_OK))
                self.assertTrue(self.ler(nome).startswith("#!/usr/bin/env bash\n"))
                self.assertIn("set -o errexit", self.ler(nome))

    def comandos(self, nome):
        """Linhas do script sem comentários."""
        return "\n".join(
            linha for linha in self.ler(nome).splitlines() if not linha.lstrip().startswith("#")
        )

    def test_build_coleta_static_sem_comandos_de_banco(self):
        build = self.comandos("build.sh")

        self.assertIn("pip install -r requirements.txt", build)
        self.assertIn("collectstatic --noinput", build)
        for proibido in ("migrate", "makemigrations", "createsuperuser", "loaddata", "flush"):
            self.assertNotIn(proibido, build)

    def test_start_usa_gunicorn_na_porta_do_render(self):
        start = self.comandos("start.sh")

        self.assertIn("gunicorn config.wsgi:application", start)
        self.assertIn('--bind "0.0.0.0:${PORT:-8000}"', start)
        self.assertIn('--workers "${WEB_CONCURRENCY:-1}"', start)
        self.assertIn('--timeout "${GUNICORN_TIMEOUT:-420}"', start)
        self.assertNotIn("runserver", start)

    def test_versao_do_python_fixada(self):
        versao = self.ler(".python-version").strip()

        self.assertRegex(versao, r"^3\.\d+\.\d+$")
        self.assertGreaterEqual(tuple(map(int, versao.split(".")[:2])), (3, 12))  # Django 6.1

    def test_dependencias_de_producao_fixadas_e_sem_banco(self):
        requisitos = self.ler("requirements.txt").lower()

        self.assertRegex(requisitos, r"(?m)^gunicorn==\d")
        self.assertRegex(requisitos, r"(?m)^whitenoise==\d")
        for proibido in ("uvicorn", "psycopg", "dj-database-url", "celery", "redis"):
            self.assertNotIn(proibido, requisitos)

    def test_env_example_sem_chave_gemini_nem_banco(self):
        exemplo = self.ler(".env.example")

        for variavel in ("DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_TRUSTED_ORIGINS", "GUNICORN_TIMEOUT"):
            self.assertRegex(exemplo, rf"(?m)^{variavel}=")
        for proibido in ("GEMINI_API_KEY=", "DATABASE_URL", "onrender.com", "\nPORT="):
            self.assertNotIn(proibido, exemplo)
        for variavel in ("DJANGO_SECRET_KEY", "DEMO_LOGIN", "DEMO_PASSWORD"):
            self.assertRegex(exemplo, rf"(?m)^{variavel}=$")
