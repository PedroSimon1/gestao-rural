import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from agents.classificador.agent import (
    AgentClassificador,
    ClassificacaoInconclusivaError,
    ClassificacaoIndisponivelError,
    ClassificacaoInvalidaError,
)
from agents.classificador.schemas import ClassificacaoDespesa
from agents.extrator.agent import (
    AgentExtrator,
    DocumentoIlegivelError,
    ExtracaoIndisponivelError,
    ExtracaoInvalidaError,
)
from agents.extrator.schemas import NotaFiscalExtraida
from agents.gemini_client import GeminiClient

from .processamento import (
    MENSAGEM_ERRO_INTERNO,
    ProcessamentoError,
    ResultadoProcessamento,
    montar_resultado,
    processar_pdf,
)

PDF = b"%PDF-1.4\nconteudo de teste\n%%EOF\n"
DETALHE_INTERNO = "detalhe-interno-xyz"

CHAVES_RESULTADO = [
    "fornecedor",
    "faturado",
    "numero_nota",
    "data_emissao",
    "itens",
    "quantidade_parcelas",
    "parcelas",
    "valor_total",
    "tipo_despesa",
    "validacoes",
]


def dados_nota(parcelas=None):
    # Dados fictícios. O CPF 999.999.999-99 tem DV inválido de propósito.
    if parcelas is None:
        parcelas = [
            {"numero": 1, "data_vencimento": "2026-10-20", "valor": 750},
            {"numero": 2, "data_vencimento": "2026-11-20", "valor": 750},
        ]
    return {
        "documento_e_nota_fiscal": True,
        "fornecedor": {
            "razao_social": "Pecas Exemplo Ltda",
            "nome_fantasia": "Pecas Exemplo",
            "cnpj": "11.222.333/0001-81",
        },
        "faturado": {"nome": "Produtor Ficticio", "cpf": "999.999.999-99"},
        "numero_nota": "000123",
        "data_emissao": "2026-09-20",
        "itens": [
            {
                "descricao": "Filtro de oleo",
                "quantidade": 2,
                "valor_unitario": 500,
                "valor_total": 1000,
            },
            {"descricao": "Correia", "quantidade": 1, "valor_total": 500},
        ],
        "parcelas": parcelas,
        "valor_total": 1500,
    }


def nota_extraida(**kwargs):
    return NotaFiscalExtraida.model_validate(dados_nota(**kwargs))


def classificacao(tipo="MANUTENCAO_E_OPERACAO"):
    return ClassificacaoDespesa.model_validate(
        {"tipo_despesa": tipo, "justificativa": "Pecas de manutencao."}
    )


class MontarResultadoTests(SimpleTestCase):
    def test_chaves_do_json_final(self):
        resultado = montar_resultado(nota_extraida(), classificacao())

        self.assertEqual(list(resultado), CHAVES_RESULTADO)

    def test_documento_e_nota_fiscal_nao_entra_no_json_final(self):
        resultado = montar_resultado(nota_extraida(), classificacao())

        self.assertNotIn("documento_e_nota_fiscal", resultado)

    def test_conteudo_extraido_e_preservado(self):
        resultado = montar_resultado(nota_extraida(), classificacao())

        self.assertEqual(
            resultado["fornecedor"],
            {
                "razao_social": "Pecas Exemplo Ltda",
                "nome_fantasia": "Pecas Exemplo",
                "cnpj": "11222333000181",
            },
        )
        self.assertEqual(
            resultado["faturado"], {"nome": "Produtor Ficticio", "cpf": "99999999999"}
        )
        self.assertEqual(resultado["numero_nota"], "000123")
        self.assertEqual(
            [item["descricao"] for item in resultado["itens"]],
            ["Filtro de oleo", "Correia"],
        )

    def test_quantidade_de_parcelas(self):
        tres = [
            {"data_vencimento": "2026-10-20", "valor": 500},
            {"data_vencimento": "2026-11-20", "valor": 500},
            {"data_vencimento": "2026-12-20", "valor": 500},
        ]
        casos = (
            ([], 0),
            ([{"numero": 1, "data_vencimento": "2026-10-20", "valor": 1500}], 1),
            (tres, 3),
        )
        for parcelas, esperado in casos:
            with self.subTest(esperado=esperado):
                resultado = montar_resultado(
                    nota_extraida(parcelas=parcelas), classificacao()
                )

                self.assertEqual(resultado["quantidade_parcelas"], esperado)
                self.assertEqual(len(resultado["parcelas"]), esperado)

    def test_parcelas_numeradas_pelo_extrator_sao_mantidas(self):
        parcelas = [{"valor": 500}, {"valor": 1000}]

        resultado = montar_resultado(nota_extraida(parcelas=parcelas), classificacao())

        self.assertEqual([p["numero"] for p in resultado["parcelas"]], [1, 2])

    def test_tipo_despesa_como_string(self):
        for tipo in ("MANUTENCAO_E_OPERACAO", "INFRAESTRUTURA_E_UTILIDADES"):
            with self.subTest(tipo=tipo):
                resultado = montar_resultado(nota_extraida(), classificacao(tipo))

                self.assertEqual(resultado["tipo_despesa"], tipo)
                self.assertIs(type(resultado["tipo_despesa"]), str)

    def test_justificativa_nao_entra_no_json_final(self):
        resultado = montar_resultado(nota_extraida(), classificacao())

        self.assertNotIn("justificativa", json.dumps(resultado))

    def test_validacoes_sao_preservadas(self):
        resultado = montar_resultado(nota_extraida(), classificacao())

        self.assertEqual(
            resultado["validacoes"],
            {
                "fornecedor_cnpj": {"status": "valido", "motivo": None},
                "faturado_cpf": {
                    "status": "invalido",
                    "motivo": "digitos_verificadores_invalidos",
                },
            },
        )

    def test_dinheiro_e_datas_serializaveis(self):
        resultado = montar_resultado(nota_extraida(), classificacao())

        json.dumps(resultado)  # o mesmo json.dumps usado pela tela
        self.assertEqual(resultado["valor_total"], "1500.00")
        self.assertEqual(resultado["data_emissao"], "2026-09-20")
        self.assertEqual(resultado["itens"][0]["valor_unitario"], "500.00")
        self.assertEqual(resultado["itens"][0]["quantidade"], "2")
        self.assertIsNone(resultado["itens"][1]["valor_unitario"])
        self.assertEqual(
            resultado["parcelas"][0],
            {"numero": 1, "data_vencimento": "2026-10-20", "valor": "750.00"},
        )

    def test_funcao_pura(self):
        nota = nota_extraida()
        antes = nota.model_dump()

        primeiro = montar_resultado(nota, classificacao())
        segundo = montar_resultado(nota, classificacao())
        primeiro["parcelas"].append({"numero": 99})

        self.assertEqual(nota.model_dump(), antes)
        self.assertEqual(segundo["quantidade_parcelas"], 2)
        self.assertEqual(len(segundo["parcelas"]), 2)


# GEMINI_API_KEY ausente: mesmo que algo escape dos mocks, não há como autenticar.
# SimpleTestCase: qualquer consulta ao banco faria o teste falhar.
@override_settings(GEMINI_API_KEY=None, GEMINI_MODEL="modelo-teste")
class ProcessarPdfTestBase(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch(
            "agents.gemini_client.genai.Client",
            side_effect=AssertionError("O SDK real do Gemini não deve ser usado."),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.extrator = mock.Mock(spec=AgentExtrator)
        self.extrator.extrair.return_value = nota_extraida()
        self.classificador = mock.Mock(spec=AgentClassificador)
        self.classificador.classificar.return_value = classificacao()

    def processar(self, pdf=PDF):
        return processar_pdf(
            pdf, extrator=self.extrator, classificador=self.classificador
        )

    def assert_erro(self, etapa, codigo, mensagem=None):
        with self.assertLogs("documentos.processamento", "WARNING"):
            with self.assertRaises(ProcessamentoError) as contexto:
                self.processar()
        erro = contexto.exception
        self.assertEqual((erro.etapa, erro.codigo), (etapa, codigo))
        if mensagem is not None:
            self.assertEqual(erro.mensagem, mensagem)
            self.assertEqual(str(erro), mensagem)
        return erro


class ProcessarPdfSucessoTests(ProcessarPdfTestBase):
    def test_devolve_json_final_e_justificativa(self):
        processamento = self.processar()

        self.assertIsInstance(processamento, ResultadoProcessamento)
        self.assertEqual(
            processamento.resultado, montar_resultado(nota_extraida(), classificacao())
        )
        self.assertEqual(processamento.justificativa, "Pecas de manutencao.")

    def test_extrator_recebe_os_bytes_do_pdf(self):
        self.processar()

        self.extrator.extrair.assert_called_once_with(PDF)

    def test_classificador_recebe_a_nota_extraida(self):
        self.processar()

        self.classificador.classificar.assert_called_once_with(
            self.extrator.extrair.return_value
        )

    def test_agents_em_sequencia(self):
        ordem = []
        self.extrator.extrair.side_effect = lambda pdf: ordem.append("extrator") or nota_extraida()
        self.classificador.classificar.side_effect = (
            lambda nota: ordem.append("classificador") or classificacao()
        )

        self.processar()

        self.assertEqual(ordem, ["extrator", "classificador"])

    def test_agents_padrao_sao_criados_quando_nao_injetados(self):
        with mock.patch("documentos.processamento.AgentExtrator") as extrator, mock.patch(
            "documentos.processamento.AgentClassificador"
        ) as classificador:
            extrator.return_value.extrair.return_value = nota_extraida()
            classificador.return_value.classificar.return_value = classificacao()

            processar_pdf(PDF)

        extrator.assert_called_once_with()
        classificador.assert_called_once_with()


class ProcessarPdfErrosTests(ProcessarPdfTestBase):
    def test_cada_erro_do_extrator(self):
        for excecao in (
            DocumentoIlegivelError(),
            ExtracaoIndisponivelError(),
            ExtracaoInvalidaError("O documento enviado não foi reconhecido como nota fiscal."),
        ):
            with self.subTest(excecao=type(excecao).__name__):
                self.extrator.extrair.side_effect = excecao

                self.assert_erro("extracao", excecao.codigo, str(excecao))
                self.classificador.classificar.assert_not_called()

    def test_cada_erro_do_classificador(self):
        for excecao in (
            ClassificacaoIndisponivelError(),
            ClassificacaoInvalidaError(),
            ClassificacaoInconclusivaError(),
        ):
            with self.subTest(excecao=type(excecao).__name__):
                self.classificador.classificar.side_effect = excecao

                self.assert_erro("classificacao", excecao.codigo, str(excecao))

    def test_erro_esperado_nao_carrega_causa_nem_detalhes(self):
        erro_interno = RuntimeError(DETALHE_INTERNO)
        excecao = ExtracaoIndisponivelError()
        excecao.__cause__ = erro_interno
        self.extrator.extrair.side_effect = excecao

        erro = self.assert_erro("extracao", "servico_indisponivel")

        self.assertIsNone(erro.__cause__)
        self.assertTrue(erro.__suppress_context__)
        self.assertNotIn(DETALHE_INTERNO, erro.mensagem)

    def test_erro_inesperado_vira_erro_interno_seguro(self):
        for agente in ("extrator", "classificador"):
            with self.subTest(agente=agente):
                self.setUp()
                if agente == "extrator":
                    self.extrator.extrair.side_effect = RuntimeError(DETALHE_INTERNO)
                else:
                    self.classificador.classificar.side_effect = RuntimeError(DETALHE_INTERNO)

                with self.assertLogs("documentos.processamento", "ERROR") as logs:
                    with self.assertRaises(ProcessamentoError) as contexto:
                        self.processar()

                erro = contexto.exception
                self.assertEqual(
                    (erro.etapa, erro.codigo, erro.mensagem),
                    ("processamento", "erro_interno", MENSAGEM_ERRO_INTERNO),
                )
                self.assertIsNone(erro.__cause__)
                self.assertTrue(erro.__suppress_context__)
                # O traceback completo fica só no log do servidor.
                self.assertIn("Traceback", "\n".join(logs.output))

    def test_erro_de_configuracao_do_gemini_vira_servico_indisponivel(self):
        # Agents reais, GEMINI_API_KEY ausente: nenhuma chamada real possível.
        with self.assertLogs("documentos.processamento", "WARNING"), self.assertLogs(
            "agents.extrator.agent", "WARNING"
        ):
            with self.assertRaises(ProcessamentoError) as contexto:
                processar_pdf(PDF)

        self.assertEqual(contexto.exception.codigo, "servico_indisponivel")

    def test_pdf_ilegivel_com_agents_reais_nao_chama_o_gemini(self):
        with mock.patch.object(GeminiClient, "gerar_json") as gerar_json:
            with self.assertLogs("documentos.processamento", "WARNING"):
                with self.assertRaises(ProcessamentoError) as contexto:
                    processar_pdf(b"nao e pdf")

        self.assertEqual(contexto.exception.codigo, "documento_ilegivel")
        gerar_json.assert_not_called()
