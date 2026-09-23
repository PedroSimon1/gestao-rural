import copy
import json
import threading
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.base import ContentFile
from django.db import DatabaseError, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

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

from .models import Documento
from .processamento import (
    MENSAGEM_ERRO_INTERNO,
    VERSAO_RESULTADO,
    DocumentoEmProcessamentoError,
    ProcessamentoError,
    _montar_resultado,
    _reservar,
    processar_documento,
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


def criar_documento(status=Documento.Status.PENDENTE, **campos):
    return Documento.objects.create(
        arquivo="documentos/nota.pdf",
        nome_original="nota.pdf",
        status=status,
        **campos,
    )


class ExcecoesTests(SimpleTestCase):
    def test_hierarquia_codigos_e_mensagens(self):
        self.assertTrue(issubclass(DocumentoEmProcessamentoError, ProcessamentoError))
        self.assertEqual(ProcessamentoError.codigo, "erro_processamento")
        self.assertEqual(
            DocumentoEmProcessamentoError.codigo, "documento_em_processamento"
        )
        self.assertEqual(
            str(DocumentoEmProcessamentoError()),
            "O documento já está sendo processado.",
        )

    def test_versao_do_resultado(self):
        self.assertEqual(VERSAO_RESULTADO, 1)


class MontarResultadoTests(SimpleTestCase):
    def test_chaves_do_json_final(self):
        resultado = _montar_resultado(nota_extraida(), classificacao())

        self.assertEqual(list(resultado), CHAVES_RESULTADO)

    def test_documento_e_nota_fiscal_nao_entra_no_json_final(self):
        resultado = _montar_resultado(nota_extraida(), classificacao())

        self.assertNotIn("documento_e_nota_fiscal", resultado)

    def test_conteudo_extraido_e_preservado(self):
        resultado = _montar_resultado(nota_extraida(), classificacao())

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
                resultado = _montar_resultado(
                    nota_extraida(parcelas=parcelas), classificacao()
                )

                self.assertEqual(resultado["quantidade_parcelas"], esperado)
                self.assertEqual(len(resultado["parcelas"]), esperado)

    def test_parcelas_numeradas_pelo_extrator_sao_mantidas(self):
        parcelas = [{"valor": 500}, {"valor": 1000}]

        resultado = _montar_resultado(nota_extraida(parcelas=parcelas), classificacao())

        self.assertEqual([p["numero"] for p in resultado["parcelas"]], [1, 2])

    def test_tipo_despesa_como_string(self):
        for tipo in ("MANUTENCAO_E_OPERACAO", "INFRAESTRUTURA_E_UTILIDADES"):
            with self.subTest(tipo=tipo):
                resultado = _montar_resultado(nota_extraida(), classificacao(tipo))

                self.assertEqual(resultado["tipo_despesa"], tipo)
                self.assertIs(type(resultado["tipo_despesa"]), str)

    def test_justificativa_nao_entra_no_json_final(self):
        resultado = _montar_resultado(nota_extraida(), classificacao())

        self.assertNotIn("justificativa", json.dumps(resultado))

    def test_validacoes_sao_preservadas(self):
        resultado = _montar_resultado(nota_extraida(), classificacao())

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
        resultado = _montar_resultado(nota_extraida(), classificacao())

        json.dumps(resultado)  # mesmo encoder padrão usado pelo JSONField
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

        primeiro = _montar_resultado(nota, classificacao())
        segundo = _montar_resultado(nota, classificacao())
        primeiro["parcelas"].append({"numero": 99})

        self.assertEqual(nota.model_dump(), antes)
        self.assertEqual(segundo["quantidade_parcelas"], 2)
        self.assertEqual(len(segundo["parcelas"]), 2)


class ReservaTests(TestCase):
    def assert_iniciado_em_valido(self, documento, antes, depois):
        processamento = documento.metadados["processamento"]
        self.assertEqual(processamento["versao_resultado"], VERSAO_RESULTADO)
        iniciado_em = datetime.fromisoformat(processamento["iniciado_em"])
        self.assertIsNotNone(iniciado_em.tzinfo)
        self.assertLessEqual(antes, iniciado_em)
        self.assertLessEqual(iniciado_em, depois)

    def test_reserva_documento_pendente(self):
        documento = criar_documento()

        antes = timezone.now()
        reservado_doc, reservado = _reservar(documento.pk)
        depois = timezone.now()

        self.assertTrue(reservado)
        self.assertEqual(reservado_doc.status, Documento.Status.PROCESSANDO)
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PROCESSANDO)
        self.assertEqual(documento.resultado_estruturado, {})
        self.assert_iniciado_em_valido(documento, antes, depois)

    def test_reserva_documento_em_erro_e_remove_erro_antigo(self):
        documento = criar_documento(
            status=Documento.Status.ERRO,
            metadados={
                "erro": {
                    "etapa": "extracao",
                    "codigo": "servico_indisponivel",
                    "mensagem": "Serviço de extração indisponível no momento.",
                },
                "processamento": {
                    "iniciado_em": "2026-01-01T00:00:00+00:00",
                    "extracao": {"versao_schema": 1, "modelo": "modelo-antigo"},
                },
                "outra_chave": "preservada",
            },
        )

        antes = timezone.now()
        _, reservado = _reservar(documento.pk)
        depois = timezone.now()

        self.assertTrue(reservado)
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PROCESSANDO)
        self.assertNotIn("erro", documento.metadados)
        # O bloco de processamento recomeça do zero na nova tentativa.
        self.assertEqual(
            set(documento.metadados["processamento"]),
            {"versao_resultado", "iniciado_em"},
        )
        self.assertEqual(documento.metadados["outra_chave"], "preservada")
        self.assert_iniciado_em_valido(documento, antes, depois)

    def test_documento_processando_e_recusado(self):
        metadados = {"processamento": {"iniciado_em": "2026-01-01T00:00:00+00:00"}}
        documento = criar_documento(
            status=Documento.Status.PROCESSANDO, metadados=copy.deepcopy(metadados)
        )

        with self.assertRaises(DocumentoEmProcessamentoError):
            _reservar(documento.pk)

        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PROCESSANDO)
        self.assertEqual(documento.metadados, metadados)

    def test_documento_concluido_nao_e_reservado(self):
        resultado = {"tipo_despesa": "MANUTENCAO_E_OPERACAO"}
        metadados = {"processamento": {"iniciado_em": "2026-01-01T00:00:00+00:00"}}
        documento = criar_documento(
            status=Documento.Status.CONCLUIDO,
            resultado_estruturado=copy.deepcopy(resultado),
            metadados=copy.deepcopy(metadados),
        )

        devolvido, reservado = _reservar(documento.pk)

        self.assertFalse(reservado)
        self.assertEqual(devolvido.pk, documento.pk)
        self.assertEqual(devolvido.status, Documento.Status.CONCLUIDO)
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.CONCLUIDO)
        self.assertEqual(documento.resultado_estruturado, resultado)
        self.assertEqual(documento.metadados, metadados)

    def test_documento_inexistente(self):
        with self.assertRaises(Documento.DoesNotExist):
            _reservar(999999)

    def test_reserva_nao_sobrescreve_outros_campos(self):
        documento = criar_documento()
        Documento.objects.filter(pk=documento.pk).update(nome_original="renomeado.pdf")

        _reservar(documento.pk)

        documento.refresh_from_db()
        self.assertEqual(documento.nome_original, "renomeado.pdf")

    def test_reserva_termina_a_transacao_antes_de_retornar(self):
        documento = criar_documento()

        # Dentro do TestCase já existe um atomic externo; o _reservar não
        # pode deixar blocos atomic próprios abertos ao retornar.
        profundidade = len(connection.savepoint_ids)
        _reservar(documento.pk)

        self.assertEqual(len(connection.savepoint_ids), profundidade)


class ReservaConcorrenteTests(TransactionTestCase):
    """Duas reservas simultâneas, cada uma com sua conexão ao banco."""

    def test_segunda_execucao_espera_o_lock_e_encontra_processando(self):
        documento = criar_documento()
        lock_obtido = threading.Event()
        liberar_lock = threading.Event()
        resultado_segunda = {}

        def primeira_execucao():
            # Simula a 1ª reserva segurando o lock por mais tempo.
            try:
                with transaction.atomic():
                    doc = Documento.objects.select_for_update().get(pk=documento.pk)
                    lock_obtido.set()
                    liberar_lock.wait(timeout=10)
                    doc.status = Documento.Status.PROCESSANDO
                    doc.save(update_fields=["status"])
            finally:
                connection.close()

        def segunda_execucao():
            try:
                _reservar(documento.pk)
                resultado_segunda["erro"] = None
            except Exception as exc:
                resultado_segunda["erro"] = exc
            finally:
                connection.close()

        primeira = threading.Thread(target=primeira_execucao)
        segunda = threading.Thread(target=segunda_execucao)

        primeira.start()
        self.assertTrue(lock_obtido.wait(timeout=10))
        segunda.start()

        # Com o lock preso, a 2ª execução fica bloqueada no select_for_update.
        segunda.join(timeout=0.5)
        self.assertTrue(segunda.is_alive())

        liberar_lock.set()
        primeira.join(timeout=10)
        segunda.join(timeout=10)
        self.assertFalse(segunda.is_alive())

        self.assertIsInstance(resultado_segunda["erro"], DocumentoEmProcessamentoError)
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PROCESSANDO)
        # A 2ª execução não tocou nos metadados.
        self.assertEqual(documento.metadados, {})


# GEMINI_API_KEY ausente: mesmo que algo escape dos mocks, não há como autenticar.
@override_settings(GEMINI_API_KEY=None, GEMINI_MODEL="modelo-teste")
class ProcessamentoTestBase(TestCase):
    def setUp(self):
        # Rede de segurança: qualquer criação do SDK real falha o teste.
        patcher = mock.patch(
            "agents.gemini_client.genai.Client",
            side_effect=AssertionError("O SDK real do Gemini não deve ser usado."),
        )
        self.sdk_client_classe = patcher.start()
        self.addCleanup(patcher.stop)

        self.nota = nota_extraida()
        self.classificacao = classificacao()

        self.extrator = mock.Mock(spec=AgentExtrator)
        self.extrator.modelo = "modelo-extracao"
        self.extrator.extrair_documento.return_value = self.nota

        self.classificador = mock.Mock(spec=AgentClassificador)
        self.classificador.modelo = "modelo-classificacao"
        self.classificador.classificar.return_value = self.classificacao

    def processar(self, documento):
        return processar_documento(
            documento.pk, extrator=self.extrator, classificador=self.classificador
        )

    def processar_com_log(self, documento, nivel="WARNING"):
        with self.assertLogs("documentos.processamento", nivel) as logs:
            retorno = self.processar(documento)
        return retorno, logs

    def assert_erro(self, documento, etapa, codigo, mensagem):
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.ERRO)
        self.assertEqual(documento.resultado_estruturado, {})
        self.assertEqual(
            documento.metadados["erro"],
            {"etapa": etapa, "codigo": codigo, "mensagem": mensagem},
        )
        # Em ERRO, processamento nunca carrega dados das etapas.
        self.assertEqual(
            set(documento.metadados["processamento"]),
            {"versao_resultado", "iniciado_em", "finalizado_em"},
        )


class ProcessamentoSucessoTests(ProcessamentoTestBase):
    def test_fluxo_completo_com_sucesso(self):
        documento = criar_documento()

        retorno = self.processar(documento)

        self.assertIsInstance(retorno, Documento)
        self.assertEqual(retorno.pk, documento.pk)
        self.assertEqual(retorno.status, Documento.Status.CONCLUIDO)
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.CONCLUIDO)

    def test_extrator_chamado_uma_vez_com_o_documento(self):
        documento = criar_documento()

        self.processar(documento)

        self.extrator.extrair_documento.assert_called_once()
        recebido = self.extrator.extrair_documento.call_args.args[0]
        self.assertIsInstance(recebido, Documento)
        self.assertEqual(recebido.pk, documento.pk)

    def test_classificador_chamado_uma_vez_com_a_nota_extraida(self):
        self.processar(criar_documento())

        self.classificador.classificar.assert_called_once()
        self.assertIs(self.classificador.classificar.call_args.args[0], self.nota)

    def test_resultado_estruturado_persistido(self):
        documento = criar_documento()

        self.processar(documento)

        documento.refresh_from_db()
        esperado = _montar_resultado(self.nota, self.classificacao)
        self.assertEqual(documento.resultado_estruturado, esperado)
        self.assertEqual(documento.resultado_estruturado["tipo_despesa"], "MANUTENCAO_E_OPERACAO")
        self.assertEqual(documento.resultado_estruturado["quantidade_parcelas"], 2)
        self.assertNotIn("documento_e_nota_fiscal", documento.resultado_estruturado)
        self.assertNotIn("justificativa", documento.resultado_estruturado)

    def test_cpf_cnpj_e_validacoes_preservados(self):
        documento = criar_documento()

        self.processar(documento)

        documento.refresh_from_db()
        resultado = documento.resultado_estruturado
        self.assertEqual(resultado["faturado"]["cpf"], "99999999999")
        self.assertEqual(resultado["validacoes"]["faturado_cpf"]["status"], "invalido")
        self.assertEqual(resultado["validacoes"]["fornecedor_cnpj"]["status"], "valido")

    def test_metadados_de_sucesso(self):
        documento = criar_documento()

        antes = timezone.now()
        self.processar(documento)
        depois = timezone.now()

        documento.refresh_from_db()
        self.assertNotIn("erro", documento.metadados)
        processamento = documento.metadados["processamento"]
        self.assertEqual(processamento["versao_resultado"], VERSAO_RESULTADO)
        self.assertEqual(
            processamento["extracao"], {"versao_schema": 1, "modelo": "modelo-extracao"}
        )
        self.assertEqual(
            processamento["classificacao"],
            {
                "versao_schema": 1,
                "modelo": "modelo-classificacao",
                "justificativa": "Pecas de manutencao.",
            },
        )
        iniciado_em = datetime.fromisoformat(processamento["iniciado_em"])
        finalizado_em = datetime.fromisoformat(processamento["finalizado_em"])
        self.assertLessEqual(antes, iniciado_em)
        self.assertLessEqual(iniciado_em, finalizado_em)
        self.assertLessEqual(finalizado_em, depois)

    def test_metadados_nao_duplicam_dados_da_nota(self):
        documento = criar_documento()

        self.processar(documento)

        documento.refresh_from_db()
        texto = json.dumps(documento.metadados)
        for dado in ("99999999999", "11222333000181", "Filtro de oleo", "1500.00"):
            self.assertNotIn(dado, texto)

    def test_iniciado_em_da_reserva_e_preservado(self):
        documento = criar_documento()
        registrado = {}

        def extrair(doc):
            registrado["iniciado_em"] = Documento.objects.get(
                pk=doc.pk
            ).metadados["processamento"]["iniciado_em"]
            return self.nota

        self.extrator.extrair_documento.side_effect = extrair

        self.processar(documento)

        documento.refresh_from_db()
        self.assertEqual(
            documento.metadados["processamento"]["iniciado_em"],
            registrado["iniciado_em"],
        )

    def test_status_processando_durante_os_agents(self):
        documento = criar_documento()
        status = {}

        def extrair(doc):
            status["extracao"] = Documento.objects.get(pk=doc.pk).status
            return self.nota

        def classificar(nota):
            status["classificacao"] = Documento.objects.get(pk=documento.pk).status
            return self.classificacao

        self.extrator.extrair_documento.side_effect = extrair
        self.classificador.classificar.side_effect = classificar

        self.processar(documento)

        self.assertEqual(status["extracao"], Documento.Status.PROCESSANDO)
        self.assertEqual(status["classificacao"], Documento.Status.PROCESSANDO)

    def test_nenhuma_transacao_aberta_durante_os_agents(self):
        documento = criar_documento()
        profundidade_base = len(connection.savepoint_ids)
        profundidades = []

        def extrair(doc):
            profundidades.append(len(connection.savepoint_ids))
            return self.nota

        self.extrator.extrair_documento.side_effect = extrair

        self.processar(documento)

        # Dentro do TestCase já existe um atomic externo; o serviço não pode
        # somar blocos atomic próprios enquanto o Agent roda.
        self.assertEqual(profundidades, [profundidade_base])

    def test_nao_sobrescreve_outros_campos(self):
        documento = criar_documento()

        def extrair(doc):
            Documento.objects.filter(pk=doc.pk).update(nome_original="renomeado.pdf")
            return self.nota

        self.extrator.extrair_documento.side_effect = extrair

        self.processar(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.nome_original, "renomeado.pdf")
        self.assertEqual(documento.status, Documento.Status.CONCLUIDO)

    def test_agents_padrao_sao_criados_quando_nao_injetados(self):
        documento = criar_documento()

        with (
            mock.patch("documentos.processamento.AgentExtrator") as extrator_classe,
            mock.patch("documentos.processamento.AgentClassificador") as classificador_classe,
        ):
            extrator_classe.return_value = self.extrator
            classificador_classe.return_value = self.classificador

            processar_documento(documento.pk)

        extrator_classe.assert_called_once_with()
        classificador_classe.assert_called_once_with()
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.CONCLUIDO)


class ProcessamentoErroExtracaoTests(ProcessamentoTestBase):
    def test_cada_erro_do_extrator(self):
        casos = (
            (DocumentoIlegivelError(), "documento_ilegivel"),
            (ExtracaoIndisponivelError(), "servico_indisponivel"),
            (ExtracaoInvalidaError(), "resposta_invalida"),
            (
                ExtracaoInvalidaError(
                    "O documento enviado não foi reconhecido como nota fiscal."
                ),
                "resposta_invalida",
            ),
        )
        for erro, codigo in casos:
            with self.subTest(erro=type(erro).__name__, mensagem=str(erro)):
                documento = criar_documento()
                self.extrator.extrair_documento.side_effect = erro
                self.classificador.classificar.reset_mock()

                retorno, _ = self.processar_com_log(documento)

                self.assertEqual(retorno.status, Documento.Status.ERRO)
                self.assert_erro(documento, "extracao", codigo, str(erro))
                self.classificador.classificar.assert_not_called()


class ProcessamentoErroClassificacaoTests(ProcessamentoTestBase):
    def test_cada_erro_do_classificador(self):
        casos = (
            (ClassificacaoIndisponivelError(), "servico_indisponivel"),
            (ClassificacaoInvalidaError(), "classificacao_invalida"),
            (ClassificacaoInconclusivaError(), "classificacao_inconclusiva"),
        )
        for erro, codigo in casos:
            with self.subTest(erro=type(erro).__name__):
                documento = criar_documento()
                self.classificador.classificar.side_effect = erro

                self.processar_com_log(documento)

                self.assert_erro(documento, "classificacao", codigo, str(erro))

    def test_falha_na_classificacao_nao_persiste_a_extracao(self):
        documento = criar_documento()
        self.classificador.classificar.side_effect = ClassificacaoIndisponivelError()

        self.processar_com_log(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.resultado_estruturado, {})
        processamento = documento.metadados["processamento"]
        self.assertNotIn("extracao", processamento)
        self.assertNotIn("classificacao", processamento)
        self.assertNotIn("99999999999", json.dumps(documento.metadados))
        self.extrator.extrair_documento.assert_called_once()


class ProcessamentoErroSeguroTests(ProcessamentoTestBase):
    def test_erro_esperado_nao_grava_causa_nem_traceback(self):
        documento = criar_documento()
        erro = ExtracaoInvalidaError()
        erro.__cause__ = ValueError(f"{DETALHE_INTERNO} cpf 99999999999 status 503")
        self.extrator.extrair_documento.side_effect = erro

        _, logs = self.processar_com_log(documento)

        documento.refresh_from_db()
        self.assertEqual(set(documento.metadados["erro"]), {"etapa", "codigo", "mensagem"})
        texto = json.dumps(documento.metadados)
        for dado in (DETALHE_INTERNO, "99999999999", "Traceback", "503"):
            self.assertNotIn(dado, texto)
        self.assertNotIn(DETALHE_INTERNO, "\n".join(logs.output))
        # Aviso sem traceback: o __cause__ pode conter dados da nota.
        self.assertTrue(all(registro.exc_info is None for registro in logs.records))
        self.assertIn("extracao/resposta_invalida", "\n".join(logs.output))


class ProcessamentoErroInesperadoTests(ProcessamentoTestBase):
    def test_erro_inesperado_no_extrator(self):
        documento = criar_documento()
        self.extrator.extrair_documento.side_effect = RuntimeError(DETALHE_INTERNO)

        retorno, logs = self.processar_com_log(documento, "ERROR")

        self.assertEqual(retorno.status, Documento.Status.ERRO)
        self.assert_erro(documento, "processamento", "erro_interno", MENSAGEM_ERRO_INTERNO)
        self.assertNotIn(DETALHE_INTERNO, json.dumps(documento.metadados))
        self.classificador.classificar.assert_not_called()

    def test_erro_inesperado_no_classificador(self):
        documento = criar_documento()
        self.classificador.classificar.side_effect = KeyError("inesperado")

        self.processar_com_log(documento, "ERROR")

        self.assert_erro(documento, "processamento", "erro_interno", MENSAGEM_ERRO_INTERNO)

    def test_logger_exception_so_para_erro_inesperado(self):
        documento = criar_documento()
        self.extrator.extrair_documento.side_effect = RuntimeError(DETALHE_INTERNO)

        _, logs = self.processar_com_log(documento, "ERROR")

        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].levelname, "ERROR")
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_falha_ao_gravar_sucesso_vira_erro_interno(self):
        documento = criar_documento()

        with mock.patch(
            "documentos.processamento._registrar_sucesso",
            side_effect=DatabaseError("falha ao gravar"),
        ):
            self.processar_com_log(documento, "ERROR")

        self.assert_erro(documento, "processamento", "erro_interno", MENSAGEM_ERRO_INTERNO)

    def test_falha_no_save_final_de_sucesso_nao_deixa_dados_das_etapas(self):
        documento = criar_documento()
        save_original = Documento.save
        registrado = {}

        def save(instancia, *args, **kwargs):
            if instancia.status == Documento.Status.CONCLUIDO:
                # Neste ponto extracao/classificacao/justificativa já estão em memória.
                registrado["processamento"] = dict(instancia.metadados["processamento"])
                raise DatabaseError("falha ao gravar o sucesso")
            return save_original(instancia, *args, **kwargs)

        def extrair(doc):
            registrado["iniciado_em"] = Documento.objects.get(
                pk=doc.pk
            ).metadados["processamento"]["iniciado_em"]
            return self.nota

        self.extrator.extrair_documento.side_effect = extrair

        with mock.patch.object(Documento, "save", autospec=True, side_effect=save):
            retorno, logs = self.processar_com_log(documento, "ERROR")

        # Confirma que o cenário realmente ocorreu: o save de sucesso tinha as etapas.
        self.assertIn("extracao", registrado["processamento"])
        self.assertIn("classificacao", registrado["processamento"])
        self.assertIsNotNone(logs.records[0].exc_info)

        self.assertEqual(retorno.status, Documento.Status.ERRO)
        self.assert_erro(documento, "processamento", "erro_interno", MENSAGEM_ERRO_INTERNO)
        processamento = documento.metadados["processamento"]
        self.assertNotIn("extracao", processamento)
        self.assertNotIn("classificacao", processamento)
        self.assertNotIn("justificativa", json.dumps(documento.metadados))
        self.assertEqual(documento.resultado_estruturado, {})
        self.assertEqual(processamento["iniciado_em"], registrado["iniciado_em"])
        self.assertEqual(processamento["versao_resultado"], VERSAO_RESULTADO)
        datetime.fromisoformat(processamento["finalizado_em"])

    def test_falha_ao_gravar_o_erro_sobe(self):
        documento = criar_documento()
        self.extrator.extrair_documento.side_effect = ExtracaoIndisponivelError()

        with (
            mock.patch(
                "documentos.processamento._registrar_erro",
                side_effect=DatabaseError("banco fora"),
            ),
            self.assertLogs("documentos.processamento", "WARNING"),
        ):
            with self.assertRaises(DatabaseError):
                self.processar(documento)


class ProcessamentoEstadosTests(ProcessamentoTestBase):
    def test_concluido_nao_chama_agents(self):
        resultado = {"tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES"}
        documento = criar_documento(
            status=Documento.Status.CONCLUIDO,
            resultado_estruturado=copy.deepcopy(resultado),
        )

        with mock.patch("documentos.processamento.AgentExtrator") as extrator_classe:
            retorno = processar_documento(documento.pk)
        retorno_injetado = self.processar(documento)

        extrator_classe.assert_not_called()
        self.extrator.extrair_documento.assert_not_called()
        self.classificador.classificar.assert_not_called()
        self.assertEqual(retorno.status, Documento.Status.CONCLUIDO)
        self.assertEqual(retorno_injetado.resultado_estruturado, resultado)
        documento.refresh_from_db()
        self.assertEqual(documento.resultado_estruturado, resultado)

    def test_processando_nao_chama_agents(self):
        documento = criar_documento(status=Documento.Status.PROCESSANDO)

        with self.assertRaises(DocumentoEmProcessamentoError):
            self.processar(documento)

        self.extrator.extrair_documento.assert_not_called()
        self.classificador.classificar.assert_not_called()
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.PROCESSANDO)
        self.assertEqual(documento.metadados, {})

    def test_erro_pode_reprocessar(self):
        documento = criar_documento(
            status=Documento.Status.ERRO,
            metadados={
                "erro": {
                    "etapa": "classificacao",
                    "codigo": "servico_indisponivel",
                    "mensagem": "Serviço de classificação indisponível no momento.",
                },
                "processamento": {"finalizado_em": "2026-01-01T00:00:00+00:00"},
            },
        )

        self.processar(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.CONCLUIDO)
        self.assertNotIn("erro", documento.metadados)
        self.assertNotEqual(
            documento.metadados["processamento"]["finalizado_em"],
            "2026-01-01T00:00:00+00:00",
        )
        self.extrator.extrair_documento.assert_called_once()

    def test_documento_inexistente(self):
        with self.assertRaises(Documento.DoesNotExist):
            self.processar(Documento(pk=999999))

        self.extrator.extrair_documento.assert_not_called()


@override_settings(GEMINI_API_KEY=None, GEMINI_MODEL="modelo-teste")
class ProcessamentoComAgentsReaisTests(TestCase):
    """Agents reais, sem chamada ao Gemini: nenhum caminho aqui chega à rede."""

    def setUp(self):
        self.pasta_temporaria = TemporaryDirectory()
        self.addCleanup(self.pasta_temporaria.cleanup)
        configuracao = override_settings(MEDIA_ROOT=self.pasta_temporaria.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)

        patcher = mock.patch(
            "agents.gemini_client.genai.Client",
            side_effect=AssertionError("O SDK real do Gemini não deve ser usado."),
        )
        self.sdk_client_classe = patcher.start()
        self.addCleanup(patcher.stop)

    def processar_com_log(self, documento):
        with self.assertLogs(level="WARNING"):
            return processar_documento(documento.pk)

    def test_documento_sem_arquivo(self):
        documento = Documento.objects.create(arquivo="", nome_original="nota.pdf")

        self.processar_com_log(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.ERRO)
        self.assertEqual(documento.metadados["erro"]["codigo"], "documento_ilegivel")
        self.sdk_client_classe.assert_not_called()

    def test_arquivo_removido_do_storage(self):
        documento = Documento.objects.create(
            arquivo=ContentFile(PDF, name="nota.pdf"), nome_original="nota.pdf"
        )
        documento.arquivo.storage.delete(documento.arquivo.name)

        self.processar_com_log(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.metadados["erro"]["etapa"], "extracao")
        self.assertEqual(documento.metadados["erro"]["codigo"], "documento_ilegivel")
        self.sdk_client_classe.assert_not_called()

    def test_sem_api_key_nenhuma_chamada_real_ao_gemini(self):
        documento = Documento.objects.create(
            arquivo=ContentFile(PDF, name="nota.pdf"), nome_original="nota.pdf"
        )

        # GeminiClient real: sem chave, falha na configuração, antes do SDK.
        with mock.patch(
            "agents.extrator.agent.GeminiClient", wraps=GeminiClient
        ) as cliente_classe:
            self.processar_com_log(documento)

        cliente_classe.assert_called_once_with()
        documento.refresh_from_db()
        self.assertEqual(documento.status, Documento.Status.ERRO)
        self.assertEqual(
            documento.metadados["erro"],
            {
                "etapa": "extracao",
                "codigo": "servico_indisponivel",
                "mensagem": "Serviço de extração indisponível no momento.",
            },
        )
        self.sdk_client_classe.assert_not_called()
