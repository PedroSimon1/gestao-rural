"""D1: baixa de parcela (paga/recebida) e sua tela; D3: nota fiscal no detalhe. PostgreSQL local de teste."""
import threading
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from . import manual
from .models import AlteracaoNaoPermitida, MovimentoConta, ParcelaConta
from .pagamentos import desfazer_pagamento, registrar_pagamento
from .test_manual import VENCIMENTOS, ContaManualBase, parcelas

ONTEM = timezone.localdate() - timedelta(days=1)


def parcela(detalhe, numero=1):
    return ParcelaConta.objects.get(movimento_id=detalhe.id, numero=numero)


class RegistroDePagamentoTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        self.conta = manual.registrar_conta_manual(self.pagar(parcelas=parcelas("600.00", "400.00")))
        self.primeira = parcela(self.conta, 1)

    def assert_recusado(self, codigo, funcao, *args):
        with self.assertRaises(ValidationError) as contexto:
            funcao(*args)
        self.assertEqual(contexto.exception.code, codigo)

    def test_registra_a_data_e_so_ela(self):
        antes = ParcelaConta.objects.values("numero", "valor", "data_vencimento", "status", "identificador")

        registrar_pagamento(self.primeira.pk, ONTEM)

        self.primeira.refresh_from_db()
        self.assertEqual(self.primeira.pago_em, ONTEM)
        self.assertEqual(list(ParcelaConta.objects.values("numero", "valor", "data_vencimento", "status", "identificador")), list(antes))
        self.assertIsNone(parcela(self.conta, 2).pago_em)

    def test_aceita_hoje_e_recusa_data_futura_ou_invalida(self):
        registrar_pagamento(self.primeira.pk, timezone.localdate())
        segunda = parcela(self.conta, 2)

        self.assert_recusado("data_futura", registrar_pagamento, segunda.pk, timezone.localdate() + timedelta(days=1))
        for invalida in (None, "2026-11-01", timezone.now()):
            with self.subTest(data=invalida):
                self.assert_recusado("data_invalida", registrar_pagamento, segunda.pk, invalida)
        segunda.refresh_from_db()
        self.assertIsNone(segunda.pago_em)

    def test_nao_registra_duas_vezes_e_desfaz_voltando_a_em_aberto(self):
        registrar_pagamento(self.primeira.pk, ONTEM)

        self.assert_recusado("pagamento_ja_registrado", registrar_pagamento, self.primeira.pk, ONTEM)
        desfazer_pagamento(self.primeira.pk)
        self.primeira.refresh_from_db()
        self.assertIsNone(self.primeira.pago_em)
        self.assert_recusado("pagamento_nao_registrado", desfazer_pagamento, self.primeira.pk)

    def test_parcela_inexistente_e_identificador_de_tipo_errado(self):
        self.assert_recusado("parcela_inexistente", registrar_pagamento, 99999999, ONTEM)
        for errado in ("1", True, None):
            with self.subTest(parcela_id=errado), self.assertRaises(TypeError):
                registrar_pagamento(errado, ONTEM)

    def test_lancamento_cancelado_nao_recebe_baixa(self):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s", [self.conta.id])

        self.assert_recusado("movimento_cancelado", registrar_pagamento, self.primeira.pk, ONTEM)

    def test_demais_campos_da_parcela_continuam_imutaveis(self):
        registrar_pagamento(self.primeira.pk, ONTEM)
        pago = ParcelaConta.objects.get(pk=self.primeira.pk)
        pago.valor = Decimal("1.00")

        with self.assertRaises(AlteracaoNaoPermitida):
            pago.save()
        with self.assertRaises(AlteracaoNaoPermitida):
            ParcelaConta.objects.filter(pk=pago.pk).update(valor=Decimal("1.00"))

    def test_baixa_de_todas_as_parcelas_nao_quebra_a_soma_do_lancamento(self):
        registrar_pagamento(self.primeira.pk, ONTEM)
        registrar_pagamento(parcela(self.conta, 2).pk, ONTEM)

        detalhe = manual.consultar_movimento(self.conta.id)

        self.assertEqual(detalhe.valor_em_aberto, Decimal("0.00"))
        self.assertEqual(sum(p.valor for p in detalhe.parcelas), detalhe.valor_total)


class ConsultaComPagamentoTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        self.duas = manual.registrar_conta_manual(self.pagar(parcelas=parcelas("600.00", "400.00")))
        self.uma = manual.registrar_conta_manual(self.receber())

    def test_detalhe_mostra_baixa_e_valor_em_aberto(self):
        registrar_pagamento(parcela(self.duas, 1).pk, ONTEM)

        detalhe = manual.consultar_movimento(self.duas.id)

        self.assertEqual(detalhe.valor_em_aberto, Decimal("400.00"))
        self.assertEqual([p.pago_em for p in detalhe.parcelas], [ONTEM, None])
        self.assertIsNone(detalhe.nota_fiscal)

    def test_resumo_conta_pagas_e_o_proximo_vencimento_ignora_as_pagas(self):
        registrar_pagamento(parcela(self.duas, 1).pk, ONTEM)

        resumo = {item.id: item for item in manual.listar_movimentos().itens}

        self.assertEqual((resumo[self.duas.id].quantidade_parcelas, resumo[self.duas.id].quantidade_pagas), (2, 1))
        self.assertEqual(resumo[self.duas.id].proximo_vencimento, VENCIMENTOS[1])
        self.assertEqual((resumo[self.uma.id].quantidade_parcelas, resumo[self.uma.id].quantidade_pagas), (1, 0))
        self.assertEqual(resumo[self.uma.id].proximo_vencimento, VENCIMENTOS[0])

    def test_filtro_em_aberto_e_quitado(self):
        registrar_pagamento(parcela(self.duas, 1).pk, ONTEM)
        registrar_pagamento(parcela(self.uma, 1).pk, ONTEM)
        ids = lambda pagamento: {i.id for i in manual.listar_movimentos(pagamento=pagamento).itens}

        self.assertEqual(ids("EM_ABERTO"), {self.duas.id})
        self.assertEqual(ids("QUITADO"), {self.uma.id})
        registrar_pagamento(parcela(self.duas, 2).pk, ONTEM)
        self.assertEqual(ids("EM_ABERTO"), set())
        self.assertEqual(ids("QUITADO"), {self.duas.id, self.uma.id})
        self.assertEqual(ids(None), {self.duas.id, self.uma.id})
        with self.assertRaises(ValueError):
            manual.listar_movimentos(pagamento="PAGO")


@override_settings(**CREDENCIAIS_TESTE)
class TelaDePagamentoTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        autenticar_demo(self.client)
        self.pagar_conta = manual.registrar_conta_manual(self.pagar(parcelas=parcelas("600.00", "400.00")))
        self.receber_conta = manual.registrar_conta_manual(self.receber())
        self.primeira = parcela(self.pagar_conta, 1)

    def url(self, parcela_id):
        return reverse("parcela_pagamento", args=[parcela_id])

    def detalhe(self, conta):
        return reverse("conta_detalhe", args=[conta.id])

    def test_detalhe_oferece_a_baixa_de_cada_parcela_em_aberto(self):
        resposta = self.client.get(self.detalhe(self.pagar_conta))

        self.assertContains(resposta, "Marcar como paga", count=2)
        self.assertContains(resposta, f'action="{self.url(self.primeira.pk)}"')
        self.assertContains(resposta, "Ainda a pagar")
        self.assertContains(self.client.get(self.detalhe(self.receber_conta)), "Marcar como recebida")

    def test_marcar_como_paga_redireciona_e_mostra_a_data(self):
        resposta = self.client.post(self.url(self.primeira.pk), {"acao": "registrar", "data_pagamento": ONTEM.isoformat()})

        self.assertRedirects(resposta, self.detalhe(self.pagar_conta), fetch_redirect_response=False)
        pagina = self.client.get(self.detalhe(self.pagar_conta))
        self.assertContains(pagina, f"Paga em {ONTEM:%d/%m/%Y}")
        self.assertContains(pagina, "Desfazer baixa")
        self.assertContains(pagina, "1 de 2 parcelas pagas")

    def test_receber_diz_recebida(self):
        recebida = parcela(self.receber_conta, 1)
        self.client.post(self.url(recebida.pk), {"acao": "registrar", "data_pagamento": ONTEM.isoformat()})

        self.assertContains(self.client.get(self.detalhe(self.receber_conta)), f"Recebida em {ONTEM:%d/%m/%Y}")

    def test_desfazer_volta_a_em_aberto(self):
        registrar_pagamento(self.primeira.pk, ONTEM)

        resposta = self.client.post(self.url(self.primeira.pk), {"acao": "desfazer"})

        self.assertEqual(resposta.status_code, 302)
        self.primeira.refresh_from_db()
        self.assertIsNone(self.primeira.pago_em)

    def test_erros_voltam_para_o_detalhe_com_mensagem_e_nada_muda(self):
        casos = (
            ({"acao": "registrar", "data_pagamento": (timezone.localdate() + timedelta(days=2)).isoformat()}, "não pode ser futura"),
            ({"acao": "registrar", "data_pagamento": ""}, "Informe a data do pagamento"),
            ({"acao": "registrar", "data_pagamento": "31/02/2026"}, "dia/mês/ano"),
            ({"acao": "apagar"}, "escolha válida"),
            ({"acao": "registrar", "data_pagamento": ONTEM.isoformat(), "valor": "1"}, "Pedido inválido"),
            ({"acao": "desfazer"}, "não tem baixa para desfazer"),
        )
        for dados, mensagem in casos:
            with self.subTest(dados=dados):
                resposta = self.client.post(self.url(self.primeira.pk), dados)

                self.assertEqual(resposta.status_code, 400)
                self.assertTemplateUsed(resposta, "financeiro/conta_detalhe.html")
                self.assertContains(resposta, mensagem, status_code=400)
        self.primeira.refresh_from_db()
        self.assertIsNone(self.primeira.pago_em)

    def test_parcela_inexistente_e_metodo_errado(self):
        self.assertEqual(self.client.post(self.url(99999999), {"acao": "desfazer"}).status_code, 404)
        self.assertEqual(self.client.get(self.url(self.primeira.pk)).status_code, 405)

    def test_exige_login_e_csrf(self):
        anonimo = Client().post(self.url(self.primeira.pk), {"acao": "registrar", "data_pagamento": ONTEM.isoformat()})
        self.assertRedirects(anonimo, reverse("login"), fetch_redirect_response=False)
        cliente = Client(enforce_csrf_checks=True)
        autenticar_demo(cliente)

        self.assertEqual(cliente.post(self.url(self.primeira.pk), {"acao": "desfazer"}).status_code, 403)
        self.primeira.refresh_from_db()
        self.assertIsNone(self.primeira.pago_em)

    def test_lancamento_cancelado_nao_mostra_botoes(self):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s", [self.pagar_conta.id])

        self.assertNotContains(self.client.get(self.detalhe(self.pagar_conta)), "Marcar como paga")

    def test_lista_de_contas_filtra_por_pagamento_e_mostra_pagas(self):
        registrar_pagamento(parcela(self.receber_conta, 1).pk, ONTEM)

        em_aberto = self.client.get(reverse("contas"), {"modo": "buscar", "pagamento": "EM_ABERTO"})
        quitadas = self.client.get(reverse("contas"), {"modo": "buscar", "pagamento": "QUITADO"})

        self.assertEqual([l["dados"].id for l in em_aberto.context["linhas"]], [self.pagar_conta.id])
        self.assertEqual([l["dados"].id for l in quitadas.context["linhas"]], [self.receber_conta.id])
        self.assertContains(quitadas, "1 / 1")
        self.assertEqual(self.client.get(reverse("contas"), {"modo": "buscar", "pagamento": "X"}).status_code, 200)


class BaixaSimultaneaTests(ContaManualBase, TransactionTestCase):
    # As classificações iniciais vêm de uma migration, que o flush de outros testes apaga.
    serialized_rollback = True

    def test_so_uma_de_duas_baixas_simultaneas_da_mesma_parcela_passa(self):
        conta = manual.registrar_conta_manual(self.pagar())
        alvo = parcela(conta).pk
        resultados, barreira = [], threading.Barrier(2)

        def baixar(data):
            try:
                barreira.wait(timeout=10)
                registrar_pagamento(alvo, data)
                resultados.append("ok")
            except ValidationError as erro:
                resultados.append(erro.code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=baixar, args=(ONTEM - timedelta(days=i),)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(sorted(resultados), ["ok", "pagamento_ja_registrado"])
        self.assertIsNotNone(ParcelaConta.objects.get(pk=alvo).pago_em)
        self.assertEqual(MovimentoConta.objects.count(), 1)
