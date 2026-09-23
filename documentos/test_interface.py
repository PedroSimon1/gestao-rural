import inspect
import json
import re
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import (
    Client,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import dateformat, timezone

from agents.classificador.agent import AgentClassificador, ClassificacaoInconclusivaError
from agents.classificador.schemas import ClassificacaoDespesa
from agents.extrator.agent import AgentExtrator, ExtracaoIndisponivelError
from agents.extrator.schemas import NotaFiscalExtraida

from . import views
from .forms import DocumentoUploadForm
from .models import Documento
from .processamento import DocumentoEmProcessamentoError

PDF = b"%PDF-1.4\n%%EOF\n"
DETALHE_INTERNO = "detalhe-interno-xyz"
MENSAGEM_FALHA = "Não foi possível salvar o documento."


def pdf(nome="nota.pdf", conteudo=PDF, content_type="application/pdf"):
    return SimpleUploadedFile(nome, conteudo, content_type=content_type)


class InterfaceTestMixin:
    """MEDIA_ROOT temporário, usuário staff logado e proteção contra o Gemini."""

    def setUp(self):
        super().setUp()
        self.pasta_temporaria = TemporaryDirectory()
        self.addCleanup(self.pasta_temporaria.cleanup)
        configuracao = override_settings(MEDIA_ROOT=self.pasta_temporaria.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)

        # Rede de segurança: nenhum teste da interface pode chegar ao SDK.
        patcher = mock.patch(
            "agents.gemini_client.genai.Client",
            side_effect=AssertionError("O SDK real do Gemini não deve ser usado."),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.staff = get_user_model().objects.create_user(
            username="staff_interface", is_staff=True
        )
        self.client.force_login(self.staff)
        self.url = reverse("documento_inicio")
        self.storage = Documento._meta.get_field("arquivo").storage

    def arquivos_no_storage(self):
        if not self.storage.exists("documentos"):
            return []
        _, arquivos = self.storage.listdir("documentos")
        return arquivos

    def criar_documento(self, nome, enviado_em=None, **campos):
        documento = Documento.objects.create(
            arquivo=f"documentos/{nome}", nome_original=nome, **campos
        )
        if enviado_em is not None:
            # enviado_em é auto_now_add: ajuste direto no banco.
            Documento.objects.filter(pk=documento.pk).update(enviado_em=enviado_em)
        return documento


class AcessoTests(InterfaceTestMixin, TestCase):
    def test_raiz_redireciona_para_documentos(self):
        resposta = self.client.get("/")

        self.assertRedirects(resposta, "/documentos/")
        self.assertEqual(reverse("inicio"), "/")
        self.assertEqual(reverse("documento_inicio"), "/documentos/")

    def test_staff_acessa_a_tela(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "documentos/inicio.html")
        self.assertTemplateUsed(resposta, "documentos/base.html")

    def test_anonimo_na_raiz_segue_para_o_login(self):
        self.client.logout()

        resposta = self.client.get("/", follow=True)

        login = f"{reverse('admin:login')}?next=/documentos/"
        self.assertEqual(
            [url for url, _ in resposta.redirect_chain], ["/documentos/", login]
        )

    def test_anonimo_em_documentos_vai_para_o_login(self):
        self.client.logout()

        for metodo in ("get", "post"):
            with self.subTest(metodo=metodo):
                resposta = getattr(self.client, metodo)(self.url)

                self.assertRedirects(
                    resposta,
                    f"{reverse('admin:login')}?next=/documentos/",
                    fetch_redirect_response=False,
                )
        self.assertFalse(Documento.objects.exists())

    def test_usuario_nao_staff_vai_para_o_login(self):
        comum = get_user_model().objects.create_user(username="comum", is_staff=False)
        self.client.force_login(comum)

        resposta = self.client.get(self.url)

        self.assertRedirects(
            resposta,
            f"{reverse('admin:login')}?next=/documentos/",
            fetch_redirect_response=False,
        )

    def test_metodos_nao_permitidos(self):
        for metodo in ("put", "delete", "patch"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(self.url).status_code, 405)


class TelaInicialTests(InterfaceTestMixin, TestCase):
    def test_formulario_de_upload(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, 'method="post"')
        self.assertContains(resposta, 'enctype="multipart/form-data"')
        self.assertContains(resposta, "csrfmiddlewaretoken")
        self.assertContains(resposta, 'type="file"')
        self.assertContains(resposta, 'name="arquivo"')
        self.assertContains(resposta, 'accept="application/pdf,.pdf"')
        self.assertContains(resposta, "required")
        self.assertContains(resposta, "Enviar PDF")
        self.assertContains(resposta, "Enviar nota")
        self.assertContains(resposta, "documentos/documentos.css")
        self.assertContains(resposta, '<html lang="pt-BR">', html=False)

    @override_settings(MAX_PDF_UPLOAD_SIZE_MB=7)
    def test_limite_de_upload_vem_das_configuracoes(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, "até 7 MB")

    def test_lista_vazia(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, "Documentos recentes")
        self.assertContains(resposta, "Nenhum documento enviado ainda.")

    def test_lista_no_maximo_10_do_mais_recente_para_o_mais_antigo(self):
        agora = timezone.now()
        for indice in range(12):
            self.criar_documento(
                f"nota-{indice:02d}.pdf", enviado_em=agora - timedelta(hours=indice)
            )

        resposta = self.client.get(self.url)

        nomes = [doc.nome_original for doc in resposta.context["documentos"]]
        self.assertEqual(nomes, [f"nota-{indice:02d}.pdf" for indice in range(10)])
        conteudo = resposta.content.decode()
        self.assertLess(conteudo.index("nota-00.pdf"), conteudo.index("nota-09.pdf"))
        self.assertNotIn("nota-10.pdf", conteudo)
        self.assertNotIn("nota-11.pdf", conteudo)
        self.assertNotContains(resposta, "Nenhum documento enviado ainda.")

    def test_lista_mostra_status_legivel(self):
        self.criar_documento("a.pdf", status=Documento.Status.PENDENTE)
        self.criar_documento("b.pdf", status=Documento.Status.CONCLUIDO)
        self.criar_documento("c.pdf", status=Documento.Status.ERRO)

        resposta = self.client.get(self.url)

        for rotulo in ("Pendente", "Concluído", "Erro"):
            self.assertContains(resposta, rotulo)

    def test_nome_original_e_escapado(self):
        self.criar_documento("<script>alert(1)</script>.pdf")

        resposta = self.client.get(self.url)

        self.assertContains(resposta, "&lt;script&gt;alert(1)&lt;/script&gt;.pdf")
        self.assertNotContains(resposta, "<script>alert(1)</script>")

    def test_nao_expoe_caminho_media_nem_metadados(self):
        self.criar_documento(
            "segredo.pdf",
            metadados={"erro": {"mensagem": DETALHE_INTERNO}},
            resultado_estruturado={"interno": DETALHE_INTERNO},
        )

        resposta = self.client.get(self.url)

        self.assertContains(resposta, "segredo.pdf")
        self.assertNotContains(resposta, "documentos/segredo.pdf")
        self.assertNotContains(resposta, "/media/")
        self.assertNotContains(resposta, DETALHE_INTERNO)

    def test_lista_tem_link_para_o_detalhe(self):
        documento = self.criar_documento("<b>nota</b>.pdf")

        resposta = self.client.get(self.url)

        url_detalhe = reverse("documento_detalhe", args=[documento.pk])
        self.assertEqual(url_detalhe, f"/documentos/{documento.pk}/")
        self.assertContains(
            resposta, f'<a href="{url_detalhe}">&lt;b&gt;nota&lt;/b&gt;.pdf</a>', html=False
        )
        self.assertNotContains(resposta, "documentos/<b>nota</b>.pdf")


class UploadHtmlTests(InterfaceTestMixin, TestCase):
    def test_pdf_valido_cria_documento_pendente(self):
        resposta = self.client.post(self.url, {"arquivo": pdf("nota fiscal.pdf")})

        documento = Documento.objects.get()
        self.assertRedirects(resposta, reverse("documento_detalhe", args=[documento.pk]))
        self.assertEqual(documento.status, Documento.Status.PENDENTE)
        self.assertEqual(documento.nome_original, "nota_fiscal.pdf")
        self.assertTrue(self.storage.exists(documento.arquivo.name))

    def test_mensagem_de_sucesso_na_pagina_do_documento(self):
        resposta = self.client.post(self.url, {"arquivo": pdf()}, follow=True)

        self.assertTemplateUsed(resposta, "documentos/detalhe.html")
        self.assertContains(resposta, "Documento “nota.pdf” enviado.")
        self.assertContains(resposta, "mensagem--success")
        self.assertContains(resposta, "Pendente")
        self.assertContains(resposta, "Pronto para processar.")
        self.assertEqual(Documento.objects.get().status, Documento.Status.PENDENTE)

    def test_upload_usa_salvar_documento(self):
        with mock.patch(
            "documentos.views._salvar_documento", wraps=views._salvar_documento
        ) as salvar:
            self.client.post(self.url, {"arquivo": pdf()})

        salvar.assert_called_once()
        self.assertEqual(Documento.objects.count(), 1)

    def mensagem_do_form_para_arquivo_vazio(self):
        # Arquivo vazio é barrado pelo próprio FileField do Django antes de
        # validar_pdf (comportamento existente desde a GR-7/GR-8).
        form = DocumentoUploadForm({}, {"arquivo": pdf(conteudo=b"")})
        form.is_valid()
        return form.errors["arquivo"][0]

    def test_pdf_invalido_mostra_mensagem_do_form(self):
        casos = (
            ({}, "Selecione um arquivo PDF."),
            ({"arquivo": pdf("nota.txt", b"texto", "text/plain")}, "Selecione um arquivo PDF."),
            ({"arquivo": pdf(conteudo=b"texto")}, "O arquivo enviado não é um PDF válido."),
            ({"arquivo": pdf(conteudo=b"")}, self.mensagem_do_form_para_arquivo_vazio()),
            ({"arquivo": pdf(content_type="text/plain")}, "O tipo do arquivo enviado não é PDF."),
        )
        for dados, mensagem in casos:
            with self.subTest(mensagem=mensagem):
                resposta = self.client.post(self.url, dados)

                self.assertEqual(resposta.status_code, 200)
                self.assertTemplateUsed(resposta, "documentos/inicio.html")
                self.assertContains(resposta, mensagem)
                self.assertContains(resposta, 'class="erros-campo"')
                self.assertFalse(Documento.objects.exists())
                self.assertEqual(self.arquivos_no_storage(), [])

    @override_settings(MAX_PDF_UPLOAD_SIZE=10, MAX_PDF_UPLOAD_SIZE_MB=1)
    def test_pdf_acima_do_limite(self):
        resposta = self.client.post(
            self.url, {"arquivo": pdf(conteudo=b"%PDF-" + b"x" * 20)}
        )

        self.assertContains(resposta, "O arquivo excede o limite de 1 MB.")
        self.assertFalse(Documento.objects.exists())

    def test_validacao_nao_e_duplicada_na_view(self):
        # A view delega a validação ao DocumentoUploadForm (GR-8).
        codigo = inspect.getsource(views.documento_inicio)

        self.assertIn("DocumentoUploadForm(request.POST, request.FILES)", codigo)
        self.assertNotIn("%PDF", codigo)
        self.assertNotIn("content_type", codigo)

    def test_views_so_processam_via_processar_documento(self):
        codigo = inspect.getsource(views)

        for proibido in ("agents", "AgentExtrator", "AgentClassificador", "GeminiClient", "genai"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, codigo)
        self.assertIn(
            "from .processamento import DocumentoEmProcessamentoError, processar_documento",
            codigo,
        )
        self.assertEqual(views.processar_documento.__module__, "documentos.processamento")


class UploadHtmlFalhaAoSalvarTests(InterfaceTestMixin, TransactionTestCase):
    """TransactionTestCase: como em produção (autocommit); a falha simulada no
    banco inutilizaria o atomic externo de um TestCase."""

    def assert_erro_geral_seguro(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "documentos/inicio.html")
        self.assertContains(resposta, MENSAGEM_FALHA)
        self.assertContains(resposta, 'class="erro-geral"')
        self.assertNotContains(resposta, DETALHE_INTERNO)
        self.assertNotContains(resposta, "Traceback")
        self.assertNotContains(resposta, "mensagem--success")
        self.assertNotContains(resposta, self.pasta_temporaria.name)
        self.assertFalse(Documento.objects.exists())
        self.assertEqual(self.arquivos_no_storage(), [])

    def test_falha_no_banco_depois_de_gravar_o_arquivo(self):
        gravados = []

        def inserir(documento, *args, **kwargs):
            gravados.append(documento.arquivo.name)
            self.assertTrue(self.storage.exists(documento.arquivo.name))
            raise DatabaseError(f"{DETALHE_INTERNO} documentos_documento")

        with mock.patch.object(
            Documento, "_do_insert", side_effect=inserir, autospec=True
        ):
            resposta = self.client.post(self.url, {"arquivo": pdf()})

        self.assertEqual(len(gravados), 1)  # o arquivo chegou a ser gravado
        self.assert_erro_geral_seguro(resposta)
        self.assertNotContains(resposta, "documentos_documento")

    def test_falha_no_storage(self):
        with mock.patch.object(
            FileSystemStorage,
            "_save",
            side_effect=OSError(f"{DETALHE_INTERNO} disco cheio"),
        ):
            resposta = self.client.post(self.url, {"arquivo": pdf()})

        self.assert_erro_geral_seguro(resposta)


class RegressaoUploadJsonTests(InterfaceTestMixin, TestCase):
    def test_endpoint_json_mantem_url_nome_e_contrato(self):
        self.assertEqual(reverse("documento_upload"), "/documentos/upload/")

        resposta = self.client.post(reverse("documento_upload"), {"arquivo": pdf()})

        self.assertEqual(resposta.status_code, 201)
        documento = Documento.objects.get()
        self.assertEqual(
            resposta.json(),
            {"id": documento.pk, "nome_original": "nota.pdf", "status": "PENDENTE"},
        )

    def test_endpoint_json_continua_so_post(self):
        self.assertEqual(self.client.get(reverse("documento_upload")).status_code, 405)


def resultado_concluido(**alteracoes):
    """JSON final fictício, com as chaves fora da ordem do contrato."""
    resultado = {
        "validacoes": {
            "faturado_cpf": {"status": "invalido", "motivo": "digitos_verificadores_invalidos"},
            "fornecedor_cnpj": {"status": "valido", "motivo": None},
        },
        "extra_desconhecida": "fica no fim",
        "tipo_despesa": "MANUTENCAO_E_OPERACAO",
        "valor_total": "1500.00",
        "parcelas": [{"numero": 1, "data_vencimento": "2026-10-20", "valor": "1500.00"}],
        "quantidade_parcelas": 1,
        "itens": [{"descricao": "<script>alert(1)</script>", "valor_total": "1500.00"}],
        "data_emissao": "2026-09-20",
        "numero_nota": "000123",
        "faturado": {"nome": "Produtor Ficticio", "cpf": "99999999999"},
        "fornecedor": {
            "razao_social": "Pecas Exemplo Ltda",
            "nome_fantasia": "Pecas Exemplo",
            "cnpj": "11222333000181",
        },
    }
    resultado.update(alteracoes)
    return resultado


def metadados_concluido(justificativa="Itens de manutenção de máquinas."):
    classificacao = {"versao_schema": 1, "modelo": "modelo-secreto-xyz"}
    if justificativa is not None:
        classificacao["justificativa"] = justificativa
    return {
        "processamento": {
            "versao_resultado": 1,
            "iniciado_em": "2026-09-24T10:00:00+00:00",
            "finalizado_em": "2026-09-24T10:00:30+00:00",
            "extracao": {"versao_schema": 1, "modelo": "modelo-secreto-xyz"},
            "classificacao": classificacao,
        }
    }


class DetalheTestMixin(InterfaceTestMixin):
    def detalhe(self, documento):
        return self.client.get(reverse("documento_detalhe", args=[documento.pk]))

    def assert_form_processar(self, resposta, documento, texto_botao):
        """Botão de processamento é um form POST real, com CSRF, não desabilitado."""
        conteudo = resposta.content.decode()
        acao = reverse("documento_processar", args=[documento.pk])
        form = re.search(
            rf'<form method="post" action="{re.escape(acao)}"([^>]*)>(.*?)</form>', conteudo, re.S
        )
        self.assertIsNotNone(form, "form POST para documento_processar não encontrado")
        atributos, corpo = form.groups()
        self.assertIn('name="csrfmiddlewaretoken"', corpo)
        self.assertIn(f'<button type="submit" class="botao">{texto_botao}</button>', corpo)
        self.assertNotIn("disabled", corpo)
        # Proteção visual contra clique duplo (etapa 5; documentos.js).
        self.assertIn("data-submit-lock", atributos)
        self.assertIn('data-submit-texto="Processando..."', atributos)


class DetalheAcessoTests(DetalheTestMixin, TestCase):
    def test_staff_acessa(self):
        documento = self.criar_documento("nota.pdf")

        resposta = self.detalhe(documento)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "documentos/detalhe.html")

    def test_anonimo_e_nao_staff_vao_para_o_login(self):
        documento = self.criar_documento("nota.pdf")
        url = reverse("documento_detalhe", args=[documento.pk])
        comum = get_user_model().objects.create_user(username="comum_detalhe")

        for usuario in (None, comum):
            with self.subTest(usuario=getattr(usuario, "username", "anonimo")):
                self.client.logout()
                if usuario:
                    self.client.force_login(usuario)

                resposta = self.client.get(url)

                self.assertRedirects(
                    resposta,
                    f"{reverse('admin:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_documento_inexistente(self):
        resposta = self.client.get(reverse("documento_detalhe", args=[999999]))

        self.assertEqual(resposta.status_code, 404)

    def test_metodos_nao_permitidos(self):
        documento = self.criar_documento("nota.pdf")
        url = reverse("documento_detalhe", args=[documento.pk])

        for metodo in ("post", "put", "delete"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(url).status_code, 405)
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PENDENTE)

    def test_nome_data_status_e_link_de_volta(self):
        documento = self.criar_documento("nota.pdf")
        documento.refresh_from_db()

        resposta = self.detalhe(documento)

        data = dateformat.format(timezone.localtime(documento.enviado_em), "d/m/Y H:i")
        self.assertContains(resposta, "nota.pdf")
        self.assertContains(resposta, f"Enviado em {data}")
        self.assertContains(resposta, "Pendente")
        self.assertContains(resposta, f'href="{reverse("documento_inicio")}"')

    def test_nome_com_script_e_escapado(self):
        documento = self.criar_documento("<script>alert(1)</script>.pdf")

        resposta = self.detalhe(documento)

        self.assertContains(resposta, "&lt;script&gt;alert(1)&lt;/script&gt;.pdf")
        self.assertNotContains(resposta, "<script>alert(1)</script>")

    def test_nao_expoe_caminho_do_arquivo_nem_media(self):
        documento = self.criar_documento("segredo.pdf")

        resposta = self.detalhe(documento)

        self.assertNotContains(resposta, "documentos/segredo.pdf")
        self.assertNotContains(resposta, "/media/")


class DetalhePendenteTests(DetalheTestMixin, TestCase):
    def test_pronto_para_processar_com_form_post(self):
        documento = self.criar_documento("nota.pdf")

        with mock.patch("documentos.views.processar_documento") as processar:
            resposta = self.detalhe(documento)

        # Abrir a página não processa nada.
        processar.assert_not_called()
        self.assertContains(resposta, "Pronto para processar.")
        self.assert_form_processar(resposta, documento, "Processar")
        self.assertNotContains(resposta, 'http-equiv="refresh"')
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PENDENTE)


class DetalheProcessandoTests(DetalheTestMixin, TestCase):
    def test_mensagem_e_atualizacao_automatica(self):
        documento = self.criar_documento("nota.pdf", status=Documento.Status.PROCESSANDO)

        resposta = self.detalhe(documento)

        self.assertContains(resposta, "Processando... a página atualiza automaticamente.")
        self.assertContains(resposta, '<meta http-equiv="refresh" content="5">', html=False)
        self.assertNotContains(resposta, "<button")
        self.assertNotContains(resposta, "<form")

    def test_meta_refresh_so_em_processando(self):
        for status in (
            Documento.Status.PENDENTE,
            Documento.Status.CONCLUIDO,
            Documento.Status.ERRO,
        ):
            with self.subTest(status=status):
                documento = self.criar_documento(f"{status}.pdf", status=status)

                self.assertNotContains(self.detalhe(documento), 'http-equiv="refresh"')


class DetalheConcluidoTests(DetalheTestMixin, TestCase):
    def concluido(self, resultado=None, metadados=None):
        documento = self.criar_documento(
            "nota.pdf",
            status=Documento.Status.CONCLUIDO,
            resultado_estruturado=resultado if resultado is not None else resultado_concluido(),
            metadados=metadados if metadados is not None else metadados_concluido(),
        )
        return self.detalhe(documento)

    def test_resumo(self):
        resposta = self.concluido()

        self.assertContains(resposta, "Resumo")
        for rotulo, valor in (
            ("Tipo de despesa", "Manutenção e operação"),
            ("Valor total", "R$ 1.500,00"),
            ("Quantidade de parcelas", "1"),
            ("Fornecedor", "Pecas Exemplo Ltda"),
            ("Número da nota", "000123"),
            ("Data de emissão", "20/09/2026"),
        ):
            with self.subTest(rotulo=rotulo):
                self.assertContains(
                    resposta, f"<dt>{rotulo}</dt><dd>{valor}</dd>", html=False
                )

    def test_quantidade_de_parcelas_zero(self):
        resposta = self.concluido(resultado_concluido(quantidade_parcelas=0, parcelas=[]))

        self.assertContains(
            resposta, "<dt>Quantidade de parcelas</dt><dd>0</dd>", html=False
        )

    def test_tipo_infraestrutura_e_desconhecido(self):
        casos = (
            ("INFRAESTRUTURA_E_UTILIDADES", "Infraestrutura e utilidades"),
            ("<i>NOVO</i>", "&lt;i&gt;NOVO&lt;/i&gt;"),
        )
        for tipo, esperado in casos:
            with self.subTest(tipo=tipo):
                resposta = self.concluido(resultado_concluido(tipo_despesa=tipo))

                self.assertEqual(resposta.status_code, 200)
                self.assertContains(
                    resposta, f"<dt>Tipo de despesa</dt><dd>{esperado}</dd>", html=False
                )

    def test_justificativa(self):
        resposta = self.concluido()

        self.assertContains(resposta, "Justificativa da classificação")
        self.assertContains(resposta, "Itens de manutenção de máquinas.")

    def test_sem_justificativa(self):
        resposta = self.concluido(metadados=metadados_concluido(justificativa=None))

        self.assertNotContains(resposta, "Justificativa da classificação")

    def test_aviso_de_cpf_invalido(self):
        resposta = self.concluido()

        self.assertContains(resposta, "CPF do faturado com dígitos verificadores inválidos.")
        self.assertNotContains(resposta, "CNPJ do fornecedor com dígitos verificadores inválidos.")
        self.assertContains(resposta, "Isso não impediu o processamento.")
        self.assertContains(resposta, "não a existência do documento")

    def test_aviso_de_cnpj_invalido(self):
        validacoes = {
            "fornecedor_cnpj": {"status": "invalido", "motivo": "digitos_verificadores_invalidos"},
            "faturado_cpf": {"status": "valido", "motivo": None},
        }

        resposta = self.concluido(resultado_concluido(validacoes=validacoes))

        self.assertContains(resposta, "CNPJ do fornecedor com dígitos verificadores inválidos.")
        self.assertNotContains(resposta, "CPF do faturado com dígitos verificadores inválidos.")

    def test_sem_avisos_quando_tudo_valido(self):
        validacoes = {
            "fornecedor_cnpj": {"status": "valido", "motivo": None},
            "faturado_cpf": {"status": "ausente", "motivo": None},
        }

        resposta = self.concluido(resultado_concluido(validacoes=validacoes))

        self.assertNotContains(resposta, "dígitos verificadores inválidos")

    def test_json_na_ordem_do_contrato(self):
        resposta = self.concluido()

        self.assertContains(resposta, "JSON final")
        texto = resposta.context["json_resultado"]
        self.assertEqual(
            list(json.loads(texto)),
            list(views.CHAVES_RESULTADO) + ["extra_desconhecida"],
        )
        self.assertIn("  ", texto)  # indentado
        self.assertIn("Produtor Ficticio", texto)  # ensure_ascii=False
        self.assertContains(resposta, '<pre class="bloco-json">', html=False)
        conteudo = resposta.content.decode()
        self.assertLess(
            conteudo.index("&quot;fornecedor&quot;"),
            conteudo.index("&quot;validacoes&quot;"),
        )
        self.assertLess(
            conteudo.index("&quot;validacoes&quot;"),
            conteudo.index("&quot;extra_desconhecida&quot;"),
        )

    def test_script_no_resultado_e_escapado(self):
        resposta = self.concluido()

        self.assertContains(resposta, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(resposta, "<script>alert(1)</script>")

    def test_nao_mostra_metadados_internos_nem_modelo(self):
        resposta = self.concluido()

        for interno in ("modelo-secreto-xyz", "versao_schema", "iniciado_em", "finalizado_em"):
            with self.subTest(interno=interno):
                self.assertNotContains(resposta, interno)

    def test_sem_botao_de_processamento(self):
        resposta = self.concluido()

        self.assertNotContains(resposta, "<button")
        self.assertNotContains(resposta, "Pronto para processar.")

    def test_resultado_invalido_nao_quebra_a_pagina(self):
        resposta = self.concluido(resultado=["nao", "e", "objeto"], metadados=[])

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Resumo")


class DetalheErroTests(DetalheTestMixin, TestCase):
    def com_erro(self, erro, **metadados_extras):
        documento = self.criar_documento(
            "nota.pdf",
            status=Documento.Status.ERRO,
            metadados={
                "processamento": {
                    "versao_resultado": 1,
                    "iniciado_em": "2026-09-24T10:00:00+00:00",
                    "finalizado_em": "2026-09-24T10:00:30+00:00",
                },
                "erro": erro,
                **metadados_extras,
            },
        )
        return self.detalhe(documento)

    def test_mensagem_segura_e_sugestao(self):
        resposta = self.com_erro(
            {
                "etapa": "extracao",
                "codigo": "servico_indisponivel",
                "mensagem": "Serviço de extração indisponível no momento.",
            }
        )

        self.assertContains(resposta, "O processamento não foi concluído.")
        self.assertContains(resposta, "Serviço de extração indisponível no momento.")
        self.assertContains(resposta, "Tente novamente mais tarde.")
        documento = Documento.objects.get()
        self.assert_form_processar(resposta, documento, "Tentar novamente")

    def test_sugestao_por_codigo(self):
        casos = {
            "documento_ilegivel": "Envie o arquivo PDF novamente.",
            "servico_indisponivel": "Tente novamente mais tarde.",
            "resposta_invalida": "Confira se o arquivo enviado é uma nota fiscal válida.",
            "classificacao_invalida": "Tente novamente.",
            "classificacao_inconclusiva": "não se encaixaram nas categorias de despesa",
            "erro_interno": "Tente novamente. Se o problema persistir, avise a equipe.",
        }
        for codigo, sugestao in casos.items():
            with self.subTest(codigo=codigo):
                resposta = self.com_erro(
                    {"etapa": "extracao", "codigo": codigo, "mensagem": "Mensagem segura."}
                )

                self.assertContains(resposta, sugestao)

    def test_codigo_desconhecido_ou_erro_ausente_nao_quebram(self):
        casos = (
            {"codigo": "codigo_novo", "mensagem": "Mensagem segura."},
            {},
            "nao-e-objeto",
        )
        for erro in casos:
            with self.subTest(erro=erro):
                resposta = self.com_erro(erro)

                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, views.SUGESTAO_ERRO_PADRAO)
        self.assertContains(self.com_erro({}), views.MENSAGEM_ERRO_PADRAO)

    def test_mensagem_e_escapada(self):
        resposta = self.com_erro({"codigo": "erro_interno", "mensagem": "<script>x</script>"})

        self.assertContains(resposta, "&lt;script&gt;x&lt;/script&gt;")
        self.assertNotContains(resposta, "<script>x</script>")

    def test_nao_exibe_dados_internos(self):
        resposta = self.com_erro(
            {
                "etapa": "extracao",
                "codigo": "servico_indisponivel",
                "mensagem": "Serviço de extração indisponível no momento.",
                "traceback": "Traceback (most recent call last)",
                "status_code": 503,
                "resposta_gemini": DETALHE_INTERNO,
            },
            processamento_extra={"modelo": "modelo-secreto-xyz", "api_key": "chave-xyz"},
        )

        for interno in (
            "Traceback",
            "503",
            DETALHE_INTERNO,
            "modelo-secreto-xyz",
            "chave-xyz",
            "servico_indisponivel",
            "extracao",
        ):
            with self.subTest(interno=interno):
                self.assertNotContains(resposta, interno)


PASTA_TEMPLATES = Path(__file__).parent / "templates" / "documentos"
ARQUIVO_JS = Path(__file__).parent / "static" / "documentos" / "documentos.js"


class SegurancaTemplatesTests(SimpleTestCase):
    def test_templates_nao_usam_safe(self):
        pasta = Path(__file__).parent / "templates" / "documentos"
        templates = sorted(pasta.glob("*.html"))

        self.assertTrue(templates)
        for template in templates:
            with self.subTest(template=template.name):
                self.assertNotIn("|safe", template.read_text())
                self.assertNotIn("autoescape off", template.read_text())


class ProcessarTestMixin(DetalheTestMixin):
    def url_processar(self, documento_ou_pk):
        pk = getattr(documento_ou_pk, "pk", documento_ou_pk)
        return reverse("documento_processar", args=[pk])

    def url_detalhe(self, documento_ou_pk):
        pk = getattr(documento_ou_pk, "pk", documento_ou_pk)
        return reverse("documento_detalhe", args=[pk])

    def mensagens(self, resposta):
        return [str(mensagem) for mensagem in resposta.context["messages"]]


class ProcessarRotaEAcessoTests(ProcessarTestMixin, TestCase):
    def test_reverse(self):
        self.assertEqual(self.url_processar(7), "/documentos/7/processar/")

    def test_so_aceita_post(self):
        documento = self.criar_documento("nota.pdf")

        with mock.patch("documentos.views.processar_documento") as processar:
            for metodo in ("get", "put", "delete", "patch"):
                with self.subTest(metodo=metodo):
                    resposta = getattr(self.client, metodo)(self.url_processar(documento))
                    self.assertEqual(resposta.status_code, 405)

        processar.assert_not_called()

    def test_anonimo_e_nao_staff_vao_para_o_login_sem_processar(self):
        documento = self.criar_documento("nota.pdf")
        url = self.url_processar(documento)
        comum = get_user_model().objects.create_user(username="comum_processar")

        for usuario in (None, comum):
            with self.subTest(usuario=getattr(usuario, "username", "anonimo")):
                self.client.logout()
                if usuario:
                    self.client.force_login(usuario)

                with mock.patch("documentos.views.processar_documento") as processar:
                    resposta = self.client.post(url)

                self.assertRedirects(
                    resposta,
                    f"{reverse('admin:login')}?next={url}",
                    fetch_redirect_response=False,
                )
                processar.assert_not_called()

    def test_csrf_obrigatorio(self):
        documento = self.criar_documento("nota.pdf")
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.staff)

        with mock.patch("documentos.views.processar_documento") as processar:
            resposta = cliente.post(self.url_processar(documento))

        self.assertEqual(resposta.status_code, 403)
        processar.assert_not_called()

    def test_csrf_do_formulario_da_pagina_e_aceito(self):
        documento = self.criar_documento("nota.pdf")
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.staff)
        pagina = cliente.get(self.url_detalhe(documento))
        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina.content.decode()
        ).group(1)
        concluido = Documento(pk=documento.pk, status=Documento.Status.CONCLUIDO)

        with mock.patch("documentos.views.processar_documento", return_value=concluido) as processar:
            resposta = cliente.post(
                self.url_processar(documento), {"csrfmiddlewaretoken": token}
            )

        self.assertRedirects(resposta, self.url_detalhe(documento), fetch_redirect_response=False)
        processar.assert_called_once_with(documento.pk)


class ProcessarEstadosDaPaginaTests(ProcessarTestMixin, TestCase):
    def test_processando_e_concluido_continuam_sem_botao(self):
        for status in (Documento.Status.PROCESSANDO, Documento.Status.CONCLUIDO):
            with self.subTest(status=status):
                documento = self.criar_documento(
                    f"{status}.pdf",
                    status=status,
                    resultado_estruturado=resultado_concluido(),
                    metadados=metadados_concluido(),
                )

                resposta = self.detalhe(documento)

                self.assertNotContains(resposta, "<button")
                self.assertNotContains(resposta, "<form")
                self.assertNotContains(resposta, self.url_processar(documento))


class ProcessarServicoMockadoTests(ProcessarTestMixin, TestCase):
    def processar(self, documento, **patch_kwargs):
        with mock.patch("documentos.views.processar_documento", **patch_kwargs) as processar:
            resposta = self.client.post(self.url_processar(documento), follow=True)
        return resposta, processar

    def retorno(self, documento, status):
        return Documento(pk=documento.pk, nome_original=documento.nome_original, status=status)

    def test_chama_o_servico_uma_vez_com_o_pk(self):
        documento = self.criar_documento("nota.pdf")

        _, processar = self.processar(
            documento, return_value=self.retorno(documento, Documento.Status.CONCLUIDO)
        )

        processar.assert_called_once_with(documento.pk)

    def test_parametros_do_request_nao_chegam_ao_servico(self):
        documento = self.criar_documento("nota.pdf")
        concluido = self.retorno(documento, Documento.Status.CONCLUIDO)

        with mock.patch("documentos.views.processar_documento", return_value=concluido) as processar:
            self.client.post(
                self.url_processar(documento),
                {"api_key": "chave-xyz", "modelo": "outro", "extrator": "x"},
            )

        processar.assert_called_once_with(documento.pk)

    def test_concluido(self):
        documento = self.criar_documento("nota.pdf")

        resposta, _ = self.processar(
            documento, return_value=self.retorno(documento, Documento.Status.CONCLUIDO)
        )

        self.assertRedirects(resposta, self.url_detalhe(documento))
        self.assertEqual(self.mensagens(resposta), ["Processamento concluído."])
        self.assertContains(resposta, "mensagem--success")

    def test_erro(self):
        documento = self.criar_documento("nota.pdf")

        resposta, _ = self.processar(
            documento, return_value=self.retorno(documento, Documento.Status.ERRO)
        )

        self.assertRedirects(resposta, self.url_detalhe(documento))
        self.assertEqual(
            self.mensagens(resposta), ["O processamento falhou. Veja os detalhes abaixo."]
        )
        self.assertContains(resposta, "mensagem--error")

    def test_documento_ja_em_processamento(self):
        documento = self.criar_documento("nota.pdf", status=Documento.Status.PROCESSANDO)

        resposta, _ = self.processar(documento, side_effect=DocumentoEmProcessamentoError())

        self.assertRedirects(resposta, self.url_detalhe(documento))
        self.assertEqual(self.mensagens(resposta), ["O documento já está sendo processado."])
        self.assertContains(resposta, "mensagem--info")

    def test_documento_inexistente(self):
        with mock.patch(
            "documentos.views.processar_documento", side_effect=Documento.DoesNotExist
        ) as processar:
            resposta = self.client.post(self.url_processar(999999))

        self.assertEqual(resposta.status_code, 404)
        processar.assert_called_once_with(999999)

    def test_excecao_inesperada(self):
        documento = self.criar_documento("nota.pdf")
        erro = RuntimeError(f"{DETALHE_INTERNO} status=503 modelo-secreto-xyz")

        with self.assertLogs("documentos.views", "ERROR") as logs:
            resposta, _ = self.processar(documento, side_effect=erro)

        self.assertRedirects(resposta, self.url_detalhe(documento))
        self.assertEqual(self.mensagens(resposta), [views.MENSAGEM_FALHA_INESPERADA])
        self.assertIsNotNone(logs.records[0].exc_info)  # logger.exception
        for interno in (DETALHE_INTERNO, "Traceback", "RuntimeError", "503", "modelo-secreto-xyz"):
            with self.subTest(interno=interno):
                self.assertNotContains(resposta, interno)


# Rede de segurança adicional para a integração: sem chave, nada autentica.
@override_settings(GEMINI_API_KEY=None)
class ProcessarIntegracaoTests(ProcessarTestMixin, TestCase):
    """processar_documento REAL + Agents falsos no ponto em que o serviço os cria."""

    def setUp(self):
        super().setUp()
        self.nota = NotaFiscalExtraida.model_validate(
            {
                "documento_e_nota_fiscal": True,
                "fornecedor": {
                    "razao_social": "Pecas Exemplo Ltda",
                    "nome_fantasia": "Pecas Exemplo",
                    "cnpj": "11.222.333/0001-81",
                },
                "faturado": {"nome": "Produtor Ficticio", "cpf": "999.999.999-99"},
                "numero_nota": "000123",
                "data_emissao": "2026-09-20",
                "itens": [{"descricao": "Filtro de oleo", "quantidade": 2, "valor_total": 1500}],
                "parcelas": [{"data_vencimento": "2026-10-20", "valor": 1500}],
                "valor_total": 1500,
            }
        )
        self.classificacao = ClassificacaoDespesa.model_validate(
            {"tipo_despesa": "MANUTENCAO_E_OPERACAO", "justificativa": "Peças de manutenção."}
        )

        self.extrator = mock.Mock(spec=AgentExtrator)
        self.extrator.modelo = "modelo-secreto-xyz"
        self.extrator.extrair_documento.return_value = self.nota
        self.classificador = mock.Mock(spec=AgentClassificador)
        self.classificador.modelo = "modelo-secreto-xyz"
        self.classificador.classificar.return_value = self.classificacao

        for alvo, agente in (
            ("documentos.processamento.AgentExtrator", self.extrator),
            ("documentos.processamento.AgentClassificador", self.classificador),
        ):
            patcher = mock.patch(alvo, return_value=agente)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.documento = self.criar_documento("nota.pdf")

    def test_sucesso_ponta_a_ponta(self):
        resposta = self.client.post(self.url_processar(self.documento))

        self.assertRedirects(resposta, self.url_detalhe(self.documento), fetch_redirect_response=False)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.status, Documento.Status.CONCLUIDO)
        resultado = self.documento.resultado_estruturado
        self.assertEqual(resultado["tipo_despesa"], "MANUTENCAO_E_OPERACAO")
        self.assertEqual(resultado["quantidade_parcelas"], 1)
        self.assertEqual(resultado["valor_total"], "1500.00")
        self.extrator.extrair_documento.assert_called_once()
        self.classificador.classificar.assert_called_once_with(self.nota)

        pagina = self.client.get(self.url_detalhe(self.documento))
        self.assertEqual(self.mensagens(pagina), ["Processamento concluído."])
        self.assertContains(pagina, "Manutenção e operação")
        self.assertContains(pagina, "R$ 1.500,00")
        self.assertContains(pagina, "CPF do faturado com dígitos verificadores inválidos.")
        self.assertContains(pagina, "Peças de manutenção.")
        self.assertContains(pagina, "&quot;quantidade_parcelas&quot;: 1")
        self.assertNotContains(pagina, "modelo-secreto-xyz")
        self.assertNotContains(pagina, "<form")

    def test_falha_do_extrator(self):
        self.extrator.extrair_documento.side_effect = ExtracaoIndisponivelError()

        with self.assertLogs("documentos.processamento", "WARNING"):
            resposta = self.client.post(self.url_processar(self.documento), follow=True)

        self.assertRedirects(resposta, self.url_detalhe(self.documento))
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.status, Documento.Status.ERRO)
        self.assertEqual(self.documento.resultado_estruturado, {})
        self.classificador.classificar.assert_not_called()
        self.assertEqual(
            self.mensagens(resposta), ["O processamento falhou. Veja os detalhes abaixo."]
        )
        self.assertContains(resposta, "Serviço de extração indisponível no momento.")
        self.assertContains(resposta, "Tente novamente mais tarde.")
        self.assert_form_processar(resposta, self.documento, "Tentar novamente")
        for interno in ("servico_indisponivel", "extracao", "modelo-secreto-xyz"):
            self.assertNotContains(resposta, interno)

    def test_falha_do_classificador_nao_persiste_resultado_parcial(self):
        self.classificador.classificar.side_effect = ClassificacaoInconclusivaError()

        with self.assertLogs("documentos.processamento", "WARNING"):
            resposta = self.client.post(self.url_processar(self.documento), follow=True)

        self.documento.refresh_from_db()
        self.assertEqual(self.documento.status, Documento.Status.ERRO)
        self.assertEqual(self.documento.resultado_estruturado, {})
        processamento = self.documento.metadados["processamento"]
        self.assertNotIn("extracao", processamento)
        self.assertNotIn("classificacao", processamento)
        self.assertNotContains(resposta, "Pecas Exemplo Ltda")
        self.assertNotContains(resposta, "99999999999")
        self.assertContains(resposta, "A despesa não se encaixa nas categorias disponíveis no MVP.")
        self.assertContains(resposta, "não se encaixaram nas categorias de despesa")

    def test_documento_concluido_nao_reprocessa(self):
        self.client.post(self.url_processar(self.documento), follow=True)  # consome a mensagem
        self.extrator.extrair_documento.reset_mock()

        resposta = self.client.post(self.url_processar(self.documento), follow=True)

        self.extrator.extrair_documento.assert_not_called()
        self.assertEqual(self.mensagens(resposta), ["Processamento concluído."])


class JavaScriptTests(DetalheTestMixin, TestCase):
    """Etapa 5: JS mínimo de proteção visual. Sem navegador automatizado no
    projeto, os testes conferem o arquivo e a marcação que ele usa."""

    def js(self):
        return ARQUIVO_JS.read_text()

    def test_arquivo_existe_e_e_encontrado_pelo_staticfiles(self):
        from django.contrib.staticfiles import finders

        self.assertTrue(ARQUIVO_JS.exists())
        self.assertEqual(Path(finders.find("documentos/documentos.js")), ARQUIVO_JS)

    def test_base_carrega_o_js_com_defer(self):
        resposta = self.client.get(reverse("documento_inicio"))

        self.assertContains(
            resposta,
            '<script src="/static/documentos/documentos.js" defer></script>',
            html=False,
        )

    def test_formulario_de_upload_protegido(self):
        resposta = self.client.get(reverse("documento_inicio"))

        self.assertContains(
            resposta,
            '<form method="post" enctype="multipart/form-data" class="formulario" '
            'data-submit-lock data-submit-texto="Enviando...">',
            html=False,
        )
        self.assertContains(resposta, "csrfmiddlewaretoken")
        self.assertContains(resposta, '<button type="submit" class="botao">Enviar PDF</button>', html=False)

    def test_forms_de_processamento_protegidos(self):
        # PENDENTE ("Processar") e ERRO ("Tentar novamente"): assert_form_processar
        # exige data-submit-lock, data-submit-texto, POST, CSRF e botão habilitado.
        pendente = self.criar_documento("pendente.pdf")
        erro = self.criar_documento(
            "erro.pdf",
            status=Documento.Status.ERRO,
            metadados={"erro": {"codigo": "erro_interno", "mensagem": "Falhou."}},
        )

        self.assert_form_processar(self.detalhe(pendente), pendente, "Processar")
        self.assert_form_processar(self.detalhe(erro), erro, "Tentar novamente")

    def test_processando_e_concluido_sem_form_protegido(self):
        for status in (Documento.Status.PROCESSANDO, Documento.Status.CONCLUIDO):
            with self.subTest(status=status):
                documento = self.criar_documento(
                    f"{status}.pdf",
                    status=status,
                    resultado_estruturado=resultado_concluido(),
                    metadados=metadados_concluido(),
                )

                resposta = self.client.get(reverse("documento_detalhe", args=[documento.pk]))

                self.assertNotContains(resposta, "data-submit-lock")
                self.assertNotContains(resposta, "<form")

    def test_processando_continua_com_meta_refresh(self):
        documento = self.criar_documento("p.pdf", status=Documento.Status.PROCESSANDO)

        resposta = self.client.get(reverse("documento_detalhe", args=[documento.pk]))

        self.assertContains(resposta, '<meta http-equiv="refresh" content="5">', html=False)

    def test_js_so_age_nos_formularios_marcados(self):
        js = self.js()

        self.assertIn('form[data-submit-lock]', js)
        self.assertIn("data-submit-texto", js)
        self.assertIn("textContent", js)
        self.assertIn("disabled = true", js)
        self.assertNotIn('querySelectorAll("form")', js)

    def test_js_nao_cancela_o_primeiro_envio(self):
        js = self.js()

        # preventDefault só aparece no ramo do segundo envio.
        self.assertEqual(js.count("preventDefault"), 1)
        ramo = js[js.index('=== "true"'):js.index("preventDefault")]
        self.assertNotIn("travar(", ramo)

    def test_js_sem_rede_polling_ou_html_dinamico(self):
        js = self.js()

        for proibido in (
            "fetch(",
            "XMLHttpRequest",
            "$.ajax",
            "WebSocket",
            "setInterval",
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "eval(",
            "new Function",
            "document.write",
        ):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, js)

    def test_js_sem_referencia_a_gemini_chave_ou_metadados(self):
        js = self.js().lower()

        for proibido in ("gemini", "api_key", "apikey", "api key", "metadados", "modelo", ".pdf"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, js)

    def test_templates_sem_fetch_nem_xmlhttprequest(self):
        for template in sorted(PASTA_TEMPLATES.glob("*.html")):
            with self.subTest(template=template.name):
                conteudo = template.read_text()
                self.assertNotIn("fetch(", conteudo)
                self.assertNotIn("XMLHttpRequest", conteudo)
                self.assertNotIn("<script>", conteudo)  # sem JS inline

    def test_fluxo_continua_sendo_post_html_sem_js(self):
        # O client do Django não executa JS: o fluxo completo funciona só com HTML.
        with mock.patch(
            "documentos.views.processar_documento",
            side_effect=lambda pk: Documento(pk=pk, status=Documento.Status.CONCLUIDO),
        ) as processar:
            enviado = self.client.post(reverse("documento_inicio"), {"arquivo": pdf()})
            documento = Documento.objects.get()
            processado = self.client.post(reverse("documento_processar", args=[documento.pk]))

        self.assertRedirects(enviado, reverse("documento_detalhe", args=[documento.pk]))
        self.assertRedirects(
            processado, reverse("documento_detalhe", args=[documento.pk]), fetch_redirect_response=False
        )
        processar.assert_called_once_with(documento.pk)
