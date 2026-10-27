"""GR-47: regras observáveis da interface usando o domínio real."""
from datetime import date
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from documentos.testing import CPF
from financeiro.models import MovimentoConta
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .forms_classificacoes import DescricaoClassificacaoForm
from .models import Classificacao, Papel, Pessoa, Status, TipoClassificacao


@override_settings(**CREDENCIAIS_TESTE)
class InterfaceClassificacoesTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        self.registro = Classificacao.objects.create(
            tipo=TipoClassificacao.RECEITA, codigo="VENDA_TESTE", descricao="Receita de teste",
        )

    def url(self, nome, *args):
        return reverse(nome, args=args)

    def criar(self, **extra):
        return self.client.post(self.url("classificacao_nova"), {
            "tipo": TipoClassificacao.DESPESA, "codigo": "CUSTO_TESTE", "descricao": "Custo de teste", **extra,
        })

    def test_login_obrigatorio_em_todas_as_rotas(self):
        anonimo = Client()
        for nome, args in (("classificacoes", ()), ("classificacao_nova", ()), ("classificacao_editar", (self.registro.pk,)), ("classificacao_status", (self.registro.pk, "inativar"))):
            for metodo in (anonimo.get, anonimo.post):
                with self.subTest(nome=nome, metodo=metodo.__name__):
                    self.assertRedirects(metodo(self.url(nome, *args)), reverse("login"), fetch_redirect_response=False)

    def test_lista_inicial_vazia_e_todos_ativos(self):
        inativa = Classificacao.objects.create(tipo="RECEITA", codigo="OCULTA", descricao="Classificação oculta")
        inativa.inativar()
        inicial = self.client.get(self.url("classificacoes"))
        self.assertEqual(inicial.context["pagina"].paginator.count, 0)
        self.assertNotContains(inicial, self.registro.descricao)
        todos = self.client.get(self.url("classificacoes"), {"modo": "todos"})
        self.assertContains(todos, self.registro.descricao)
        self.assertNotContains(todos, inativa.descricao)
        self.assertTrue(all(item.ativo for item in todos.context["pagina"]))

    def test_busca_combina_termos_tipo_e_status(self):
        self.registro.inativar()
        dados = {"modo": "buscar", "busca": "VENDA teste", "tipo": "RECEITA", "status": Status.INATIVO}
        resp = self.client.get(self.url("classificacoes"), dados)
        self.assertEqual(list(resp.context["pagina"]), [self.registro])
        dados["tipo"] = "DESPESA"
        self.assertEqual(self.client.get(self.url("classificacoes"), dados).context["pagina"].paginator.count, 0)
        dados.update(tipo="RECEITA", status=Status.ATIVO)
        self.assertEqual(self.client.get(self.url("classificacoes"), dados).context["pagina"].paginator.count, 0)

    def test_busca_vazia_e_filtros_invalidos_nao_carregam_todos(self):
        for dados in ({"modo": "buscar"}, {"modo": "buscar", "tipo": "INVALIDO"}, {"modo": "buscar", "status": "INVALIDO"}):
            resp = self.client.get(self.url("classificacoes"), dados)
            self.assertEqual(resp.context["pagina"].paginator.count, 0)
            self.assertTrue(resp.context["form"].errors)

    def test_ordenacao_controlada_e_paginacao_preservam_filtros(self):
        for numero in range(32):
            Classificacao.objects.create(tipo="RECEITA", codigo=f"ITEM_{numero:02}", descricao=f"Venda {numero:02}")
        dados = {"modo": "buscar", "tipo": "RECEITA", "ordem": "-codigo"}
        primeira = self.client.get(self.url("classificacoes"), dados)
        self.assertEqual(len(primeira.context["pagina"]), 30)
        self.assertContains(primeira, "tipo=RECEITA")
        dados["pagina"] = "2"
        segunda = self.client.get(self.url("classificacoes"), dados)
        self.assertEqual(len(segunda.context["pagina"]), 3)
        ids = {r.pk for r in primeira.context["pagina"]}
        self.assertFalse(ids & {r.pk for r in segunda.context["pagina"]})
        dados.update(ordem="movimentos__valor_total", pagina="invalida")
        self.assertEqual(self.client.get(self.url("classificacoes"), dados).status_code, 200)

    def test_cadastro_receita_e_despesa_normaliza_codigo_e_descricao(self):
        for tipo in TipoClassificacao.values:
            resp = self.criar(tipo=tipo, codigo="  novo_codigo  ", descricao="  Descrição   nova  ")
            registro = Classificacao.objects.get(tipo=tipo, codigo="NOVO_CODIGO")
            self.assertRedirects(resp, self.url("classificacao_editar", registro.pk))
            self.assertEqual((registro.descricao, registro.status), ("Descrição nova", Status.ATIVO))
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_unicidade_tipo_codigo_inclui_inativos_sem_reativacao(self):
        self.registro.inativar()
        resp = self.criar(tipo="RECEITA", codigo=" venda_teste ")
        self.assertTrue(resp.context["form"].errors)
        self.assertEqual(Classificacao.objects.filter(tipo="RECEITA", codigo="VENDA_TESTE").count(), 1)
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.status, Status.INATIVO)
        self.assertEqual(self.criar(tipo="DESPESA", codigo="VENDA_TESTE").status_code, 302)

    def test_campos_invalidos_ou_status_injetado_nao_criam_registro(self):
        antes = Classificacao.objects.count()
        for extras in ({"codigo": "INVÁLIDO"}, {"codigo": "CODIGO COM ESPACO"}, {"tipo": "INVALIDO"}, {"descricao": "  "}, {"descricao": "Texto\x00inválido"}, {"status": Status.INATIVO}):
            with self.subTest(extras=extras):
                resp = self.criar(**extras)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.context["form"].errors)
                self.assertEqual(Classificacao.objects.count(), antes)

    def test_edicao_so_permite_descricao_sem_expor_identidade_ou_status(self):
        url = self.url("classificacao_editar", self.registro.pk)
        form = self.client.get(url).context["form"]
        self.assertEqual(set(form.fields), {"descricao"})
        for extras in ({"codigo": "OUTRO"}, {"tipo": "DESPESA"}, {"status": "INATIVO"}):
            resp = self.client.post(url, {"descricao": "Não deve salvar", **extras})
            self.assertTrue(resp.context["form"].errors)
            self.registro.refresh_from_db()
            self.assertEqual(self.registro.descricao, "Receita de teste")
        self.assertEqual(self.client.post(url, {"descricao": "Receita corrigida"}).status_code, 302)
        self.registro.refresh_from_db()
        self.assertEqual((self.registro.tipo, self.registro.codigo, self.registro.descricao), ("RECEITA", "VENDA_TESTE", "Receita corrigida"))

    def test_edicao_nao_desfaz_inativacao_intercalada(self):
        form = DescricaoClassificacaoForm({"descricao": "Corrigida"}, instance=self.registro)
        self.assertTrue(form.is_valid(), form.errors)
        Classificacao.objects.get(pk=self.registro.pk).inativar()
        form.save()
        self.registro.refresh_from_db()
        self.assertEqual((self.registro.status, self.registro.descricao), (Status.INATIVO, "Corrigida"))

    def test_status_exige_post_confirmacao_e_csrf_sem_exclusao_fisica(self):
        url = self.url("classificacao_status", self.registro.pk, "inativar")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(self.client.post(url, {}).context["form"].errors)
        csrf = Client(enforce_csrf_checks=True)
        autenticar_demo(csrf)
        self.assertEqual(csrf.post(url, {"confirmar": "on"}).status_code, 403)
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.status, Status.ATIVO)
        self.assertEqual(self.client.delete(url).status_code, 405)
        for acao, esperado in (("inativar", Status.INATIVO), ("reativar", Status.ATIVO)):
            resp = self.client.post(self.url("classificacao_status", self.registro.pk, acao), {"confirmar": "on"})
            self.assertEqual(resp.status_code, 302)
            self.registro.refresh_from_db()
            self.assertEqual(self.registro.status, esperado)

    def test_acao_invalida_e_id_inexistente_retornam_404(self):
        for args in ((self.registro.pk, "excluir"), (999999, "inativar")):
            self.assertEqual(self.client.post(self.url("classificacao_status", *args), {"confirmar": "on"}).status_code, 404)

    def test_descricao_renderizada_com_escape_html(self):
        self.registro.descricao = '<script>alert("teste")</script>'
        self.registro.save(update_fields=["descricao"])
        resp = self.client.get(self.url("classificacoes"), {"modo": "todos"})
        self.assertNotContains(resp, self.registro.descricao)
        self.assertContains(resp, "&lt;script&gt;")

    def test_historico_financeiro_preservado_ao_editar_e_inativar(self):
        pessoa = Pessoa.objects.create(documento=CPF, razao_social="Cliente teste")
        pessoa.atribuir_papel(Papel.CLIENTE)
        movimento, _ = registrar_movimento(DadosMovimento(
            tipo="ARECEBER", origem="MANUAL", contraparte=pessoa, valor_total=Decimal("10.00"),
            classificacoes=(ItemClassificacao(self.registro, principal=True),),
            parcelas=(ItemParcela(1, date(2026, 12, 1), Decimal("10.00")),),
        ))
        vinculos = list(movimento.classificacoes.values_list("pk", "classificacao_id", "principal"))
        parcelas = list(movimento.parcelas.values_list("pk", "valor", "status"))
        self.client.post(self.url("classificacao_editar", self.registro.pk), {"descricao": "Descrição corrigida"})
        self.client.post(self.url("classificacao_status", self.registro.pk, "inativar"), {"confirmar": "on"})
        movimento.refresh_from_db()
        self.assertEqual(list(movimento.classificacoes.values_list("pk", "classificacao_id", "principal")), vinculos)
        self.assertEqual(list(movimento.parcelas.values_list("pk", "valor", "status")), parcelas)
        self.assertEqual(movimento.valor_total, Decimal("10.00"))
