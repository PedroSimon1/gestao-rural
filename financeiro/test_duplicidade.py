"""2C: aviso de conta parecida, no formulário manual e na confirmação da nota. PostgreSQL local de teste."""
import uuid
from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from . import manual
from .duplicidade import movimentos_parecidos
from .models import MovimentoConta
from .test_manual import VENCIMENTOS, ContaManualBase, parcelas


class MovimentosParecidosTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        self.existente = manual.registrar_conta_manual(self.pagar(parcelas=parcelas("1000.00")))

    def buscar(self, contraparte=None, valor=Decimal("1000.00"), vencimento=VENCIMENTOS[0], **kw):
        return movimentos_parecidos(contraparte or self.fornecedor.pk, valor, vencimento, **kw)

    def test_acha_mesma_contraparte_valor_e_primeiro_vencimento(self):
        achados = self.buscar()

        self.assertEqual([m.id for m in achados], [self.existente.id])
        self.assertEqual((achados[0].origem, achados[0].primeiro_vencimento), ("MANUAL", VENCIMENTOS[0]))

    def test_qualquer_diferenca_nao_e_parecida(self):
        outro_fornecedor = self.cliente.pk
        self.assertEqual(self.buscar(contraparte=outro_fornecedor), ())
        self.assertEqual(self.buscar(valor=Decimal("1000.01")), ())
        self.assertEqual(self.buscar(vencimento=VENCIMENTOS[1]), ())

    def test_sem_vencimento_compara_so_contraparte_e_valor(self):
        self.assertEqual([m.id for m in self.buscar(vencimento=None)], [self.existente.id])

    def test_cancelada_nao_conta(self):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s", [self.existente.id])

        self.assertEqual(self.buscar(), ())

    def test_a_propria_solicitacao_nao_e_outra_conta(self):
        chave = MovimentoConta.objects.get(pk=self.existente.id).chave_idempotencia

        self.assertEqual(self.buscar(excluir_chave=chave), ())
        self.assertEqual(len(self.buscar(excluir_chave=uuid.uuid4())), 1)

    def test_limite_e_mais_recentes_primeiro(self):
        outras = [manual.registrar_conta_manual(self.pagar(parcelas=parcelas("1000.00"))) for _ in range(6)]

        achados = self.buscar(limite=3)

        self.assertEqual([m.id for m in achados], [o.id for o in reversed(outras)][:3])

    def test_argumentos_de_tipo_errado(self):
        for args in (("1", Decimal("1")), (True, Decimal("1")), (1, 1.0), (1, "1.00")):
            with self.subTest(args=args), self.assertRaises(TypeError):
                movimentos_parecidos(*args)


@override_settings(**CREDENCIAIS_TESTE)
class FormularioManualComAvisoTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        autenticar_demo(self.client)
        self.url = reverse("conta_manual_nova")

    def abrir(self):
        """GET do formulário: devolve o POST que o navegador enviaria (chave e assinatura reais)."""
        resposta = self.client.get(self.url)
        form = resposta.context["form"]
        return {
            "tipo": "APAGAR", "chave_idempotencia": str(form["chave_idempotencia"].value()),
            "solicitacao": form["solicitacao"].value(),
            "contraparte": self.fornecedor.pk, "faturado": self.faturado.pk, "valor_total": "1000,00",
            "classificacoes": [self.manutencao.pk], "principal": self.manutencao.pk, "confirmar": "on",
            "parcelas-TOTAL_FORMS": "1", "parcelas-INITIAL_FORMS": "0", "parcelas-MIN_NUM_FORMS": "1",
            "parcelas-MAX_NUM_FORMS": "120", "parcelas-0-data_vencimento": VENCIMENTOS[0].isoformat(),
            "parcelas-0-valor": "1000,00",
        }

    def test_sem_conta_parecida_registra_direto(self):
        resposta = self.client.post(self.url, self.abrir())

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_com_conta_parecida_avisa_e_nao_registra_sem_ciencia(self):
        existente = manual.registrar_conta_manual(self.pagar(parcelas=parcelas("1000.00")))

        resposta = self.client.post(self.url, self.abrir())

        self.assertEqual(resposta.status_code, 409)
        self.assertContains(resposta, "Já existe conta parecida", status_code=409)
        self.assertContains(resposta, f"Conta nº {existente.id}", status_code=409)
        self.assertContains(resposta, 'name="ciente_duplicidade"', status_code=409)
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_com_ciencia_registra_mesmo_assim_usando_a_mesma_solicitacao(self):
        manual.registrar_conta_manual(self.pagar(parcelas=parcelas("1000.00")))
        dados = self.abrir()
        self.assertEqual(self.client.post(self.url, dados).status_code, 409)

        resposta = self.client.post(self.url, {**dados, "ciente_duplicidade": "on"})

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(MovimentoConta.objects.count(), 2)

    def test_reenviar_a_mesma_solicitacao_ja_registrada_nao_vira_aviso(self):
        dados = self.abrir()
        primeira = self.client.post(self.url, dados)
        self.assertEqual(primeira.status_code, 302)

        segunda = self.client.post(self.url, dados)

        self.assertEqual(segunda.status_code, 302)  # idempotente: devolve a conta já gravada
        self.assertEqual(segunda.headers["Location"], primeira.headers["Location"])
        self.assertEqual(MovimentoConta.objects.count(), 1)

    def test_a_pagina_nova_esconde_o_campo_de_ciencia_e_nao_mostra_aviso(self):
        pagina = self.client.get(self.url)

        self.assertContains(pagina, "<div hidden>")  # o campo existe (o servidor o espera), mas oculto
        self.assertNotContains(pagina, "Já existe conta parecida")

    def test_valor_ou_vencimento_diferente_nao_avisa(self):
        manual.registrar_conta_manual(self.pagar(parcelas=parcelas("1000.00")))
        dados = self.abrir()
        dados["parcelas-0-data_vencimento"] = date(2027, 5, 5).isoformat()

        self.assertEqual(self.client.post(self.url, dados).status_code, 302)
