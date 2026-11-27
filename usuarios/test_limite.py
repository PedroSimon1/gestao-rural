"""Limite de tentativas de login, vida da sessão e senha curta (auditoria M-01)."""
import time
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from . import limite
from .checks import senha_da_demonstracao_curta
from .testing import CREDENCIAIS_TESTE
from .tests import LOGIN, SENHA, LoginDemo
from .views import MENSAGEM_CREDENCIAIS_INVALIDAS, MENSAGEM_MUITAS_TENTATIVAS


@override_settings(**CREDENCIAIS_TESTE)
class LimiteDeTentativasTests(LoginDemo, SimpleTestCase):
    def errar(self, vezes, **extra):
        for _ in range(vezes):
            resposta = self.client.post(self.url_login, {"login": LOGIN, "senha": "errada"}, **extra)
            self.assertContains(resposta, MENSAGEM_CREDENCIAIS_INVALIDAS)

    def test_depois_do_teto_ate_a_senha_certa_e_recusada(self):
        self.errar(limite.TENTATIVAS_POR_ORIGEM)

        resposta = self.entrar()

        self.assertEqual(resposta.status_code, 429)
        self.assertContains(resposta, MENSAGEM_MUITAS_TENTATIVAS, status_code=429)
        self.assertFalse(self.autenticado())

    def test_ate_o_teto_a_senha_certa_ainda_entra(self):
        self.errar(limite.TENTATIVAS_POR_ORIGEM - 1)

        self.assertEqual(self.entrar().status_code, 302)
        self.assertTrue(self.autenticado())

    def test_login_certo_zera_as_falhas_da_origem(self):
        self.errar(limite.TENTATIVAS_POR_ORIGEM - 1)
        self.entrar()
        self.client.cookies.clear()  # sai sem tocar no banco (SimpleTestCase)

        self.errar(limite.TENTATIVAS_POR_ORIGEM - 1)

        self.assertEqual(self.entrar().status_code, 302)

    def test_bloqueio_acaba_com_a_janela(self):
        self.errar(limite.TENTATIVAS_POR_ORIGEM)
        self.assertEqual(self.entrar().status_code, 429)

        depois = time.time() + limite.JANELA_EM_SEGUNDOS + 1
        with mock.patch("time.time", return_value=depois):
            resposta = self.entrar()

        self.assertEqual(resposta.status_code, 302)

    def test_outra_origem_nao_e_bloqueada(self):
        self.errar(limite.TENTATIVAS_POR_ORIGEM, HTTP_X_FORWARDED_FOR="203.0.113.1")

        bloqueada = self.entrar_de("203.0.113.1")
        livre = self.entrar_de("203.0.113.2")

        self.assertEqual(bloqueada.status_code, 429)
        self.assertEqual(livre.status_code, 302)

    def test_valores_forjados_no_inicio_do_cabecalho_nao_contornam_o_limite(self):
        for i in range(limite.TENTATIVAS_POR_ORIGEM):
            self.client.post(
                self.url_login, {"login": LOGIN, "senha": "errada"},
                HTTP_X_FORWARDED_FOR=f"198.51.100.{i}, 203.0.113.9",
            )

        resposta = self.client.post(
            self.url_login, {"login": LOGIN, "senha": SENHA},
            HTTP_X_FORWARDED_FOR="198.51.100.99, 203.0.113.9",
        )

        self.assertEqual(resposta.status_code, 429)

    def test_teto_global_bloqueia_ate_origem_nova(self):
        for i in range(limite.TENTATIVAS_GLOBAIS):
            self.client.post(
                self.url_login, {"login": LOGIN, "senha": "errada"},
                HTTP_X_FORWARDED_FOR=f"192.0.2.{i}",
            )

        self.assertEqual(self.entrar_de("203.0.113.77").status_code, 429)

    def test_enderecos_nao_ficam_em_texto_no_cache(self):
        self.errar(1, HTTP_X_FORWARDED_FOR="203.0.113.5")

        chaves = " ".join(map(str, cache._cache))

        self.assertIn("login-falhas", chaves)
        self.assertNotIn("203.0.113.5", chaves)

    def test_nao_conta_falhas_sem_configuracao(self):
        with override_settings(DEMO_LOGIN="", DEMO_PASSWORD=""):
            for _ in range(limite.TENTATIVAS_POR_ORIGEM + 1):
                self.client.post(self.url_login, {"login": LOGIN, "senha": "errada"})

        self.assertEqual(self.entrar().status_code, 302)

    def entrar_de(self, ip):
        return self.client.post(
            self.url_login, {"login": LOGIN, "senha": SENHA}, HTTP_X_FORWARDED_FOR=ip,
        )


@override_settings(**CREDENCIAIS_TESTE)
class VidaDaSessaoTests(LoginDemo, SimpleTestCase):
    def test_cookie_de_sessao_dura_oito_horas(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 8 * 60 * 60)

        self.entrar()

        self.assertEqual(self.client.cookies[settings.SESSION_COOKIE_NAME]["max-age"], 8 * 60 * 60)


class SenhaCurtaTests(SimpleTestCase):
    def avisos(self, senha):
        with override_settings(DEMO_PASSWORD=senha):
            return senha_da_demonstracao_curta(None)

    def test_senha_curta_gera_aviso_sem_expor_o_valor(self):
        avisos = self.avisos("curta123")

        self.assertEqual([a.id for a in avisos], ["usuarios.W001"])
        self.assertNotIn("curta123", f"{avisos[0].msg} {avisos[0].hint}")

    def test_senha_longa_ou_ausente_nao_gera_aviso(self):
        for senha in ("uma-senha-bem-longa-123", "", None):
            with self.subTest(senha=senha):
                self.assertEqual(self.avisos(senha), [])


class OrigemDoClienteTests(SimpleTestCase):
    def origem(self, encaminhado, proxies, remoto="10.0.0.1"):
        meta = {"REMOTE_ADDR": remoto}
        if encaminhado is not None:
            meta["HTTP_X_FORWARDED_FOR"] = encaminhado
        with override_settings(PROXIES_CONFIAVEIS=proxies):
            return limite._origem(RequestFactory().get("/", **meta))

    def test_um_proxy_usa_o_ultimo_valor(self):
        self.assertEqual(self.origem("1.1.1.1, 203.0.113.9", 1), "203.0.113.9")

    def test_dois_proxies_usam_o_penultimo_valor(self):
        # Valor forjado pelo cliente; o endereço real, que o 1º proxy viu; o do próprio 1º proxy, acrescentado pelo 2º.
        self.assertEqual(self.origem("forjado, 203.0.113.9, 172.16.0.1", 2), "203.0.113.9")

    def test_cabecalho_mais_curto_que_o_esperado_usa_o_primeiro_valor(self):
        self.assertEqual(self.origem("203.0.113.9", 3), "203.0.113.9")

    def test_zero_proxies_ignora_o_cabecalho_forjavel(self):
        self.assertEqual(self.origem("198.51.100.7", 0), "10.0.0.1")

    def test_sem_cabecalho_usa_o_endereco_da_conexao(self):
        self.assertEqual(self.origem(None, 1), "10.0.0.1")
        self.assertEqual(self.origem(" , ", 1), "10.0.0.1")
