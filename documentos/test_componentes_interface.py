"""Peças reutilizáveis da interface: cabeçalho de página, aviso, campo de formulário e situação."""
from datetime import date
from types import SimpleNamespace

import re

from django import forms
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from documentos.forms import DocumentoUploadForm


def renderizar(modelo, **contexto):
    return Template(modelo).render(Context(contexto))


class CabecalhoDePaginaTests(SimpleTestCase):
    def cabecalho(self, **contexto):
        return render_to_string("documentos/_cabecalho_pagina.html", contexto)

    def test_so_titulo(self):
        html = self.cabecalho(titulo="Pessoas")
        self.assertIn("<h1>Pessoas</h1>", html)
        self.assertNotIn("migalhas", html)
        self.assertNotIn('class="botao"', html)

    def test_apoio_trilha_e_acao(self):
        html = self.cabecalho(
            titulo="Detalhe", apoio="Veja os dados.", migalha_url="/contas/", migalha_rotulo="Contas",
            acao_url="/nova/", acao_rotulo="Nova conta",
        )
        self.assertIn("<p>Veja os dados.</p>", html)
        self.assertIn('<a href="/contas/">Contas</a>', html)
        self.assertIn("Detalhe</p>", html)
        self.assertIn('<a class="botao" href="/nova/">Nova conta</a>', html)

    def test_titulo_com_html_e_escapado(self):
        self.assertIn("&lt;b&gt;", self.cabecalho(titulo="<b>x</b>"))


class AvisoTests(SimpleTestCase):
    def aviso(self, **contexto):
        return render_to_string("documentos/_aviso.html", contexto)

    def test_roles_por_tipo(self):
        for tipo, role in {"erro": "alert", "atencao": "alert", "info": "status", "ok": "status", "": "status"}.items():
            with self.subTest(tipo=tipo):
                self.assertIn(f'role="{role}"', self.aviso(tipo=tipo, texto="x"))

    def test_titulo_opcional_e_texto_escapado(self):
        html = self.aviso(tipo="atencao", titulo="Atenção", texto="<i>x</i>")
        self.assertIn("<strong>Atenção</strong>", html)
        self.assertIn("&lt;i&gt;x&lt;/i&gt;", html)
        self.assertNotIn("<strong>", self.aviso(tipo="info", texto="só texto"))


class FormularioDeTeste(forms.Form):
    nome = forms.CharField(label="Nome", help_text="Como no documento.")
    apelido = forms.CharField(label="Apelido", required=False)
    papeis = forms.MultipleChoiceField(label="Papéis", choices=[("F", "Fornecedor"), ("C", "Cliente")], widget=forms.CheckboxSelectMultiple)
    escolha = forms.ChoiceField(label="Escolha", choices=[("a", "A"), ("b", "B")], widget=forms.RadioSelect)
    confirmar = forms.BooleanField(label="Confirmo")
    oculto = forms.CharField(widget=forms.HiddenInput, required=False)


class CampoTests(SimpleTestCase):
    def campo(self, nome, formulario=None):
        formulario = formulario or FormularioDeTeste()
        return render_to_string("documentos/_campo.html", {"campo": formulario[nome]})

    def test_obrigatorio_tem_asterisco_e_rotulo_ligado_ao_campo(self):
        html = self.campo("nome")
        self.assertIn('<label class="rotulo" for="id_nome">Nome<span class="req" aria-hidden="true"> *</span></label>', html)
        self.assertIn('name="nome"', html)
        self.assertIn('id="id_nome"', html)

    def test_opcional_sem_asterisco(self):
        self.assertNotIn("req", self.campo("apelido"))

    def test_dica_e_ligada_ao_campo(self):
        html = self.campo("nome")
        self.assertIn('id="id_nome_helptext"', html)
        self.assertIn("Como no documento.", html)
        self.assertIn('aria-describedby="id_nome_helptext"', html)

    def test_erro_marca_o_campo_como_invalido(self):
        formulario = FormularioDeTeste(data={"nome": ""})
        formulario.is_valid()
        html = self.campo("nome", formulario)
        self.assertIn("errorlist", html)
        self.assertIn('aria-invalid="true"', html)

    def test_caixa_unica_vira_confirmacao_com_rotulo_ao_lado(self):
        html = self.campo("confirmar")
        self.assertIn('class="confirma"', html)
        self.assertRegex(html, r'<input type="checkbox" name="confirmar"[^>]*id="id_confirmar"')
        self.assertIn('<label for="id_confirmar">Confirmo</label>', html)

    def test_grupos_de_opcoes_usam_fieldset_e_legenda(self):
        for nome, rotulo in (("papeis", "Papéis"), ("escolha", "Escolha")):
            with self.subTest(campo=nome):
                html = self.campo(nome)
                self.assertIn("<fieldset", html)
                self.assertRegex(html, rf"<legend>{rotulo}")
                self.assertGreaterEqual(len(re.findall(rf'name="{nome}"', html)), 2)

    def test_campo_oculto_so_emite_o_input(self):
        html = self.campo("oculto").strip()
        self.assertTrue(html.startswith("<input"))
        self.assertNotIn("label", html)


class SituacaoTests(SimpleTestCase):
    def test_tons_conhecidos(self):
        casos = {"Ativo": "ok", "Ativa": "ok", "Confirmado": "ok", "A receber": "ok", "A pagar": "pagar",
                 "Pendente": "atencao", "Inativo": "neutro", "Cancelado": "neutro", "Qualquer coisa": "neutro"}
        for texto, tom in casos.items():
            with self.subTest(texto=texto):
                html = renderizar("{% load interface %}{% situacao t %}", t=texto)
                self.assertEqual(html, f'<span class="sit sit--{tom}">{texto}</span>')

    def test_tom_explicito_e_texto_escapado(self):
        html = renderizar('{% load interface %}{% situacao t "atencao" %}', t="<x>")
        self.assertEqual(html, '<span class="sit sit--atencao">&lt;x&gt;</span>')


class EtapasETelasDaNotaTests(SimpleTestCase):
    def etapas(self, atual, **extra):
        return render_to_string("documentos/_etapas.html", {"atual": atual, **extra})

    def test_etapa_atual_concluidas_e_aguardando_com_estado_em_texto(self):
        html = self.etapas(3)
        self.assertEqual(html.count('aria-current="step"'), 1)
        self.assertIn('<li aria-current="step"><b>3.</b>Confirmar<small>Em andamento</small></li>', html)
        self.assertEqual(html.count('class="feita"'), 2)
        self.assertEqual(html.count("<small>Concluída</small>"), 2)
        self.assertEqual(html.count("<small>Aguardando</small>"), 1)

    def test_nomes_longos_das_quatro_etapas(self):
        html = self.etapas(1)
        for nome in ("Enviar a nota", "Conferir os dados", "Confirmar", "Lançamento concluído"):
            with self.subTest(etapa=nome):
                self.assertIn(nome, html)

    def test_primeira_etapa_sem_concluidas_e_ultima_concluida(self):
        self.assertNotIn("feita", self.etapas(1))
        ultima = self.etapas(4)
        self.assertEqual(ultima.count('class="feita"'), 4)
        self.assertIn('<li aria-current="step" class="feita"><b>4.</b>Lançamento concluído<small>Concluído</small></li>', ultima)

    def test_detalhe_e_alerta_so_valem_para_a_etapa_atual(self):
        html = self.etapas(2, detalhe="3 pendências", alerta=True)
        self.assertIn('<li aria-current="step" class="alerta"><b>2.</b>Conferir os dados<small>3 pendências</small></li>', html)
        self.assertEqual(html.count("alerta"), 1)
        self.assertNotIn("alerta", self.etapas(2))

    def test_topo_do_fluxo_traz_trilha_titulo_apoio_e_etapas(self):
        html = render_to_string("documentos/_topo_fluxo.html", {
            "titulo": "Confirmar", "apoio": "Confira.", "migalha_url": "/x/", "migalha_rotulo": "Conferência", "migalha_atual": "Confirmação", "atual": 3})
        self.assertIn('<p class="migalhas"><a href="/x/">Conferência</a><span aria-hidden="true">/</span>Confirmação</p>', html)
        self.assertIn("<h1>Confirmar</h1>", html)
        self.assertIn('<p class="apoio">Confira.</p>', html)
        self.assertIn('<ol class="passos"', html)

    def test_topo_do_fluxo_sem_etapa_atual_nao_mostra_etapas(self):
        html = render_to_string("documentos/_topo_fluxo.html", {"titulo": "Análise da nota"})
        self.assertIn("<h1>Análise da nota</h1>", html)
        self.assertNotIn("passos", html)

    def test_ficha_da_nota_mostra_as_cinco_informacoes_e_so_com_dados(self):
        ficha = SimpleNamespace(numero=123, fornecedor="Boa Safra", faturado="Três Marias", valor_total="1840.00", parcelas="2 × R$ 920,00")
        html = render_to_string("documentos/_ficha_nota.html", {"ficha": ficha})
        for texto in ("123", "Boa Safra", "Três Marias", "R$ 1.840,00", "2 × R$ 920,00"):
            with self.subTest(texto=texto):
                self.assertIn(texto, html)
        self.assertNotIn("ficha", render_to_string("documentos/_ficha_nota.html", {}))

    def test_sucesso_mostra_resumo_leva_a_conta_lancada_e_marca_a_quarta_etapa(self):
        resumo = SimpleNamespace(valor_total="1840.00", quantidade_parcelas=2, primeiro_vencimento=date(2026, 12, 27))
        ficha = SimpleNamespace(numero=123, fornecedor="Boa Safra", faturado="Três Marias", valor_total="1840.00", parcelas="2 × R$ 920,00")
        html = render_to_string("documentos/lancamento_sucesso.html", {"movimento_id": 7, "nota_fiscal_id": 3, "resumo": resumo, "ficha": ficha})
        self.assertIn('href="/financeiro/contas/7/"', html)
        self.assertIn("Ver a conta lançada", html)
        self.assertIn("Enviar outra nota", html)
        self.assertIn("A pagar nº 7", html)
        self.assertIn("nº 3", html)
        self.assertIn("2 (a primeira vence em 27/12/2026)", html)
        self.assertIn("R$ 1.840,00", html)
        self.assertIn('aria-current="step" class="feita"><b>4.</b>', html)

    def test_sucesso_sem_resumo_ainda_mostra_os_numeros_do_lancamento(self):
        html = render_to_string("documentos/lancamento_sucesso.html", {"movimento_id": 7, "nota_fiscal_id": 3})
        self.assertIn("A pagar nº 7", html)
        self.assertNotIn("a primeira vence", html)

    def test_envio_usa_o_topo_do_fluxo_e_a_acao_principal_na_barra_do_rodape_dentro_do_formulario(self):
        html = render_to_string("documentos/inicio.html", {"form": DocumentoUploadForm(), "limite_upload_mb": 10})
        self.assertIn('<div class="topo-fluxo">', html)
        self.assertIn('<li aria-current="step"><b>1.</b>Enviar a nota<small>Em andamento</small></li>', html)
        formulario = html[html.index("<form"):html.index("</form>")]
        self.assertIn('<div class="acoes-rodape">', formulario)
        self.assertIn('<button type="submit" class="botao">Processar</button>', formulario)

    def test_mensagem_de_analise_usa_o_topo_sem_etapas_e_a_acao_na_barra_do_rodape(self):
        html = render_to_string("documentos/analise_mensagem.html", {"mensagem": "Análise expirada."})
        self.assertIn("<h1>Análise da nota</h1>", html)
        self.assertNotIn("passos", html)
        self.assertIn('role="alert"', html)
        self.assertRegex(html, r'<div class="acoes-rodape">\s*<a class="botao" href="/documentos/">Voltar ao envio da nota</a>')

    def test_envio_traz_aviso_de_espera_escondido_ate_o_envio(self):
        html = render_to_string("documentos/inicio.html", {"form": DocumentoUploadForm(), "limite_upload_mb": 10})
        self.assertRegex(html, r'<div class="aviso aviso--info" role="status" data-estado hidden>')
        self.assertIn("até 10 MB", html)
