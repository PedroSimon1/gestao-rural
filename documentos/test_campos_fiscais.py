"""Componente fiscal com validadores oficiais; nenhuma consulta ou escrita."""
from copy import deepcopy

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from financeiro.test_identidade_fiscal import chave
from .forms_fiscais import CamposFiscaisForm, mensagem_fiscal, preparar_campos_fiscais
from .testing import CNPJ, CPF, resultado_da_nota


class CamposFiscaisTests(SimpleTestCase):
    def dados(self):
        return {'chave_acesso': '', 'modelo': '55', 'serie': '1', 'numero_nota': '123'}

    def test_fallback_completo_validado_oficialmente_sem_banco(self):
        form = CamposFiscaisForm(self.dados(), emitente_cnpj=CNPJ)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.identidade.emitente_cnpj, CNPJ)
        self.assertEqual(form.identidade.numero, 123)
        self.assertEqual(form.proposta_correcoes(), {'modelo': '55', 'serie': '1', 'numero_nota': '123'})

    def test_chave_numerica_e_alfanumerica_sem_inventar_campos(self):
        for cnpj in (CNPJ, '12ABC34501DE35'):
            with self.subTest(cnpj=cnpj):
                k = chave(cnpj=cnpj)
                form = CamposFiscaisForm({'chave_acesso': k}, emitente_cnpj=cnpj)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.proposta_correcoes(), {'chave_acesso': k})

    def test_dv_invalido_e_divergencia_bloqueados(self):
        k = chave()
        invalida = k[:-1]+str((int(k[-1])+1) % 10)
        form = CamposFiscaisForm({'chave_acesso': invalida}, emitente_cnpj=CNPJ)
        self.assertFalse(form.is_valid())
        self.assertIn('chave_acesso', form.errors)
        d = self.dados()
        d.update(chave_acesso=k, numero_nota='999')
        form = CamposFiscaisForm(d, emitente_cnpj=CNPJ)
        self.assertFalse(form.is_valid())
        self.assertIn('diverge', str(form.non_field_errors()))

    def test_faltantes_modelo_e_emitente_nao_sao_inventados(self):
        for d, emitente in (({}, None), (self.dados(), None), (self.dados(), CPF),
                           ({**self.dados(), 'modelo': '99'}, CNPJ)):
            with self.subTest(d=d, emitente=emitente):
                form = CamposFiscaisForm(d, emitente_cnpj=emitente)
                self.assertFalse(form.is_valid())
                with self.assertRaises(ValueError):
                    form.proposta_correcoes()

    def test_v1_nao_convertida_e_correcoes_reabertas_separadamente(self):
        original = resultado_da_nota()
        antes = deepcopy(original)
        form = preparar_campos_fiscais(original, {'modelo': '65', 'serie': '0', 'numero_nota': '456'})
        self.assertEqual(form.initial['modelo'], '65')
        self.assertEqual(form.initial['serie'], '0')
        self.assertEqual(form.initial['numero_nota'], '456')
        self.assertIsNone(form.initial['chave_acesso'])
        self.assertEqual(original, antes)
        self.assertNotIn('documento_fiscal', original)

    def test_v2_proposta_preserva_original_e_prioriza_correcao(self):
        original = resultado_da_nota()
        original['documento_fiscal'] = {'chave_acesso': None, 'modelo': '55', 'serie': '2'}
        antes = deepcopy(original)
        form = preparar_campos_fiscais(original, {'serie': '3'})
        self.assertEqual(form.initial['modelo'], '55')
        self.assertEqual(form.initial['serie'], '3')
        self.assertEqual(original, antes)

    def test_chave_malformada_preservada_no_campo_escapado(self):
        form = CamposFiscaisForm({'chave_acesso': '<script>alert(1)</script>'})
        self.assertFalse(form.is_valid())
        html = render_to_string('documentos/_campos_fiscais.html', {'fiscal': form})
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('type="submit"', html)
        self.assertNotIn('<form', html)

    def test_mensagem_desconhecida_nao_reflete_conteudo(self):
        self.assertNotIn('segredo-interno', mensagem_fiscal('segredo-interno'))
        self.assertIn('já foi lançada', mensagem_fiscal('nota_ja_lancada'))
