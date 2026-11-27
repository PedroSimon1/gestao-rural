"""GR-45/43: sessão real, correções otimistas e banco local; Agents simulados."""
from datetime import timedelta
import json
import uuid
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Classificacao, Pessoa
from financeiro.models import MovimentoConta
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .analises import criar_analise, garantir_dono, registrar_correcoes
from .models import AnalisePendente, StatusAnalise
from .processamento import ResultadoProcessamento
from .testing import resultado_da_nota


@override_settings(**CREDENCIAIS_TESTE)
class FluxoConferenciaTests(TestCase):
    def autenticar(self, cliente):
        autenticar_demo(cliente)
        sessao = cliente.session
        garantir_dono(sessao)
        sessao.save()
        cliente.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key

    def setUp(self):
        self.autenticar(self.client)
        self.original = resultado_da_nota()
        self.analise = criar_analise(self.client.session, self.original)
        self.url = reverse('analise_conferencia', args=[self.analise.id])

    def dados(self, versao='0'):
        c = Classificacao.objects.get(tipo='DESPESA', codigo='MANUTENCAO_E_OPERACAO')
        return {
            'versao_correcoes': versao, 'fornecedor_nome': 'Nome corrigido',
            'fornecedor_documento': '11222333000181', 'faturado_nome': 'Produtor corrigido',
            'faturado_cpf': '12345678909', 'faturado_cnpj': '', 'documento_faturado': 'CPF',
            'classificacao': str(c.pk), 'numero_nota': '123', 'serie_nota': '1',
            'data_emissao': '2026-10-01', 'valor_total': '150.00',
            'parcelas-TOTAL_FORMS': '1', 'parcelas-INITIAL_FORMS': '1',
            'parcelas-0-data_vencimento': '2026-11-01', 'parcelas-0-valor': '150.00',
        }

    def enviar_pdf(self, cliente=None):
        return (cliente or self.client).post(reverse('analise_criar'), {
            'gemini_api_key': 'chave-ficticia-nao-persistir',
            'arquivo': SimpleUploadedFile('nota.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf'),
        })

    def test_upload_cria_analise_e_redireciona_sem_pdf_chave_ou_financeiro(self):
        with mock.patch('documentos.views_analises.processar_pdf', return_value=ResultadoProcessamento(self.original, 'Teste')):
            r = self.enviar_pdf()
        self.assertEqual(r.status_code, 302)
        nova = AnalisePendente.objects.exclude(pk=self.analise.pk).get()
        self.assertEqual(nova.dados, self.original)
        self.assertNotIn('chave-ficticia', str(nova.dados))
        self.assertNotIn('%PDF', str(nova.dados))
        self.assertRedirects(r, reverse('analise_conferencia', args=[nova.id]))
        self.assertEqual(Pessoa.objects.count(), 0)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_salvar_e_reabrir_correcoes_preserva_original_e_bloqueio(self):
        r = self.client.post(self.url, self.dados())
        self.assertEqual(r.status_code, 302)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.dados, self.original)
        self.assertEqual(self.analise.correcoes['fornecedor.razao_social'], 'Nome corrigido')
        self.assertEqual(self.analise.versao_correcoes, 1)
        tela = self.client.get(self.url)
        self.assertContains(tela, 'Nome corrigido')
        self.assertContains(tela, 'confirmação permanece bloqueada')
        self.assertEqual(tela.context['form'].initial['serie_nota'], 1)
        self.assertEqual(tela.context['versao_correcoes'], 1)
        self.assertEqual(Pessoa.objects.count(), 0)
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_outra_aba_desatualizada_nao_sobrescreve_nem_recebe_versao_nova(self):
        registrar_correcoes(self.client.session, self.analise.id, {'faturado.nome': 'Outra aba'}, 0)
        r = self.client.post(self.url, self.dados('0'))
        self.assertContains(r, 'outra janela', status_code=409)
        self.assertEqual(r.context['versao_correcoes'], '0')
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.correcoes, {'faturado.nome': 'Outra aba'})

    def test_outra_sessao_nao_revela_analise_em_get_post_ou_cancelamento(self):
        outro = Client()
        self.autenticar(outro)
        inexistente = reverse('analise_conferencia', args=[uuid.uuid4()])
        esperado = outro.get(inexistente).content
        self.assertEqual(outro.get(self.url).content, esperado)
        self.assertEqual(outro.post(self.url, self.dados()).status_code, 404)
        self.assertEqual(outro.post(reverse('analise_cancelar', args=[self.analise.id])).status_code, 404)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)

    def test_expirada_impede_salvar_e_apaga_dados(self):
        with mock.patch('documentos.analises.timezone.now', return_value=timezone.now()+timedelta(minutes=31)):
            self.assertEqual(self.client.post(self.url, self.dados()).status_code, 409)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.EXPIRADA)
        self.assertIsNone(self.analise.dados)

    def test_cancelar_somente_post_e_impede_reutilizacao(self):
        url = reverse('analise_cancelar', args=[self.analise.id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.CANCELADA)
        self.assertIsNone(self.analise.dados)
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 409)

    def test_csrf_exigido_para_salvar_e_cancelar(self):
        cliente = Client(enforce_csrf_checks=True)
        self.autenticar(cliente)
        self.assertEqual(cliente.post(self.url, self.dados()).status_code, 403)
        self.assertEqual(cliente.post(reverse('analise_cancelar', args=[self.analise.id])).status_code, 403)

    def test_campos_internos_versao_e_parcelas_invalidas_nao_gravam(self):
        for extra in ({'analise_id': str(uuid.uuid4())}, {'versao_correcoes': '-1'},
                      {'versao_correcoes': '1e3'}, {'parcelas-0-valor': '149.00'}):
            with self.subTest(extra=extra):
                dados = self.dados()
                dados.update(extra)
                self.assertEqual(self.client.post(self.url, dados).status_code, 400)
                self.analise.refresh_from_db()
                self.assertEqual(self.analise.versao_correcoes, 0)

    def test_falha_banco_nao_expoe_detalhes(self):
        with mock.patch('documentos.views_analises.registrar_correcoes', side_effect=DatabaseError('senha-interna')):
            r = self.client.post(self.url, self.dados())
        self.assertEqual(r.status_code, 503)
        self.assertNotContains(r, 'senha-interna', status_code=503)

    def test_conferencia_oferece_copiar_e_baixar_o_json_original(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'data-copiar-json="json-original"')
        self.assertContains(r, 'id="json-original"')
        self.assertContains(r, f'href="{reverse("analise_json", args=[self.analise.id])}"')
        self.assertNotContains(r, 'bloco-json--curto')

    def test_download_do_json_original_tem_nome_que_identifica_a_nota(self):
        r = self.client.get(reverse('analise_json', args=[self.analise.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/json; charset=utf-8')
        self.assertEqual(
            r['Content-Disposition'],
            'attachment; filename="nota-fiscal_123_fornecedor-teste-ltda_2026-10-01_dados-extraidos.json"',
        )
        self.assertEqual(json.loads(r.content), self.original)
        self.assertIn('Óleo', r.content.decode())  # acentos preservados, como na tela

    def test_download_sem_dados_de_identificacao_usa_o_inicio_do_id(self):
        original = resultado_da_nota()
        original.update(numero_nota=None, data_emissao=None)
        original['fornecedor'].update(razao_social=None, nome_fantasia=None)
        analise = criar_analise(self.client.session, original)
        r = self.client.get(reverse('analise_json', args=[analise.id]))
        self.assertIn(f'nota-fiscal_{str(analise.id)[:8]}_dados-extraidos.json', r['Content-Disposition'])

    def test_download_do_json_so_para_a_sessao_dona_logada(self):
        url = reverse('analise_json', args=[self.analise.id])
        self.assertEqual(Client().get(url).status_code, 302)
        outro = Client()
        self.autenticar(outro)
        r = outro.get(url)
        self.assertEqual(r.status_code, 404)
        self.assertNotIn('Fornecedor Teste', r.content.decode())
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_download_do_json_apos_cancelar_ou_expirar_nao_entrega_dados(self):
        url = reverse('analise_json', args=[self.analise.id])
        AnalisePendente.objects.filter(pk=self.analise.pk).update(
            expira_em=timezone.now() - timedelta(seconds=1), criado_em=timezone.now() - timedelta(hours=1))
        r = self.client.get(url)
        self.assertEqual(r.status_code, 409)
        self.assertNotIn('Fornecedor Teste', r.content.decode())

    def test_falha_de_banco_no_download_nao_expoe_detalhes(self):
        with mock.patch('documentos.views_analises.obter_analise', side_effect=DatabaseError('senha-interna')):
            r = self.client.get(reverse('analise_json', args=[self.analise.id]))
        self.assertEqual(r.status_code, 503)
        self.assertNotContains(r, 'senha-interna', status_code=503)

    def test_banco_fora_do_ar_nao_chama_o_gemini_nem_expoe_detalhes(self):
        from django.db import InterfaceError
        antes = AnalisePendente.objects.count()
        for erro in (DatabaseError('senha-interna'), InterfaceError('senha-interna')):
            with self.subTest(erro=type(erro).__name__):
                with mock.patch('documentos.views_analises.verificar_banco', side_effect=erro), \
                        mock.patch('documentos.views_analises.processar_pdf') as processar:
                    r = self.enviar_pdf()
                processar.assert_not_called()
                self.assertContains(r, 'A nota não foi enviada ao Gemini', status_code=503)
                self.assertNotContains(r, 'senha-interna', status_code=503)
        self.assertEqual(AnalisePendente.objects.count(), antes)

    def test_banco_no_ar_a_checagem_passa_antes_do_processamento(self):
        ordem = []
        with mock.patch('documentos.views_analises.verificar_banco', side_effect=lambda: ordem.append('banco')), \
                mock.patch('documentos.views_analises.processar_pdf',
                           side_effect=lambda *a, **k: ordem.append('gemini') or ResultadoProcessamento(resultado_da_nota(), 'ok')):
            self.assertEqual(self.enviar_pdf().status_code, 302)
        self.assertEqual(ordem, ['banco', 'gemini'])

    def test_upload_sem_codigo_de_dono_exige_renovar_sessao(self):
        cliente = Client()
        autenticar_demo(cliente)
        with mock.patch('documentos.views_analises.processar_pdf') as processar:
            r = self.enviar_pdf(cliente)
        processar.assert_not_called()
        self.assertContains(r, 'renovada', status_code=409)
        self.assertEqual(AnalisePendente.objects.count(), 1)

    def test_login_obrigatorio_e_criacao_somente_post(self):
        self.assertEqual(Client().get(self.url).status_code, 302)
        self.assertEqual(self.client.get(reverse('analise_criar')).status_code, 405)

    def test_documento_inconclusivo_pode_ser_guardado_e_categoria_corrigida(self):
        original = resultado_da_nota()
        original['tipo_despesa'] = None
        with mock.patch('documentos.views_analises.processar_pdf', return_value=ResultadoProcessamento(original, 'Inconclusiva')):
            r = self.enviar_pdf()
        nova = AnalisePendente.objects.exclude(pk=self.analise.pk).get()
        self.assertEqual(self.client.post(r.url, self.dados()).status_code, 302)
        nova.refresh_from_db()
        self.assertEqual(nova.correcoes['tipo_despesa'], 'MANUTENCAO_E_OPERACAO')
