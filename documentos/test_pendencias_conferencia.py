"""Pendências da conferência: onde estão (seção e campo) e como a tela as mostra."""
import re
from types import SimpleNamespace

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.testing import CREDENCIAIS_TESTE, autenticar_demo
from .analises import criar_analise, garantir_dono
from .conferencia import Problema
from .interface_conferencia import preparar_conferencia, validar_conferencia
from .pendencias_conferencia import resumir_pendencias
from .testing import resultado_da_nota
from .views_confirmacao import mensagem_validacao


def resumo(*problemas):
    form, parcelas = preparar_conferencia(resultado_da_nota(), {})
    return resumir_pendencias(SimpleNamespace(problemas=tuple(problemas)), form, parcelas)


class ResumoDePendenciasTests(TestCase):
    def test_sem_problemas_nao_ha_itens_nem_campos_marcados(self):
        r = resumo()
        self.assertEqual((r.total, r.itens, r.campos), (0, [], {}))
        self.assertEqual([s["total"] for s in r.secoes], [0, 0, 0, 0])

    def test_problema_aponta_a_secao_e_o_campo(self):
        r = resumo(Problema("fornecedor.documento", "invalido"))
        self.assertEqual([s["total"] for s in r.secoes], [1, 0, 0, 0])
        self.assertEqual(r.itens[0]["ancora"], "id_fornecedor_documento")
        self.assertEqual(r.itens[0]["rotulo"], "Documento do fornecedor")
        self.assertEqual(r.campos, {"fornecedor_documento": mensagem_validacao("invalido")})

    def test_identidade_fiscal_marca_os_quatro_campos_e_so_a_chave_leva_o_motivo(self):
        r = resumo(Problema("identidade_fiscal", "invalido"))
        self.assertEqual(set(r.campos), {"chave_acesso", "modelo", "serie_nota", "numero_nota"})
        self.assertEqual(r.itens[0]["ancora"], "id_chave_acesso")
        self.assertEqual(r.campos["chave_acesso"], mensagem_validacao("invalido"))
        self.assertIn("identificação fiscal", r.campos["modelo"])
        self.assertEqual([s["total"] for s in r.secoes], [0, 0, 1, 0])

    def test_documento_do_faturado_aponta_para_o_campo_preenchido_ou_para_a_escolha(self):
        # O resultado de teste traz CPF do faturado.
        self.assertEqual(resumo(Problema("faturado.documento", "invalido")).itens[0]["ancora"], "id_faturado_cpf")
        escolha = resumo(Problema("faturado.documento", "escolha_necessaria"))
        self.assertEqual(set(escolha.campos), {"documento_faturado"})
        self.assertEqual([s["total"] for s in escolha.secoes], [0, 1, 0, 0])

    def test_problema_de_parcelas_aponta_para_a_secao_e_nao_marca_campo(self):
        r = resumo(Problema("parcelas", "parcela_soma"))
        self.assertEqual(r.itens[0]["ancora"], "secao-parcelas")
        self.assertEqual(r.campos, {})
        self.assertEqual([s["total"] for s in r.secoes], [0, 0, 0, 1])

    def test_problema_sem_lugar_na_tela_entra_na_lista_sem_secao_nem_link(self):
        r = resumo(Problema("correcoes", "invalido"))
        self.assertEqual((r.itens[0]["secao"], r.itens[0]["ancora"]), (None, None))
        self.assertEqual([s["total"] for s in r.secoes], [0, 0, 0, 0])
        self.assertEqual(r.total, 1)

    def test_erros_do_formulario_enviado_entram_na_contagem_por_secao(self):
        dados = {"valor_total": "abc", "parcelas-TOTAL_FORMS": "1", "parcelas-INITIAL_FORMS": "1",
                 "parcelas-0-valor": "", "parcelas-0-data_vencimento": ""}
        form, parcelas, _ = validar_conferencia(resultado_da_nota(), dados)
        r = resumir_pendencias(SimpleNamespace(problemas=()), form, parcelas)
        ancoras = {i["ancora"] for i in r.itens}
        self.assertIn("id_valor_total", ancoras)
        self.assertIn("id_parcelas-0-valor", ancoras)
        self.assertGreater(r.secoes[2]["total"], 0)
        self.assertGreater(r.secoes[3]["total"], 0)
        # Erro de formulário já aparece sob o campo: não duplica como "pendência" de campo.
        self.assertEqual(r.campos, {})
        self.assertEqual([i["secao"] for i in r.itens], sorted(i["secao"] for i in r.itens))


@override_settings(**CREDENCIAIS_TESTE)
class TelaDePendenciasTests(TestCase):
    def setUp(self):
        autenticar_demo(self.client)
        sessao = self.client.session
        garantir_dono(sessao)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        self.analise = criar_analise(self.client.session, resultado_da_nota())
        self.html = self.client.get(reverse("analise_conferencia", args=[self.analise.id])).content.decode()

    def test_lista_de_pendencias_leva_ao_campo_e_diz_a_secao(self):
        painel = re.search(r'<section class="pendencias".*?</section>', self.html, re.S).group(0)
        self.assertRegex(painel, r"\d+ pendência")
        self.assertIn('<a href="#id_chave_acesso">', painel)
        self.assertIn('<span class="pendencias__secao">3. Dados da nota</span>', painel)

    def test_secao_com_pendencia_e_marcada_e_a_sem_pendencia_diz_que_esta_ok(self):
        secao_nota = re.search(r'<section class="secao-nota[^"]*" id="secao-nota".*?</section>', self.html, re.S).group(0)
        self.assertIn("secao-nota--pendente", secao_nota)
        self.assertRegex(secao_nota, r'<span class="st st--erro">\d+ pendência')
        secao_parcelas = re.search(r'<section class="secao-nota[^"]*" id="secao-parcelas".*?</section>', self.html, re.S).group(0)
        self.assertNotIn("secao-nota--pendente", secao_parcelas)
        self.assertIn('<span class="st st--ok">Sem pendências</span>', secao_parcelas)

    def test_campo_pendente_e_marcado_e_o_motivo_aparece_em_texto(self):
        campo = re.search(r'<div class="campo campo--g campo--pendente">.*?</div>', self.html, re.S).group(0)
        self.assertIn('id="id_chave_acesso"', campo)
        self.assertIn("<strong>Pendente:</strong>", campo)

    def test_painel_lateral_resume_a_situacao_de_cada_secao_com_link(self):
        lateral = re.search(r'<nav class="cartao cartao--status".*?</nav>', self.html, re.S).group(0)
        for ancora in ("secao-fornecedor", "secao-faturado", "secao-nota", "secao-parcelas"):
            self.assertIn(f'href="#{ancora}"', lateral)
        self.assertEqual(lateral.count('class="st st--'), 4)
