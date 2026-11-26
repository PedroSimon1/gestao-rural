"""Rede de proteção da interface: todo campo de formulário que o servidor espera aparece no HTML.

Ao redesenhar um template, um campo esquecido some do POST sem erro visível. Aqui, para cada
tela com formulário, os nomes dos campos dos formulários e formsets do contexto precisam existir
como `name=` no HTML devolvido. Cobre também o que o template renderiza campo a campo.
"""
from html.parser import HTMLParser

from django.conf import settings
from django.forms import BaseForm
from django.forms.formsets import BaseFormSet
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cadastros.models import Classificacao, Papel, Pessoa, TipoClassificacao
from documentos.analises import criar_analise, garantir_dono
from documentos.testing import CNPJ, CPF, resultado_da_nota
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo


class _Nomes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nomes = set()

    def handle_starttag(self, tag, attrs):
        if tag in {"input", "select", "textarea", "button"}:
            nome = dict(attrs).get("name")
            if nome:
                self.nomes.add(nome)


def nomes_no_html(resposta):
    analisador = _Nomes()
    analisador.feed(resposta.content.decode())
    return analisador.nomes


def _contextos(resposta):
    contexto = resposta.context
    return list(contexto) if isinstance(contexto, list) else [contexto]


def nomes_esperados(resposta):
    """Nomes de campo de todos os formulários e formsets que a view colocou no contexto."""
    esperados = set()
    for contexto in _contextos(resposta):
        for valor in contexto.flatten().values():
            if isinstance(valor, BaseForm):
                esperados |= {campo.html_name for campo in valor}
            elif isinstance(valor, BaseFormSet):
                esperados |= {campo.html_name for campo in valor.management_form}
                for formulario in valor.forms:
                    esperados |= {campo.html_name for campo in formulario}
    return esperados


@override_settings(**CREDENCIAIS_TESTE)
class CompletudeDosFormulariosTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        self.pessoa = Pessoa.objects.create(documento=CPF, razao_social="Pessoa Teste")
        self.papel, _ = self.pessoa.atribuir_papel(Papel.FORNECEDOR)
        self.classificacao = Classificacao.objects.get(tipo=TipoClassificacao.DESPESA, codigo="MANUTENCAO_E_OPERACAO")
        # Sem opções de RECEITA, as caixas de marcar da conta a receber nem existiriam no HTML.
        Classificacao.objects.create(tipo=TipoClassificacao.RECEITA, codigo="VENDA_TESTE", descricao="Venda de teste")

    def conferir(self, nome, url, cliente=None):
        resposta = (cliente or self.client).get(url)
        self.assertEqual(resposta.status_code, 200, nome)
        esperados = nomes_esperados(resposta)
        self.assertTrue(esperados, f"{nome}: nenhum formulário no contexto (teste sem efeito)")
        ausentes = esperados - nomes_no_html(resposta)
        self.assertEqual(ausentes, set(), f"{nome}: campos que o servidor espera e o HTML não tem")

    def test_telas_de_cadastros_financeiro_e_envio(self):
        telas = {
            "envio da nota": reverse("documento_inicio"),
            "pessoas (filtro)": reverse("pessoas") + "?modo=buscar",
            "pessoa nova": reverse("pessoa_nova"),
            "pessoa editar": reverse("pessoa_editar", args=[self.pessoa.pk]),
            "pessoa detalhe (papel)": reverse("pessoa_detalhe", args=[self.pessoa.pk]),
            "pessoa inativar": reverse("pessoa_status", args=[self.pessoa.pk, "inativar"]),
            "papel inativar": reverse("papel_status", args=[self.pessoa.pk, self.papel.pk, "inativar"]),
            "classificações (filtro)": reverse("classificacoes") + "?modo=buscar",
            "classificação nova": reverse("classificacao_nova"),
            "classificação editar": reverse("classificacao_editar", args=[self.classificacao.pk]),
            "classificação inativar": reverse("classificacao_status", args=[self.classificacao.pk, "inativar"]),
            "contas (filtro)": reverse("contas") + "?modo=buscar",
            "conta manual a pagar": reverse("conta_manual_nova") + "?tipo=APAGAR",
            "conta manual a receber": reverse("conta_manual_nova") + "?tipo=ARECEBER",
        }
        for nome, url in telas.items():
            with self.subTest(tela=nome):
                self.conferir(nome, url)

    def test_pessoa_incompleta_exibe_o_formulario_de_regularizacao(self):
        incompleta = Pessoa.objects.create(razao_social="Sem documento", situacao_documental="INCOMPLETO")
        self.conferir("regularizar documento", reverse("pessoa_regularizar", args=[incompleta.pk]))

    def test_login_anonimo(self):
        self.conferir("login", reverse("login"), cliente=Client())

    def test_conferencia_e_confirmacao_da_nota(self):
        original = resultado_da_nota()
        original["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        analise = criar_analise(self.client.session, original)
        url = reverse("analise_conferencia", args=[analise.id])
        self.conferir("conferência da nota", url)

        dados = {
            "versao_correcoes": "0", "fornecedor_nome": "Fornecedor corrigido", "fornecedor_documento": CNPJ,
            "faturado_nome": "Faturado corrigido", "faturado_cpf": CPF, "faturado_cnpj": "",
            "documento_faturado": "CPF", "classificacao": str(self.classificacao.pk),
            "numero_nota": "123", "serie_nota": "1", "modelo": "55", "chave_acesso": "",
            "data_emissao": "2026-10-01", "valor_total": "150.00",
            "parcelas-TOTAL_FORMS": "1", "parcelas-INITIAL_FORMS": "1",
            "parcelas-0-data_vencimento": "2026-11-01", "parcelas-0-valor": "150.00",
        }
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        self.conferir("conferência salva", url)
        self.conferir("confirmação do lançamento", reverse("analise_confirmar", args=[analise.id]))
