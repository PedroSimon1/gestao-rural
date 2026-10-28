import logging
import re
from unittest import mock

from django.conf import settings
from django.contrib.sessions.serializers import JSONSerializer
from django.core import signing
from django.db import InterfaceError, OperationalError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from documentos.analises import (
    CHAVE_DA_SESSAO, AnaliseError, criar_analise, descartar_analises, obter_analise,
)
from documentos.models import AnalisePendente, StatusAnalise
from documentos.testing import resultado_da_nota

from .demo import SESSAO_DEMO, credenciais_validas
from .testing import CREDENCIAIS_TESTE, autenticar_demo
from .views import MENSAGEM_CREDENCIAIS_INVALIDAS, MENSAGEM_LOGIN_INDISPONIVEL

LOGIN = CREDENCIAIS_TESTE["DEMO_LOGIN"]
SENHA = CREDENCIAIS_TESTE["DEMO_PASSWORD"]


class LoginDemo:
    url_login = "/login/"
    url_logout = "/logout/"
    url_documentos = "/documentos/"

    def entrar(self, login=LOGIN, senha=SENHA, client=None):
        return (client or self.client).post(
            self.url_login, {"login": login, "senha": senha}
        )

    def autenticado(self, client=None):
        return (client or self.client).session.get(SESSAO_DEMO) is True


# SimpleTestCase: qualquer consulta ao banco faria o teste falhar. Login e
# logout de uma sessão sem o código das análises não consultam o banco.
@override_settings(**CREDENCIAIS_TESTE)
class LoginDemoTestBase(LoginDemo, SimpleTestCase):
    pass


# TestCase (PostgreSQL local, DB_TEST_*): o logout cancela as análises
# pendentes da sessão (GR-43).
@override_settings(**CREDENCIAIS_TESTE)
class LoginDemoComBancoTestBase(LoginDemo, TestCase):
    pass


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

    def test_sessao_nao_guarda_credenciais(self):
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


class LogoutTests(LoginDemoComBancoTestBase):
    def test_logout_remove_a_autenticacao_e_volta_para_o_login(self):
        for metodo in ("post",):
            with self.subTest(metodo=metodo):
                self.entrar()

                resposta = getattr(self.client, metodo)(self.url_logout)

                self.assertRedirects(resposta, self.url_login)
                self.assertFalse(self.autenticado())

    def test_depois_do_logout_documentos_volta_para_o_login(self):
        self.entrar()
        self.client.post(self.url_logout)

        resposta = self.client.get(self.url_documentos)

        self.assertRedirects(resposta, self.url_login, fetch_redirect_response=False)

    def test_logout_apaga_o_cookie_de_sessao(self):
        self.entrar()

        resposta = self.client.post(self.url_logout)

        cookie = resposta.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie.value, "")
        self.assertEqual(cookie["max-age"], 0)

    def test_logout_sem_sessao_nao_quebra(self):
        resposta = self.client.post(self.url_logout)

        self.assertRedirects(resposta, self.url_login)

    def test_link_sair_nas_paginas_do_sistema(self):
        self.entrar()

        resposta = self.client.get(self.url_documentos)

        self.assertContains(resposta, f'<a href="{reverse("logout")}">Sair</a>', html=True)


class LogoutSemBancoTests(LoginDemoTestBase):
    def test_sessao_sem_codigo_sai_sem_consultar_o_banco(self):
        # Cookie anterior à GR-43, como o de autenticar_demo: só o indicador.
        autenticar_demo(self.client)

        resposta = self.client.post(self.url_logout)

        self.assertRedirects(resposta, self.url_login)
        self.assertFalse(self.autenticado())


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

    def test_cookie_contem_somente_o_indicador_e_o_codigo_das_analises(self):
        self.entrar()

        conteudo = signing.loads(self.cookie().value, salt=self.SALT, serializer=JSONSerializer)

        self.assertEqual(set(conteudo), {SESSAO_DEMO, CHAVE_DA_SESSAO})
        self.assertIs(conteudo[SESSAO_DEMO], True)
        # Código aleatório e opaco: nada de credenciais nem dados da nota.
        self.assertRegex(conteudo[CHAVE_DA_SESSAO], r"^[A-Za-z0-9_-]{43}$")
        self.assertNotIn(LOGIN, str(conteudo))
        self.assertNotIn(SENHA, str(conteudo))

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


class AnalisesNoLoginELogoutTests(LoginDemoComBancoTestBase):
    """Ciclo de vida das análises pendentes (GR-43) ligado ao login e ao logout."""

    def codigo(self, client=None):
        return (client or self.client).session.get(CHAVE_DA_SESSAO)

    def criar(self, client=None):
        return criar_analise((client or self.client).session, resultado_da_nota())

    def assert_cancelada_sem_dados(self, analise):
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.CANCELADA)
        self.assertIsNone(analise.dados)

    def test_login_cria_o_codigo_da_sessao(self):
        self.entrar()

        self.assertRegex(self.codigo(), r"^[A-Za-z0-9_-]{43}$")

    def test_criar_analise_nao_muda_a_sessao_do_login(self):
        # O código já existe: a requisição de processamento não regrava o cookie.
        self.entrar()
        sessao = self.client.session

        self.criar()
        criar_analise(sessao, resultado_da_nota())

        self.assertFalse(sessao.modified)

    def test_cada_login_recebe_um_codigo_novo(self):
        self.entrar()
        primeiro = self.codigo()
        self.client.post(self.url_logout)

        self.entrar()

        self.assertNotEqual(self.codigo(), primeiro)

    def test_codigo_de_sessao_nao_autenticada_nao_e_reaproveitado(self):
        # Cookie válido com código e sem o indicador de login. Não acontece pelo
        # caminho normal (o logout limpa tudo) e não protege contra quem planta
        # um cookie já autenticado: esse vai direto para /documentos/.
        sessao = self.client.session
        sessao[CHAVE_DA_SESSAO] = "codigo-conhecido-por-outra-pessoa"
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        plantada = criar_analise({CHAVE_DA_SESSAO: "codigo-conhecido-por-outra-pessoa"}, resultado_da_nota())

        self.entrar()

        self.assertNotEqual(self.codigo(), "codigo-conhecido-por-outra-pessoa")
        self.assert_cancelada_sem_dados(plantada)
        nova = self.criar()
        with self.assertRaises(AnaliseError):
            obter_analise({CHAVE_DA_SESSAO: "codigo-conhecido-por-outra-pessoa"}, nova.id)

    def test_logout_cancela_as_pendentes_da_sessao(self):
        self.entrar()
        primeira, segunda = self.criar(), self.criar()
        outro = Client()
        self.entrar(client=outro)
        de_outro_navegador = self.criar(outro)

        self.client.post(self.url_logout)

        self.assert_cancelada_sem_dados(primeira)
        self.assert_cancelada_sem_dados(segunda)
        de_outro_navegador.refresh_from_db()
        self.assertEqual(de_outro_navegador.status, StatusAnalise.PENDENTE)

    def test_navegadores_diferentes_nao_veem_as_analises_um_do_outro(self):
        self.entrar()
        outro = Client()
        self.entrar(client=outro)
        analise = self.criar()

        self.assertNotEqual(self.codigo(), self.codigo(outro))
        with self.assertRaises(AnaliseError) as contexto:
            obter_analise(outro.session, analise.id)
        self.assertEqual(contexto.exception.codigo, "analise_nao_encontrada")

    def test_varias_abas_do_mesmo_navegador_compartilham_as_analises(self):
        self.entrar()
        aba = Client()
        aba.cookies = self.client.cookies  # mesmo cookie de sessão
        da_primeira, da_segunda = self.criar(), self.criar(aba)

        self.assertEqual(obter_analise(aba.session, da_primeira.id).pk, da_primeira.pk)
        self.assertEqual(obter_analise(self.client.session, da_segunda.id).pk, da_segunda.pk)

        aba.post(self.url_logout)

        self.assert_cancelada_sem_dados(da_primeira)
        self.assert_cancelada_sem_dados(da_segunda)

    def test_cookie_antigo_reenviado_depois_do_logout(self):
        self.entrar()
        analise = self.criar()
        cookie_antigo = self.client.cookies[settings.SESSION_COOKIE_NAME].value

        self.client.post(self.url_logout)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = cookie_antigo

        # Limite conhecido: cookie assinado não é revogável no servidor e a
        # cópia continua autenticando até expirar (SESSION_COOKIE_AGE).
        self.assertTrue(self.autenticado())
        # Mas as análises daquela sessão foram canceladas e não têm mais dados.
        with self.assertRaises(AnaliseError) as contexto:
            obter_analise(self.client.session, analise.id)
        self.assertEqual(contexto.exception.codigo, "analise_cancelada")
        self.assert_cancelada_sem_dados(analise)

    def test_logout_com_banco_indisponivel_ainda_limpa_a_sessao(self):
        for erro in (OperationalError("sem conexão"), InterfaceError("conexão fechada")):
            with self.subTest(erro=type(erro).__name__):
                self.entrar()
                analise = self.criar()

                with mock.patch("usuarios.demo.descartar_analises", side_effect=erro), \
                        self.assertLogs("usuarios.demo", level="WARNING") as logs:
                    resposta = self.client.post(self.url_logout)

                self.assertRedirects(resposta, self.url_login)
                self.assertFalse(self.autenticado())
                self.assertNotIn(str(erro), "\n".join(logs.output))
                # Continua PENDENTE: deixa de ser usável em 30 minutos, mas os
                # dados só são apagados na próxima limpeza.
                analise.refresh_from_db()
                self.assertEqual(analise.status, StatusAnalise.PENDENTE)

    def test_login_com_banco_indisponivel_ainda_entra_com_codigo_novo(self):
        sessao = self.client.session
        sessao[CHAVE_DA_SESSAO] = "codigo-anterior"
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key

        with mock.patch(
            "usuarios.demo.descartar_analises", side_effect=InterfaceError("conexão fechada")
        ), self.assertLogs("usuarios.demo", level="WARNING"):
            resposta = self.entrar()

        self.assertRedirects(resposta, self.url_documentos, fetch_redirect_response=False)
        self.assertTrue(self.autenticado())
        self.assertNotEqual(self.codigo(), "codigo-anterior")

    def test_cookie_anterior_a_gr43_nao_cria_analise(self):
        # Autentica, mas sem código: precisa de novo login para criar análises.
        autenticar_demo(self.client)
        sessao = self.client.session

        with self.assertRaises(AnaliseError) as contexto:
            criar_analise(sessao, resultado_da_nota())

        self.assertEqual(contexto.exception.codigo, "sessao_sem_codigo")
        self.assertFalse(sessao.modified)
        self.assertTrue(self.autenticado())
        self.assertEqual(AnalisePendente.objects.count(), 0)

    def test_analise_criada_depois_do_logout_por_cookie_antigo(self):
        # Limite documentado: sem revogação completa, a cópia do cookie cria
        # análises novas com o mesmo código, que ficam pendentes.
        self.entrar()
        cookie_antigo = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.client.post(self.url_logout)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = cookie_antigo

        nova = self.criar()

        self.assertEqual(obter_analise(self.client.session, nova.id).status, StatusAnalise.PENDENTE)

    def test_logout_sem_analises_nao_altera_nada(self):
        self.entrar()

        self.client.post(self.url_logout)

        self.assertEqual(AnalisePendente.objects.count(), 0)
        self.assertEqual(descartar_analises({}), 0)
