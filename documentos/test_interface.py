import inspect
import json
import logging
import os
import re
from pathlib import Path
from unittest import mock

import httpx
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from google.genai import errors

from agents import gemini_client
from agents.extrator.agent import ExtracaoIndisponivelError
from usuarios.demo import SESSAO_DEMO
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from . import forms, processamento as modulo_processamento, views
from .processamento import ProcessamentoError, ResultadoProcessamento
from .test_processamento import dados_nota

PDF = b"%PDF-1.4\n%%EOF\n"
# Chave fictícia; nenhuma chamada real ao Gemini é feita.
CHAVE_FORMULARIO = "CHAVE_CORRETA_DO_TESTE-n2-9f3a"
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

    def dados(self, arquivo=None, chave=CHAVE_FORMULARIO):
        dados = {} if arquivo is False else {"arquivo": arquivo or pdf()}
        if chave is not False:
            dados["gemini_api_key"] = chave
        return dados

    def enviar(self, arquivo=None, retorno=None, chave=CHAVE_FORMULARIO, **kwargs):
        """POST da chave e do PDF com processar_pdf simulado; devolve (resposta, mock)."""
        dados = self.dados(arquivo, chave)
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
                    resposta = getattr(self.client, metodo)(self.url, self.dados())

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

        processar.assert_called_once_with(PDF + b"conteudo", CHAVE_FORMULARIO)

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
        self.assertContains(resposta, views.SUGESTOES_ERRO["servico_indisponivel"])
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
            resposta = cliente.post(self.url, self.dados())

        self.assertEqual(resposta.status_code, 403)
        processar.assert_not_called()

    def test_csrf_do_formulario_da_pagina_e_aceito(self):
        cliente = Client(enforce_csrf_checks=True)
        autenticar_demo(cliente)
        pagina = cliente.get(self.url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina).group(1)

        with mock.patch("documentos.views.processar_pdf", return_value=processamento()) as processar:
            resposta = cliente.post(self.url, {**self.dados(), "csrfmiddlewaretoken": token})

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


class IntegracaoTestBase(InterfaceTestBase):
    """View + processar_pdf + Agents + GeminiClient REAIS; só o SDK do Gemini é falso."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("agents.gemini_client.genai.Client")
        self.sdk_classe = patcher.start()
        self.addCleanup(patcher.stop)
        self.generate_content = self.sdk_classe.return_value.models.generate_content
        self.respostas(
            {"tipo_despesa": "MANUTENCAO_E_OPERACAO", "justificativa": "Peças de manutenção."}
        )

    def respostas(self, classificacao):
        nota = dados_nota(parcelas=[{"data_vencimento": "2026-10-20", "valor": 1500}])
        self.generate_content.side_effect = [
            mock.Mock(text=json.dumps(nota)),
            mock.Mock(text=json.dumps(classificacao)),
        ]

    def enviar_real(self, chave=CHAVE_FORMULARIO):
        return self.client.post(self.url, self.dados(chave=chave))


class IntegracaoTests(IntegracaoTestBase):
    def test_sucesso_ponta_a_ponta(self):
        resposta = self.enviar_real()

        self.assertEqual(resposta.status_code, 200)
        parte_pdf = self.generate_content.call_args_list[0].kwargs["contents"][1]
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

    def test_extrator_e_classificador_usam_um_cliente_com_a_chave_do_formulario(self):
        self.enviar_real()

        # Um único SDK, criado com a chave da tela, atendeu as duas chamadas.
        self.sdk_classe.assert_called_once()
        self.assertEqual(self.sdk_classe.call_args.kwargs["api_key"], CHAVE_FORMULARIO)
        self.assertEqual(self.generate_content.call_count, 2)

    def test_espacos_externos_da_chave_sao_removidos(self):
        self.enviar_real(chave=f"  {CHAVE_FORMULARIO}  ")

        self.assertEqual(self.sdk_classe.call_args.kwargs["api_key"], CHAVE_FORMULARIO)

    def test_funciona_sem_gemini_api_key_e_com_google_api_key_no_ambiente(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "CHAVE_ERRADA_DO_AMBIENTE"}):
            os.environ.pop("GEMINI_API_KEY", None)
            resposta = self.enviar_real()

        self.assertContains(resposta, "JSON final")
        self.assertEqual(self.sdk_classe.call_args.kwargs["api_key"], CHAVE_FORMULARIO)

    def test_gemini_indisponivel_na_extracao(self):
        self.generate_content.side_effect = httpx.ReadTimeout(DETALHE_INTERNO)

        with self.assertLogs("documentos.processamento", "WARNING"), self.assertLogs(
            "agents.extrator.agent", "WARNING"
        ):
            resposta = self.enviar_real()

        self.assertContains(resposta, ExtracaoIndisponivelError.mensagem_padrao)
        self.assertContains(resposta, views.SUGESTOES_ERRO["servico_indisponivel"])
        self.assertNotContains(resposta, DETALHE_INTERNO)
        self.assertEqual(self.generate_content.call_count, 1)

    def test_chave_recusada_pela_api_mostra_erro_seguro(self):
        self.generate_content.side_effect = errors.ClientError(
            400,
            {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                       "message": f"API key not valid: {CHAVE_FORMULARIO}"}},
        )

        with self.assertLogs(level="WARNING") as logs:
            resposta = self.enviar_real()

        self.assertContains(resposta, ExtracaoIndisponivelError.mensagem_padrao)
        self.assertContains(resposta, "Confira se a Gemini API Key informada é válida.")
        for vazamento in (CHAVE_FORMULARIO, "INVALID_ARGUMENT", "API key not valid", "Traceback"):
            with self.subTest(vazamento=vazamento):
                self.assertNotContains(resposta, vazamento)
        self.assertNotIn(CHAVE_FORMULARIO, "\n".join(logs.output))

    def test_erro_inesperado(self):
        self.generate_content.side_effect = RuntimeError(DETALHE_INTERNO)

        with self.assertLogs("documentos.processamento", "ERROR"):
            resposta = self.enviar_real()

        self.assertContains(resposta, "Erro inesperado ao processar o documento.")
        self.assertNotContains(resposta, DETALHE_INTERNO)
        self.assertNotContains(resposta, "Traceback")
        self.assertEqual(self.generate_content.call_count, 1)

    def test_classificacao_inconclusiva(self):
        self.respostas({"tipo_despesa": None, "justificativa": "Itens fora das categorias."})

        with self.assertLogs("documentos.processamento", "WARNING"):
            resposta = self.enviar_real()

        self.assertContains(resposta, "A despesa não se encaixa nas categorias disponíveis no MVP.")
        self.assertContains(resposta, views.SUGESTOES_ERRO["classificacao_inconclusiva"])
        self.assertNotContains(resposta, "JSON final")


class GeminiApiKeyFormularioTests(InterfaceTestBase):
    """Campo da Gemini API Key: obrigatório, password e nunca devolvido no HTML."""

    def campo(self, resposta):
        return re.search(r'<input[^>]*name="gemini_api_key"[^>]*>', resposta.content.decode()).group(0)

    def test_campo_aparece_como_password_obrigatorio(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, '<label for="id_gemini_api_key" class="formulario__rotulo">Gemini API Key</label>', html=True)
        campo = self.campo(resposta)
        self.assertIn('type="password"', campo)
        self.assertIn("required", campo)
        self.assertIn('autocomplete="off"', campo)
        self.assertIn('maxlength="256"', campo)
        self.assertNotIn("value=", campo)
        self.assertContains(
            resposta, "A chave é utilizada somente durante este processamento e não é armazenada."
        )

    def test_chave_e_pdf_no_mesmo_formulario(self):
        html = self.client.get(self.url).content.decode()
        formulario = re.search(r"<form.*?</form>", html, re.S).group(0)

        self.assertEqual(html.count("<form"), 1)  # um único formulário e um único POST
        self.assertIn('name="gemini_api_key"', formulario)
        self.assertIn('name="arquivo"', formulario)
        self.assertLess(formulario.index("gemini_api_key"), formulario.index('name="arquivo"'))

    def test_campo_nao_usa_render_value(self):
        self.assertFalse(forms.DocumentoUploadForm.base_fields["gemini_api_key"].widget.render_value)

    def test_chave_ausente_vazia_ou_so_com_espacos_e_recusada(self):
        for chave in (False, "", "   ", "\t \n"):
            with self.subTest(chave=chave):
                resposta, processar = self.enviar(chave=chave)

                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "Informe a Gemini API Key.")
                self.assertIn('aria-invalid="true"', self.campo(resposta))
                processar.assert_not_called()

    def test_chave_longa_demais_e_recusada_sem_ser_exibida(self):
        chave = "k" * 300
        resposta, processar = self.enviar(chave=chave)

        self.assertContains(resposta, "A Gemini API Key deve ter no máximo 256 caracteres.")
        self.assertNotContains(resposta, chave[:40])
        processar.assert_not_called()

    def test_formato_da_chave_nao_e_validado_localmente(self):
        for chave in ("qualquer-formato", "AIza-sem-garantia", "abc 123"):
            with self.subTest(chave=chave):
                _, processar = self.enviar(chave=chave, retorno=processamento())

                processar.assert_called_once_with(PDF, chave)

    def test_chave_nao_reaparece_apos_sucesso(self):
        resposta, _ = self.enviar(retorno=processamento())

        self.assertContains(resposta, "JSON final")
        self.assertNotContains(resposta, CHAVE_FORMULARIO)
        self.assertNotIn("value=", self.campo(resposta))

    def test_chave_nao_reaparece_apos_erro_do_pdf(self):
        resposta, processar = self.enviar(pdf(conteudo=b"texto qualquer"))

        self.assertContains(resposta, "O arquivo enviado não é um PDF válido.")
        self.assertNotContains(resposta, CHAVE_FORMULARIO)
        self.assertNotIn("value=", self.campo(resposta))
        processar.assert_not_called()

    def test_chave_nao_reaparece_apos_erro_de_processamento(self):
        erro = ProcessamentoError("extracao", "servico_indisponivel", "Serviço de extração indisponível no momento.")
        resposta, _ = self.enviar(side_effect=erro)

        self.assertContains(resposta, "não foi concluído")
        self.assertNotContains(resposta, CHAVE_FORMULARIO)
        self.assertNotIn("value=", self.campo(resposta))

    def test_chave_fora_das_mensagens_e_do_contexto(self):
        for kwargs in ({"retorno": processamento()},
                       {"side_effect": ProcessamentoError("x", "servico_indisponivel", "Falhou.")}):
            with self.subTest(kwargs=list(kwargs)):
                resposta, _ = self.enviar(**kwargs)

                self.assertEqual(resposta.context["form"].data, {})  # formulário novo
                for nome in resposta.context.keys() - {"request"}:
                    self.assertNotIn(CHAVE_FORMULARIO, repr(resposta.context[nome]), nome)

    def test_nova_visita_e_nova_execucao_exigem_nova_chave(self):
        self.enviar(retorno=processamento())

        visita = self.client.get(self.url)
        self.assertNotContains(visita, CHAVE_FORMULARIO)
        self.assertNotIn("value=", self.campo(visita))

        resposta, processar = self.enviar(chave=False)
        self.assertContains(resposta, "Informe a Gemini API Key.")
        processar.assert_not_called()

    def test_view_oculta_a_chave_nos_relatorios_de_erro(self):
        # sensitive_post_parameters marca a requisição; o relatório de erro do
        # Django troca o valor do campo por asteriscos.
        with mock.patch("documentos.views.render", return_value=HttpResponse()) as render, mock.patch(
            "documentos.views.processar_pdf", return_value=processamento()
        ):
            self.client.post(self.url, self.dados())

        requisicao = render.call_args.args[0]
        self.assertEqual(tuple(requisicao.sensitive_post_parameters), ("gemini_api_key",))


class NaoPersistenciaDaChaveTests(IntegracaoTestBase):
    """Depois de um processamento completo, a chave não fica em lugar nenhum."""

    def arquivos_do_projeto(self):
        raiz = Path(settings.BASE_DIR)
        return {
            arquivo for arquivo in raiz.rglob("*")
            if not {".git", ".venv", "__pycache__"} & set(arquivo.relative_to(raiz).parts)
        }

    def processar_com_logs(self):
        raiz = logging.getLogger()
        with self.assertLogs(raiz, "DEBUG") as logs:
            raiz.debug("marcador")  # assertLogs exige ao menos um registro
            resposta = self.enviar_real()
        self.assertContains(resposta, "JSON final")
        return resposta, "\n".join(logs.output)

    def test_chave_fora_da_sessao_e_do_cookie(self):
        resposta, _ = self.processar_com_logs()

        self.assertEqual(dict(self.client.session.items()), {SESSAO_DEMO: True})
        for cookie in (*resposta.cookies.values(), *self.client.cookies.values()):
            self.assertNotIn(CHAVE_FORMULARIO, cookie.value)

    def test_chave_fora_da_resposta_e_do_json(self):
        resposta, _ = self.processar_com_logs()

        self.assertNotContains(resposta, CHAVE_FORMULARIO)
        self.assertNotIn(CHAVE_FORMULARIO, resposta.context["json_resultado"])
        self.assertNotIn(CHAVE_FORMULARIO, str(dict(resposta.headers)))

    def test_chave_fora_dos_logs(self):
        _, logs = self.processar_com_logs()

        self.assertNotIn(CHAVE_FORMULARIO, logs)

    def test_nenhum_arquivo_criado(self):
        antes = self.arquivos_do_projeto()

        self.processar_com_logs()

        self.assertEqual(self.arquivos_do_projeto() - antes, set())

    def test_chave_fora_de_variaveis_globais_settings_e_ambiente(self):
        modulos = (views, forms, modulo_processamento, gemini_client)
        settings_antes = dict(vars(settings._wrapped))

        self.processar_com_logs()

        for modulo in modulos:
            with self.subTest(modulo=modulo.__name__):
                for nome, valor in vars(modulo).items():
                    self.assertNotIn(CHAVE_FORMULARIO, repr(valor), nome)
        self.assertEqual(dict(vars(settings._wrapped)), settings_antes)
        self.assertFalse(hasattr(settings, "GEMINI_API_KEY"))
        self.assertNotIn(CHAVE_FORMULARIO, repr(dict(os.environ)))

    def test_sem_banco(self):
        # SimpleTestCase já falha em qualquer consulta; aqui só se confirma o backend.
        self.processar_com_logs()

        self.assertEqual(connections["default"].settings_dict["ENGINE"], "django.db.backends.dummy")


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
