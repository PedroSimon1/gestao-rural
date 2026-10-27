"""GR-15: composição real de cliente/Agents/schemas, com SDK externo simulado.

Sem banco, PDF real ou chave real. A integração exercitada termina no JSON;
não substitui testes do provedor real nem da confirmação transacional.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings
from google.genai import errors

from agents.classificador.schemas import ClassificacaoDespesa
from agents.extrator.schemas import NotaFiscalExtraida
from agents.extrator.schemas_v2 import NotaFiscalExtraidaV2
from .processamento import ProcessamentoError, processar_pdf

PDF = b"%PDF-1.4\nfixture ficticia GR-15\n%%EOF\n"
CHAVE_FICTICIA = "gr15-chave-ficticia-sem-validade"
CNPJ = "11222333000181"
CNPJ_ALFA = "12ABC34501DE35"
CPF = "52998224725"
CAMPOS_V1 = {
    "fornecedor", "faturado", "numero_nota", "data_emissao", "itens",
    "quantidade_parcelas", "parcelas", "valor_total", "tipo_despesa", "validacoes",
}


def extracao(versao=2, *, pj=False):
    """Entrada do provedor, independente de helpers de implementação."""
    dados = {
        "documento_e_nota_fiscal": True,
        "fornecedor": {"razao_social": "Fornecedor fictício", "nome_fantasia": None, "cnpj": "11.222.333/0001-81"},
        "faturado": {"nome": "Destinatário fictício", "cpf": None if pj else "529.982.247-25", "cnpj": "12.ABC.345/01DE-35" if pj else None},
        "numero_nota": "000123", "data_emissao": "2026-10-27",
        "itens": [{"descricao": "Peça de máquina", "quantidade": "2", "valor_unitario": "75.00", "valor_total": "150.00"}],
        "parcelas": [{"numero": 1, "data_vencimento": "2026-11-27", "valor": "150.00"}],
        "valor_total": "150.00",
    }
    if versao == 2:
        dados["fornecedor"]["cpf"] = None
        dados["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "001"}
    return dados


def resposta(dados):
    return SimpleNamespace(text=json.dumps(dados, ensure_ascii=False))


@override_settings(GEMINI_MODEL="modelo-ficticio-gr15", GEMINI_MAX_TENTATIVAS=1)
class ContratoAgentsTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch("agents.gemini_client.genai.Client")
        self.fabrica_sdk = patcher.start()
        self.addCleanup(patcher.stop)
        self.gerar = self.fabrica_sdk.return_value.models.generate_content
        # Segunda barreira: se o limite do mock mudar, transporte real falha.
        transporte = mock.patch("httpx.Client.send", side_effect=AssertionError("Rede real proibida nos testes GR-15."))
        self.transporte = transporte.start()
        self.addCleanup(transporte.stop)

    def executar(self, dados, classificacao=None, *, versao=2):
        self.fabrica_sdk.reset_mock()
        self.gerar.side_effect = [resposta(dados), resposta(classificacao or {
            "tipo_despesa": "MANUTENCAO_E_OPERACAO", "justificativa": "Manutenção da máquina.",
        })]
        argumentos = {} if versao is None else {"versao_dados": versao}
        retorno = processar_pdf(PDF, CHAVE_FICTICIA, **argumentos)
        self.transporte.assert_not_called()
        return retorno

    def test_pf_pj_e_categorias_conclusivas_nas_duas_versoes(self):
        for versao in (1, 2):
            for pj in (False, True):
                for categoria in ("MANUTENCAO_E_OPERACAO", "INFRAESTRUTURA_E_UTILIDADES"):
                    with self.subTest(versao=versao, pj=pj, categoria=categoria):
                        r = self.executar(extracao(versao, pj=pj), {"tipo_despesa": categoria, "justificativa": "Baseada nos itens."}, versao=versao)
                        dados = r.resultado
                        self.assertEqual(r.situacao, "CLASSIFICADA")
                        self.assertEqual(dados["tipo_despesa"], categoria)
                        self.assertEqual(dados["fornecedor"]["cnpj"], CNPJ)
                        self.assertEqual(dados["faturado"]["cnpj"], CNPJ_ALFA if pj else None)
                        self.assertEqual(dados["faturado"]["cpf"], None if pj else CPF)
                        self.assertEqual(dados["numero_nota"], "000123")
                        self.assertEqual(dados["data_emissao"], "2026-10-27")
                        self.assertEqual(dados["valor_total"], "150.00")
                        self.assertEqual(dados["parcelas"], [{"numero": 1, "data_vencimento": "2026-11-27", "valor": "150.00"}])
                        self.assertEqual(dados["quantidade_parcelas"], 1)
                        self.assertEqual(json.loads(json.dumps(dados, allow_nan=False)), dados)
                        self.assertEqual(set(dados), CAMPOS_V1 | ({"documento_fiscal"} if versao == 2 else set()))

    def test_v1_padrao_preserva_contrato_e_nao_injeta_campos_fiscais(self):
        r = self.executar(extracao(1), versao=None)
        self.assertEqual(set(r.resultado), CAMPOS_V1)
        self.assertNotIn("cpf", r.resultado["fornecedor"])
        self.assertNotIn("documento_fiscal", r.resultado)
        self.assertIs(self.gerar.call_args_list[0].kwargs["config"].response_schema, NotaFiscalExtraida)

    def test_v2_usa_schema_correto_cliente_unico_e_contexto_minimo(self):
        r = self.executar(extracao())
        self.fabrica_sdk.assert_called_once()
        self.assertEqual(self.fabrica_sdk.call_args.kwargs["api_key"], CHAVE_FICTICIA)
        self.assertIs(self.fabrica_sdk.call_args.kwargs["vertexai"], False)
        self.assertEqual(self.gerar.call_count, 2)
        primeira, segunda = self.gerar.call_args_list
        self.assertIs(primeira.kwargs["config"].response_schema, NotaFiscalExtraidaV2)
        self.assertIs(segunda.kwargs["config"].response_schema, ClassificacaoDespesa)
        self.assertEqual(primeira.kwargs["contents"][1].inline_data.data, PDF)
        self.assertEqual(primeira.kwargs["contents"][1].inline_data.mime_type, "application/pdf")
        contexto = json.loads(segunda.kwargs["contents"][1])
        self.assertEqual(set(contexto), {"fornecedor", "itens", "valor_total"})
        self.assertEqual(set(contexto["fornecedor"]), {"razao_social", "nome_fantasia"})
        serializado = json.dumps(contexto) + json.dumps(r.resultado)
        self.assertNotIn(CHAVE_FICTICIA, serializado)
        for chamada in (primeira, segunda):
            self.assertEqual(chamada.kwargs["config"].response_mime_type, "application/json")
            self.assertEqual(chamada.kwargs["config"].temperature, 0)

    def test_inconclusiva_preserva_extracao_e_justificativa_sem_categoria_ficticia(self):
        for versao in (1, 2):
            dados = extracao(versao, pj=True)
            antes = deepcopy(dados)
            r = self.executar(dados, {"tipo_despesa": None, "justificativa": "Não há elementos suficientes."}, versao=versao)
            self.assertEqual(r.situacao, "AGUARDANDO_CLASSIFICACAO")
            self.assertIsNone(r.resultado["tipo_despesa"])
            self.assertEqual(r.justificativa, "Não há elementos suficientes.")
            self.assertEqual(r.resultado["faturado"]["cnpj"], CNPJ_ALFA)
            self.assertEqual(r.resultado["valor_total"], "150.00")
            self.assertEqual(dados, antes)

    def test_ausencias_v2_permanecem_null_ate_na_inconclusiva(self):
        dados = extracao()
        dados["valor_total"] = None
        dados["parcelas"][0].update(valor=None, data_vencimento=None)
        dados["documento_fiscal"] = {"chave_acesso": None, "modelo": None, "serie": None}
        r = self.executar(dados, {"tipo_despesa": None, "justificativa": "Precisa de conferência."})
        self.assertIsNone(r.resultado["valor_total"])
        self.assertIsNone(r.resultado["parcelas"][0]["valor"])
        self.assertIsNone(r.resultado["parcelas"][0]["data_vencimento"])
        self.assertEqual(r.resultado["documento_fiscal"], dados["documento_fiscal"])

    def test_cpf_cnpj_ambiguos_preservados_sem_escolha_automatica(self):
        dados = extracao()
        dados["fornecedor"]["cpf"] = CPF
        dados["faturado"]["cnpj"] = CNPJ_ALFA
        r = self.executar(dados)
        for parte, cnpj in (("fornecedor", CNPJ), ("faturado", CNPJ_ALFA)):
            self.assertEqual(r.resultado[parte]["cpf"], CPF)
            self.assertEqual(r.resultado[parte]["cnpj"], cnpj)

    def test_emitente_pf_nao_e_convertido_em_pj_ou_faturado(self):
        dados = extracao(pj=True)
        dados["fornecedor"].update(cnpj=None, cpf=CPF)
        r = self.executar(dados)
        self.assertIsNone(r.resultado["fornecedor"]["cnpj"])
        self.assertEqual(r.resultado["fornecedor"]["cpf"], CPF)
        self.assertEqual(r.resultado["faturado"]["cnpj"], CNPJ_ALFA)
        self.assertIsNone(r.resultado["faturado"]["cpf"])

    def test_dv_invalido_continua_aviso_sem_correcao_ficticia(self):
        dados = extracao()
        dados["faturado"]["cpf"] = "111.111.111-11"
        r = self.executar(dados)
        self.assertEqual(r.resultado["faturado"]["cpf"], "11111111111")
        self.assertEqual(r.resultado["validacoes"]["faturado_cpf"]["status"], "invalido")
        self.assertEqual(r.situacao, "CLASSIFICADA")

    def test_erros_rede_api_timeout_nao_viram_classificacao_inconclusiva(self):
        for etapa in ("extracao", "classificacao"):
            for tipo in ("timeout", "rede", "api"):
                with self.subTest(etapa=etapa, tipo=tipo):
                    erro = {
                        "timeout": httpx.ReadTimeout(CHAVE_FICTICIA),
                        "rede": httpx.ConnectError(CHAVE_FICTICIA),
                        "api": errors.APIError(503, {"error": {"message": CHAVE_FICTICIA}}),
                    }[tipo]
                    self.gerar.reset_mock()
                    self.gerar.side_effect = [erro] if etapa == "extracao" else [resposta(extracao()), erro]
                    with self.assertLogs(level="WARNING") as logs, self.assertRaises(ProcessamentoError) as contexto:
                        processar_pdf(PDF, CHAVE_FICTICIA, versao_dados=2)
                    self.assertEqual((contexto.exception.etapa, contexto.exception.codigo), (etapa, "servico_indisponivel"))
                    self.assertEqual(self.gerar.call_count, 1 if etapa == "extracao" else 2)
                    self.assertNotIn(CHAVE_FICTICIA, str(contexto.exception) + " ".join(logs.output))

    def test_json_malformado_e_schema_invalido_sao_erros_em_ambas_as_etapas(self):
        for etapa in ("extracao", "classificacao"):
            for texto in ("{json quebrado", '{"campo_inesperado": 1}'):
                with self.subTest(etapa=etapa, texto=texto):
                    invalida = SimpleNamespace(text=texto)
                    self.gerar.side_effect = [invalida] if etapa == "extracao" else [resposta(extracao()), invalida]
                    with self.assertRaises(ProcessamentoError) as contexto:
                        processar_pdf(PDF, CHAVE_FICTICIA, versao_dados=2)
                    codigo = "resposta_invalida" if etapa == "extracao" else "classificacao_invalida"
                    self.assertEqual((contexto.exception.etapa, contexto.exception.codigo), (etapa, codigo))

    def test_v2_alinhado_as_chaves_publicadas_do_contrato(self):
        contrato = json.loads((Path(__file__).resolve().parents[1]/"docs/contratos/JSONFiscalV2.schema.json").read_text(encoding="utf-8"))
        dados = self.executar(extracao()).resultado
        self.assertEqual(set(dados), set(contrato["required"]))
        for bloco in ("fornecedor", "faturado", "documento_fiscal"):
            self.assertEqual(set(dados[bloco]), set(contrato["properties"][bloco]["required"]))
        self.assertNotIn("versao_dados", dados)

    def test_pdf_invalido_bloqueia_antes_de_chamar_provedor(self):
        with self.assertRaises(ProcessamentoError) as contexto:
            processar_pdf(b"arquivo sem assinatura PDF", CHAVE_FICTICIA, versao_dados=2)
        self.assertEqual((contexto.exception.etapa, contexto.exception.codigo), ("extracao", "documento_ilegivel"))
        self.gerar.assert_not_called()
