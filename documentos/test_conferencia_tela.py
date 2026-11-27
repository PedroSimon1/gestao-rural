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

    def test_secoes_numeradas_e_etapa_atual(self):
        html = self.pagina()
        for numero, titulo in (("1.", "Fornecedor"), ("2.", "Faturado"), ("3.", "Dados da nota"), ("4.", "Parcelas")):
            with self.subTest(secao=titulo):
                self.assertRegex(html, rf'<h2 id="titulo-\w+"><span class="n">{numero}</span>{titulo}</h2>')
        self.assertEqual(html.count('aria-current="step"'), 1)
        self.assertIn('<li aria-current="step"><span class="so-leitor">2. Conferir os dados</span></li>', html)
        self.assertIn("Etapa <b>2 de 4</b> · Conferir os dados", html)

    def test_salvar_e_o_primeiro_botao_de_envio_para_o_enter_nao_cadastrar_classificacao(self):
        html = self.pagina()
        self.assertLess(html.index('value="salvar"'), html.index('value="criar_classificacao"'))

    def test_acoes_ficam_no_painel_lateral_e_apontam_para_os_formularios(self):
        html = self.pagina()
        cancelar = reverse("analise_cancelar", args=[self.analise.id])
        painel = re.search(r'<aside class="lado".*?</aside>', html, re.S).group(0)
        self.assertIn('<button type="submit" class="botao" form="form-conferencia" name="acao" value="salvar"', painel)
        self.assertIn('class="botao botao--perigo botao--texto" form="cancelar-analise" data-submit-texto="Cancelando...">Cancelar análise</button>', painel)
        self.assertIn('<form id="form-conferencia" method="post"', html)
        self.assertIn(f'<form id="cancelar-analise" method="post" action="{cancelar}" data-submit-lock>', html)

    def test_com_pendencias_o_botao_de_revisar_fica_bloqueado_e_nao_e_link(self):
        html = self.pagina()
        self.assertIn('<button type="button" class="botao botao--secundario" aria-disabled="true" aria-describedby="nota-bloqueio">Revisar para confirmar</button>', html)
        self.assertNotIn("Revisar dados salvos para confirmar", html)
        # O motivo do bloqueio é o texto que o botão aponta (aria-describedby).
        self.assertIn('<p class="nota-bloq" id="nota-bloqueio">Existem pendências', html)

    def test_consulta_aos_cadastros_aparece_na_propria_secao(self):
        html = self.pagina()
        fornecedor = re.search(r'<section class="secao-nota[^"]*" id="secao-fornecedor".*?</section>', html, re.S).group(0)
        self.assertRegex(fornecedor, r'<span class="cadastro cadastro--\w+">Cadastro: <b>[^<]+</b>')
        classificacao = re.search(r'<section class="secao-nota[^"]*" id="secao-nota".*?</section>', html, re.S).group(0)
        self.assertIn("Classificação: <b>", classificacao)

    def test_parcelas_sao_linhas_nomeadas_para_leitor_de_tela(self):
        html = self.pagina()
        self.assertIn('<div class="parcela" role="group" aria-labelledby="titulo-parcela-1">', html)
        self.assertIn('<span class="parcela__nome" id="titulo-parcela-1">Parcela 1</span>', html)

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
