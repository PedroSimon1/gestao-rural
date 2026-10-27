"""Contrato v2 opt-in e compatibilidade v1, sem Gemini real nem consultas."""
from copy import deepcopy
import json
from unittest import mock

from django.test import SimpleTestCase
from pydantic import ValidationError

from agents.classificador.agent import _montar_contexto
from agents.classificador.schemas import ClassificacaoDespesa
from agents.extrator.agent import AgentExtrator, INSTRUCAO_SISTEMA_V2
from agents.extrator.schemas import NotaFiscalExtraida
from agents.extrator.schemas_v2 import NotaFiscalExtraidaV2
from documentos.forms_fiscais import preparar_campos_fiscais
from documentos.processamento import montar_resultado, processar_pdf
from documentos.views import _avisos_validacao
from financeiro.test_identidade_fiscal import chave


class SchemaFiscalV2Tests(SimpleTestCase):
    def bruto(self):
        return {
            'documento_e_nota_fiscal': True,
            'fornecedor': {'razao_social': 'Fornecedor fictício', 'nome_fantasia': None,
                           'cnpj': '11222333000181', 'cpf': None},
            'faturado': {'nome': 'Faturado fictício', 'cpf': '12345678909', 'cnpj': None},
            'numero_nota': '123', 'data_emissao': '2026-10-27',
            'documento_fiscal': {'chave_acesso': None, 'modelo': None, 'serie': None},
            'itens': [{'descricao': 'Óleo', 'quantidade': '1', 'valor_unitario': None, 'valor_total': None}],
            'valor_total': None,
            'parcelas': [{'numero': 1, 'data_vencimento': None, 'valor': None}],
        }

    def categoria(self):
        return ClassificacaoDespesa(tipo_despesa='MANUTENCAO_E_OPERACAO', justificativa='Manutenção.')

    def test_valores_ausentes_preservados_sem_inventar(self):
        nota = NotaFiscalExtraidaV2.model_validate(self.bruto())
        resultado = montar_resultado(nota, self.categoria(), versao_dados=2)
        self.assertIsNone(resultado['valor_total'])
        self.assertIsNone(resultado['parcelas'][0]['valor'])
        self.assertIsNone(resultado['parcelas'][0]['data_vencimento'])
        self.assertEqual(resultado['documento_fiscal'], {'chave_acesso': None, 'modelo': None, 'serie': None})
        json.dumps(resultado, allow_nan=False)

    def test_v2_tem_onze_chaves_e_fontes_canonicas_sem_versao_no_corpo(self):
        nota = NotaFiscalExtraidaV2.model_validate(self.bruto())
        resultado = montar_resultado(nota, self.categoria(), versao_dados=2)
        self.assertEqual(len(resultado), 11)
        self.assertEqual(resultado['numero_nota'], '123')
        self.assertEqual(resultado['fornecedor']['cnpj'], '11222333000181')
        self.assertNotIn('numero', resultado['documento_fiscal'])
        self.assertNotIn('emitente_cnpj', resultado['documento_fiscal'])
        self.assertNotIn('versao_dados', resultado)

    def test_total_e_parcela_presentes_continuam_positivos_e_validos(self):
        for campo in ('valor_total', 'parcela'):
            for valor in ('-1', '0', 'NaN', 'Infinity'):
                with self.subTest(campo=campo, valor=valor):
                    d = self.bruto()
                    if campo == 'parcela':
                        d['parcelas'][0]['valor'] = valor
                    else:
                        d['valor_total'] = valor
                    with self.assertRaises(ValidationError):
                        NotaFiscalExtraidaV2.model_validate(d)

    def test_cpf_cnpj_das_partes_preservados_sem_escolha(self):
        d = self.bruto()
        d['fornecedor']['cpf'] = '123.456.789-09'
        d['faturado']['cnpj'] = '12.abc.345/01de-35'
        nota = NotaFiscalExtraidaV2.model_validate(d)
        self.assertEqual(nota.fornecedor.cpf, '12345678909')
        self.assertEqual(nota.fornecedor.cnpj, '11222333000181')
        self.assertEqual(nota.faturado.cnpj, '12ABC34501DE35')
        self.assertEqual(nota.validacoes.fornecedor_cpf.status, 'valido')

    def test_chave_invalida_preservada_e_validacoes_nao_confiadas(self):
        d = self.bruto()
        d['documento_fiscal']['chave_acesso'] = 'leitura-malformada'
        d['validacoes'] = {'chave_acesso': {'status': 'valido', 'motivo': None}}
        nota = NotaFiscalExtraidaV2.model_validate(d)
        self.assertEqual(nota.documento_fiscal.chave_acesso, 'leitura-malformada')
        self.assertEqual(nota.validacoes.chave_acesso.status, 'invalido')
        r = montar_resultado(nota, self.categoria(), versao_dados=2)
        self.assertTrue(any('Chave de acesso' in aviso for aviso in _avisos_validacao(r)))

    def test_chave_numerica_alfanumerica_e_dv_oficiais(self):
        for cnpj in ('11222333000181', '12ABC34501DE35'):
            d = self.bruto()
            d['documento_fiscal']['chave_acesso'] = chave(cnpj=cnpj)
            self.assertEqual(NotaFiscalExtraidaV2.model_validate(d).validacoes.chave_acesso.status, 'valido')

    def test_classificador_recebe_total_nulo_real(self):
        nota = NotaFiscalExtraidaV2.model_validate(self.bruto())
        self.assertIsNone(_montar_contexto(nota)['valor_total'])

    def test_extrator_v2_usa_schema_e_prompt_apropriados(self):
        cliente = mock.Mock()
        cliente.gerar_json.return_value = self.bruto()
        nota = AgentExtrator(cliente, versao_schema=3).extrair(b'%PDF-1.4\n%%EOF')
        self.assertIsInstance(nota, NotaFiscalExtraidaV2)
        self.assertIs(cliente.gerar_json.call_args.kwargs['schema_resposta'], NotaFiscalExtraidaV2)
        self.assertEqual(cliente.gerar_json.call_args.kwargs['instrucao_sistema'], INSTRUCAO_SISTEMA_V2)

    def test_pipeline_v2_explicito_nao_descarta_nota_sem_valores(self):
        cliente = mock.Mock()
        cliente.gerar_json.return_value = self.bruto()
        classificador = mock.Mock()
        classificador.classificar.return_value = self.categoria()
        r = processar_pdf(b'%PDF-1.4\n%%EOF', 'ficticia',
            extrator=AgentExtrator(cliente, versao_schema=3), classificador=classificador, versao_dados=2)
        self.assertEqual(len(r.resultado), 11)
        self.assertIsNone(r.resultado['valor_total'])

    def test_legado_permanece_com_dez_chaves(self):
        d = self.bruto()
        d['valor_total'] = '150.00'
        d['parcelas'][0]['valor'] = '150.00'
        nota = NotaFiscalExtraida.model_validate(d)
        r = montar_resultado(nota, self.categoria())
        self.assertEqual(len(r), 10)
        self.assertNotIn('documento_fiscal', r)
        self.assertNotIn('cpf', r['fornecedor'])
        with self.assertRaises(ValidationError):
            NotaFiscalExtraida.model_validate(self.bruto())

    def test_versoes_incompativeis_recusadas(self):
        nota = NotaFiscalExtraidaV2.model_validate(self.bruto())
        with self.assertRaises(ValueError):
            montar_resultado(nota, self.categoria())
        for versao in (True, 0, 3, '2'):
            with self.subTest(versao=versao), self.assertRaises(ValueError):
                processar_pdf(b'%PDF', 'ficticia', versao_dados=versao)

    def test_reabertura_fiscal_v2_nao_muta_original_nem_preenche_ausentes(self):
        nota = NotaFiscalExtraidaV2.model_validate(self.bruto())
        r = montar_resultado(nota, self.categoria(), versao_dados=2)
        antes = deepcopy(r)
        form = preparar_campos_fiscais(r, {'modelo': '65', 'serie': '0'})
        self.assertEqual(form.initial['modelo'], '65')
        self.assertEqual(form.initial['serie'], '0')
        self.assertIsNone(form.initial['chave_acesso'])
        self.assertEqual(r, antes)
