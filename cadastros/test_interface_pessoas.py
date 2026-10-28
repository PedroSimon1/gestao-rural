"""GR-46: interface autenticada com domínio real e PostgreSQL descartável."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from documentos.testing import CNPJ, CPF
from financeiro.models import MovimentoConta, OrigemMovimento, TipoMovimento
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo

from .forms import PessoaForm
from .models import Classificacao, Papel, PapelPessoa, Pessoa, SituacaoDocumental, Status, TipoClassificacao
from .pendentes import regularizar_cadastro_pendente, salvar_cadastro_pendente


@override_settings(**CREDENCIAIS_TESTE)
class InterfacePessoasTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        self.pessoa = Pessoa.objects.create(documento=CPF, razao_social="Pessoa Teste")
        self.papel, _ = self.pessoa.atribuir_papel(Papel.CLIENTE)

    def url(self, nome, *args):
        return reverse(nome, args=args)

    def editar(self, **extra):
        return self.client.post(self.url("pessoa_editar", self.pessoa.pk), {
            "razao_social": "Pessoa Editada", "documento": CPF, **extra,
        })

    def test_rotas_exigem_login(self):
        anonimo = Client()
        rotas = [
            ("pessoas", ()), ("pessoa_nova", ()), ("pessoa_detalhe", (self.pessoa.pk,)),
            ("pessoa_editar", (self.pessoa.pk,)), ("pessoa_atribuir_papel", (self.pessoa.pk,)),
            ("pessoa_status", (self.pessoa.pk, "inativar")),
            ("papel_status", (self.pessoa.pk, self.papel.pk, "inativar")),
            ("pessoa_regularizar", (self.pessoa.pk,)),
        ]
        for nome, args in rotas:
            with self.subTest(nome=nome):
                for metodo in (anonimo.get, anonimo.post):
                    self.assertRedirects(metodo(self.url(nome, *args)), reverse("login"), fetch_redirect_response=False)

    def test_lista_inicial_vazia_e_todos_somente_ativos(self):
        inativa = Pessoa.objects.create(documento=CNPJ, razao_social="Empresa oculta de teste")
        inativa.inativar()
        inicial = self.client.get(self.url("pessoas"))
        self.assertEqual(inicial.context["pagina"].paginator.count, 0)
        self.assertNotContains(inicial, self.pessoa.razao_social)
        todos = self.client.get(self.url("pessoas"), {"modo": "todos"})
        self.assertContains(todos, self.pessoa.razao_social)
        self.assertNotContains(todos, inativa.razao_social)

    def test_busca_documento_formatado_com_papel_e_inativos_explicitos(self):
        self.pessoa.inativar()
        filtro = {"modo": "buscar", "busca": "123.456.789-09", "papel": Papel.CLIENTE}
        self.assertEqual(self.client.get(self.url("pessoas"), filtro).context["pagina"].paginator.count, 0)
        filtro["status"] = Status.INATIVO
        resp = self.client.get(self.url("pessoas"), filtro)
        self.assertEqual(list(resp.context["pagina"]), [self.pessoa])
        filtro["papel"] = Papel.FORNECEDOR
        self.assertEqual(self.client.get(self.url("pessoas"), filtro).context["pagina"].paginator.count, 0)

    def test_pesquisa_sem_filtro_nao_carrega_todos_e_ordenacao_e_controlada(self):
        vazia = self.client.get(self.url("pessoas"), {"modo": "buscar", "status": Status.ATIVO})
        self.assertEqual(vazia.context["pagina"].paginator.count, 0)
        self.assertTrue(vazia.context["form"].non_field_errors())
        outra = Pessoa.objects.create(documento=CNPJ, razao_social="AAA Empresa")
        resp = self.client.get(self.url("pessoas"), {"modo": "todos", "ordem": "-nome"})
        self.assertEqual(list(resp.context["pagina"]), [self.pessoa, outra])
        invalida = self.client.get(self.url("pessoas"), {"modo": "todos", "ordem": "movimentos_como_contraparte__valor_total"})
        self.assertEqual(list(invalida.context["pagina"]), [outra, self.pessoa])

    def test_criar_cnpj_com_multiplos_papeis_sem_inferir_tipo(self):
        resp = self.client.post(self.url("pessoa_nova"), {
            "razao_social": "  Empresa   Teste ", "documento": "11.222.333/0001-81",
            "papeis": [Papel.CLIENTE, Papel.FATURADO],
        })
        pessoa = Pessoa.objects.get(documento=CNPJ)
        self.assertRedirects(resp, self.url("pessoa_detalhe", pessoa.pk))
        self.assertEqual(pessoa.razao_social, "Empresa Teste")
        self.assertEqual(set(pessoa.papeis.values_list("papel", flat=True)), {Papel.CLIENTE, Papel.FATURADO})
        self.assertFalse(pessoa.papeis.filter(papel=Papel.FORNECEDOR).exists())
        self.assertEqual(MovimentoConta.objects.count(), 0)

    def test_cpf_pode_ser_fornecedor_sem_criar_outra_pessoa(self):
        resp = self.client.post(self.url("pessoa_atribuir_papel", self.pessoa.pk), {"papel": Papel.FORNECEDOR})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(set(self.pessoa.papeis.values_list("papel", flat=True)), {Papel.CLIENTE, Papel.FORNECEDOR})

    def test_criacao_recusa_documento_duplicado_e_invalido_sem_gravar_papeis(self):
        for documento in ("123.456.789-09", "12345678900", "", "INVENTADO"):
            with self.subTest(documento=documento):
                resp = self.client.post(self.url("pessoa_nova"), {
                    "razao_social": "Outra", "documento": documento, "papeis": [Papel.FORNECEDOR],
                })
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.context["form"].errors)
                self.assertEqual((Pessoa.objects.count(), PapelPessoa.objects.count()), (1, 1))

    def test_campos_e_papel_invalidos_nao_alteram_cadastro(self):
        self.assertEqual(self.editar(status=Status.INATIVO).status_code, 200)
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.razao_social, "Pessoa Teste")
        self.assertEqual(self.pessoa.status, Status.ATIVO)
        resp = self.client.post(self.url("pessoa_atribuir_papel", self.pessoa.pk), {"papel": "ADMIN"})
        self.assertTrue(resp.context["papel_form"].errors)
        self.assertEqual(PapelPessoa.objects.count(), 1)

    def test_documento_unico_na_edicao_e_tipo_derivado_no_backend(self):
        outra = Pessoa.objects.create(documento=CNPJ, razao_social="Outra")
        resp = self.editar(documento="11.222.333/0001-81")
        self.assertTrue(resp.context["form"].errors)
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.documento, CPF)
        self.assertEqual(outra.documento, CNPJ)
        resp = self.editar(documento="123.456.789-09")
        self.assertEqual(resp.status_code, 302)
        self.pessoa.refresh_from_db()
        self.assertEqual((self.pessoa.documento, self.pessoa.tipo_documento), (CPF, "CPF"))

    def test_edicao_nao_reativa_status_alterado_apos_leitura(self):
        form = PessoaForm({"razao_social": "Nome corrigido", "documento": CPF}, instance=self.pessoa)
        self.assertTrue(form.is_valid(), form.errors)
        outra_leitura = Pessoa.objects.get(pk=self.pessoa.pk)
        outra_leitura.inativar()
        form.save()
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.status, Status.INATIVO)
        self.assertEqual(self.pessoa.razao_social, "Nome corrigido")

    def test_reativar_pessoa_nao_reativa_papel_e_atribuir_nao_reativa_existente(self):
        self.papel.inativar()
        self.pessoa.inativar()
        resp = self.client.post(self.url("pessoa_atribuir_papel", self.pessoa.pk), {"papel": Papel.CLIENTE})
        self.assertContains(resp, "Este papel já existe")
        self.client.post(self.url("pessoa_status", self.pessoa.pk, "reativar"), {"confirmar": "on"})
        self.pessoa.refresh_from_db()
        self.papel.refresh_from_db()
        self.assertEqual((self.pessoa.status, self.papel.status), (Status.ATIVO, Status.INATIVO))
        self.assertEqual(PapelPessoa.objects.count(), 1)

    def test_status_papel_nao_altera_pessoa_nem_outro_papel(self):
        outro, _ = self.pessoa.atribuir_papel(Papel.FATURADO)
        self.client.post(self.url("papel_status", self.pessoa.pk, self.papel.pk, "inativar"), {"confirmar": "on"})
        self.pessoa.refresh_from_db()
        self.papel.refresh_from_db()
        outro.refresh_from_db()
        self.assertEqual((self.pessoa.status, self.papel.status, outro.status), (Status.ATIVO, Status.INATIVO, Status.ATIVO))
        self.client.post(self.url("papel_status", self.pessoa.pk, self.papel.pk, "reativar"), {"confirmar": "on"})
        self.papel.refresh_from_db()
        self.assertEqual(self.papel.status, Status.ATIVO)

    def test_get_e_post_sem_confirmacao_nao_mudam_status(self):
        for nome, args in (("pessoa_status", (self.pessoa.pk, "inativar")), ("papel_status", (self.pessoa.pk, self.papel.pk, "inativar"))):
            self.assertEqual(self.client.get(self.url(nome, *args)).status_code, 200)
            resp = self.client.post(self.url(nome, *args), {})
            self.assertTrue(resp.context["form"].errors)
        self.pessoa.refresh_from_db()
        self.papel.refresh_from_db()
        self.assertEqual((self.pessoa.status, self.papel.status), (Status.ATIVO, Status.ATIVO))
        self.assertEqual(self.client.get(self.url("pessoa_atribuir_papel", self.pessoa.pk)).status_code, 405)
        self.assertEqual(self.client.delete(self.url("pessoa_detalhe", self.pessoa.pk)).status_code, 405)

    def test_papel_de_outra_pessoa_e_acoes_desconhecidas_retornam_404(self):
        outra = Pessoa.objects.create(documento=CNPJ, razao_social="Outra")
        for url in (self.url("papel_status", outra.pk, self.papel.pk, "inativar"), self.url("pessoa_status", self.pessoa.pk, "excluir")):
            self.assertEqual(self.client.post(url, {"confirmar": "on"}).status_code, 404)
        self.papel.refresh_from_db()
        self.assertEqual(self.papel.status, Status.ATIVO)

    def test_csrf_obrigatorio(self):
        protegido = Client(enforce_csrf_checks=True)
        autenticar_demo(protegido)
        resp = protegido.post(self.url("pessoa_status", self.pessoa.pk, "inativar"), {"confirmar": "on"})
        self.assertEqual(resp.status_code, 403)
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.status, Status.ATIVO)

    def test_incompleto_regulariza_no_mesmo_id_e_preserva_status_e_papeis(self):
        pendente = salvar_cadastro_pendente("Pendente", Papel.FORNECEDOR, consentimento=True)
        pessoa = Pessoa.objects.get(pk=pendente.id)
        pessoa.inativar()
        vinculo = pessoa.papeis.get()
        vinculo.inativar()
        resp = self.client.post(self.url("pessoa_editar", pessoa.pk), {"razao_social": "Nome corrigido", "documento": CNPJ})
        self.assertEqual(resp.status_code, 302)
        pessoa.refresh_from_db()
        self.assertIsNone(pessoa.documento)
        with patch("cadastros.views.regularizar_cadastro_pendente", wraps=regularizar_cadastro_pendente) as oficial:
            resp = self.client.post(self.url("pessoa_regularizar", pessoa.pk), {"documento": "11.222.333/0001-81", "confirmar": "on"})
            oficial.assert_called_once_with(pessoa.pk, CNPJ)
        self.assertEqual(resp.status_code, 302)
        pessoa.refresh_from_db()
        vinculo.refresh_from_db()
        self.assertEqual((pessoa.documento, pessoa.situacao_documental, pessoa.status, vinculo.status), (CNPJ, SituacaoDocumental.COMPLETO, Status.INATIVO, Status.INATIVO))
        self.assertEqual(pessoa.papeis.get().pk, vinculo.pk)

    def test_regularizacao_recusa_duplicado_e_ausencia_de_consentimento(self):
        pendente = salvar_cadastro_pendente("Pendente", Papel.CLIENTE, consentimento=True)
        for dados in ({"documento": CPF, "confirmar": "on"}, {"documento": CNPJ}):
            resp = self.client.post(self.url("pessoa_regularizar", pendente.id), dados)
            self.assertTrue(resp.context["form"].errors)
            self.assertIsNone(Pessoa.objects.get(pk=pendente.id).documento)

    def test_nome_editado_apos_regularizacao_concorrente_nao_apaga_documento(self):
        pendente = salvar_cadastro_pendente("Pendente", Papel.CLIENTE, consentimento=True)
        pessoa = Pessoa.objects.get(pk=pendente.id)
        form = PessoaForm({"razao_social": "Corrigido"}, instance=pessoa)
        self.assertTrue(form.is_valid(), form.errors)
        Pessoa.objects.get(pk=pessoa.pk).regularizar(CNPJ)
        form.save()
        pessoa.refresh_from_db()
        self.assertEqual((pessoa.razao_social, pessoa.documento, pessoa.situacao_documental), ("Corrigido", CNPJ, SituacaoDocumental.COMPLETO))

    def test_edicao_e_inativacao_preservam_movimento_e_parcelas(self):
        classificacao = Classificacao.objects.create(codigo="RECEITA_TESTE", descricao="Receita teste", tipo=TipoClassificacao.RECEITA)
        movimento, criado = registrar_movimento(DadosMovimento(
            tipo=TipoMovimento.ARECEBER, origem=OrigemMovimento.MANUAL,
            contraparte=self.pessoa, valor_total=Decimal("10.00"),
            classificacoes=(ItemClassificacao(classificacao, principal=True),),
            parcelas=(ItemParcela(numero=1, data_vencimento=date(2026, 12, 1), valor=Decimal("10.00")),),
        ))
        parcelas = list(movimento.parcelas.values_list("pk", "valor", "status"))
        self.assertEqual(self.editar().status_code, 302)
        self.client.post(self.url("pessoa_status", self.pessoa.pk, "inativar"), {"confirmar": "on"})
        self.client.post(self.url("papel_status", self.pessoa.pk, self.papel.pk, "inativar"), {"confirmar": "on"})
        movimento.refresh_from_db()
        self.assertEqual(movimento.contraparte_id, self.pessoa.pk)
        self.assertEqual(list(movimento.parcelas.values_list("pk", "valor", "status")), parcelas)
        self.assertEqual(MovimentoConta.objects.count(), 1)
