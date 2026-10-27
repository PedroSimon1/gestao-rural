"""P08/GR-48: confirmação e reenvios com serviço real, somente PostgreSQL TEST."""
from unittest import mock

from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cadastros.models import Papel
from cadastros.pendentes import salvar_cadastro_pendente
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from . import manual
from .models import MovimentoConta
from .test_manual import ContaManualBase, contagens


@override_settings(**CREDENCIAIS_TESTE)
class InterfaceManuaisTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        autenticar_demo(self.client)
        self.url = reverse("conta_manual_nova")

    def dados(self, tipo="APAGAR", *, client=None):
        client = client or self.client
        tela = client.get(self.url, {"tipo": tipo})
        self.assertEqual(tela.status_code, 200)
        inicial = tela.context["form"].initial
        classificacao = self.manutencao if tipo == "APAGAR" else self.venda
        return {
            "tipo": tipo, "chave_idempotencia": str(inicial["chave_idempotencia"]),
            "solicitacao": inicial["solicitacao"],
            "contraparte": str((self.fornecedor if tipo == "APAGAR" else self.cliente).pk),
            "faturado": str(self.faturado.pk) if tipo == "APAGAR" else "",
            "valor_total": "150,00", "classificacoes": [str(classificacao.pk)],
            "principal": str(classificacao.pk), "confirmar": "on",
            "parcelas-TOTAL_FORMS": "1", "parcelas-INITIAL_FORMS": "0",
            "parcelas-MIN_NUM_FORMS": "1", "parcelas-MAX_NUM_FORMS": "120",
            "parcelas-0-data_vencimento": "2026-11-30", "parcelas-0-valor": "150,00",
        }

    def test_sem_login_nao_abre_nem_registra(self):
        for metodo in (Client().get, Client().post):
            self.assertRedirects(metodo(self.url), reverse("login"), fetch_redirect_response=False)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_novo_formulario_gera_uuid_distinto_sem_gravar(self):
        a, b = self.dados(), self.dados()
        self.assertNotEqual(a["chave_idempotencia"], b["chave_idempotencia"])
        self.assertEqual(contagens(), (0, 0, 0))
        self.assertIn("no-store", self.client.get(self.url).headers["Cache-Control"])

    def test_pagar_multiplas_classificacoes_com_principal_e_parcelas(self):
        d = self.dados()
        d.update(classificacoes=[str(self.manutencao.pk), str(self.infraestrutura.pk)], principal=str(self.infraestrutura.pk))
        d.update({"parcelas-TOTAL_FORMS": "2", "parcelas-0-valor": "50,00", "parcelas-1-data_vencimento": "2026-12-30", "parcelas-1-valor": "100.00"})
        with mock.patch("financeiro.views_manuais.registrar_conta_manual", wraps=manual.registrar_conta_manual) as registrar:
            r = self.client.post(self.url, d)
        registrar.assert_called_once()
        m = MovimentoConta.objects.get()
        self.assertRedirects(r, reverse("conta_detalhe", args=[m.pk]))
        self.assertEqual((m.tipo, m.origem, m.faturado_id), ("APAGAR", "MANUAL", self.faturado.pk))
        self.assertEqual(m.classificacoes.get(principal=True).classificacao_id, self.infraestrutura.pk)
        self.assertEqual(list(m.parcelas.values_list("numero", flat=True)), [1, 2])
        self.assertEqual(contagens(), (1, 2, 2))

    def test_receber_sem_faturado(self):
        r = self.client.post(self.url, self.dados("ARECEBER"))
        self.assertEqual(r.status_code, 302)
        m = MovimentoConta.objects.get()
        self.assertEqual((m.tipo, m.contraparte_id, m.faturado_id), ("ARECEBER", self.cliente.pk, None))

    def test_pf_fornecedor_e_pj_faturado_sem_inferencia_por_documento(self):
        self.faturado.atribuir_papel(Papel.FORNECEDOR)
        self.cliente.atribuir_papel(Papel.FATURADO)
        d = self.dados()
        d.update(contraparte=str(self.faturado.pk), faturado=str(self.cliente.pk))
        self.assertEqual(self.client.post(self.url, d).status_code, 302)
        m = MovimentoConta.objects.get()
        self.assertEqual((m.contraparte_id, m.faturado_id), (self.faturado.pk, self.cliente.pk))

    def test_confirmacao_explicita_obrigatoria(self):
        d = self.dados()
        del d["confirmar"]
        with mock.patch("financeiro.views_manuais.registrar_conta_manual") as registrar:
            r = self.client.post(self.url, d)
        self.assertEqual(r.status_code, 400)
        registrar.assert_not_called()
        self.assertEqual(contagens(), (0, 0, 0))

    def test_faturado_obrigatorio_em_pagar_e_papel_correto_quando_opcional(self):
        for tipo, faturado in (("APAGAR", ""), ("ARECEBER", str(self.fornecedor.pk))):
            d = self.dados(tipo)
            d["faturado"] = faturado
            self.assertEqual(self.client.post(self.url, d).status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_classificacao_compativel_e_principal_selecionada(self):
        for extras in ({"classificacoes": [str(self.venda.pk)], "principal": str(self.venda.pk)}, {"principal": str(self.infraestrutura.pk)}, {"classificacoes": []}):
            d = self.dados()
            d.update(extras)
            self.assertEqual(self.client.post(self.url, d).status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_soma_invalida_preserva_chave_e_reenvio_corrigido_grava_uma_vez(self):
        d = self.dados()
        d["parcelas-0-valor"] = "100,00"
        r = self.client.post(self.url, d)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.context["form"].data["chave_idempotencia"], d["chave_idempotencia"])
        self.assertEqual(r.context["form"].data["solicitacao"], d["solicitacao"])
        self.assertEqual(contagens(), (0, 0, 0))
        d["parcelas-0-valor"] = "150,00"
        self.assertEqual(self.client.post(self.url, d).status_code, 302)
        self.assertEqual(contagens(), (1, 1, 1))

    def test_reenvio_identico_nao_duplica(self):
        d = self.dados()
        a, b = self.client.post(self.url, d), self.client.post(self.url, d)
        self.assertEqual((a.status_code, b.status_code), (302, 302))
        self.assertEqual(a.headers["Location"], b.headers["Location"])
        self.assertEqual(contagens(), (1, 1, 1))

    def test_mesma_chave_com_dados_diferentes_recusa_sem_alterar_original(self):
        d = self.dados()
        self.assertEqual(self.client.post(self.url, d).status_code, 302)
        d.update(valor_total="200.00", **{"parcelas-0-valor": "200.00"})
        r = self.client.post(self.url, d)
        self.assertContains(r, "já registrou outra conta", status_code=400)
        self.assertEqual(str(MovimentoConta.objects.get().valor_total), "150.00")
        self.assertEqual(contagens(), (1, 1, 1))

    def test_nova_conta_identica_com_novo_uuid_e_permitida(self):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, self.dados()).status_code, 302)
        self.assertEqual(contagens(), (2, 2, 2))

    def test_chave_ausente_ou_token_adulterado_nao_chega_ao_servico(self):
        for campo, valor in (("chave_idempotencia", ""), ("chave_idempotencia", "5c95a345-2395-4411-bf03-0dc51d13cb12"), ("solicitacao", "adulterado")):
            d = self.dados()
            d[campo] = valor
            with mock.patch("financeiro.views_manuais.registrar_conta_manual") as registrar:
                self.assertEqual(self.client.post(self.url, d).status_code, 400)
                registrar.assert_not_called()

    def test_solicitacao_de_outra_sessao_nao_registra(self):
        d = self.dados()
        outro = Client()
        autenticar_demo(outro)
        self.dados(client=outro)
        self.assertEqual(outro.post(self.url, d).status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_tipo_assinado_nao_pode_ser_trocado_no_post(self):
        d = self.dados()
        d.update(tipo="ARECEBER", contraparte=str(self.cliente.pk), faturado="", classificacoes=[str(self.venda.pk)], principal=str(self.venda.pk))
        self.assertEqual(self.client.post(self.url, d).status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_csrf_obrigatorio(self):
        client = Client(enforce_csrf_checks=True)
        autenticar_demo(client)
        d = self.dados(client=client)
        self.assertEqual(client.post(self.url, d).status_code, 403)
        d["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, d).status_code, 302)

    def test_inativos_e_incompletos_nao_sao_lancados(self):
        d = self.dados()
        self.fornecedor.inativar()
        self.assertEqual(self.client.post(self.url, d).status_code, 400)
        self.fornecedor.reativar()
        papel = self.fornecedor.papeis.get(papel=Papel.FORNECEDOR)
        papel.inativar()
        self.assertEqual(self.client.post(self.url, d).status_code, 400)
        pendente = salvar_cadastro_pendente("Pendente fictício", Papel.FORNECEDOR, consentimento=True)
        d["contraparte"] = str(pendente.id)
        self.assertEqual(self.client.post(self.url, d).status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_backend_revalida_inativacao_apos_validacao_do_formulario(self):
        d = self.dados()
        def registrar(conta):
            self.manutencao.inativar()
            return manual.registrar_conta_manual(conta)
        with mock.patch("financeiro.views_manuais.registrar_conta_manual", side_effect=registrar):
            r = self.client.post(self.url, d)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_remover_parcela_antes_de_registrar_renumera_no_servico(self):
        d = self.dados()
        d.update({"parcelas-TOTAL_FORMS": "2", "parcelas-0-DELETE": "on", "parcelas-1-data_vencimento": "2026-12-30", "parcelas-1-valor": "150,00"})
        self.assertEqual(self.client.post(self.url, d).status_code, 302)
        m = MovimentoConta.objects.get()
        self.assertEqual(list(m.parcelas.values_list("numero", flat=True)), [1])

    def test_formset_ausente_excessivo_ou_sem_parcela_ativa_nao_grava(self):
        for extras in ({"parcelas-TOTAL_FORMS": ""}, {"parcelas-TOTAL_FORMS": "1000000"}, {"parcelas-0-DELETE": "on"}):
            d = self.dados()
            d.update(extras)
            r = self.client.post(self.url, d)
            self.assertEqual(r.status_code, 400)
            self.assertLessEqual(len(r.context["parcelas"].forms), 120)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_valores_ambiguos_ou_invalidos_nao_sao_convertidos_silenciosamente(self):
        for valor in ("1.250", "1.250,00", "NaN", "Infinity", "-1", "0", "1e3"):
            d = self.dados()
            d["valor_total"] = valor
            with mock.patch("financeiro.views_manuais.registrar_conta_manual") as registrar:
                self.assertEqual(self.client.post(self.url, d).status_code, 400)
                registrar.assert_not_called()

    def test_campos_externos_e_scalar_repetido_nao_gravam(self):
        d = self.dados()
        d["origem"] = "NOTA_FISCAL"
        self.assertEqual(self.client.post(self.url, d).status_code, 400)
        del d["origem"]
        d["valor_total"] = ["1.00", "150.00"]
        self.assertEqual(self.client.post(self.url, d).status_code, 400)
        self.assertEqual(contagens(), (0, 0, 0))

    def test_resposta_falha_depois_da_gravacao_reenvio_nao_duplica(self):
        d = self.dados()
        def gravar_e_falhar(conta):
            manual.registrar_conta_manual(conta)
            raise DatabaseError("SQL-ficticio-nao-expor")
        with mock.patch("financeiro.views_manuais.registrar_conta_manual", side_effect=gravar_e_falhar):
            r = self.client.post(self.url, d)
        self.assertEqual(r.status_code, 503)
        self.assertNotContains(r, "SQL-ficticio-nao-expor", status_code=503)
        self.assertEqual(r.context["form"].data["chave_idempotencia"], d["chave_idempotencia"])
        self.assertEqual(contagens(), (1, 1, 1))
        self.assertEqual(self.client.post(self.url, d).status_code, 302)
        self.assertEqual(contagens(), (1, 1, 1))
