"""GR-41: faturado PF/PJ, sem rede ou banco e sem inventar documentos."""

import copy
import json
from unittest import mock

from django.test import SimpleTestCase
from pydantic import ValidationError

from agents.classificador.schemas import ClassificacaoDespesa
from agents.gemini_client import GeminiClient
from documentos.processamento import montar_resultado, processar_pdf
from documentos.views import _avisos_validacao

from .agent import AgentExtrator
from .schemas import NotaFiscalExtraida
from .test_schemas import nota_valida

PDF = b"%PDF-1.4\nconteudo ficticio\n%%EOF"


def nota_pj(cnpj="11.222.333/0001-81"):
    dados = nota_valida()
    dados["faturado"] = {"nome": "Empresa Fictícia", "cnpj": cnpj}
    return dados


class FaturadoPJTests(SimpleTestCase):
    def test_faturado_pj_numerico_e_alfanumerico(self):
        for original, normalizado in (
            ("11.222.333/0001-81", "11222333000181"),
            ("12.abc.345/01de-35", "12ABC34501DE35"),
        ):
            with self.subTest(cnpj=original):
                nota = NotaFiscalExtraida.model_validate(nota_pj(original))
                self.assertEqual(nota.faturado.cnpj, normalizado)
                self.assertIsNone(nota.faturado.cpf)
                self.assertEqual(nota.validacoes.faturado_cnpj.status, "valido")
                self.assertEqual(nota.validacoes.faturado_cpf.status, "ausente")

    def test_faturado_pf_antigo_permanece_compativel(self):
        nota = NotaFiscalExtraida.model_validate(nota_valida())
        self.assertEqual(nota.faturado.cpf, "52998224725")
        self.assertIsNone(nota.faturado.cnpj)
        self.assertEqual(nota.validacoes.faturado_cpf.status, "valido")
        self.assertEqual(nota.validacoes.faturado_cnpj.status, "ausente")

    def test_cnpj_ausente_nulo_e_vazio_nao_copia_fornecedor(self):
        for faturado in ({}, {"cnpj": None}, {"cnpj": "  "}):
            with self.subTest(faturado=faturado):
                dados = nota_valida()
                dados["faturado"] = faturado
                nota = NotaFiscalExtraida.model_validate(dados)
                self.assertIsNotNone(nota.fornecedor.cnpj)
                self.assertIsNone(nota.faturado.cnpj)
                self.assertEqual(nota.validacoes.faturado_cnpj.status, "ausente")

    def test_dv_invalido_preservado_e_sinalizado_sem_corrigir(self):
        for cnpj in ("11222333000182", "12ABC34501DE36", "00000000000000"):
            with self.subTest(cnpj=cnpj):
                nota = NotaFiscalExtraida.model_validate(nota_pj(cnpj))
                self.assertEqual(nota.faturado.cnpj, cnpj)
                self.assertEqual(nota.validacoes.faturado_cnpj.status, "invalido")
                self.assertEqual(nota.validacoes.faturado_cnpj.motivo, "digitos_verificadores_invalidos")

    def test_estrutura_impossivel_rejeitada(self):
        for cnpj in ("123", "12ABC34501DE3X", "112223330001811", 11222333000181):
            with self.subTest(cnpj=cnpj), self.assertRaises(ValidationError):
                NotaFiscalExtraida.model_validate(nota_pj(cnpj))

    def test_validacoes_recebidas_nao_substituem_calculo_local(self):
        dados = nota_pj("11222333000182")
        dados["validacoes"] = {"faturado_cnpj": {"status": "valido"}}
        self.assertEqual(
            NotaFiscalExtraida.model_validate(dados).validacoes.faturado_cnpj.status, "invalido"
        )

    def test_cpf_e_cnpj_preservados_independentemente_quando_informados(self):
        dados = nota_pj()
        dados["faturado"]["cpf"] = "529.982.247-25"
        antes = copy.deepcopy(dados)
        nota = NotaFiscalExtraida.model_validate(dados)
        self.assertEqual(dados, antes)
        self.assertEqual(nota.faturado.cpf, "52998224725")
        self.assertEqual(nota.faturado.cnpj, "11222333000181")
        self.assertEqual(nota.validacoes.faturado_cpf.status, "valido")
        self.assertEqual(nota.validacoes.faturado_cnpj.status, "valido")

    def test_schema_gemini_cnpj_opcional_sem_validacoes_calculadas(self):
        schema = NotaFiscalExtraida.model_json_schema()
        faturado = schema["$defs"]["Faturado"]
        self.assertIn("cnpj", faturado["properties"])
        self.assertNotIn("cnpj", faturado.get("required", []))
        self.assertEqual(
            faturado["properties"]["cnpj"]["anyOf"], [{"type": "string"}, {"type": "null"}]
        )
        self.assertNotIn("validacoes", schema["properties"])

    def test_agent_simulado_entrega_pj_no_json_final_sem_mudar_chaves_principais(self):
        cliente = mock.Mock(spec=GeminiClient)
        cliente.gerar_json.return_value = nota_pj("12ABC34501DE35")
        classificador = mock.Mock()
        classificador.classificar.return_value = ClassificacaoDespesa(
            tipo_despesa="MANUTENCAO_E_OPERACAO", justificativa="Manutenção."
        )
        with mock.patch("agents.gemini_client.genai.Client", side_effect=AssertionError("Rede proibida")):
            retorno = processar_pdf(
                PDF, "chave-ficticia", extrator=AgentExtrator(cliente=cliente), classificador=classificador
            )
        self.assertEqual(retorno.resultado["faturado"], {
            "nome": "Empresa Fictícia", "cpf": None, "cnpj": "12ABC34501DE35"
        })
        self.assertEqual(retorno.resultado["validacoes"]["faturado_cnpj"]["status"], "valido")
        self.assertEqual(len(retorno.resultado), 10)
        json.dumps(retorno.resultado)
        self.assertNotIn("chave-ficticia", json.dumps(retorno.resultado))

    def test_aviso_cnpj_invalido_chega_a_apresentacao(self):
        nota = NotaFiscalExtraida.model_validate(nota_pj("11222333000182"))
        categoria = ClassificacaoDespesa(tipo_despesa="MANUTENCAO_E_OPERACAO", justificativa="Teste")
        dados = montar_resultado(nota, categoria)
        self.assertIn("CNPJ do faturado com dígitos verificadores inválidos.", _avisos_validacao(dados))

    def test_aviso_cnpj_ausente_nao_quebra_resultados_anteriores(self):
        self.assertEqual(_avisos_validacao({"validacoes": {
            "fornecedor_cnpj": {"status": "valido"}, "faturado_cpf": {"status": "valido"}
        }}), [])
