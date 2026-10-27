"""GR-44: view + consultas oficiais em PostgreSQL local, Agents simulados."""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastros.models import Papel, Pessoa, Status
from financeiro.models import MovimentoConta
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .processamento import ResultadoProcessamento
from .test_consultas import resultado


@override_settings(**CREDENCIAIS_TESTE)
class InterfaceConsultasTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)

    def enviar(self, dados):
        with mock.patch("documentos.views.processar_pdf", return_value=ResultadoProcessamento(dados, "Teste")):
            return self.client.post(reverse("documento_inicio"), {
                "arquivo": SimpleUploadedFile("nota.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
                "gemini_api_key": "chave-ficticia-testes",
            })

    def test_exibe_existentes_ids_status_e_papel_sem_escrita(self):
        pessoa = Pessoa.objects.create(documento="11222333000181", razao_social="Empresa cadastrada")
        pessoa.inativar()
        with CaptureQueriesContext(connection) as queries:
            resposta = self.enviar(resultado())
        self.assertContains(resposta, "Consulta aos cadastros")
        self.assertContains(resposta, f"EXISTE — ID: {pessoa.pk}")
        self.assertContains(resposta, "Empresa cadastrada")
        self.assertContains(resposta, "INATIVO")
        self.assertContains(resposta, "AUSENTE")
        self.assertContains(resposta, "NÃO EXISTE")
        for query in queries:
            self.assertTrue(query["sql"].lstrip().upper().startswith("SELECT"))
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(MovimentoConta.objects.count(), 0)
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.INATIVO)

    def test_exibe_faturado_pj(self):
        pj = Pessoa.objects.create(documento="12ABC34501DE35", razao_social="Faturado PJ cadastrado")
        pj.atribuir_papel(Papel.FATURADO)
        dados = resultado()
        dados["faturado"] = {"nome": "Faturado PJ", "cpf": None, "cnpj": "12ABC34501DE35"}
        resposta = self.enviar(dados)
        self.assertContains(resposta, "Faturado PJ cadastrado")
        self.assertContains(resposta, f"EXISTE — ID: {pj.pk}")

    def test_documento_ausente_invalido_e_classificacao_pendente(self):
        dados = resultado()
        dados["fornecedor"]["cnpj"] = None
        dados["faturado"]["cpf"] = "12345678900"
        dados["tipo_despesa"] = None
        with self.assertNumQueries(0):
            resposta = self.enviar(dados)
        self.assertContains(resposta, "DOCUMENTO AUSENTE")
        self.assertContains(resposta, "DOCUMENTO INVÁLIDO")
        self.assertContains(resposta, "AGUARDANDO CLASSIFICAÇÃO")

    def test_ambiguidade_preserva_json_e_pede_revisao_sem_query(self):
        dados = resultado()
        dados["faturado"]["cnpj"] = "12ABC34501DE35"
        with self.assertNumQueries(0):
            resposta = self.enviar(dados)
        self.assertContains(resposta, "a identificação precisa ser esclarecida")
        self.assertContains(resposta, "JSON final")
        self.assertNotContains(resposta, "chave-ficticia-testes")

    def test_erro_banco_preserva_extracao_sem_detalhes_internos(self):
        with mock.patch("documentos.views.consultar_resultado", side_effect=DatabaseError("senha-interna-nao-exibir")):
            resposta = self.enviar(resultado())
        self.assertContains(resposta, "Não foi possível consultar os cadastros agora.")
        self.assertContains(resposta, "JSON final")
        self.assertNotContains(resposta, "senha-interna-nao-exibir")
