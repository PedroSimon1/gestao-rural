import inspect
import re
from pathlib import Path
from unittest import mock

from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from agents.extrator.agent import ExtracaoIndisponivelError
from agents.gemini_client import GeminiTimeoutError
from usuarios.demo import SESSAO_DEMO
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from . import views
from .processamento import ProcessamentoError, ResultadoProcessamento
from .test_processamento import dados_nota

PDF = b"%PDF-1.4\n%%EOF\n"
DETALHE_INTERNO = "detalhe-interno-xyz"
PASTA_APP = Path(__file__).resolve().parent
PASTA_TEMPLATES = PASTA_APP / "templates" / "documentos"
ARQUIVO_JS = PASTA_APP / "static" / "documentos" / "documentos.js"
PASTA_TEMPLATES_USUARIOS = PASTA_APP.parent / "usuarios" / "templates" / "usuarios"


def pdf(nome="nota.pdf", conteudo=PDF, content_type="application/pdf"):
    return SimpleUploadedFile(nome, conteudo, content_type=content_type)


def resultado(**alteracoes):
    base = {
        "fornecedor": {
            "razao_social": "Pecas Exemplo Ltda",
            "nome_fantasia": "Pecas Exemplo",
            "cnpj": "11222333000181",
        },
        "faturado": {"nome": "Produtor Ficticio", "cpf": "99999999999"},
        "numero_nota": "000123",
        "data_emissao": "2026-09-20",
        "itens": [{"descricao": "Filtro de oleo", "quantidade": "2",
                   "valor_unitario": None, "valor_total": "1500.00"}],
        "quantidade_parcelas": 1,
        "parcelas": [{"numero": 1, "data_vencimento": "2026-10-20", "valor": "1500.00"}],
        "valor_total": "1500.00",
        "tipo_despesa": "MANUTENCAO_E_OPERACAO",
        "validacoes": {
            "fornecedor_cnpj": {"status": "valido", "motivo": None},
            "faturado_cpf": {"status": "invalido", "motivo": "digitos_verificadores_invalidos"},
        },
    }
    base.update(alteracoes)
    return base


def processamento(justificativa="Itens de manutenção de máquinas.", **alteracoes):
    return ResultadoProcessamento(resultado(**alteracoes), justificativa)


# SimpleTestCase: não há banco, e qualquer consulta faria o teste falhar.
class InterfaceTestBase(SimpleTestCase):
    """Sessão da demonstração e redes de segurança contra Gemini e gravação de arquivos."""

    def setUp(self):
        configuracao = override_settings(**CREDENCIAIS_TESTE)
        configuracao.enable()
        self.addCleanup(configuracao.disable)

        for alvo, mensagem in (
            ("agents.gemini_client.genai.Client", "O SDK real do Gemini não deve ser usado."),
            ("django.core.files.storage.FileSystemStorage._save", "Nenhum arquivo deve ser gravado."),
        ):
            patcher = mock.patch(alvo, side_effect=AssertionError(mensagem))
            patcher.start()
            self.addCleanup(patcher.stop)

        autenticar_demo(self.client)
        self.url = reverse("documento_inicio")

    def enviar(self, arquivo=None, retorno=None, **kwargs):
        """POST do PDF com processar_pdf simulado; devolve (resposta, mock)."""
        dados = {} if arquivo is False else {"arquivo": arquivo or pdf()}
        with mock.patch("documentos.views.processar_pdf", **kwargs) as processar:
            if retorno is not None:
                processar.return_value = retorno
            resposta = self.client.post(self.url, dados)
        return resposta, processar


class AcessoTests(InterfaceTestBase):
    def test_raiz_autenticada_vai_para_documentos(self):
        resposta = self.client.get("/")

        self.assertRedirects(resposta, "/documentos/")
        self.assertEqual(reverse("inicio"), "/")
        self.assertEqual(reverse("documento_inicio"), "/documentos/")

    def test_anonimo_na_raiz_segue_para_o_login(self):
        self.client.cookies.clear()

        resposta = self.client.get("/", follow=True)

        self.assertEqual(
            [url for url, _ in resposta.redirect_chain], ["/documentos/", "/login/"]
        )
        self.assertTemplateUsed(resposta, "usuarios/login.html")

    def test_anonimo_nao_envia_nem_processa(self):
        self.client.cookies.clear()

        for metodo in ("get", "post"):
            with self.subTest(metodo=metodo):
                with mock.patch("documentos.views.processar_pdf") as processar:
                    resposta = getattr(self.client, metodo)(self.url, {"arquivo": pdf()})

                self.assertRedirects(resposta, "/login/", fetch_redirect_response=False)
                processar.assert_not_called()

    def test_metodos_nao_permitidos(self):
        for metodo in ("put", "delete", "patch"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(self.url).status_code, 405)

    def test_rotas_da_arquitetura_antiga_nao_existem(self):
        for url in ("/documentos/upload/", "/documentos/1/", "/documentos/1/processar/", "/admin/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class TelaTests(InterfaceTestBase):
    def test_formulario_de_envio(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "documentos/inicio.html")
        self.assertContains(
            resposta,
            '<form method="post" enctype="multipart/form-data" class="formulario" '
            'data-submit-lock data-submit-texto="Processando...">',
            html=False,
        )
        self.assertContains(resposta, "csrfmiddlewaretoken")
        self.assertContains(resposta, 'accept="application/pdf,.pdf"')
        self.assertContains(resposta, '<button type="submit" class="botao">Processar</button>', html=False)
        self.assertContains(resposta, f'<a href="{reverse("logout")}">Sair</a>', html=True)

    @override_settings(MAX_PDF_UPLOAD_SIZE_MB=3)
    def test_limite_de_upload_vem_das_configuracoes(self):
        self.assertContains(self.client.get(self.url), "até 3 MB")

    def test_get_sem_resultado_nem_erro(self):
        resposta = self.client.get(self.url)

        self.assertNotContains(resposta, "JSON final")
        self.assertNotContains(resposta, 'role="alert"')
        self.assertNotContains(resposta, "Documentos recentes")


class ValidacaoTests(InterfaceTestBase):
    def assert_recusado(self, arquivo, mensagem):
        resposta, processar = self.enviar(arquivo)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, mensagem)
        self.assertContains(resposta, 'aria-invalid="true"')
        processar.assert_not_called()

    def test_sem_arquivo(self):
        self.assert_recusado(False, "Selecione um arquivo PDF.")

    def test_extensao_diferente_de_pdf(self):
        self.assert_recusado(pdf("nota.txt", content_type="text/plain"), "Selecione um arquivo PDF.")

    def test_pdf_sem_cabecalho(self):
        self.assert_recusado(pdf(conteudo=b"texto qualquer"), "O arquivo enviado não é um PDF válido.")

    def test_content_type_incorreto(self):
        self.assert_recusado(
            pdf(content_type="application/octet-stream"), "O tipo do arquivo enviado não é PDF."
        )

    def test_arquivo_vazio(self):
        self.assert_recusado(pdf(conteudo=b""), "O arquivo PDF está vazio.")

    @override_settings(MAX_PDF_UPLOAD_SIZE_MB=1, MAX_PDF_UPLOAD_SIZE=10)
    def test_pdf_acima_do_limite(self):
        self.assert_recusado(pdf(conteudo=PDF + b"x" * 20), "O arquivo excede o limite de 1 MB.")

    def test_nome_do_arquivo_e_sanitizado(self):
        resposta, _ = self.enviar(pdf("../pasta/minha nota.pdf"), retorno=processamento())

        self.assertContains(resposta, "minha_nota.pdf")
        self.assertNotContains(resposta, "../pasta")

    def test_validacao_nao_e_duplicada_na_view(self):
        codigo = inspect.getsource(views)

        self.assertNotIn("%PDF", codigo)
        self.assertNotIn("content_type", codigo)


class ProcessamentoTests(InterfaceTestBase):
    def test_processa_os_bytes_exatos_do_pdf(self):
        _, processar = self.enviar(pdf(conteudo=PDF + b"conteudo"), retorno=processamento())

        processar.assert_called_once_with(PDF + b"conteudo")

    def test_resumo_justificativa_e_json(self):
        resposta, _ = self.enviar(retorno=processamento())

        self.assertEqual(resposta.status_code, 200)
        for esperado in (
            "Resultado — nota.pdf",
            "Manutenção e operação",
            "R$ 1.500,00",
            "Pecas Exemplo Ltda",
            "000123",
            "20/09/2026",
            "Justificativa da classificação",
            "Itens de manutenção de máquinas.",
            "JSON final",
            "&quot;quantidade_parcelas&quot;: 1",
            "CPF do faturado com dígitos verificadores inválidos.",
        ):
            with self.subTest(esperado=esperado):
                self.assertContains(resposta, esperado)

    def test_json_na_ordem_do_contrato(self):
        resposta, _ = self.enviar(retorno=processamento())

        json_tela = re.search(r"<code>(.*?)</code>", resposta.content.decode(), re.S).group(1)
        posicoes = [
            # Só chaves do primeiro nível (indentação de 2 espaços).
            json_tela.index(f"\n  &quot;{chave}&quot;: ")
            for chave in (
                "fornecedor", "faturado", "numero_nota", "data_emissao", "itens",
                "quantidade_parcelas", "parcelas", "valor_total", "tipo_despesa", "validacoes",
            )
        ]
        self.assertEqual(posicoes, sorted(posicoes))
        self.assertNotIn("justificativa", json_tela)

    def test_variacoes_do_resumo(self):
        valido = {"status": "valido", "motivo": None}
        resposta, _ = self.enviar(
            retorno=processamento(
                tipo_despesa="INFRAESTRUTURA_E_UTILIDADES",
                fornecedor={"razao_social": None, "nome_fantasia": "Loja Fantasia", "cnpj": None},
                quantidade_parcelas=0,
                parcelas=[],
                validacoes={"fornecedor_cnpj": valido, "faturado_cpf": valido},
            )
        )

        self.assertContains(resposta, "Infraestrutura e utilidades")
        self.assertContains(resposta, "Loja Fantasia")
        self.assertContains(resposta, "<dd>0</dd>", html=True)
        self.assertNotContains(resposta, "dígitos verificadores inválidos")

    def test_erro_mostra_mensagem_segura_e_sugestao(self):
        erro = ProcessamentoError("extracao", "servico_indisponivel", "Serviço de extração indisponível no momento.")
        resposta, _ = self.enviar(side_effect=erro)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O processamento de “nota.pdf” não foi concluído.")
        self.assertContains(resposta, "Serviço de extração indisponível no momento.")
        self.assertContains(resposta, "Tente novamente mais tarde.")
        self.assertNotContains(resposta, "JSON final")
        for interno in ("servico_indisponivel", "extracao"):
            self.assertNotContains(resposta, interno)

    def test_sugestao_por_codigo(self):
        for codigo, sugestao in views.SUGESTOES_ERRO.items():
            with self.subTest(codigo=codigo):
                resposta, _ = self.enviar(side_effect=ProcessamentoError("x", codigo, "Falhou."))

                self.assertContains(resposta, sugestao)

    def test_codigo_desconhecido_usa_sugestao_padrao(self):
        resposta, _ = self.enviar(side_effect=ProcessamentoError("x", "novo_codigo", "Falhou."))

        self.assertContains(resposta, views.SUGESTAO_ERRO_PADRAO)

    def test_formulario_continua_disponivel_apos_resultado_ou_erro(self):
        for kwargs in ({"retorno": processamento()},
                       {"side_effect": ProcessamentoError("x", "erro_interno", "Falhou.")}):
            with self.subTest(kwargs=list(kwargs)):
                resposta, _ = self.enviar(**kwargs)

                self.assertContains(resposta, '<button type="submit" class="botao">Processar</button>', html=False)


class SegurancaTests(InterfaceTestBase):
    def test_resultado_e_justificativa_sao_escapados(self):
        script = "<script>alert(1)</script>"
        resposta, _ = self.enviar(
            retorno=processamento(
                justificativa=script,
                fornecedor={"razao_social": script, "nome_fantasia": None, "cnpj": None},
                numero_nota=script,
            )
        )

        self.assertNotContains(resposta, script)
        self.assertContains(resposta, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_mensagem_de_erro_e_escapada(self):
        resposta, _ = self.enviar(side_effect=ProcessamentoError("x", "y", "<b>falhou</b>"))

        self.assertNotContains(resposta, "<b>falhou</b>")
        self.assertContains(resposta, "&lt;b&gt;falhou&lt;/b&gt;")

    def test_templates_nao_usam_safe(self):
        templates = [*PASTA_TEMPLATES.glob("*.html"), *PASTA_TEMPLATES_USUARIOS.glob("*.html")]
        self.assertTrue(templates)
        for template in templates:
            with self.subTest(template=template.name):
                self.assertNotIn("|safe", template.read_text())
                self.assertNotIn("autoescape off", template.read_text())

    def test_csrf_obrigatorio(self):
        cliente = Client(enforce_csrf_checks=True)
        autenticar_demo(cliente)

        with mock.patch("documentos.views.processar_pdf") as processar:
            resposta = cliente.post(self.url, {"arquivo": pdf()})

        self.assertEqual(resposta.status_code, 403)
        processar.assert_not_called()

    def test_csrf_do_formulario_da_pagina_e_aceito(self):
        cliente = Client(enforce_csrf_checks=True)
        autenticar_demo(cliente)
        pagina = cliente.get(self.url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina).group(1)

        with mock.patch("documentos.views.processar_pdf", return_value=processamento()) as processar:
            resposta = cliente.post(self.url, {"arquivo": pdf(), "csrfmiddlewaretoken": token})

        self.assertEqual(resposta.status_code, 200)
        processar.assert_called_once()

    def test_resultado_nao_vai_para_a_sessao(self):
        self.enviar(retorno=processamento())

        self.assertEqual(dict(self.client.session.items()), {SESSAO_DEMO: True})

    def test_resultado_nao_e_repetido_em_nova_visita(self):
        self.enviar(retorno=processamento())

        resposta = self.client.get(self.url)

        self.assertNotContains(resposta, "JSON final")
        self.assertNotContains(resposta, "Pecas Exemplo Ltda")


# Rede de segurança adicional para a integração: sem chave, nada autentica.
@override_settings(GEMINI_API_KEY=None)
class IntegracaoTests(InterfaceTestBase):
    """View + processar_pdf + Agents e schemas REAIS; só o GeminiClient é falso."""

    def setUp(self):
        super().setUp()
        self.cliente_extrator = mock.Mock()
        self.cliente_extrator.gerar_json.return_value = dados_nota(
            parcelas=[{"data_vencimento": "2026-10-20", "valor": 1500}]
        )
        self.cliente_classificador = mock.Mock()
        self.cliente_classificador.gerar_json.return_value = {
            "tipo_despesa": "MANUTENCAO_E_OPERACAO",
            "justificativa": "Peças de manutenção.",
        }
        for alvo, cliente in (
            ("agents.extrator.agent.GeminiClient", self.cliente_extrator),
            ("agents.classificador.agent.GeminiClient", self.cliente_classificador),
        ):
            patcher = mock.patch(alvo, return_value=cliente)
            patcher.start()
            self.addCleanup(patcher.stop)

    def enviar_real(self):
        return self.client.post(self.url, {"arquivo": pdf()})

    def test_sucesso_ponta_a_ponta(self):
        resposta = self.enviar_real()

        self.assertEqual(resposta.status_code, 200)
        parte_pdf = self.cliente_extrator.gerar_json.call_args.args[0][1]
        self.assertEqual(parte_pdf.inline_data.data, PDF)
        for esperado in (
            "Manutenção e operação",
            "R$ 1.500,00",
            "Peças de manutenção.",
            "&quot;tipo_despesa&quot;: &quot;MANUTENCAO_E_OPERACAO&quot;",
            "&quot;quantidade_parcelas&quot;: 1",
            "&quot;valor_total&quot;: &quot;1500.00&quot;",
            "&quot;cpf&quot;: &quot;99999999999&quot;",
            "CPF do faturado com dígitos verificadores inválidos.",
        ):
            with self.subTest(esperado=esperado):
                self.assertContains(resposta, esperado)

    def test_gemini_indisponivel_na_extracao(self):
        self.cliente_extrator.gerar_json.side_effect = GeminiTimeoutError(DETALHE_INTERNO)

        with self.assertLogs("documentos.processamento", "WARNING"), self.assertLogs(
            "agents.extrator.agent", "WARNING"
        ):
            resposta = self.enviar_real()

        self.assertContains(resposta, ExtracaoIndisponivelError.mensagem_padrao)
        self.assertContains(resposta, "Tente novamente mais tarde.")
        self.assertNotContains(resposta, DETALHE_INTERNO)
        self.cliente_classificador.gerar_json.assert_not_called()

    def test_erro_inesperado(self):
        self.cliente_extrator.gerar_json.side_effect = RuntimeError(DETALHE_INTERNO)

        with self.assertLogs("documentos.processamento", "ERROR"):
            resposta = self.enviar_real()

        self.assertContains(resposta, "Erro inesperado ao processar o documento.")
        self.assertNotContains(resposta, DETALHE_INTERNO)
        self.assertNotContains(resposta, "Traceback")
        self.cliente_classificador.gerar_json.assert_not_called()

    def test_classificacao_inconclusiva(self):
        self.cliente_classificador.gerar_json.return_value = {
            "tipo_despesa": None,
            "justificativa": "Itens fora das categorias.",
        }

        with self.assertLogs("documentos.processamento", "WARNING"):
            resposta = self.enviar_real()

        self.assertContains(resposta, "A despesa não se encaixa nas categorias disponíveis no MVP.")
        self.assertContains(resposta, views.SUGESTOES_ERRO["classificacao_inconclusiva"])
        self.assertNotContains(resposta, "JSON final")


class JavaScriptTests(InterfaceTestBase):
    """JS mínimo de proteção visual. Sem navegador automatizado no projeto, os
    testes conferem o arquivo e a marcação que ele usa."""

    def js(self):
        return ARQUIVO_JS.read_text()

    def test_arquivo_existe_e_e_encontrado_pelo_staticfiles(self):
        self.assertEqual(Path(finders.find("documentos/documentos.js")), ARQUIVO_JS)

    def test_base_carrega_o_js_com_defer(self):
        self.assertContains(
            self.client.get(self.url),
            '<script src="/static/documentos/documentos.js" defer></script>',
            html=False,
        )

    def test_js_so_age_nos_formularios_marcados(self):
        js = self.js()

        self.assertIn("form[data-submit-lock]", js)
        self.assertIn("data-submit-texto", js)
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

        for proibido in ("fetch(", "XMLHttpRequest", "WebSocket", "setInterval",
                         "innerHTML", "outerHTML", "insertAdjacentHTML", "eval(",
                         "new Function", "document.write", "localStorage"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, js)

    def test_js_sem_referencia_a_gemini_ou_chave(self):
        js = self.js().lower()

        for proibido in ("gemini", "api_key", "apikey", "senha", "password"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, js)

    def test_templates_sem_js_inline_nem_requisicoes(self):
        for template in [*PASTA_TEMPLATES.glob("*.html"), *PASTA_TEMPLATES_USUARIOS.glob("*.html")]:
            with self.subTest(template=template.name):
                conteudo = template.read_text()
                self.assertNotIn("fetch(", conteudo)
                self.assertNotIn("XMLHttpRequest", conteudo)
                self.assertNotIn("<script>", conteudo)
