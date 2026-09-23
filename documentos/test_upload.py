from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Documento


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
