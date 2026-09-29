import json
import logging
import os
from unittest import mock

from django.test import SimpleTestCase, override_settings
from google.genai import errors

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

from .processamento import (
    MENSAGEM_ERRO_INTERNO,
    MENSAGEM_GEMINI_NAO_CONFIGURADO,
    ProcessamentoError,
    ResultadoProcessamento,
    montar_resultado,
    processar_pdf,
)

PDF = b"%PDF-1.4\nconteudo de teste\n%%EOF\n"
CHAVE_FORMULARIO = "chave-do-formulario-teste-n2"
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


# SimpleTestCase: qualquer consulta ao banco faria o teste falhar.
@override_settings(GEMINI_MODEL="modelo-teste")
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
            pdf, CHAVE_FORMULARIO, extrator=self.extrator, classificador=self.classificador
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

    def test_agents_padrao_compartilham_um_cliente_com_a_chave_informada(self):
        with mock.patch("documentos.processamento.GeminiClient") as gemini, mock.patch(
            "documentos.processamento.AgentExtrator"
        ) as extrator, mock.patch(
            "documentos.processamento.AgentClassificador"
        ) as classificador:
            extrator.return_value.extrair.return_value = nota_extraida()
            classificador.return_value.classificar.return_value = classificacao()

            processar_pdf(PDF, CHAVE_FORMULARIO)

        gemini.assert_called_once_with(api_key=CHAVE_FORMULARIO)
        extrator.assert_called_once_with(cliente=gemini.return_value)
        classificador.assert_called_once_with(cliente=gemini.return_value)
        extrator.return_value.extrair.assert_called_once_with(PDF)


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

    def test_chave_ausente_vira_servico_indisponivel_sem_chamar_o_gemini(self):
        # Agents reais, sem chave: nenhuma chamada real possível.
        for chave in (None, "", "   "):
            with self.subTest(chave=chave):
                with self.assertLogs("documentos.processamento", "WARNING"):
                    with self.assertRaises(ProcessamentoError) as contexto:
                        processar_pdf(PDF, chave)

                erro = contexto.exception
                self.assertEqual(
                    (erro.etapa, erro.codigo, erro.mensagem),
                    ("configuracao", "servico_indisponivel", MENSAGEM_GEMINI_NAO_CONFIGURADO),
                )
                self.assertIsNone(erro.__cause__)

    @override_settings(GEMINI_MODEL=None)
    def test_configuracao_invalida_nao_expoe_a_chave(self):
        with self.assertLogs("documentos.processamento", "WARNING") as logs:
            with self.assertRaises(ProcessamentoError) as contexto:
                processar_pdf(PDF, CHAVE_FORMULARIO)

        self.assertEqual(contexto.exception.codigo, "servico_indisponivel")
        self.assertNotIn(CHAVE_FORMULARIO, str(contexto.exception))
        self.assertNotIn(CHAVE_FORMULARIO, "\n".join(logs.output))

    def test_pdf_ilegivel_com_agents_reais_nao_chama_o_gemini(self):
        with mock.patch("agents.gemini_client.genai.Client") as sdk:
            with self.assertLogs("documentos.processamento", "WARNING"):
                with self.assertRaises(ProcessamentoError) as contexto:
                    processar_pdf(b"nao e pdf", CHAVE_FORMULARIO)

        self.assertEqual(contexto.exception.codigo, "documento_ilegivel")
        sdk.return_value.models.generate_content.assert_not_called()


class GeminiApiKeyDaRequisicaoTests(ProcessarPdfTestBase):
    """processar_pdf com Agents e GeminiClient REAIS; só o SDK é falso (sem rede)."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("agents.gemini_client.genai.Client")
        self.sdk_classe = patcher.start()
        self.addCleanup(patcher.stop)
        self.generate_content = self.sdk_classe.return_value.models.generate_content
        self.generate_content.side_effect = [
            mock.Mock(text=json.dumps(dados_nota())),
            mock.Mock(text=json.dumps(
                {"tipo_despesa": "MANUTENCAO_E_OPERACAO", "justificativa": "Pecas de manutencao."}
            )),
        ]

    def test_extrator_e_classificador_usam_o_mesmo_cliente_com_a_chave_informada(self):
        processamento = processar_pdf(PDF, CHAVE_FORMULARIO)

        # Um único SDK, criado com a chave do formulário, atende os dois Agents.
        self.sdk_classe.assert_called_once()
        self.assertEqual(self.sdk_classe.call_args.kwargs["api_key"], CHAVE_FORMULARIO)
        self.assertEqual(self.generate_content.call_count, 2)
        pdf_enviado = self.generate_content.call_args_list[0].kwargs["contents"][1]
        self.assertEqual(pdf_enviado.inline_data.data, PDF)
        self.assertEqual(
            processamento.resultado, montar_resultado(nota_extraida(), classificacao())
        )

    def test_chaves_do_ambiente_nao_substituem_a_chave_informada(self):
        ambiente = {"GOOGLE_API_KEY": "CHAVE_ERRADA_DO_AMBIENTE"}
        with mock.patch.dict(os.environ, ambiente):
            os.environ.pop("GEMINI_API_KEY", None)
            processar_pdf(PDF, CHAVE_FORMULARIO)

        self.assertEqual(self.sdk_classe.call_args.kwargs["api_key"], CHAVE_FORMULARIO)

    def test_chave_fica_fora_do_resultado_e_dos_logs(self):
        raiz = logging.getLogger()
        with self.assertLogs(raiz, "DEBUG") as logs:
            raiz.debug("marcador")  # assertLogs exige ao menos um registro
            processamento = processar_pdf(PDF, CHAVE_FORMULARIO)

        self.assertNotIn(CHAVE_FORMULARIO, json.dumps(processamento.resultado))
        self.assertNotIn(CHAVE_FORMULARIO, processamento.justificativa)
        self.assertNotIn(CHAVE_FORMULARIO, repr(processamento))
        self.assertNotIn(CHAVE_FORMULARIO, "\n".join(logs.output))

    def test_chave_recusada_pela_api_vira_erro_seguro(self):
        for codigo, status in ((400, "INVALID_ARGUMENT"), (401, "UNAUTHENTICATED"),
                               (403, "PERMISSION_DENIED")):
            with self.subTest(codigo=codigo):
                self.generate_content.side_effect = errors.ClientError(
                    codigo,
                    {"error": {"code": codigo, "status": status,
                               "message": f"API key not valid: {CHAVE_FORMULARIO}"}},
                )

                with self.assertLogs(level="DEBUG") as logs:
                    with self.assertRaises(ProcessamentoError) as contexto:
                        processar_pdf(PDF, CHAVE_FORMULARIO)

                erro = contexto.exception
                self.assertEqual(erro.codigo, "servico_indisponivel")
                self.assertIsNone(erro.__cause__)
                self.assertNotIn(CHAVE_FORMULARIO, str(erro))
                self.assertNotIn(CHAVE_FORMULARIO, "\n".join(logs.output))
