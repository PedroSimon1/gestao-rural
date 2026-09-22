from django.test import TestCase

from .models import Documento


class DocumentoModelTests(TestCase):
    def test_cria_documento_com_status_inicial(self):
        documento = Documento.objects.create(
            arquivo="documentos/exemplo.pdf",
            nome_original="exemplo.pdf",
        )

        self.assertEqual(documento.status, Documento.Status.PENDENTE)
        self.assertIsNone(documento.titular)
        self.assertIsNotNone(documento.enviado_em)
        self.assertEqual(documento.resultado_estruturado, {})
        self.assertEqual(documento.metadados, {})

    def test_representacao_textual_mostra_nome_original(self):
        documento = Documento(
            arquivo="documentos/exemplo.pdf",
            nome_original="exemplo.pdf",
        )

        self.assertEqual(str(documento), "exemplo.pdf")

    def test_resultado_estruturado_pode_ser_salvo(self):
        documento = Documento.objects.create(
            arquivo="documentos/exemplo.pdf",
            nome_original="exemplo.pdf",
            resultado_estruturado={"tipo": "nota_fiscal"},
        )

        documento.refresh_from_db()
        self.assertEqual(
            documento.resultado_estruturado,
            {"tipo": "nota_fiscal"},
        )