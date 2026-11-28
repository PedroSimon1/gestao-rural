"""Serviço de consulta com Gemini falso (sem rede) e dados fictícios no banco local."""

from unittest import mock

from django.test import TestCase, override_settings

from agents.gemini_client import (
    GeminiAPIError, GeminiConfiguracaoError, GeminiRespostaInvalidaError, GeminiTimeoutError,
)

from financeiro.servicos import registrar_movimento

from .servico import (
    MODO_SEMANTICO, MODO_SIMPLES, MODOS, ConsultaError, FonteExibida, RespostaConsulta, consultar,
)
from .test_texto import DadosConsulta

CHAVE = "chave-ficticia-servico-consulta"
PERGUNTA = "Quanto gastei com sal mineral?"


class ClienteFalso:
    def __init__(self, resposta="Gastou R$ 1.250,40 (#1).", erro=None):
        self.resposta = resposta
        self.erro = erro
        self.chamadas = []

    def gerar_conteudo(self, conteudo, **kwargs):
        self.chamadas.append((conteudo, kwargs))
        if self.erro:
            raise self.erro
        return self.resposta


class ServicoConsultaTests(DadosConsulta, TestCase):
    def consultar(self, cliente, pergunta=PERGUNTA, modo=MODO_SIMPLES):
        with mock.patch("consulta.servico.GeminiClient", return_value=cliente) as fabrica:
            try:
                return consultar(pergunta, modo, CHAVE)
            finally:
                self.fabrica = fabrica

    def test_fluxo_feliz_devolve_resposta_fontes_rotuladas_e_usa_a_chave_informada(self):
        racao = self.criar_nota(descricao="Sal mineral")
        cliente = ClienteFalso()

        resposta = self.consultar(cliente)

        self.assertIsInstance(resposta, RespostaConsulta)
        self.assertEqual((resposta.modo, resposta.pergunta, resposta.resposta),
                         (MODO_SIMPLES, PERGUNTA, "Gastou R$ 1.250,40 (#1)."))
        self.assertEqual(resposta.fontes, (FonteExibida(
            racao.pk, f"Conta a pagar #{racao.pk} — Fornecedor Teste — R$ 1.250,40", 4.0,
            resposta.fontes[0].motivo,
        ),))
        self.assertIn("sal (itens)", resposta.fontes[0].motivo)
        self.assertIsNone(resposta.aviso)
        self.fabrica.assert_called_once_with(api_key=CHAVE)
        self.assertEqual(len(cliente.chamadas), 1)

    def test_rotulo_de_conta_a_receber(self):
        movimento = self.criar_nota(descricao="Sal mineral")
        recebimento, _ = registrar_movimento(self.areceber())
        resposta = self.consultar(ClienteFalso(), "cliente venda")
        rotulos = {fonte.movimento_id: fonte.rotulo for fonte in resposta.fontes}
        self.assertEqual(rotulos[recebimento.pk], f"Conta a receber #{recebimento.pk} — Cliente Teste — R$ 900,00")
        self.assertNotIn(movimento.pk, rotulos)

    def test_prompt_recebe_so_o_contexto_recuperado_sem_documentos_nem_chave(self):
        racao = self.criar_nota(descricao="Sal mineral")
        arame = self.criar_nota(numero=124, descricao="Arame farpado")
        cliente = ClienteFalso()

        self.consultar(cliente, "sal")

        prompt, _ = cliente.chamadas[0]
        self.assertIn(f"### MOVIMENTO #{racao.pk}", prompt)
        self.assertNotIn(f"### MOVIMENTO #{arame.pk}", prompt)
        self.assertNotIn("Arame", prompt)
        for proibido in (CHAVE, self.fornecedor.documento, self.faturado.documento):
            self.assertNotIn(proibido, prompt)

    def test_sem_termo_casado_usa_mais_recentes_e_avisa(self):
        self.criar_nota(descricao="Sal mineral")
        resposta = self.consultar(ClienteFalso(), "zzzzzz")
        self.assertEqual(len(resposta.fontes), 1)
        self.assertIn("mais recentes", resposta.aviso)

    @override_settings(RAG_TOP_K="1")
    def test_rag_top_k_limita_as_fontes(self):
        for numero in (1, 2, 3):
            self.criar_nota(numero=numero, descricao="Sal mineral")
        cliente = ClienteFalso()
        resposta = self.consultar(cliente, "sal")
        self.assertEqual(len(resposta.fontes), 1)
        self.assertEqual(cliente.chamadas[0][0].count("### MOVIMENTO #"), 1)

    def test_sem_dados_nao_chama_o_gemini(self):
        with self.assertLogs("consulta.servico", "WARNING") as logs, self.assertRaises(ConsultaError) as contexto:
            self.consultar(ClienteFalso())
        self.assertEqual(contexto.exception.codigo, "sem_dados")
        self.fabrica.assert_not_called()
        self.assertEqual(logs.output, ["WARNING:consulta.servico:Consulta falhou (sem_dados)."])

    def test_erros_do_gemini_viram_mensagens_claras_sem_detalhe_interno(self):
        self.criar_nota()
        casos = (
            (GeminiAPIError("detalhe-interno-x", status_code=400), "chave_invalida"),
            (GeminiAPIError("detalhe-interno-x", status_code=401), "chave_invalida"),
            (GeminiAPIError("detalhe-interno-x", status_code=403), "chave_invalida"),
            (GeminiAPIError("detalhe-interno-x", status_code=429), "limite_excedido"),
            (GeminiAPIError("detalhe-interno-x", status_code=500), "servico_indisponivel"),
            (GeminiAPIError("detalhe-interno-x"), "servico_indisponivel"),
            (GeminiTimeoutError("detalhe-interno-x"), "tempo_esgotado"),
            (GeminiRespostaInvalidaError("detalhe-interno-x"), "resposta_invalida"),
            (GeminiConfiguracaoError("detalhe-interno-x"), "servico_indisponivel"),
        )
        for erro, codigo in casos:
            with self.subTest(erro=repr(erro), codigo=codigo):
                with self.assertLogs("consulta.servico", "WARNING") as logs, self.assertRaises(ConsultaError) as contexto:
                    self.consultar(ClienteFalso(erro=erro))
                self.assertEqual(contexto.exception.codigo, codigo)
                self.assertNotIn("detalhe-interno-x", contexto.exception.mensagem)
                self.assertIsNone(contexto.exception.__cause__)
                texto = " ".join(logs.output)
                for sigiloso in ("detalhe-interno-x", CHAVE, PERGUNTA):
                    self.assertNotIn(sigiloso, texto)

    def test_falha_ao_criar_o_cliente_vira_servico_indisponivel(self):
        self.criar_nota()
        with mock.patch("consulta.servico.GeminiClient", side_effect=GeminiConfiguracaoError("x")):
            with self.assertRaises(ConsultaError) as contexto:
                consultar(PERGUNTA, MODO_SIMPLES, CHAVE)
        self.assertEqual(contexto.exception.codigo, "servico_indisponivel")

    def test_modo_desconhecido_e_recusado(self):
        self.criar_nota()
        for modo in ("outro", ""):
            with self.subTest(modo=modo), self.assertRaises(ConsultaError) as contexto:
                self.consultar(ClienteFalso(), modo=modo)
            self.assertEqual(contexto.exception.codigo, "modo_invalido")
        self.assertEqual(list(MODOS), [MODO_SIMPLES, MODO_SEMANTICO])

    def test_pergunta_vazia_e_recusada_sem_chamar_o_gemini(self):
        self.criar_nota()
        with self.assertRaises(ConsultaError) as contexto:
            self.consultar(ClienteFalso(), "   ")
        self.assertEqual(contexto.exception.codigo, "pergunta_vazia")
        self.fabrica.assert_not_called()

    def test_rag_top_k_invalido_e_erro_de_configuracao_sem_detalhes(self):
        self.criar_nota()
        for valor in ("0", "-1", "abc", "", "2.5", None):
            with self.subTest(valor=valor), override_settings(RAG_TOP_K=valor):
                with self.assertRaises(ConsultaError) as contexto:
                    self.consultar(ClienteFalso())
                self.assertEqual(contexto.exception.codigo, "configuracao")
                self.assertNotIn("RAG_TOP_K", contexto.exception.mensagem)
                self.fabrica.assert_not_called()
