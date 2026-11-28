"""Modo semântico e "Atualizar índice": serviço e tela, com Gemini falso (sem rede) e banco local."""

import logging
import re
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from agents.gemini_client import (
    GeminiAPIError, GeminiConfiguracaoError, GeminiRespostaInvalidaError, GeminiTimeoutError,
)
from cadastros.models import Pessoa
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .indexacao import SituacaoIndice, atualizar_indice
from .models import EmbeddingMovimento
from .servico import (
    MODO_SEMANTICO, MODO_SIMPLES, ConsultaError, atualizar_indice_com_chave, consultar,
    descrever_atualizacao,
)
from .test_indexacao import ClienteEmbeddingFalso
from .test_texto import DadosConsulta

CHAVE = "chave-sentinela-semantica-7c1d"
PERGUNTA = "Qual foi a compra de ração?"
CONFIGURACAO_INDICE = {"GEMINI_MODELO_EMBEDDING": "modelo-teste", "GEMINI_DIMENSAO_EMBEDDING": "8"}

CASOS_DE_ERRO = (
    (GeminiAPIError("detalhe-interno-x", status_code=400), "chave_invalida"),
    (GeminiAPIError("detalhe-interno-x", status_code=401), "chave_invalida"),
    (GeminiAPIError("detalhe-interno-x", status_code=403), "chave_invalida"),
    (GeminiAPIError("detalhe-interno-x", status_code=429), "limite_excedido"),
    (GeminiAPIError("detalhe-interno-x", status_code=500), "servico_indisponivel"),
    (GeminiTimeoutError("detalhe-interno-x"), "tempo_esgotado"),
    (GeminiRespostaInvalidaError("detalhe-interno-x"), "resposta_invalida"),
    (GeminiConfiguracaoError("detalhe-interno-x"), "servico_indisponivel"),
)


class ClienteSemanticoFalso(ClienteEmbeddingFalso):
    """Embeddings determinísticos mais a geração de texto, tudo registrado."""

    def __init__(self, texto="Foi a conta #1.", **kwargs):
        super().__init__(**kwargs)
        self.texto = texto
        self.conteudos = []

    def gerar_conteudo(self, conteudo, **kwargs):
        self.conteudos.append(conteudo)
        return self.texto


class NotasIndexaveis(DadosConsulta):
    def criar_tres_notas(self):
        self.racao = self.criar_nota(numero=1, descricao="Ração bovina")
        self.vacina = self.criar_nota(numero=2, descricao="Vacina aftosa")
        self.arame = self.criar_nota(numero=3, descricao="Arame farpado")

    def indexar(self, limite=10):
        return atualizar_indice(ClienteEmbeddingFalso(), limite)


@override_settings(RAG_TOP_K="5", RAG_LOTE_INDEXACAO="20", **CONFIGURACAO_INDICE)
class ConsultaSemanticaServicoTests(NotasIndexaveis, TestCase):
    def consultar(self, cliente, pergunta=PERGUNTA):
        with mock.patch("consulta.servico.GeminiClient", return_value=cliente) as fabrica:
            try:
                return consultar(pergunta, MODO_SEMANTICO, CHAVE)
            finally:
                self.fabrica = fabrica

    def test_fluxo_feliz_ordena_por_cosseno_e_exibe_a_pontuacao(self):
        self.criar_tres_notas()
        self.indexar()
        cliente = ClienteSemanticoFalso()

        resposta = self.consultar(cliente)

        self.assertEqual(resposta.modo, MODO_SEMANTICO)
        self.assertEqual(resposta.resposta, "Foi a conta #1.")
        self.assertEqual(resposta.fontes[0].movimento_id, self.racao.pk)
        self.assertEqual(resposta.fontes[0].pontuacao, 1.0)
        self.assertEqual(resposta.fontes[0].motivo, "similaridade 1,00")
        self.assertEqual({f.pontuacao for f in resposta.fontes[1:]}, {0.0})
        self.assertIsNone(resposta.aviso)
        self.fabrica.assert_called_once_with(api_key=CHAVE)
        # Uma chamada de embedding (a pergunta) e uma de geração de texto.
        self.assertEqual([tarefa for _, tarefa in cliente.chamadas], ["RETRIEVAL_QUERY"])
        self.assertEqual(len(cliente.conteudos), 1)

    @override_settings(RAG_TOP_K="1")
    def test_prompt_recebe_contexto_so_do_movimento_de_maior_cosseno(self):
        self.criar_tres_notas()
        self.indexar()
        cliente = ClienteSemanticoFalso()

        resposta = self.consultar(cliente)

        prompt = cliente.conteudos[0]
        self.assertEqual(len(resposta.fontes), 1)
        self.assertEqual(prompt.count("### MOVIMENTO #"), 1)
        self.assertIn(f"### MOVIMENTO #{self.racao.pk}", prompt)
        for fora in (self.vacina, self.arame):
            self.assertNotIn(f"### MOVIMENTO #{fora.pk}", prompt)
        self.assertNotIn("Vacina", prompt)
        for proibido in (CHAVE, self.fornecedor.documento, self.faturado.documento):
            self.assertNotIn(proibido, prompt)

    def test_indice_vazio_orienta_a_atualizar_e_nao_chama_o_gerador(self):
        self.criar_tres_notas()
        cliente = ClienteSemanticoFalso()
        with self.assertLogs("consulta.servico", "WARNING") as logs, self.assertRaises(ConsultaError) as contexto:
            self.consultar(cliente)
        self.assertEqual(contexto.exception.codigo, "indice_vazio")
        self.assertIn("Atualizar índice", contexto.exception.mensagem)
        self.assertEqual(cliente.conteudos, [])
        self.assertEqual(logs.output, ["WARNING:consulta.servico:Consulta falhou (indice_vazio)."])

    def test_aviso_informa_quantos_movimentos_ficaram_fora_do_indice(self):
        self.criar_tres_notas()
        self.indexar(2)
        resposta = self.consultar(ClienteSemanticoFalso())
        self.assertIn(": 1.", resposta.aviso)
        self.assertIn("Atualizar índice", resposta.aviso)

        # Desatualizado (texto estável mudou) também conta como fora do índice.
        self.indexar(10)
        self.assertIsNone(self.consultar(ClienteSemanticoFalso()).aviso)
        Pessoa.objects.filter(pk=self.fornecedor.pk).update(razao_social="Fornecedor Renomeado")
        resposta = self.consultar(ClienteSemanticoFalso())
        self.assertIn(": 3.", resposta.aviso)

    def test_sem_pendencias_nao_ha_aviso(self):
        self.criar_tres_notas()
        self.indexar()
        self.assertIsNone(self.consultar(ClienteSemanticoFalso()).aviso)

    def test_erros_do_gemini_nos_embeddings_usam_o_mesmo_mapeamento(self):
        self.criar_tres_notas()
        self.indexar()
        for erro, codigo in CASOS_DE_ERRO:
            with self.subTest(codigo=codigo, erro=type(erro).__name__):
                cliente = ClienteSemanticoFalso(erro=erro)
                with self.assertLogs("consulta.servico", "WARNING") as logs, self.assertRaises(ConsultaError) as contexto:
                    self.consultar(cliente)
                self.assertEqual(contexto.exception.codigo, codigo)
                self.assertNotIn("detalhe-interno-x", contexto.exception.mensagem)
                self.assertIsNone(contexto.exception.__cause__)
                self.assertEqual(cliente.conteudos, [])
                texto = " ".join(logs.output)
                for sigiloso in ("detalhe-interno-x", CHAVE, PERGUNTA):
                    self.assertNotIn(sigiloso, texto)

    def test_vetor_invalido_vindo_do_gemini_e_resposta_invalida(self):
        self.criar_tres_notas()
        self.indexar()
        cliente = ClienteSemanticoFalso(resposta=[[1.0, 0.0]])  # dimensão errada
        with self.assertLogs("consulta.servico", "WARNING"), self.assertRaises(ConsultaError) as contexto:
            self.consultar(cliente)
        self.assertEqual(contexto.exception.codigo, "resposta_invalida")

    def test_configuracao_do_indice_invalida_vira_erro_de_configuracao(self):
        self.criar_tres_notas()
        for dimensao in ("abc", "0", "", None):
            with self.subTest(dimensao=dimensao), override_settings(GEMINI_DIMENSAO_EMBEDDING=dimensao):
                with self.assertLogs("consulta.servico", "WARNING"), self.assertRaises(ConsultaError) as contexto:
                    self.consultar(ClienteSemanticoFalso())
                self.assertEqual(contexto.exception.codigo, "configuracao")
                self.assertNotIn("GEMINI_", contexto.exception.mensagem)

    def test_modo_simples_continua_sem_depender_do_indice(self):
        self.criar_tres_notas()
        with mock.patch("consulta.servico.GeminiClient", return_value=ClienteSemanticoFalso()):
            resposta = consultar("arame", MODO_SIMPLES, CHAVE)
        self.assertEqual(resposta.fontes[0].movimento_id, self.arame.pk)
        self.assertFalse(EmbeddingMovimento.objects.exists())


@override_settings(RAG_TOP_K="5", RAG_LOTE_INDEXACAO="2", **CONFIGURACAO_INDICE)
class AtualizarIndiceServicoTests(NotasIndexaveis, TestCase):
    def atualizar(self, cliente):
        with mock.patch("consulta.servico.GeminiClient", return_value=cliente) as fabrica:
            try:
                return atualizar_indice_com_chave(CHAVE)
            finally:
                self.fabrica = fabrica

    def test_lote_respeita_a_configuracao_e_o_segundo_clique_continua(self):
        self.criar_tres_notas()
        cliente = ClienteSemanticoFalso()

        self.assertEqual(self.atualizar(cliente), SituacaoIndice(3, 2, 0, 1))
        self.fabrica.assert_called_once_with(api_key=CHAVE)
        self.assertEqual(len(cliente.chamadas[0][0]), 2)
        self.assertEqual(self.atualizar(cliente), SituacaoIndice(3, 3, 0, 0))
        self.assertEqual(len(cliente.chamadas[1][0]), 1)
        self.assertEqual(self.atualizar(cliente), SituacaoIndice(3, 3, 0, 0))
        self.assertEqual(len(cliente.chamadas), 2)
        self.assertEqual(EmbeddingMovimento.objects.count(), 3)

    def test_lote_invalido_e_erro_de_configuracao_sem_chamar_o_gemini(self):
        self.criar_tres_notas()
        for valor in ("0", "-1", "abc", "", "2.5", None):
            with self.subTest(valor=valor), override_settings(RAG_LOTE_INDEXACAO=valor):
                with self.assertLogs("consulta.servico", "WARNING"), self.assertRaises(ConsultaError) as contexto:
                    self.atualizar(ClienteSemanticoFalso())
                self.assertEqual(contexto.exception.codigo, "configuracao")
                self.assertNotIn("RAG_LOTE", contexto.exception.mensagem)
                self.fabrica.assert_not_called()
        self.assertFalse(EmbeddingMovimento.objects.exists())

    def test_configuracao_do_indice_invalida_vira_erro_de_configuracao(self):
        self.criar_tres_notas()
        with override_settings(GEMINI_MODELO_EMBEDDING=""):
            with self.assertLogs("consulta.servico", "WARNING"), self.assertRaises(ConsultaError) as contexto:
                self.atualizar(ClienteSemanticoFalso())
        self.assertEqual(contexto.exception.codigo, "configuracao")

    def test_erros_do_gemini_sao_mapeados_sem_gravar_nem_vazar(self):
        self.criar_tres_notas()
        for erro, codigo in CASOS_DE_ERRO:
            with self.subTest(codigo=codigo, erro=type(erro).__name__):
                with self.assertLogs("consulta.servico", "WARNING") as logs, self.assertRaises(ConsultaError) as contexto:
                    self.atualizar(ClienteSemanticoFalso(erro=erro))
                self.assertEqual(contexto.exception.codigo, codigo)
                self.assertNotIn("detalhe-interno-x", contexto.exception.mensagem)
                self.assertIsNone(contexto.exception.__cause__)
                texto = " ".join(logs.output)
                for sigiloso in ("detalhe-interno-x", CHAVE):
                    self.assertNotIn(sigiloso, texto)
        self.assertFalse(EmbeddingMovimento.objects.exists())

    def test_falha_ao_criar_o_cliente_vira_servico_indisponivel(self):
        self.criar_tres_notas()
        with mock.patch("consulta.servico.GeminiClient", side_effect=GeminiConfiguracaoError("x")):
            with self.assertLogs("consulta.servico", "WARNING"), self.assertRaises(ConsultaError) as contexto:
                atualizar_indice_com_chave(CHAVE)
        self.assertEqual(contexto.exception.codigo, "servico_indisponivel")

    def test_mensagem_do_resultado(self):
        self.assertEqual(
            descrever_atualizacao(SituacaoIndice(3, 0, 0, 3), SituacaoIndice(3, 2, 0, 1)),
            'Indexados neste lote: 2. Total no índice: 2 de 3; faltam 1. '
            'Clique em "Atualizar índice" novamente para continuar.',
        )
        self.assertEqual(
            descrever_atualizacao(SituacaoIndice(3, 2, 0, 1), SituacaoIndice(3, 3, 0, 0)),
            "Indexados neste lote: 1. Total no índice: 3 de 3; faltam 0. O índice está completo.",
        )
        self.assertEqual(
            descrever_atualizacao(SituacaoIndice(3, 3, 0, 0), SituacaoIndice(3, 3, 0, 0)),
            "Indexados neste lote: 0. Total no índice: 3 de 3; faltam 0. O índice está completo.",
        )
        # Reindexar desatualizados também conta no lote.
        self.assertIn(
            "Indexados neste lote: 2.",
            descrever_atualizacao(SituacaoIndice(3, 1, 2, 0), SituacaoIndice(3, 3, 0, 0)),
        )


def _capturar_logs(teste):
    registros = []
    captura = logging.Handler(level=logging.DEBUG)
    captura.emit = lambda registro: registros.append(registro.getMessage())
    raiz = logging.getLogger()
    nivel_anterior = raiz.level
    raiz.addHandler(captura)
    raiz.setLevel(logging.DEBUG)
    teste.addCleanup(raiz.setLevel, nivel_anterior)
    teste.addCleanup(raiz.removeHandler, captura)
    return registros


@override_settings(RAG_TOP_K="5", RAG_LOTE_INDEXACAO="2", **CREDENCIAIS_TESTE, **CONFIGURACAO_INDICE)
class TelaSemanticaTests(NotasIndexaveis, TestCase):
    def setUp(self):
        super().setUp()
        autenticar_demo(self.client)
        self.url = reverse("consulta")
        self.url_indice = reverse("consulta_indice")

    def post_consulta(self, cliente, **alteracoes):
        dados = {"pergunta": PERGUNTA, "modo": MODO_SEMANTICO, "gemini_api_key": CHAVE, **alteracoes}
        with mock.patch("consulta.servico.GeminiClient", return_value=cliente) as fabrica:
            resposta = self.client.post(self.url, dados)
        self.fabrica = fabrica
        return resposta

    def post_indice(self, cliente, **dados):
        dados = {"gemini_api_key": CHAVE, **dados}
        with mock.patch("consulta.servico.GeminiClient", return_value=cliente) as fabrica:
            resposta = self.client.post(self.url_indice, dados)
        self.fabrica = fabrica
        return resposta

    def test_rotas(self):
        self.assertEqual(self.url_indice, "/consulta/indice/")

    def test_get_mostra_seletor_de_modo_estado_do_indice_e_formulario_de_atualizacao(self):
        self.criar_tres_notas()
        self.indexar(2)
        html = self.client.get(self.url).content.decode()

        self.assertRegex(html, r'<input type="radio" name="modo" value="simples"')
        self.assertRegex(html, r'<input type="radio" name="modo" value="semantico"')
        self.assertIn("Busca semântica", html)
        self.assertIn("Índice semântico", html)
        for rotulo, valor in (("Contas no sistema", 3), ("No índice", 2), ("Faltam entrar", 1), ("Mudaram", 0)):
            self.assertRegex(html, rf"<dt>{rotulo}[^<]*</dt><dd>{valor}<small>")
        self.assertIn("Atualizar índice", html)
        formulario = re.search(r'<form\b[^>]*action="/consulta/indice/"[^>]*>.*?</form>', html, re.S).group(0)
        self.assertRegex(formulario, r'<form\b[^>]*method="post"[^>]*data-submit-lock')
        self.assertRegex(formulario, r'<input type="password"[^>]*name="gemini_api_key"|name="gemini_api_key"[^>]*type="password"')
        self.assertRegex(formulario, r'<input[^>]*name="gemini_api_key"[^>]*autocomplete="off"')
        self.assertNotRegex(formulario, r'name="gemini_api_key"[^>]*\bvalue=')
        self.assertRegex(formulario, r'<label[^>]*for="id_indice_gemini_api_key"')
        self.assertRegex(html, r'<form\b[^>]*action="/consulta/"[^>]*data-submit-lock')
        ids = re.findall(r'\bid="([^"]+)"', html)
        self.assertEqual(sorted({i for i in ids if ids.count(i) > 1}), [])
        self.assertIn("atualizar o índice", html)

    def test_estado_do_indice_indisponivel_nao_quebra_a_pagina(self):
        self.criar_tres_notas()
        with override_settings(GEMINI_DIMENSAO_EMBEDDING="abc"):
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Estado do índice indisponível")
        self.assertContains(resposta, "Atualizar índice")
        self.assertNotContains(resposta, "Contas no sistema")

    def test_consulta_semantica_feliz_mostra_cosseno_e_aviso_de_pendentes(self):
        self.criar_tres_notas()
        self.indexar()
        self.criar_nota(numero=4, descricao="Diesel S10")  # ainda fora do índice
        cliente = ClienteSemanticoFalso(texto="Foi a compra <b>#1</b>.")
        resposta = self.post_consulta(cliente)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Foi a compra &lt;b&gt;#1&lt;/b&gt;.")
        self.assertContains(resposta, "Fontes consultadas")
        self.assertRegex(resposta.content.decode(), r"cosseno 1[,.]00")
        self.assertContains(resposta, "<meter")
        self.assertContains(resposta, "Forma de busca usada: Busca semântica")
        self.assertContains(resposta, "Movimentos ainda fora do índice")
        self.fabrica.assert_called_once_with(api_key=CHAVE)

    def test_indice_vazio_mostra_orientacao_na_tela(self):
        self.criar_tres_notas()
        cliente = ClienteSemanticoFalso()
        with self.assertLogs("consulta.servico", "WARNING"):
            resposta = self.post_consulta(cliente)
        self.assertContains(resposta, 'role="alert"')
        self.assertContains(resposta, "índice semântico ainda está vazio")
        self.assertNotContains(resposta, "Fontes consultadas")
        self.assertEqual(cliente.conteudos, [])

    def test_estado_do_indice_resume_se_esta_incompleto_ou_em_dia(self):
        self.criar_tres_notas()
        self.indexar(2)
        html = self.client.get(self.url).content.decode()
        self.assertIn("Índice incompleto", html)
        self.assertIn("1 ainda não entrou no índice", html)
        self.assertNotIn("Índice em dia", html)
        self.assertIn("resumo__item resumo__item--alerta", html)

        self.indexar(10)
        html = self.client.get(self.url).content.decode()
        self.assertIn("Índice em dia", html)
        self.assertIn("3 de 3 contas estão no índice", html)
        self.assertNotIn("Índice incompleto", html)
        self.assertNotIn("resumo__item--alerta", html)

    def test_atualizar_indice_em_lotes_mostra_mensagem_e_estado(self):
        self.criar_tres_notas()
        cliente = ClienteSemanticoFalso()

        resposta = self.post_indice(cliente)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Indexados neste lote: 2. Total no índice: 2 de 3; faltam 1.")
        self.assertContains(resposta, "Clique em &quot;Atualizar índice&quot; novamente para continuar.")
        self.assertRegex(resposta.content.decode(), r"<dt>No índice</dt><dd>2<small>")
        self.assertRegex(resposta.content.decode(), r"<dt>Faltam entrar</dt><dd>1<small>")
        self.fabrica.assert_called_once_with(api_key=CHAVE)
        self.assertEqual(EmbeddingMovimento.objects.count(), 2)

        resposta = self.post_indice(cliente)
        self.assertContains(resposta, "Indexados neste lote: 1. Total no índice: 3 de 3; faltam 0.")
        self.assertContains(resposta, "O índice está completo.")
        self.assertNotContains(resposta, "novamente para continuar")
        self.assertRegex(resposta.content.decode(), r"<dt>No índice</dt><dd>3<small>")
        self.assertEqual(EmbeddingMovimento.objects.count(), 3)

    def test_atualizar_indice_aparece_na_regiao_de_mensagens(self):
        self.criar_tres_notas()
        html = self.post_indice(ClienteSemanticoFalso()).content.decode()
        self.assertRegex(html, r'<div aria-live="polite">\s*<div class="aviso aviso--ok" role="status">')

    def test_erro_ao_atualizar_mostra_alerta_sem_detalhes_e_nao_grava(self):
        self.criar_tres_notas()
        cliente = ClienteSemanticoFalso(erro=GeminiAPIError("detalhe-interno-tela", status_code=429))
        with self.assertLogs("consulta.servico", "WARNING"):
            resposta = self.post_indice(cliente)
        self.assertContains(resposta, 'role="alert"')
        self.assertContains(resposta, "O índice não foi atualizado")
        self.assertContains(resposta, "limite de uso da Gemini API Key")
        self.assertNotContains(resposta, "detalhe-interno-tela")
        self.assertNotContains(resposta, "Indexados neste lote")
        self.assertFalse(EmbeddingMovimento.objects.exists())

    def test_lote_invalido_mostra_erro_de_configuracao_sem_chamar_o_gemini(self):
        self.criar_tres_notas()
        with override_settings(RAG_LOTE_INDEXACAO="0"), self.assertLogs("consulta.servico", "WARNING"):
            resposta = self.post_indice(ClienteSemanticoFalso())
        self.assertContains(resposta, "problema de configuração")
        self.assertNotContains(resposta, "RAG_LOTE_INDEXACAO")
        self.fabrica.assert_not_called()

    def test_configuracao_do_indice_invalida_ao_atualizar(self):
        self.criar_tres_notas()
        with override_settings(GEMINI_DIMENSAO_EMBEDDING="abc"), self.assertLogs("consulta.servico", "WARNING"):
            resposta = self.post_indice(ClienteSemanticoFalso())
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "problema de configuração")
        self.assertContains(resposta, "Estado do índice indisponível")

    def test_chave_obrigatoria_e_limitada_no_formulario_do_indice(self):
        self.criar_tres_notas()
        for chave, mensagem in (("", "Informe a Gemini API Key."), ("x" * 257, "no máximo 256 caracteres")):
            with self.subTest(tamanho=len(chave)):
                resposta = self.post_indice(ClienteSemanticoFalso(), gemini_api_key=chave)
                self.assertContains(resposta, mensagem)
                self.assertNotContains(resposta, "x" * 257)
                self.fabrica.assert_not_called()

    def test_chave_ausente_do_html_do_contexto_da_sessao_e_dos_logs_nos_dois_posts(self):
        self.criar_tres_notas()
        self.indexar(2)
        registros = _capturar_logs(self)
        envios = (
            ("consulta", lambda c: self.post_consulta(c)),
            ("indice", lambda c: self.post_indice(c)),
        )
        for nome, enviar in envios:
            for cliente in (
                ClienteSemanticoFalso(),
                ClienteSemanticoFalso(erro=GeminiAPIError("falha", status_code=401)),
            ):
                with self.subTest(post=nome, erro=repr(cliente.erro)):
                    resposta = enviar(cliente)
                    self.assertNotContains(resposta, CHAVE)
                    self.assertNotIn(CHAVE, repr(dict(self.client.session)))
                    for chave_form in ("form", "indice_form"):
                        formulario = resposta.context[chave_form]
                        self.assertNotIn(CHAVE, repr(formulario.data))
                        self.assertNotIn("gemini_api_key", getattr(formulario, "cleaned_data", {}))
                    for contexto in resposta.context:
                        self.assertNotIn(CHAVE, repr(contexto.flatten()))
                    self.assertNotIn(CHAVE, repr(dict(resposta.headers)))
                    self.assertNotIn(CHAVE, repr(dict(resposta.cookies)))
        self.assertTrue(registros)
        self.assertNotIn(CHAVE, "\n".join(registros))
        self.assertNotIn(PERGUNTA, "\n".join(registros))

    def test_sem_login_redireciona_sem_chamar_o_servico(self):
        anonimo = Client()
        with mock.patch("consulta.servico.GeminiClient") as fabrica:
            for metodo in (anonimo.get, anonimo.post):
                with self.subTest(metodo=metodo.__name__):
                    resposta = metodo(self.url_indice)
                    self.assertRedirects(resposta, reverse("login"), fetch_redirect_response=False)
        fabrica.assert_not_called()

    def test_indice_aceita_apenas_post(self):
        for metodo in ("get", "put", "patch", "delete"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(self.url_indice).status_code, 405)

    def test_pagina_do_indice_marca_consultar_no_menu(self):
        html = self.post_indice(ClienteSemanticoFalso()).content.decode()
        self.assertEqual(re.findall(r'<a href="[^"]+" aria-current="page">([^<]+)</a>', html), ["Consultar"])
