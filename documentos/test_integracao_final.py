"""Fluxo real GR-43/F-3/F-4/F-5; somente SDK Gemini simulado."""
from copy import deepcopy
from datetime import timedelta
import json
import uuid
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Classificacao, Papel, Pessoa, PapelPessoa, Status
from documentos.analises import criar_analise, garantir_dono, registrar_correcoes
from documentos.models import AnalisePendente, StatusAnalise
from financeiro.models import MovimentoConta, ParcelaConta, NotaFiscalLancada
from financeiro.test_identidade_fiscal import chave
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .adaptador_financeiro import adaptar_resultado
from .consultas import consultar_resultado
from .testing import resultado_da_nota


@override_settings(**CREDENCIAIS_TESTE)
class IntegracaoFinalTests(TestCase):
    def autenticar(self, cliente):
        autenticar_demo(cliente)
        s = cliente.session
        garantir_dono(s)
        s.save()
        cliente.cookies[settings.SESSION_COOKIE_NAME] = s.session_key

    def setUp(self):
        self.autenticar(self.client)
        self.original = resultado_da_nota()
        self.original['documento_fiscal'] = {'chave_acesso': None, 'modelo': '55', 'serie': '1'}
        self.a = criar_analise(self.client.session, self.original)

    def url(self, nome='analise_conferencia', analise=None):
        return reverse(nome, args=[(analise or self.a).id])

    def dados(self, versao='0'):
        c = Classificacao.objects.get(tipo='DESPESA', codigo='MANUTENCAO_E_OPERACAO')
        return {'versao_correcoes': versao, 'fornecedor_nome': 'Fornecedor corrigido',
            'fornecedor_documento': '11222333000181', 'faturado_nome': 'Faturado corrigido',
            'faturado_cpf': '12345678909', 'faturado_cnpj': '', 'documento_faturado': 'CPF',
            'classificacao': str(c.pk), 'numero_nota': '123', 'serie_nota': '1',
            'modelo': '55', 'chave_acesso': '', 'data_emissao': '2026-10-01', 'valor_total': '150.00',
            'parcelas-TOTAL_FORMS': '1', 'parcelas-INITIAL_FORMS': '1',
            'parcelas-0-data_vencimento': '2026-11-01', 'parcelas-0-valor': '150.00'}

    def confirmar(self, versao='0', **kw):
        dados = {'versao_correcoes': versao, 'confirmar': 'on',
            'fornecedor_decisoes': ['CRIAR_PESSOA'], 'faturado_decisoes': ['CRIAR_PESSOA']}
        dados.update(kw)
        return self.client.post(self.url('analise_confirmar'), dados)

    def test_campos_principais_nao_apagam_correcoes_fiscais_omitidas(self):
        legado = resultado_da_nota()
        a = criar_analise(self.client.session, legado)
        registrar_correcoes(self.client.session, a.id, {'modelo': '55', 'chave_acesso': chave()}, 0)
        d = self.dados('1')
        d.pop('chave_acesso')
        d.pop('modelo')
        r = self.client.post(self.url(analise=a), d)
        self.assertEqual(r.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.correcoes['modelo'], '55')
        self.assertEqual(a.correcoes['chave_acesso'], chave())
        self.assertEqual(a.dados, legado)
        tela = self.client.get(self.url(analise=a))
        self.assertEqual(tela.context['form'].initial['modelo'], '55')
        self.assertEqual(tela.context['form'].initial['chave_acesso'], chave())

    def test_apagar_correcao_opcional_e_acao_explicita_nao_mutacao_do_extraido(self):
        registrar_correcoes(self.client.session, self.a.id, {'chave_acesso': chave()}, 0)
        self.assertEqual(self.client.post(self.url(), self.dados('1')).status_code, 302)
        self.a.refresh_from_db()
        self.assertNotIn('chave_acesso', self.a.correcoes or {})
        self.assertEqual(self.a.dados, self.original)

    def test_correcao_fiscal_invalida_nao_grava_e_aponta_campo(self):
        d = self.dados()
        d['chave_acesso'] = 'nao-e-chave'
        r = self.client.post(self.url(), d)
        self.assertEqual(r.status_code, 400)
        self.assertIn('chave_acesso', r.context['form'].errors)
        self.a.refresh_from_db()
        self.assertEqual(self.a.versao_correcoes, 0)

    def test_divergencia_exibida_e_confirmacao_bloqueada(self):
        d = self.dados()
        d.update(chave_acesso=chave(), numero_nota='999')
        r = self.client.post(self.url(), d, follow=True)
        self.assertContains(r, 'diverge')
        self.assertNotContains(r, 'Revisar dados salvos para confirmar')
        r = self.confirmar('1')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_v1_pode_ser_completada_e_confirmada_sem_converter_ou_mudar_ttl(self):
        self.a = criar_analise(self.client.session, resultado_da_nota())
        prazo = self.a.expira_em
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.versao_dados, 1)
        self.assertEqual(self.a.expira_em, prazo)
        self.assertNotIn('documento_fiscal', self.a.dados)
        self.assertContains(self.confirmar('1'), 'Lançamento realizado com sucesso')

    def test_pdf_agents_v2_conferencia_correcao_decisoes_e_lancamento(self):
        bruto = deepcopy(self.original)
        bruto['documento_e_nota_fiscal'] = True
        cliente = mock.Mock()
        cliente.gerar_json.side_effect = [bruto, {'tipo_despesa': 'MANUTENCAO_E_OPERACAO', 'justificativa': 'Manutenção.'}]
        with mock.patch('documentos.processamento._criar_cliente', return_value=cliente):
            r = self.client.post(reverse('analise_criar'), {
                'gemini_api_key': 'ficticia-nao-guardar',
                'arquivo': SimpleUploadedFile('nota.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')})
        self.assertEqual(r.status_code, 302)
        self.a = AnalisePendente.objects.exclude(pk=self.a.pk).get()
        self.assertEqual(self.a.versao_dados, 2)
        self.assertEqual(len(self.a.dados), 11)
        self.assertNotIn('ficticia-nao-guardar', json.dumps(self.a.dados))
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 302)
        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertContains(self.client.get(self.url('analise_confirmar')), 'Confirmar lançamento financeiro')
        self.assertContains(self.confirmar('1'), 'Lançamento realizado com sucesso')
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(ParcelaConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
        self.assertEqual(Pessoa.objects.count(), 2)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, StatusAnalise.CONFIRMADA)
        self.assertIsNone(self.a.dados)
        self.assertEqual(self.confirmar('1').status_code, 409)
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_confirmacao_explicita_e_decisoes_necessarias(self):
        r = self.confirmar(confirmar='')
        self.assertEqual(r.status_code, 400)
        r = self.confirmar(fornecedor_decisoes=[], faturado_decisoes=[])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pessoa.objects.count(), 0)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_get_confirmacao_so_leitura_e_nao_marca_consentimento(self):
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get(self.url('analise_confirmar'))
        self.assertContains(r, 'Confirmar lançamento financeiro')
        for q in queries:
            self.assertFalse(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')))
        self.assertFalse(r.context['form_confirmacao'].initial.get('confirmar'))

    def test_reativacao_e_papel_exigem_autorizacao_explicita(self):
        pessoa = Pessoa.objects.create(documento='11222333000181', razao_social='Fornecedor')
        pessoa.inativar()
        self.assertEqual(self.confirmar().status_code, 400)
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.INATIVO)
        r = self.confirmar(fornecedor_decisoes=['REATIVAR_PESSOA', 'ATRIBUIR_PAPEL'])
        self.assertContains(r, 'Lançamento realizado com sucesso')
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.status, Status.ATIVO)
        self.assertTrue(PapelPessoa.objects.filter(pessoa=pessoa, papel=Papel.FORNECEDOR).exists())

    def test_outra_sessao_csrf_cancelada_expirada_e_conflito_de_versao(self):
        outro = Client()
        self.autenticar(outro)
        self.assertEqual(outro.get(self.url('analise_confirmar')).status_code, 404)
        self.assertEqual(outro.post(self.url('analise_confirmar'), {'confirmar': 'on'}).status_code, 404)
        csrf = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf.post(self.url('analise_confirmar')).status_code, 403)
        registrar_correcoes(self.client.session, self.a.id, {'faturado.nome': 'Outra aba'}, 0)
        self.assertEqual(self.confirmar('0').status_code, 409)
        with mock.patch('documentos.analises.timezone.now', return_value=timezone.now()+timedelta(minutes=31)):
            self.assertEqual(self.confirmar('1').status_code, 409)
        a = criar_analise(self.client.session, self.original)
        self.client.post(self.url('analise_cancelar', a))
        self.assertEqual(self.client.post(self.url('analise_confirmar', a), {'confirmar': 'on'}).status_code, 409)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_financeiro_incompleto_corrigivel_e_consultas_v2_sem_escrita(self):
        d = deepcopy(self.original)
        d['valor_total'] = None
        d['parcelas'][0]['valor'] = None
        d['fornecedor']['cnpj'] = None
        d['fornecedor']['cpf'] = '12345678909'
        d['faturado']['cpf'] = None
        d['faturado']['cnpj'] = '12ABC34501DE35'
        antes = deepcopy(d)
        with CaptureQueriesContext(connection) as queries:
            adaptada = adaptar_resultado(d)
            consultada = consultar_resultado(d)
        self.assertIsNone(adaptada.valor_total)
        self.assertIsNone(adaptada.parcelas[0].valor)
        self.assertEqual(consultada.fornecedor.documento, '12345678909')
        self.assertEqual(consultada.faturado.documento, '12ABC34501DE35')
        self.assertEqual(d, antes)
        for q in queries:
            self.assertTrue(q['sql'].lstrip().upper().startswith('SELECT'))
        a = criar_analise(self.client.session, d)
        self.assertContains(self.client.get(self.url(analise=a)), 'Valor total')
        self.assertEqual(self.client.post(self.url('analise_confirmar', a), {'versao_correcoes': '0', 'confirmar': 'on'}).status_code, 400)

    def test_ambiguidade_fornecedor_nao_escolhe_documento(self):
        self.original['fornecedor']['cpf'] = '12345678909'
        with self.assertRaises(ValidationError) as contexto:
            consultar_resultado(self.original)
        self.assertEqual(contexto.exception.code, 'fornecedor_documento_ambiguo')

    def test_rollback_real_depois_de_criar_pessoas_nao_mostra_sucesso(self):
        with mock.patch('financeiro.lancamento_nota.registrar_movimento', side_effect=DatabaseError('detalhe-interno')):
            r = self.confirmar()
        self.assertEqual(r.status_code, 503)
        self.assertNotContains(r, 'detalhe-interno', status_code=503)
        self.assertNotContains(r, 'Lançamento realizado com sucesso', status_code=503)
        self.assertEqual(Pessoa.objects.count(), 0)
        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, StatusAnalise.PENDENTE)

    def test_payload_adulterado_e_decisao_desconhecida_recusados(self):
        self.assertEqual(self.confirmar(analise_id=str(uuid.uuid4())).status_code, 400)
        self.assertEqual(self.confirmar(fornecedor_decisoes=['ACAO_INVENTADA']).status_code, 400)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_regularizacao_selecionada_e_autorizada_preserva_mesmo_cadastro(self):
        pessoa = Pessoa.objects.create(razao_social='Cadastro pendente', situacao_documental='INCOMPLETO')
        self.assertEqual(self.confirmar(fornecedor_pessoa_incompleta_id=str(pessoa.pk)).status_code, 400)
        pessoa.refresh_from_db()
        self.assertFalse(pessoa.documentacao_completa)
        r = self.confirmar(fornecedor_pessoa_incompleta_id=str(pessoa.pk),
            fornecedor_decisoes=['REGULARIZAR', 'ATRIBUIR_PAPEL'])
        self.assertContains(r, 'Lançamento realizado com sucesso')
        pessoa.refresh_from_db()
        self.assertTrue(pessoa.documentacao_completa)
        self.assertEqual(pessoa.documento, '11222333000181')
        self.assertEqual(Pessoa.objects.count(), 2)

    def test_mesma_nota_em_outra_analise_e_bloqueada_sem_novo_movimento(self):
        self.assertContains(self.confirmar(), 'Lançamento realizado com sucesso')
        self.a = criar_analise(self.client.session, self.original)
        r = self.confirmar()
        self.assertContains(r, 'já foi lançada', status_code=400)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, StatusAnalise.PENDENTE)
