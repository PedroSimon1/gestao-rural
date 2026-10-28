"""GR-18: dados fictícios, regressões de log, upload, cache e limpeza real."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from agents.extrator.agent import AgentExtrator
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .analises import criar_analise, garantir_dono, registrar_correcoes
from .models import StatusAnalise
from .processamento import ProcessamentoError, processar_pdf
from .testing import resultado_da_nota

SEGREDO = "gr18-api-ficticia-sem-validade"
PDF = b"%PDF-1.4\nconteudo-ficticio-gr18\n%%EOF"


class PrivacidadeSemBancoTests(SimpleTestCase):
    def test_excecao_inesperada_nao_emite_payload_causa_ou_traceback_no_log(self):
        extrator = mock.Mock(spec=AgentExtrator)
        try:
            raise ValueError("cpf-ficticio-payload-gr18")
        except ValueError as causa:
            erro = RuntimeError(SEGREDO)
            erro.__cause__ = causa
        extrator.extrair.side_effect = erro
        with self.assertLogs("documentos.processamento", "ERROR") as logs, self.assertRaises(ProcessamentoError) as contexto:
            processar_pdf(PDF, SEGREDO, extrator=extrator, classificador=mock.Mock())
        self.assertEqual((contexto.exception.etapa, contexto.exception.codigo), ("processamento", "erro_interno"))
        texto = " ".join(logs.output)
        for dado in (SEGREDO, "cpf-ficticio-payload-gr18", "RuntimeError", "Traceback"):
            self.assertNotIn(dado, texto)
        self.assertTrue(all(r.exc_info is None and r.stack_info is None for r in logs.records))

    @override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=1, MAX_PDF_UPLOAD_SIZE=2048)
    def test_upload_nao_spoola_para_disco_mesmo_acima_do_limiar_padrao(self):
        with mock.patch("django.core.files.uploadhandler.TemporaryUploadedFile", side_effect=AssertionError("PDF não deve ir para disco.")):
            request = RequestFactory().post("/documentos/", {"arquivo": SimpleUploadedFile("ficticio.pdf", PDF, content_type="application/pdf")})
            arquivo = request.FILES["arquivo"]
            try:
                self.assertIsInstance(arquivo, InMemoryUploadedFile)
                self.assertEqual(arquivo.read(), PDF)
            finally:
                arquivo.close()

    @override_settings(MAX_PDF_UPLOAD_SIZE=32)
    def test_upload_acima_do_limite_e_interrompido_sem_fallback_para_disco(self):
        with mock.patch("django.core.files.uploadhandler.TemporaryUploadedFile", side_effect=AssertionError("Disco proibido.")):
            request = RequestFactory().post("/documentos/", {"arquivo": SimpleUploadedFile("grande.pdf", PDF * 100)})
            self.assertFalse(request.FILES)


@override_settings(**CREDENCIAIS_TESTE)
class PrivacidadeAnalisesTests(TestCase):
    def autenticar(self, cliente):
        autenticar_demo(cliente)
        sessao = cliente.session
        garantir_dono(sessao)
        sessao.save()
        cliente.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key

    def setUp(self):
        self.autenticar(self.client)
        self.analise = criar_analise(self.client.session, resultado_da_nota())
        registrar_correcoes(self.client.session, self.analise.id, {"fornecedor.razao_social": "Nome fictício corrigido"}, 0)

    def url(self, nome="analise_conferencia"):
        return reverse(nome, args=[self.analise.id])

    def assert_sem_cache(self, resposta):
        controle = resposta.headers.get("Cache-Control", "")
        for diretiva in ("no-store", "private", "no-cache", "max-age=0"):
            self.assertIn(diretiva, controle)
        self.assertIn("Expires", resposta.headers)

    def test_paginas_autenticadas_e_login_nao_podem_ser_cacheadas(self):
        for url in (self.url(), self.url("analise_confirmar"), reverse("documento_inicio"), reverse("pessoas"), reverse("login")):
            with self.subTest(url=url):
                self.assert_sem_cache(self.client.get(url))

    @override_settings(MAX_PDF_UPLOAD_SIZE=32, MAX_PDF_UPLOAD_SIZE_MB=1)
    def test_upload_interrompido_exibe_limite_sem_processar_ou_guardar_chave(self):
        with mock.patch("documentos.views_analises.processar_pdf") as processar:
            resp = self.client.post(reverse("analise_criar"), {
                "arquivo": SimpleUploadedFile("grande.pdf", PDF * 10, content_type="application/pdf"),
                "gemini_api_key": SEGREDO,
            })
        self.assertContains(resp, "O arquivo excede o limite de 1 MB.", status_code=400)
        self.assertNotContains(resp, SEGREDO, status_code=400)
        processar.assert_not_called()

    def test_outra_sessao_nao_le_analise_e_erro_tambem_nao_tem_cache(self):
        outra = Client()
        self.autenticar(outra)
        resp = outra.get(self.url())
        self.assertEqual(resp.status_code, 404)
        self.assertNotContains(resp, "Nome fictício corrigido", status_code=404)
        self.assert_sem_cache(resp)

    def test_expiracao_bloqueia_acesso_e_apaga_json_e_correcoes(self):
        instante = self.analise.expira_em + timedelta(seconds=1)
        with mock.patch("documentos.analises.timezone.now", return_value=instante):
            resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 409)
        self.assert_sem_cache(resp)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.EXPIRADA)
        self.assertIsNone(self.analise.dados)
        self.assertIsNone(self.analise.correcoes)

    def test_comando_limpa_abandonadas_sem_sessao_ou_nova_requisicao(self):
        saida = StringIO()
        instante = self.analise.expira_em + timedelta(seconds=1)
        with mock.patch("documentos.analises.timezone.now", return_value=instante):
            call_command("expirar_analises", stdout=saida)
            call_command("expirar_analises", stdout=saida)
        self.analise.refresh_from_db()
        self.assertIsNone(self.analise.dados)
        self.assertIsNone(self.analise.correcoes)
        self.assertIn("Análises expiradas: 1.", saida.getvalue())
        self.assertIn("Análises expiradas: 0.", saida.getvalue())
        self.assertNotIn("Nome fictício corrigido", saida.getvalue())

    def test_csrf_em_salvar_cancelar_e_confirmar_nao_altera_analise(self):
        protegida = Client(enforce_csrf_checks=True)
        protegida.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        for nome in ("analise_conferencia", "analise_cancelar", "analise_confirmar"):
            resp = protegida.post(self.url(nome), {"versao_correcoes": "1", "confirmar": "on"})
            self.assertEqual(resp.status_code, 403)
            self.assert_sem_cache(resp)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)
        self.assertIsNotNone(self.analise.dados)

    def test_cancelar_apaga_dados_e_cookie_nao_contem_json_da_nota(self):
        resp = self.client.post(self.url("analise_cancelar"))
        self.assertEqual(resp.status_code, 200)
        self.analise.refresh_from_db()
        self.assertIsNone(self.analise.dados)
        self.assertIsNone(self.analise.correcoes)
        sessao = dict(self.client.session)
        for proibido in ("dados", "correcoes", "gemini_api_key", "arquivo", "fornecedor", "faturado"):
            self.assertNotIn(proibido, sessao)

    def test_logout_get_e_post_sem_csrf_nao_cancelam_analise(self):
        protegida = Client(enforce_csrf_checks=True)
        protegida.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        pagina = protegida.get(reverse("logout"))
        self.assertContains(pagina, "Confirmar saída")
        self.assert_sem_cache(pagina)
        self.assertEqual(protegida.post(reverse("logout")).status_code, 403)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)
        self.assertIsNotNone(self.analise.dados)
        token = protegida.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(protegida.post(reverse("logout"), {"csrfmiddlewaretoken": token}).status_code, 302)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.CANCELADA)
        self.assertIsNone(self.analise.dados)
        self.assertIsNone(self.analise.correcoes)
