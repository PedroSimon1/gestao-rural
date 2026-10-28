"""FLU-07: criação explícita no rascunho e confirmação pelo backend real."""
from copy import deepcopy
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from agents.classificador.schemas import TipoDespesa
from cadastros.models import Classificacao, Papel, Pessoa, Status
from financeiro.models import MovimentoConta, NotaFiscalLancada, ParcelaConta
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .analises import cancelar_analise, criar_analise, garantir_dono, registrar_correcoes
from .models import StatusAnalise
from .testing import CNPJ, CPF, resultado_da_nota


@override_settings(**CREDENCIAIS_TESTE)
class ClassificacaoNaConferenciaTests(TestCase):
    def autenticar(self, client):
        autenticar_demo(client)
        s = client.session
        garantir_dono(s)
        s.save()
        client.cookies[settings.SESSION_COOKIE_NAME] = s.session_key

    def setUp(self):
        self.autenticar(self.client)
        self.original = resultado_da_nota()
        self.original.update(tipo_despesa=None, documento_fiscal={"chave_acesso": None, "modelo": "55", "serie": "1"})
        self.a = criar_analise(self.client.session, self.original)
        Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste").atribuir_papel(Papel.FORNECEDOR)
        Pessoa.objects.create(documento=CPF, razao_social="Faturado Teste").atribuir_papel(Papel.FATURADO)

    def url(self, nome="analise_conferencia"):
        return reverse(nome, args=[self.a.id])

    def dados(self):
        return {
            "versao_correcoes": "0", "acao": "criar_classificacao",
            "fornecedor_nome": "Nome do rascunho", "fornecedor_documento": CNPJ,
            "faturado_nome": "Faturado Teste", "faturado_cpf": CPF, "faturado_cnpj": "", "documento_faturado": "CPF",
            "classificacao": "", "numero_nota": "123", "serie_nota": "1", "modelo": "55", "chave_acesso": "",
            "data_emissao": "2026-10-01", "valor_total": "150.00",
            "parcelas-TOTAL_FORMS": "1", "parcelas-INITIAL_FORMS": "1", "parcelas-MIN_NUM_FORMS": "1", "parcelas-MAX_NUM_FORMS": "120",
            "parcelas-0-data_vencimento": "2026-11-01", "parcelas-0-valor": "150.00",
            "nova-tipo": "DESPESA", "nova-codigo": "NOVA_DESPESA_FICTICIA", "nova-descricao": "Despesa criada explicitamente", "nova-confirmar": "on",
        }

    def assert_sem_financeiro(self):
        self.assertEqual((MovimentoConta.objects.count(), ParcelaConta.objects.count(), NotaFiscalLancada.objects.count()), (0, 0, 0))

    def test_get_oferece_cadastro_sem_preaprovar_ou_inventar_codigo(self):
        antes = Classificacao.objects.count()
        r = self.client.get(self.url())
        self.assertContains(r, "Cadastrar nova classificação de despesa")
        self.assertFalse(r.context["nova_classificacao"].initial.get("confirmar"))
        self.assertIsNone(r.context["nova_classificacao"].initial.get("codigo"))
        self.assertEqual(Classificacao.objects.count(), antes)

    def test_criar_preserva_rascunho_original_correcoes_e_prazo(self):
        registrar_correcoes(self.client.session, self.a.id, {"faturado.nome": "Correção já salva"}, 0)
        self.a.refresh_from_db()
        antes = (deepcopy(self.a.dados), deepcopy(self.a.correcoes), self.a.versao_correcoes, self.a.expira_em)
        d = self.dados()
        d.update(versao_correcoes="1", faturado_nome="Outra edição não salva")
        r = self.client.post(self.url(), d)
        self.assertEqual(r.status_code, 200)
        c = Classificacao.objects.get(tipo="DESPESA", codigo="NOVA_DESPESA_FICTICIA")
        self.assertEqual(r.context["form"]["classificacao"].value(), str(c.pk))
        self.assertEqual(r.context["form"]["fornecedor_nome"].value(), "Nome do rascunho")
        self.assertEqual(r.context["form"]["faturado_nome"].value(), "Outra edição não salva")
        self.a.refresh_from_db()
        self.assertEqual((self.a.dados, self.a.correcoes, self.a.versao_correcoes, self.a.expira_em), antes)
        self.assert_sem_financeiro()

    def test_codigo_extraido_inexistente_e_sugerido_sem_descricao_inventada(self):
        original = deepcopy(self.original)
        original["tipo_despesa"] = "DESPESA_EXTRAIDA_INEXISTENTE"
        self.a = criar_analise(self.client.session, original)
        r = self.client.get(self.url())
        self.assertEqual(r.context["nova_classificacao"].initial["codigo"], original["tipo_despesa"])
        self.assertFalse(r.context["nova_classificacao"].initial.get("descricao"))

    def test_sem_consentimento_codigo_descricao_ou_com_tipo_incompativel_nao_cria(self):
        antes = Classificacao.objects.count()
        for campo, valor in (("nova-confirmar", ""), ("nova-codigo", ""), ("nova-descricao", ""), ("nova-tipo", "RECEITA"), ("nova-codigo", "INVÁLIDO")):
            d = self.dados()
            d[campo] = valor
            self.assertEqual(self.client.post(self.url(), d).status_code, 400)
            self.assertEqual(Classificacao.objects.count(), antes)
        self.assert_sem_financeiro()

    def test_duplicada_ativa_ou_inativa_nao_e_recriada_ou_reativada(self):
        c = Classificacao.objects.create(tipo="DESPESA", codigo="NOVA_DESPESA_FICTICIA", descricao="Original")
        for inativar in (False, True):
            if inativar:
                c.inativar()
            r = self.client.post(self.url(), self.dados())
            self.assertEqual(r.status_code, 400)
            self.assertEqual(Classificacao.objects.filter(codigo=c.codigo, tipo=c.tipo).count(), 1)
            c.refresh_from_db()
            self.assertEqual(c.descricao, "Original")
            self.assertEqual(c.status, Status.INATIVO if inativar else Status.ATIVO)

    def test_reenvio_nao_duplica(self):
        d = self.dados()
        self.assertEqual(self.client.post(self.url(), d).status_code, 200)
        self.assertEqual(self.client.post(self.url(), d).status_code, 400)
        self.assertEqual(Classificacao.objects.filter(codigo=d["nova-codigo"]).count(), 1)
        self.assert_sem_financeiro()

    def test_indice_unico_em_disputa_vira_erro_seguro(self):
        with mock.patch("documentos.forms_classificacao_nota.ClassificacaoNaNotaForm.save", side_effect=IntegrityError("SQL-ficticio-nao-expor")):
            r = self.client.post(self.url(), self.dados())
        self.assertEqual(r.status_code, 409)
        self.assertNotContains(r, "SQL-ficticio-nao-expor", status_code=409)
        self.assert_sem_financeiro()

    def test_outra_sessao_anonimo_e_csrf_nao_criam(self):
        antes = Classificacao.objects.count()
        outro = Client()
        self.autenticar(outro)
        self.assertEqual(outro.post(self.url(), self.dados()).status_code, 404)
        self.assertEqual(Client().post(self.url(), self.dados()).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(csrf.post(self.url(), self.dados()).status_code, 403)
        self.assertEqual(Classificacao.objects.count(), antes)

    def test_versao_desatualizada_bloqueia_cadastro(self):
        registrar_correcoes(self.client.session, self.a.id, {"faturado.nome": "Outra aba"}, 0)
        antes = Classificacao.objects.count()
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 409)
        self.assertEqual(Classificacao.objects.count(), antes)

    def test_cancelada_e_expirada_bloqueiam_cadastro(self):
        antes = Classificacao.objects.count()
        with mock.patch("documentos.analises.timezone.now", return_value=self.a.expira_em + timedelta(seconds=1)):
            self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 409)
        self.a = criar_analise(self.client.session, self.original)
        cancelar_analise(self.client.session, self.a.id)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 409)
        self.assertEqual(Classificacao.objects.count(), antes)

    def test_campos_externos_e_repetidos_nao_criam(self):
        antes = Classificacao.objects.count()
        for extras in ({"nova-status": "INATIVO"}, {"original": "JSON-forjado"}, {"nova-codigo": ["UM", "OUTRO"]}):
            d = self.dados()
            d.update(extras)
            self.assertEqual(self.client.post(self.url(), d).status_code, 400)
            self.assertEqual(Classificacao.objects.count(), antes)

    def test_criacao_com_rascunho_incompleto_preserva_dados_sem_salvar(self):
        d = self.dados()
        d["valor_total"] = ""
        r = self.client.post(self.url(), d)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"]["valor_total"].value(), "")
        self.a.refresh_from_db()
        self.assertIsNone(self.a.correcoes)
        self.assert_sem_financeiro()

    def test_fluxo_ate_lancamento_aceita_codigo_fora_enum_sem_mudar_agent(self):
        d = self.dados()
        self.assertNotIn(d["nova-codigo"], [e.value for e in TipoDespesa])
        self.assertEqual(self.client.post(self.url(), d).status_code, 200)
        # Criar cadastro não autoriza confirmar a nota ainda sem correções salvas.
        confirmar = {"versao_correcoes": "0", "confirmar": "on"}
        self.assertEqual(self.client.post(self.url("analise_confirmar"), confirmar).status_code, 400)
        self.assert_sem_financeiro()
        c = Classificacao.objects.get(codigo=d["nova-codigo"], tipo="DESPESA")
        d.update(acao="salvar", classificacao=str(c.pk))
        self.assertEqual(self.client.post(self.url(), d).status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.correcoes["tipo_despesa"], c.codigo)
        self.assertIsNone(self.a.dados["tipo_despesa"])
        confirmar["versao_correcoes"] = "1"
        r = self.client.post(self.url("analise_confirmar"), confirmar)
        self.assertContains(r, "Lançamento realizado com sucesso")
        m = MovimentoConta.objects.get()
        self.assertEqual(m.classificacoes.get().classificacao_id, c.pk)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, StatusAnalise.CONFIRMADA)

    def test_v1_preservada_apos_criacao(self):
        original = resultado_da_nota()
        original["tipo_despesa"] = None
        self.a = criar_analise(self.client.session, original)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 200)
        self.a.refresh_from_db()
        self.assertEqual(self.a.versao_dados, 1)
        self.assertEqual(self.a.dados, original)
        self.assertIsNone(self.a.correcoes)
