from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .models import Documento
from .views import _salvar_documento


class UploadDocumentoTests(TestCase):
    def setUp(self):
        self.pasta_temporaria = TemporaryDirectory()
        self.addCleanup(self.pasta_temporaria.cleanup)

        configuracao = override_settings(
            MEDIA_ROOT=self.pasta_temporaria.name
        )
        configuracao.enable()
        self.addCleanup(configuracao.disable)

        usuario = get_user_model().objects.create_user(
            username="teste_upload",
            is_staff=True,
        )
        self.client.force_login(usuario)
        self.url = reverse("documento_upload")

    def test_upload_pdf_cria_documento_e_salva_arquivo(self):
        arquivo = SimpleUploadedFile(
            "exemplo.pdf",
            b"%PDF-1.4\n%%EOF\n",
            content_type="application/pdf",
        )

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 201)
        documento = Documento.objects.get()
        self.assertEqual(documento.nome_original, "exemplo.pdf")
        self.assertEqual(documento.status, Documento.Status.PENDENTE)
        self.assertTrue(
            documento.arquivo.storage.exists(documento.arquivo.name)
        )

    def test_upload_sem_arquivo_retorna_erro(self):
        resposta = self.client.post(self.url, {})

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("erro", resposta.json())
        self.assertFalse(Documento.objects.exists())

    def test_arquivo_txt_e_rejeitado(self):
        arquivo = SimpleUploadedFile("exemplo.txt", b"texto")

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Documento.objects.exists())

    def test_pdf_sem_cabecalho_e_rejeitado(self):
        arquivo = SimpleUploadedFile("exemplo.pdf", b"texto")

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Documento.objects.exists())

    def test_pdf_com_content_type_incorreto_e_rejeitado(self):
        arquivo = SimpleUploadedFile(
            "exemplo.pdf",
            b"%PDF-1.4\n%%EOF\n",
            content_type="text/plain",
        )

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Documento.objects.exists())

    @override_settings(
        MAX_PDF_UPLOAD_SIZE=10,
        MAX_PDF_UPLOAD_SIZE_MB=1,
    )
    def test_pdf_acima_do_limite_e_rejeitado(self):
        arquivo = SimpleUploadedFile(
            "grande.pdf",
            b"%PDF-" + b"x" * 20,
            content_type="application/pdf",
        )

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Documento.objects.exists())

    def test_pdf_vazio_e_rejeitado(self):
        arquivo = SimpleUploadedFile(
            "vazio.pdf",
            b"",
            content_type="application/pdf",
        )

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Documento.objects.exists())

    def test_nome_do_arquivo_e_sanitizado(self):
        arquivo = SimpleUploadedFile(
            "nota fiscal (teste)#.pdf",
            b"%PDF-1.4\n%%EOF\n",
            content_type="application/pdf",
        )

        resposta = self.client.post(self.url, {"arquivo": arquivo})

        self.assertEqual(resposta.status_code, 201)

        documento = Documento.objects.get()
        self.assertEqual(
            documento.nome_original,
            "nota_fiscal_teste.pdf",
        )


DETALHE_INTERNO = "detalhe-interno-xyz"


class UploadDocumentoFalhaAoSalvarTests(TransactionTestCase):
    """Caminho 500 do endpoint JSON e limpeza do arquivo (_salvar_documento).

    TransactionTestCase: como em produção (autocommit), sem o atomic externo
    do TestCase, que ficaria inutilizado pela falha simulada no banco.
    """

    def setUp(self):
        self.pasta_temporaria = TemporaryDirectory()
        self.addCleanup(self.pasta_temporaria.cleanup)

        configuracao = override_settings(MEDIA_ROOT=self.pasta_temporaria.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)

        usuario = get_user_model().objects.create_user(
            username="teste_upload_falha",
            is_staff=True,
        )
        self.client.force_login(usuario)
        self.url = reverse("documento_upload")
        self.storage = Documento._meta.get_field("arquivo").storage

    def pdf(self):
        return SimpleUploadedFile(
            "exemplo.pdf",
            b"%PDF-1.4\n%%EOF\n",
            content_type="application/pdf",
        )

    def arquivos_no_storage(self):
        if not self.storage.exists("documentos"):
            return []
        _, arquivos = self.storage.listdir("documentos")
        return arquivos

    def falhar_no_banco(self, excecao):
        """Falha no INSERT, depois que o arquivo já foi gravado no storage."""
        gravados = []

        def inserir(documento, *args, **kwargs):
            gravados.append(documento.arquivo.name)
            self.assertTrue(self.storage.exists(documento.arquivo.name))
            raise excecao

        patcher = mock.patch.object(Documento, "_do_insert", side_effect=inserir, autospec=True)
        return patcher, gravados

    def assert_resposta_500_segura(self, resposta):
        self.assertEqual(resposta.status_code, 500)
        self.assertEqual(
            resposta.json(), {"erro": "Não foi possível salvar o documento."}
        )
        conteudo = resposta.content.decode()
        self.assertNotIn(DETALHE_INTERNO, conteudo)
        self.assertNotIn("Traceback", conteudo)
        self.assertNotIn(self.pasta_temporaria.name, conteudo)

    def test_falha_no_banco_retorna_500_e_remove_o_arquivo(self):
        patcher, gravados = self.falhar_no_banco(
            DatabaseError(f"{DETALHE_INTERNO} documentos_documento")
        )

        with patcher:
            resposta = self.client.post(self.url, {"arquivo": self.pdf()})

        # O cenário realmente ocorreu: o arquivo chegou a ser gravado.
        self.assertEqual(len(gravados), 1)
        self.assert_resposta_500_segura(resposta)
        self.assertNotIn("documentos_documento", resposta.content.decode())
        self.assertFalse(Documento.objects.exists())
        self.assertFalse(self.storage.exists(gravados[0]))
        self.assertEqual(self.arquivos_no_storage(), [])

    def test_falha_no_storage_retorna_500(self):
        with mock.patch.object(
            FileSystemStorage,
            "_save",
            side_effect=OSError(f"{DETALHE_INTERNO} disco cheio"),
        ):
            resposta = self.client.post(self.url, {"arquivo": self.pdf()})

        self.assert_resposta_500_segura(resposta)
        self.assertFalse(Documento.objects.exists())
        self.assertEqual(self.arquivos_no_storage(), [])

    def test_salvar_documento_cria_pendente(self):
        documento = _salvar_documento(self.pdf())

        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PENDENTE)
        self.assertEqual(documento.nome_original, "exemplo.pdf")
        self.assertTrue(self.storage.exists(documento.arquivo.name))

    def test_salvar_documento_remove_arquivo_e_relanca(self):
        for excecao in (DatabaseError("banco"), RuntimeError("inesperado")):
            with self.subTest(excecao=type(excecao).__name__):
                patcher, gravados = self.falhar_no_banco(excecao)

                with patcher, self.assertRaises(type(excecao)):
                    _salvar_documento(self.pdf())

                self.assertFalse(self.storage.exists(gravados[0]))
                self.assertFalse(Documento.objects.exists())
