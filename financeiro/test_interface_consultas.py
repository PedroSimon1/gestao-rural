"""GR-49 parcial: interface de leitura com serviços oficiais e dados fictícios."""
from unittest import mock

from django.db import DatabaseError, connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from . import manual
from .identidade_fiscal import identificar_nota, registrar_identidade_fiscal
from .itens_nota import registrar_itens_nota
from .servicos import registrar_movimento
from .test_manual import ContaManualBase, contagens, parcelas


@override_settings(**CREDENCIAIS_TESTE)
class InterfaceConsultasTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        autenticar_demo(self.client)
        self.pagar1 = manual.registrar_conta_manual(self.pagar(parcelas=parcelas("600.00", "400.00")))
        self.receber1 = manual.registrar_conta_manual(self.receber())

    def url(self, nome="contas", *args):
        return reverse(nome, args=args)

    def ids(self, resposta):
        return [linha["dados"].id for linha in resposta.context["linhas"]]

    def test_login_obrigatorio_e_post_put_delete_recusados(self):
        for url in (self.url(), self.url("conta_detalhe", self.pagar1.id)):
            anonimo = Client().get(url)
            self.assertRedirects(anonimo, reverse("login"), fetch_redirect_response=False)
            for metodo in (self.client.post, self.client.put, self.client.delete):
                self.assertEqual(metodo(url).status_code, 405)

    def test_inicio_vazio_nao_consulta_servico_de_movimentos(self):
        with mock.patch("financeiro.views_consultas.listar_movimentos") as listar:
            resp = self.client.get(self.url())
        listar.assert_not_called()
        self.assertFalse(resp.context["pesquisou"])
        self.assertEqual(self.ids(resp), [])

    def test_todos_reutiliza_servico_oficial_e_ordem_recente(self):
        with mock.patch("financeiro.views_consultas.listar_movimentos", wraps=manual.listar_movimentos) as listar:
            resp = self.client.get(self.url(), {"modo": "todos"})
        listar.assert_called_once_with(status="CONFIRMADO", pagina=1)
        self.assertEqual(self.ids(resp), [self.receber1.id, self.pagar1.id])
        self.assertContains(resp, "Confirmado não significa pago ou recebido")

    def test_filtros_combinados_tipo_origem_pessoa_classificacao(self):
        dados = {"modo": "buscar", "tipo": "APAGAR", "origem": "MANUAL", "status": "CONFIRMADO", "contraparte": self.fornecedor.pk, "classificacao": self.manutencao.pk}
        resp = self.client.get(self.url(), dados)
        self.assertEqual(self.ids(resp), [self.pagar1.id])
        dados["tipo"] = "ARECEBER"
        self.assertEqual(self.ids(self.client.get(self.url(), dados)), [])

    def test_filtros_invalidos_nao_chegam_ao_servico(self):
        for dados in ({"tipo": "X"}, {"origem": "X"}, {"status": "PAGO"}, {"pagina": "-1"}, {"pagina": "9" * 5000}, {"contraparte": "99999999"}, {"classificacao": "nao-inteiro"}, {"por_pagina": "100000"}):
            with self.subTest(dados=dados), mock.patch("financeiro.views_consultas.listar_movimentos") as listar:
                resp = self.client.get(self.url(), {"modo": "buscar", **dados})
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.context["form"].errors)
                listar.assert_not_called()

    def test_detalhe_chama_servico_e_exibe_classificacoes_parcelas_e_valores(self):
        with mock.patch("financeiro.views_consultas.consultar_movimento", wraps=manual.consultar_movimento) as consultar:
            resp = self.client.get(self.url("conta_detalhe", self.pagar1.id))
        consultar.assert_called_once_with(self.pagar1.id)
        self.assertContains(resp, "Fornecedor Teste")
        self.assertContains(resp, "Faturado Teste")
        self.assertContains(resp, "MANUTENCAO_E_OPERACAO")
        self.assertContains(resp, "Principal")
        self.assertEqual(len(resp.context["parcelas"]), 2)
        self.assertContains(resp, "30/11/2026")
        self.assertContains(resp, "600,00")
        self.assertContains(resp, "o pagamento aparece na coluna Pagamento")
        self.assertNotContains(resp, "Editar")
        self.assertNotContains(resp, "Reativar")

    def nota_fiscal(self):
        movimento, _ = registrar_movimento(self.apagar())
        nota, _ = registrar_identidade_fiscal(movimento, identificar_nota(
            emitente_cnpj=self.fornecedor.documento, modelo="55", serie=1, numero=321,
        ))
        return movimento, nota

    def test_itens_em_secao_propria_com_valores_ausentes_e_escape(self):
        movimento, nota = self.nota_fiscal()
        registrar_itens_nota(nota, [
            {"descricao": "Ração <script>alert(1)</script>", "quantidade": "2.5",
             "valor_unitario": "80.10", "valor_total": "200.25"},
            {"descricao": "Sal mineral", "quantidade": "0", "valor_total": "0"},
            {"descricao": "Vacina"},
        ])
        resposta = self.client.get(self.url("conta_detalhe", movimento.pk))
        self.assertContains(resposta, "Itens da nota fiscal")
        self.assertContains(resposta, "Ração &lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(resposta, "<script>alert(1)</script>")
        for texto in ("Sal mineral", "2,5", "80,10", "200,25", "Não informada", "Não informado", "0,00"):
            self.assertContains(resposta, texto)
        self.assertEqual(len(resposta.context["detalhe"].nota_fiscal.itens), 3)

    def test_secao_nao_aparece_em_nota_antiga_sem_itens_nem_movimento_manual(self):
        movimento, _ = self.nota_fiscal()
        for movimento_id in (movimento.pk, self.pagar1.id):
            with self.subTest(movimento=movimento_id):
                self.assertNotContains(
                    self.client.get(self.url("conta_detalhe", movimento_id)), "Itens da nota fiscal",
                )

    def test_quantidade_de_consultas_nao_cresce_com_itens(self):
        movimento, nota = self.nota_fiscal()
        registrar_itens_nota(nota, [{"descricao": f"Item {n}"} for n in range(20)])
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.url("conta_detalhe", movimento.pk))
        consultas_itens = [c for c in consultas if 'FROM "itens_notas_fiscais"' in c["sql"]]
        self.assertEqual(len(consultas_itens), 1)
        self.assertEqual(len(resposta.context["detalhe"].nota_fiscal.itens), 20)

    def test_inexistente_404_e_respostas_sem_cache(self):
        for url, esperado in ((self.url("conta_detalhe", 99999999), 404), (self.url("conta_detalhe", self.receber1.id), 200), (self.url(), 200)):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, esperado)
            self.assertIn("no-store", resp.headers["Cache-Control"])

    def test_indisponibilidade_no_servico_ou_seletor_nao_expoe_sql(self):
        alvos = (
            ("financeiro.views_consultas.listar_movimentos", self.url(), {"modo": "todos"}),
            ("financeiro.views_consultas.consultar_movimento", self.url("conta_detalhe", self.pagar1.id), {}),
        )
        for alvo, url, dados in alvos:
            with mock.patch(alvo, side_effect=DatabaseError("SQL-secreto-ficticio")):
                resp = self.client.get(url, dados)
            self.assertEqual(resp.status_code, 503)
            self.assertNotContains(resp, "SQL-secreto-ficticio", status_code=503)
            self.assertIn("no-store", resp.headers["Cache-Control"])
        with mock.patch("django.forms.models.ModelChoiceIterator.__iter__", side_effect=DatabaseError("SQL-secreto-ficticio")):
            resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 503)

    def test_consultas_nao_gravam_nada_no_banco(self):
        antes = contagens()
        with CaptureQueriesContext(connection) as consultas:
            self.client.get(self.url(), {"modo": "todos"})
            self.client.get(self.url("conta_detalhe", self.pagar1.id))
        comandos = [c["sql"].lstrip().upper() for c in consultas]
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in comandos))
        self.assertEqual(contagens(), antes)

    def test_pessoas_e_classificacoes_inativas_continuam_no_historico(self):
        self.fornecedor.inativar()
        self.manutencao.inativar()
        resp = self.client.get(self.url(), {"modo": "buscar", "contraparte": self.fornecedor.pk, "classificacao": self.manutencao.pk})
        self.assertEqual(self.ids(resp), [self.pagar1.id])
        self.assertContains(self.client.get(self.url("conta_detalhe", self.pagar1.id)), "Fornecedor Teste")

    def test_canceladas_explicitas_e_parcelas_canceladas_visiveis(self):
        # Fixture de estado: não há serviço de cancelamento na base. Somente
        # SQL de teste, como no teste oficial do backend, sem rota de escrita.
        with connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET status='CANCELADO' WHERE id=%s", [self.pagar1.id])
            cursor.execute("UPDATE parcelas_contas SET status='CANCELADA' WHERE movimento_id=%s", [self.pagar1.id])
        self.assertNotIn(self.pagar1.id, self.ids(self.client.get(self.url(), {"modo": "todos"})))
        resp = self.client.get(self.url(), {"modo": "buscar", "status": "CANCELADO"})
        self.assertEqual(self.ids(resp), [self.pagar1.id])
        detalhe = self.client.get(self.url("conta_detalhe", self.pagar1.id))
        self.assertContains(detalhe, "Cancelada", count=2)
        self.assertEqual(len(detalhe.context["parcelas"]), 2)

    def test_paginacao_preserva_filtros(self):
        for _ in range(10):
            manual.registrar_conta_manual(self.receber())
        dados = {"modo": "buscar", "tipo": "ARECEBER", "por_pagina": "10"}
        primeira = self.client.get(self.url(), dados)
        segunda = self.client.get(self.url(), {**dados, "pagina": "2"})
        self.assertEqual((len(self.ids(primeira)), len(self.ids(segunda))), (10, 1))
        self.assertFalse(set(self.ids(primeira)) & set(self.ids(segunda)))
        self.assertContains(primeira, "tipo=ARECEBER")
