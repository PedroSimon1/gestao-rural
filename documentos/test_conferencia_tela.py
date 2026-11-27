"""Tela de conferência redesenhada: seções, barra de ações, cadastro de classificação e script de soma."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from cadastros.models import Classificacao
from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .analises import criar_analise, garantir_dono
from .testing import resultado_da_nota

ARQUIVO_JS = Path(__file__).parent / "static" / "documentos" / "conferencia.js"


@override_settings(**CREDENCIAIS_TESTE)
class TelaDeConferenciaTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        self.analise = criar_analise(self.client.session, resultado_da_nota())
        self.url = reverse("analise_conferencia", args=[self.analise.id])

    def pagina(self):
        return self.client.get(self.url).content.decode()

    def test_topo_padrao_com_etapa_atual_em_alerta_e_ficha_da_nota(self):
        html = self.pagina()
        self.assertIn('<div class="topo-fluxo">', html)
        self.assertIn("<h1>Conferir e corrigir a nota</h1>", html)
        self.assertIn('<li aria-current="step" class="alerta"><b>2.</b>Conferir os dados<small>1 pendência</small></li>', html)
        self.assertEqual(html.count('aria-current="step"'), 1)
        self.assertIn('<dl class="ficha">', html)
        self.assertIn("<dd data-resumo-fornecedor>Fornecedor Teste Ltda</dd>", html)

    def test_precisa_de_atencao_traz_so_os_campos_pendentes_e_ja_conferido_o_resto(self):
        html = self.pagina()
        atencao = re.search(r'<section class="cartao cartao--pend".*?</section>', html, re.S).group(0)
        conferido = re.search(r'<section class="cartao" aria-labelledby="titulo-conferido">.*?</section>', html, re.S).group(0)
        for nome in ("chave_acesso", "modelo", "serie_nota", "numero_nota"):
            with self.subTest(campo=nome):
                self.assertIn(f'id="id_{nome}"', atencao)
                self.assertNotIn(f'id="id_{nome}"', conferido)
        for nome in ("fornecedor_nome", "faturado_nome", "classificacao", "valor_total"):
            with self.subTest(campo=nome):
                self.assertIn(f'id="id_{nome}"', conferido)
                self.assertNotIn(f'id="id_{nome}"', atencao)
        self.assertIn("<strong>Pendente:</strong>", atencao)
        self.assertIn("3 de 4 seções sem pendências", conferido)

    def test_cada_campo_do_formulario_aparece_uma_so_vez_com_e_sem_erro(self):
        html = self.pagina()
        erro = self.client.post(self.url, {"acao": "salvar", "versao_correcoes": "0", **self.dados_da_nota(), "valor_total": "abc",
                                           "parcelas-0-valor": ""}).content.decode()
        for pagina in (html, erro):
            ids = re.findall(r'\bid="(id_[\w-]+)"', pagina)
            repetidos = {i for i in ids if ids.count(i) > 1}
            self.assertEqual(repetidos, set())
            for nome in ("fornecedor_nome", "faturado_nome", "classificacao", "valor_total", "parcelas-0-valor"):
                self.assertIn(f"id_{nome}", ids)

    def test_erro_de_validacao_leva_o_campo_para_o_cartao_de_atencao(self):
        resposta = self.client.post(self.url, {"acao": "salvar", "versao_correcoes": "0", **self.dados_da_nota(), "valor_total": "abc"})
        html = resposta.content.decode()
        atencao = re.search(r'<section class="cartao cartao--pend".*?</section>', html, re.S).group(0)
        self.assertEqual(resposta.status_code, 400)
        self.assertIn('id="id_valor_total"', atencao)

    def test_salvar_e_o_primeiro_botao_de_envio_para_o_enter_nao_cadastrar_classificacao(self):
        html = self.pagina()
        self.assertLess(html.index('value="salvar"'), html.index('value="criar_classificacao"'))

    def test_acoes_ficam_na_barra_do_rodape_e_apontam_para_os_formularios(self):
        html = self.pagina()
        cancelar = reverse("analise_cancelar", args=[self.analise.id])
        barra = re.search(r'<div class="acoes-rodape">.*?</div>', html, re.S).group(0)
        self.assertIn('class="botao botao--perigo botao--texto" form="cancelar-analise" data-submit-texto="Cancelando...">Cancelar análise</button>', barra)
        self.assertIn('class="botao botao--secundario" name="acao" value="salvar"', barra)
        self.assertIn('<form id="form-conferencia" method="post"', html)
        self.assertIn(f'<form id="cancelar-analise" method="post" action="{cancelar}" data-submit-lock>', html)

    def test_com_pendencias_o_botao_de_revisar_fica_bloqueado_e_nao_e_link(self):
        html = self.pagina()
        self.assertIn('<button type="button" class="botao" aria-disabled="true" aria-describedby="estado-conferencia">Revisar para confirmar</button>', html)
        self.assertNotIn("Revisar dados salvos para confirmar", html)
        # O motivo do bloqueio é o texto que o botão aponta (aria-describedby).
        self.assertRegex(html, r'<span class="status" id="estado-conferencia"><strong>1 pendência</strong> impede a confirmação\.')

    def test_consulta_aos_cadastros_aparece_na_linha_de_cada_parte(self):
        html = self.pagina()
        conferido = re.search(r'<section class="cartao" aria-labelledby="titulo-conferido">.*?</section>', html, re.S).group(0)
        self.assertRegex(conferido, r'<span class="cadastro cadastro--\w+">Cadastro: <b>[^<]+</b>')
        self.assertIn("Classificação: <b>", conferido)

    def test_parcelas_sem_pendencia_ficam_em_linhas_nomeadas_dentro_do_editar(self):
        html = self.pagina()
        self.assertIn('<div class="parcela" role="group" aria-labelledby="titulo-parcela-1">', html)
        self.assertIn('<span class="parcela__nome" id="titulo-parcela-1">Parcela 1</span>', html)
        self.assertIn("1 × R$ 150,00", html)

    def test_cadastro_de_classificacao_comeca_recolhido_e_abre_com_erro(self):
        self.assertIn('<details class="recolher">', self.pagina())
        resposta = self.client.post(self.url, {
            "acao": "criar_classificacao", "versao_correcoes": "0",
            "nova-tipo": "DESPESA", "nova-codigo": "", "nova-descricao": "",
            **self.dados_da_nota(),
        })
        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, '<details class="recolher" open>', status_code=400)

    def test_aviso_de_soma_vem_oculto_e_o_script_e_carregado(self):
        html = self.pagina()
        self.assertIn('data-soma-parcelas aria-live="polite" hidden', html)
        self.assertIn('/static/documentos/conferencia.js', html)

    def test_formularios_travam_o_duplo_envio_e_cada_botao_tem_o_seu_texto(self):
        html = self.pagina()
        formularios = re.findall(r'<form\b[^>]*method="post"[^>]*>', html)
        self.assertEqual(len(formularios), 2)
        for tag in formularios:
            self.assertIn("data-submit-lock", tag)
        self.assertIn('value="salvar" data-submit-texto="Salvando..."', html)
        self.assertIn('value="criar_classificacao" formnovalidate data-submit-texto="Cadastrando..."', html)
        self.assertIn('form="cancelar-analise" data-submit-texto="Cancelando..."', html)

    def dados_da_nota(self):
        c = Classificacao.objects.get(tipo="DESPESA", codigo="MANUTENCAO_E_OPERACAO")
        return {
            "fornecedor_nome": "Nome", "fornecedor_documento": "11222333000181", "faturado_nome": "Produtor",
            "faturado_cpf": "12345678909", "faturado_cnpj": "", "documento_faturado": "CPF",
            "classificacao": str(c.pk), "numero_nota": "123", "serie_nota": "1", "data_emissao": "2026-10-01",
            "valor_total": "150.00", "parcelas-TOTAL_FORMS": "1", "parcelas-INITIAL_FORMS": "1",
            "parcelas-0-data_vencimento": "2026-11-01", "parcelas-0-valor": "150.00",
        }


class ScriptDaConferenciaTests(TestCase):
    def js(self):
        return ARQUIVO_JS.read_text()

    def test_arquivo_e_encontrado_pelo_staticfiles(self):
        self.assertEqual(Path(finders.find("documentos/conferencia.js")), ARQUIVO_JS)

    def test_script_so_calcula_e_mostra_sem_rede_nem_html_dinamico(self):
        js = self.js()
        for proibido in ("fetch(", "XMLHttpRequest", "WebSocket", "innerHTML", "outerHTML", "insertAdjacentHTML",
                         "eval(", "new Function", "document.write", "localStorage", "submit("):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, js)

    def test_script_nao_mexe_nos_valores_do_formulario(self):
        js = self.js()
        self.assertIn("textContent", js)
        self.assertNotRegex(js, r"\.(value|checked|disabled)\s*=[^=]")


@override_settings(**CREDENCIAIS_TESTE)
class TelaSemPendenciasTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        original = resultado_da_nota()
        original["documento_fiscal"] = {"chave_acesso": None, "modelo": "55", "serie": "1"}
        self.analise = criar_analise(self.client.session, original)
        self.html = self.client.get(reverse("analise_conferencia", args=[self.analise.id])).content.decode()

    def test_sem_pendencias_nao_ha_cartao_de_atencao_e_diz_que_esta_tudo_conferido(self):
        self.assertNotIn("cartao--pend", self.html)
        self.assertIn("Tudo conferido", self.html)
        self.assertIn("4 de 4 seções sem pendências", self.html)
        self.assertIn('<li aria-current="step"><b>2.</b>Conferir os dados<small>Em andamento</small></li>', self.html)

    def test_sem_pendencias_revisar_para_confirmar_e_link_ativo(self):
        self.assertIn(reverse("analise_confirmar", args=[self.analise.id]), self.html)
        self.assertIn("Revisar dados salvos para confirmar", self.html)
        self.assertNotIn('aria-disabled="true"', self.html)

    def test_sem_pendencias_todos_os_campos_ficam_no_ja_conferido_sem_repetir(self):
        ids = re.findall(r'\bid="(id_[\w-]+)"', self.html)
        self.assertEqual({i for i in ids if ids.count(i) > 1}, set())
        for nome in ("fornecedor_nome", "fornecedor_documento", "faturado_nome", "chave_acesso", "modelo", "valor_total", "parcelas-0-valor"):
            self.assertIn(f"id_{nome}", ids)
