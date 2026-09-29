import logging
import re

from django.conf import settings
from django.contrib.sessions.serializers import JSONSerializer
from django.core import signing
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from .demo import SESSAO_DEMO, credenciais_validas
from .testing import CREDENCIAIS_TESTE
from .views import MENSAGEM_CREDENCIAIS_INVALIDAS, MENSAGEM_LOGIN_INDISPONIVEL

LOGIN = CREDENCIAIS_TESTE["DEMO_LOGIN"]
SENHA = CREDENCIAIS_TESTE["DEMO_PASSWORD"]


# SimpleTestCase: não há banco, e qualquer consulta faria o teste falhar.
@override_settings(**CREDENCIAIS_TESTE)
class LoginDemoTestBase(SimpleTestCase):
    url_login = "/login/"
    url_logout = "/logout/"
    url_documentos = "/documentos/"

    def entrar(self, login=LOGIN, senha=SENHA, client=None):
        return (client or self.client).post(
            self.url_login, {"login": login, "senha": senha}
        )

    def autenticado(self, client=None):
        return (client or self.client).session.get(SESSAO_DEMO) is True


class RotasTests(LoginDemoTestBase):
    def test_reverse(self):
        self.assertEqual(reverse("login"), "/login/")
        self.assertEqual(reverse("logout"), "/logout/")

    def test_get_mostra_a_tela_de_login(self):
        resposta = self.client.get(self.url_login)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "usuarios/login.html")
        self.assertContains(resposta, "Gestão Rural")
        self.assertContains(resposta, 'name="login"')
        self.assertContains(resposta, 'type="password" name="senha"')
        self.assertContains(resposta, '<button type="submit" class="botao">Entrar</button>')
        self.assertContains(resposta, 'method="post"')
        self.assertContains(resposta, "csrfmiddlewaretoken")

    def test_tela_de_login_nao_mostra_navegacao_nem_sair(self):
        resposta = self.client.get(self.url_login)

        self.assertNotContains(resposta, reverse("logout"))
        self.assertNotContains(resposta, "Enviar nota")

    def test_metodos_nao_permitidos(self):
        for metodo in ("put", "delete", "patch"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(self.url_login).status_code, 405)
                self.assertEqual(getattr(self.client, metodo)(self.url_logout).status_code, 405)


class LoginCorretoTests(LoginDemoTestBase):
    def test_cria_a_sessao(self):
        self.entrar()

        self.assertTrue(self.autenticado())

    def test_redireciona_para_documentos(self):
        resposta = self.entrar()

        self.assertRedirects(resposta, self.url_documentos)

    def test_acessa_documentos_depois_do_login(self):
        self.entrar()

        resposta = self.client.get(self.url_documentos)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "documentos/inicio.html")

    def test_ja_autenticado_em_login_vai_para_documentos(self):
        self.entrar()

        resposta = self.client.get(self.url_login)

        self.assertRedirects(resposta, self.url_documentos)

    def test_raiz_autenticada_vai_para_documentos(self):
        self.entrar()

        resposta = self.client.get("/", follow=True)

        self.assertEqual([url for url, _ in resposta.redirect_chain], ["/documentos/"])
        self.assertEqual(resposta.status_code, 200)


class LoginIncorretoTests(LoginDemoTestBase):
    def assert_recusado(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "usuarios/login.html")
        self.assertContains(resposta, MENSAGEM_CREDENCIAIS_INVALIDAS)
        self.assertFalse(self.autenticado())

    def test_login_incorreto_nao_cria_sessao(self):
        self.assert_recusado(self.entrar(login="outro-login"))

    def test_senha_incorreta_nao_cria_sessao(self):
        self.assert_recusado(self.entrar(senha="senha-errada"))

    def test_login_e_senha_incorretos(self):
        self.assert_recusado(self.entrar(login="x", senha="y"))

    def test_campos_vazios(self):
        for dados in ({}, {"login": LOGIN}, {"senha": SENHA}, {"login": "", "senha": ""}):
            with self.subTest(dados=dados):
                self.assert_recusado(self.client.post(self.url_login, dados))

    def test_diferenca_de_maiusculas_ou_espacos_na_senha_e_recusada(self):
        for senha in (SENHA.upper(), f" {SENHA}", f"{SENHA} "):
            with self.subTest(senha=senha):
                self.assert_recusado(self.entrar(senha=senha))

    def test_mensagem_e_a_mesma_para_login_ou_senha_errados(self):
        login_errado = self.entrar(login="outro-login").content.decode()
        senha_errada = self.entrar(senha="senha-errada").content.decode()

        token = re.compile(r'name="csrfmiddlewaretoken" value="[^"]+"')
        self.assertEqual(token.sub("", login_errado), token.sub("", senha_errada))

    def test_credenciais_na_query_string_nao_autenticam(self):
        resposta = self.client.get(self.url_login, {"login": LOGIN, "senha": SENHA})

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(self.autenticado())

    def test_sem_acesso_a_documentos_depois_de_falhar(self):
        self.entrar(senha="senha-errada")

        resposta = self.client.get(self.url_documentos)

        self.assertRedirects(resposta, self.url_login, fetch_redirect_response=False)


class SigiloTests(LoginDemoTestBase):
    def test_credenciais_nao_aparecem_nas_respostas(self):
        respostas = {
            "get": self.client.get(self.url_login),
            "login_errado": self.entrar(login="outro-login"),
            "senha_errada": self.entrar(senha="senha-errada"),
        }
        for nome, resposta in respostas.items():
            with self.subTest(resposta=nome):
                conteudo = resposta.content.decode()
                self.assertNotIn(LOGIN, conteudo)
                self.assertNotIn(SENHA, conteudo)

    def test_senha_digitada_nao_volta_no_html(self):
        resposta = self.entrar(login="alguem", senha="senha-digitada-xyz")

        self.assertNotContains(resposta, "senha-digitada-xyz")
        self.assertNotContains(resposta, "alguem")

    def test_credenciais_nao_aparecem_em_documentos(self):
        self.entrar()

        conteudo = self.client.get(self.url_documentos).content.decode()

        self.assertNotIn(SENHA, conteudo)
        self.assertNotIn(LOGIN, conteudo)

    def test_senha_nao_aparece_nos_logs(self):
        with self.assertLogs("usuarios", level="DEBUG") as logs:
            # Um registro garante que assertLogs não falhe por falta de logs.
            logging.getLogger("usuarios").debug("inicio")
            self.entrar(senha="senha-digitada-xyz")
            self.entrar()

        texto = "\n".join(logs.output)
        self.assertNotIn("senha-digitada-xyz", texto)
        self.assertNotIn(SENHA, texto)

    def test_sessao_guarda_somente_o_indicador(self):
        self.entrar()

        valores = [str(valor) for valor in self.client.session.values()]
        self.assertEqual(self.client.session[SESSAO_DEMO], True)
        self.assertNotIn(SENHA, " ".join(valores))
        self.assertNotIn(LOGIN, " ".join(valores))


class ConfiguracaoAusenteTests(LoginDemoTestBase):
    CASOS = (
        {"DEMO_LOGIN": None},
        {"DEMO_PASSWORD": None},
        {"DEMO_LOGIN": None, "DEMO_PASSWORD": None},
        {"DEMO_LOGIN": ""},
        {"DEMO_PASSWORD": "   "},
    )

    def test_nao_libera_acesso_e_mostra_erro_seguro(self):
        for ajuste in self.CASOS:
            with self.subTest(ajuste=ajuste), override_settings(**ajuste):
                self.client.cookies.clear()
                with self.assertLogs("usuarios.views", level="WARNING"):
                    resposta = self.entrar()

                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, MENSAGEM_LOGIN_INDISPONIVEL)
                self.assertNotContains(resposta, "DEMO_")
                self.assertNotContains(resposta, "Traceback")
                self.assertFalse(self.autenticado())
                self.assertRedirects(
                    self.client.get(self.url_documentos),
                    self.url_login,
                    fetch_redirect_response=False,
                )

    def test_login_vazio_nao_casa_com_configuracao_vazia(self):
        with override_settings(DEMO_LOGIN="", DEMO_PASSWORD=""):
            self.assertFalse(credenciais_validas("", ""))

    def test_sessao_antiga_perde_acesso_sem_configuracao(self):
        self.entrar()

        with override_settings(DEMO_PASSWORD=None):
            resposta = self.client.get(self.url_documentos)

        self.assertRedirects(resposta, self.url_login, fetch_redirect_response=False)


class LogoutTests(LoginDemoTestBase):
    def test_logout_remove_a_autenticacao_e_volta_para_o_login(self):
        for metodo in ("get", "post"):
            with self.subTest(metodo=metodo):
                self.entrar()

                resposta = getattr(self.client, metodo)(self.url_logout)

                self.assertRedirects(resposta, self.url_login)
                self.assertFalse(self.autenticado())

    def test_depois_do_logout_documentos_volta_para_o_login(self):
        self.entrar()
        self.client.get(self.url_logout)

        resposta = self.client.get(self.url_documentos)

        self.assertRedirects(resposta, self.url_login, fetch_redirect_response=False)

    def test_logout_apaga_o_cookie_de_sessao(self):
        self.entrar()

        resposta = self.client.get(self.url_logout)

        cookie = resposta.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie.value, "")
        self.assertEqual(cookie["max-age"], 0)

    def test_logout_sem_sessao_nao_quebra(self):
        resposta = self.client.get(self.url_logout)

        self.assertRedirects(resposta, self.url_login)

    def test_link_sair_nas_paginas_do_sistema(self):
        self.entrar()

        resposta = self.client.get(self.url_documentos)

        self.assertContains(resposta, f'<a href="{reverse("logout")}">Sair</a>', html=True)


class CsrfTests(LoginDemoTestBase):
    def test_post_sem_token_e_recusado(self):
        cliente = Client(enforce_csrf_checks=True)

        resposta = self.entrar(client=cliente)

        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(self.autenticado(cliente))

    def test_post_com_token_da_pagina_e_aceito(self):
        cliente = Client(enforce_csrf_checks=True)
        pagina = cliente.get(self.url_login).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina).group(1)

        resposta = cliente.post(
            self.url_login, {"login": LOGIN, "senha": SENHA, "csrfmiddlewaretoken": token}
        )

        self.assertRedirects(resposta, self.url_documentos, fetch_redirect_response=False)
        self.assertTrue(self.autenticado(cliente))


class SessaoEmCookieTests(LoginDemoTestBase):
    SALT = "django.contrib.sessions.backends.signed_cookies"

    def cookie(self):
        return self.client.cookies[settings.SESSION_COOKIE_NAME]

    def test_sessao_usa_cookie_assinado(self):
        self.assertEqual(
            settings.SESSION_ENGINE, "django.contrib.sessions.backends.signed_cookies"
        )

    def test_cookie_contem_somente_o_indicador(self):
        self.entrar()

        conteudo = signing.loads(self.cookie().value, salt=self.SALT, serializer=JSONSerializer)

        self.assertEqual(conteudo, {SESSAO_DEMO: True})

    def test_cookie_e_httponly(self):
        resposta = self.entrar()

        self.assertTrue(resposta.cookies[settings.SESSION_COOKIE_NAME]["httponly"])

    def test_cookie_adulterado_nao_autentica(self):
        # Um cookie com o mesmo conteúdo, mas assinado com outra chave.
        forjado = signing.dumps(
            {SESSAO_DEMO: True}, key="outra-chave", salt=self.SALT,
            serializer=JSONSerializer, compress=True,
        )
        self.client.cookies[settings.SESSION_COOKIE_NAME] = forjado

        resposta = self.client.get(self.url_documentos)

        self.assertRedirects(resposta, self.url_login, fetch_redirect_response=False)

    def test_cookie_sem_o_indicador_nao_autentica(self):
        valido_sem_indicador = signing.dumps(
            {"outro": True}, salt=self.SALT, serializer=JSONSerializer, compress=True
        )
        self.client.cookies[settings.SESSION_COOKIE_NAME] = valido_sem_indicador

        resposta = self.client.get(self.url_documentos)

        self.assertRedirects(resposta, self.url_login, fetch_redirect_response=False)
