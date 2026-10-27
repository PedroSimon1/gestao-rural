"""Formulários GR-45 e backend real F-2/F-3, sem persistência."""
from copy import deepcopy
import json

from django.core.exceptions import ValidationError
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from cadastros.models import Classificacao, Pessoa, Status
from financeiro.models import MovimentoConta
from .correcoes import CAMPOS_CORRIGIVEIS, validar_correcoes
from .interface_conferencia import preparar_conferencia, validar_conferencia
from .testing import resultado_da_nota


class InterfaceConferenciaTests(TestCase):
    def dados(self):
        categoria = Classificacao.objects.get(tipo='DESPESA', codigo='MANUTENCAO_E_OPERACAO')
        return {
            'fornecedor_nome': 'Empresa corrigida', 'fornecedor_documento': '11.222.333/0001-81',
            'faturado_nome': 'Produtor corrigido', 'faturado_cpf': '123.456.789-09',
            'faturado_cnpj': '', 'documento_faturado': 'CPF', 'classificacao': str(categoria.pk),
            'numero_nota': '123', 'serie_nota': '1', 'data_emissao': '2026-10-27',
            'valor_total': '150.00', 'parcelas-TOTAL_FORMS': '1', 'parcelas-INITIAL_FORMS': '1',
            'parcelas-0-data_vencimento': '2026-11-27', 'parcelas-0-valor': '150.00',
        }

    def test_contrato_oficial_sem_escrita_e_original_independente(self):
        original = resultado_da_nota()
        antes = deepcopy(original)
        with CaptureQueriesContext(connection) as queries:
            _, _, revisao = validar_conferencia(original, self.dados())
        self.assertIsNotNone(revisao)
        self.assertTrue(set(revisao.correcoes) <= set(CAMPOS_CORRIGIVEIS))
        self.assertFalse(validar_correcoes(revisao.correcoes)[1])
        self.assertEqual(revisao.correcoes['fornecedor.razao_social'], 'Empresa corrigida')
        self.assertEqual(revisao.correcoes['serie'], 1)
        self.assertEqual(original, antes)
        revisao.original['fornecedor']['razao_social'] = 'Outra cópia'
        self.assertEqual(original, antes)
        for q in queries:
            self.assertTrue(q['sql'].lstrip().upper().startswith('SELECT'))
        self.assertEqual(Pessoa.objects.count(), 0)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_identidade_fiscal_insuficiente_nao_e_ocultada(self):
        _, _, revisao = validar_conferencia(resultado_da_nota(), self.dados())
        self.assertIn(('identidade_fiscal', 'identidade_fiscal_insuficiente'),
            {(p.campo, p.codigo) for p in revisao.nota.problemas})
        self.assertFalse(revisao.nota.sem_problemas)

    def test_ambos_documentos_exigem_escolha_e_aceitam_pj_explicita(self):
        original = resultado_da_nota()
        original['faturado']['cnpj'] = '12ABC34501DE35'
        d = self.dados()
        d.update(faturado_cnpj='12ABC34501DE35', documento_faturado='')
        self.assertIsNone(validar_conferencia(original, d)[2])
        d['documento_faturado'] = 'CNPJ'
        _, _, revisao = validar_conferencia(original, d)
        self.assertEqual(revisao.correcoes['faturado.documento'], '12ABC34501DE35')
        self.assertEqual(revisao.original['faturado'], original['faturado'])

    def test_preenchimento_nao_escolhe_ambiguidade_nem_inventa_parcelas(self):
        original = resultado_da_nota()
        original['fornecedor']['cpf'] = '12345678909'
        original['faturado']['cnpj'] = '12ABC34501DE35'
        original['parcelas'] = []
        form, parcelas = preparar_conferencia(original)
        self.assertIsNone(form.initial['fornecedor_documento'])
        self.assertNotIn('documento_faturado', form.initial)
        self.assertFalse(parcelas.forms[0].initial)
        self.assertNotIn('chave_acesso', form.fields)
        self.assertNotIn('modelo_nota', form.fields)

    def test_campos_nao_autorizados_recusados(self):
        for k in ('id', 'analise_id', 'status', 'parcelas-0-id', 'modelo_nota', 'chave_acesso'):
            with self.subTest(k=k):
                d = self.dados()
                d[k] = 'alterado'
                with self.assertRaises(ValidationError):
                    validar_conferencia(resultado_da_nota(), d)

    def test_revalidacao_financeira_e_documental(self):
        for k, v in (('parcelas-0-valor', '149.99'), ('parcelas-0-data_vencimento', ''),
                     ('faturado_cpf', '12345678900'), ('valor_total', 'NaN'),
                     ('numero_nota', '000.123'), ('serie_nota', '-1')):
            with self.subTest(k=k, v=v):
                d = self.dados()
                d[k] = v
                self.assertIsNone(validar_conferencia(resultado_da_nota(), d)[2])

    def test_categoria_pendente_exige_escolha_ativa(self):
        original = resultado_da_nota()
        original['tipo_despesa'] = None
        form, _ = preparar_conferencia(original)
        self.assertIsNone(form.initial['classificacao'])
        d = self.dados()
        d['classificacao'] = ''
        self.assertIsNone(validar_conferencia(original, d)[2])
        self.assertIsNotNone(validar_conferencia(original, self.dados())[2])
        c = Classificacao.objects.get(tipo='DESPESA', codigo='MANUTENCAO_E_OPERACAO')
        c.status = Status.INATIVO
        c.save()
        self.assertIsNone(validar_conferencia(original, self.dados())[2])

    def test_limite_de_formularios_nao_permite_alocacao_excessiva(self):
        for total in ('0', '121', '1000000'):
            d = self.dados()
            d['parcelas-TOTAL_FORMS'] = total
            _, parcelas, revisao = validar_conferencia(resultado_da_nota(), d)
            self.assertIsNone(revisao)
            self.assertLessEqual(len(parcelas.forms), 120)

    def test_template_escapa_original_e_mostra_bloqueio(self):
        original = resultado_da_nota()
        original['fornecedor']['razao_social'] = '<script>alert(1)</script>'
        form, parcelas, revisao = validar_conferencia(original, self.dados())
        html = render_to_string('documentos/conferencia.html', {
            'form': form, 'parcelas': parcelas, 'revisao': revisao,
            'json_original': json.dumps(original, ensure_ascii=False),
        })
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('confirmação permanece bloqueada', html)
        self.assertNotIn('type="submit"', html)
