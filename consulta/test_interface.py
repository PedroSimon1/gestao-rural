"""Tela /consulta/: formulário, resposta com fontes, erros, sigilo da chave e acesso."""

import logging
import re
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from agents.gemini_client import GeminiAPIError
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .test_servico import ClienteFalso
from .test_texto import DadosConsulta

CHAVE = "chave-sentinela-tela-consulta-9f3a"
PERGUNTA = "Quanto gastei com sal mineral?"


def _dados(**alteracoes):
    return {"pergunta": PERGUNTA, "modo": "simples", "gemini_api_key": CHAVE, **alteracoes}


@override_settings(**CREDENCIAIS_TESTE)
class TelaConsultaTests(DadosConsulta, TestCase):
    def setUp(self):
        super().setUp()
        autenticar_demo(self.client)
        self.url = reverse("consulta")

    def post(self, cliente=None, **alteracoes):
        cliente = cliente or ClienteFalso("Gastou R$ 1.250,40 (#1).")
        with mock.patch("consulta.servico.GeminiClient", return_value=cliente) as fabrica:
            resposta = self.client.post(self.url, _dados(**alteracoes))
        self.fabrica = fabrica
        return resposta

    def test_rota(self):
        self.assertEqual(self.url, "/consulta/")

    def test_get_mostra_formulario_aviso_de_privacidade_e_trava_de_envio(self):
        resposta = self.client.get(self.url)
        html = resposta.content.decode()
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Google Gemini", html)
        self.assertIn("sem CPF/CNPJ", html)
        self.assertIn("dados fictícios", html)
        self.assertRegex(html, r'<form\b[^>]*method="post"[^>]*data-submit-lock')
        self.assertContains(resposta, "<textarea", status_code=200)
        self.assertRegex(html, r'<input type="password"[^>]*name="gemini_api_key"|name="gemini_api_key"[^>]*type="password"')
        self.assertRegex(html, r'<input[^>]*name="gemini_api_key"[^>]*autocomplete="off"')
        self.assertNotRegex(html, r'name="gemini_api_key"[^>]*\bvalue=')
        self.assertContains(resposta, 'name="modo"')
        self.assertNotContains(resposta, "Fontes consultadas")

    def test_get_organiza_a_tela_em_passos_e_explica_cada_parte(self):
        html = self.client.get(self.url).content.decode()
        for titulo in ("Como funciona", "1. Sua pergunta", "2. Como buscar as contas", "3. Chave do Gemini", "Índice semântico"):
            self.assertIn(titulo, html)
        # Cada forma de busca traz o seu texto, ligado ao rádio por aria-describedby.
        for codigo in ("simples", "semantico"):
            self.assertRegex(html, rf'<input type="radio" name="modo" value="{codigo}"[^>]*aria-describedby="id_modo_\d_descricao"')
        self.assertIn("Procura as palavras da sua pergunta", html)
        self.assertIn("Procura pelo sentido da pergunta", html)
        # Cada contagem do índice é explicada.
        for explicacao in ("Total de contas lançadas.", "Prontas para a busca semântica.", "Ainda fora da busca semântica.", "Mudaram depois de indexadas"):
            self.assertIn(explicacao, html)

    def test_botao_consultar_fica_no_card_da_chave_e_o_indice_diz_o_que_faz(self):
        html = self.client.get(self.url).content.decode()
        inicio = html.index('aria-labelledby="titulo-passo-chave"')
        card = html[inicio:html.index("</section>", inicio)]
        # O envio da pergunta fica junto da chave do passo 3, no mesmo card e no mesmo formulário.
        self.assertIn(">Consultar</button>", card)
        self.assertIn('name="gemini_api_key"', card)
        self.assertEqual(html.count(">Consultar</button>"), 1)
        # O card do índice deixa claro que "Atualizar índice" não responde perguntas.
        self.assertIn("só prepara a busca semântica; ele não responde perguntas", html)

    def test_campo_da_pergunta_aparece_em_destaque_com_dica_de_onde_escrever(self):
        html = self.client.get(self.url).content.decode()
        inicio = html.index('aria-labelledby="titulo-passo-pergunta"')
        card = html[inicio - 40:html.index("</section>", inicio)]
        self.assertIn("cartao--destaque", card)
        self.assertIn("Comece por aqui", card)
        self.assertRegex(card, r'<textarea[^>]*class="formulario__campo campo-pergunta"')
        self.assertRegex(card, r'<textarea[^>]*placeholder="Escreva aqui a sua pergunta…"')

    def test_post_valido_mostra_resposta_escapada_com_quebras_e_fontes_com_link(self):
        racao = self.criar_nota(descricao="Sal mineral")
        cliente = ClienteFalso("Total <b>R$ 1.250,40</b>\nsegunda linha (#%d)" % racao.pk)

        resposta = self.post(cliente)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Total &lt;b&gt;R$ 1.250,40&lt;/b&gt;<br>segunda linha")
        self.assertNotContains(resposta, "<b>R$ 1.250,40</b>")
        self.assertContains(resposta, "Fontes consultadas")
        self.assertContains(resposta, f'<a href="{reverse("conta_detalhe", args=[racao.pk])}">')
        self.assertContains(resposta, f"Conta a pagar #{racao.pk} — Fornecedor Teste — R$ 1.250,40")
        self.assertContains(resposta, "sal (itens)")
        self.assertContains(resposta, "pontuação 4")
        self.assertContains(resposta, "Forma de busca usada: Busca simples")
        self.fabrica.assert_called_once_with(api_key=CHAVE)

    def test_pergunta_permanece_no_campo_e_chave_nao(self):
        self.criar_nota()
        resposta = self.post()
        self.assertRegex(resposta.content.decode(), r"<textarea[^>]*>\s*" + re.escape(PERGUNTA) + r"\s*</textarea>")
        self.assertNotContains(resposta, CHAVE)

    def test_campos_obrigatorios_e_limites_nao_chamam_o_servico(self):
        self.criar_nota()
        casos = (
            ({"pergunta": ""}, "Digite a pergunta."),
            ({"pergunta": "   "}, "Digite a pergunta."),
            ({"gemini_api_key": ""}, "Informe a Gemini API Key."),
            ({"gemini_api_key": "x" * 257}, "no máximo 256 caracteres"),
            ({"pergunta": "a" * 501}, "no máximo 500 caracteres"),
            ({"modo": "inexistente"}, "forma de busca válida"),
            ({"modo": ""}, "Escolha uma forma de busca."),
        )
        for alteracao, mensagem in casos:
            with self.subTest(alteracao={k: v[:10] for k, v in alteracao.items()}):
                resposta = self.post(**alteracao)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, mensagem)
                self.assertNotContains(resposta, "Fontes consultadas")
                self.fabrica.assert_not_called()

    def test_erro_do_servico_aparece_como_alerta_sem_detalhes_e_mantem_a_pergunta(self):
        self.criar_nota()
        cliente = ClienteFalso(erro=GeminiAPIError("detalhe-interno-tela", status_code=429))
        with self.assertLogs("consulta.servico", "WARNING"):
            resposta = self.post(cliente)
        self.assertContains(resposta, 'role="alert"')
        self.assertContains(resposta, "limite de uso da Gemini API Key")
        self.assertNotContains(resposta, "detalhe-interno-tela")
        self.assertContains(resposta, PERGUNTA)
        self.assertNotContains(resposta, "Fontes consultadas")

    def test_sem_dados_mostra_mensagem_sem_chamar_o_gemini(self):
        resposta = self.post()
        self.assertContains(resposta, "Ainda não há contas cadastradas")
        self.fabrica.assert_not_called()

    def test_chave_ausente_do_html_do_contexto_da_sessao_e_dos_logs(self):
        self.criar_nota()
        registros = []
        captura = logging.Handler(level=logging.DEBUG)
        captura.emit = lambda registro: registros.append(registro.getMessage())
        raiz = logging.getLogger()
        nivel_anterior = raiz.level
        raiz.addHandler(captura)
        raiz.setLevel(logging.DEBUG)
        self.addCleanup(raiz.setLevel, nivel_anterior)
        self.addCleanup(raiz.removeHandler, captura)

        cenarios = (
            ClienteFalso("Resposta qualquer"),
            ClienteFalso(erro=GeminiAPIError("falha", status_code=401)),
        )
        for cliente in cenarios:
            with self.subTest(erro=repr(cliente.erro)):
                resposta = self.post(cliente)
                self.assertNotContains(resposta, CHAVE)
                self.assertNotIn(CHAVE, repr(dict(self.client.session)))
                formulario = resposta.context["form"]
                self.assertNotIn(CHAVE, repr(formulario.data))
                self.assertNotIn("gemini_api_key", formulario.cleaned_data)
                for contexto in resposta.context:
                    self.assertNotIn(CHAVE, repr(contexto.flatten()))
                self.assertNotIn(CHAVE, repr(dict(resposta.headers)))
                self.assertNotIn(CHAVE, repr(dict(resposta.cookies)))
        self.assertTrue(registros)
        self.assertNotIn(CHAVE, "\n".join(registros))
        self.assertNotIn(PERGUNTA, "\n".join(registros))

    def test_chave_invalida_na_validacao_tambem_nao_volta_no_html(self):
        resposta = self.post(pergunta="", gemini_api_key=CHAVE)
        self.assertContains(resposta, "Digite a pergunta.")
        self.assertNotContains(resposta, CHAVE)

    def test_sem_login_redireciona_ao_login_sem_chamar_o_servico(self):
        anonimo = Client()
        with mock.patch("consulta.servico.GeminiClient") as fabrica:
            for metodo in (anonimo.get, anonimo.post):
                with self.subTest(metodo=metodo.__name__):
                    resposta = metodo(self.url)
                    self.assertRedirects(resposta, reverse("login"), fetch_redirect_response=False)
        fabrica.assert_not_called()

    def test_metodos_fora_de_get_e_post_sao_recusados(self):
        for metodo in ("put", "patch", "delete"):
            with self.subTest(metodo=metodo):
                self.assertEqual(getattr(self.client, metodo)(self.url).status_code, 405)

    def test_menu_marca_consultar_como_pagina_atual(self):
        html = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r'<a href="[^"]+" aria-current="page">([^<]+)</a>', html), ["Consultar"])
        self.assertIn(f'<a href="{self.url}" aria-current="page">Consultar</a>', html)
        outra = self.client.get(reverse("contas")).content.decode()
        self.assertIn(f'<a href="{self.url}">Consultar</a>', outra)
