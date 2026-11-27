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
from .mensagens_conferencia import mensagem_validacao


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

    def test_item_sem_campo_proprio_carrega_a_mensagem_e_o_de_campo_nao(self):
        com_campo = resumo(Problema("fornecedor.documento", "invalido")).itens[0]
        self.assertFalse(com_campo["sem_campo"])
        for problema in (Problema("parcelas", "parcela_soma"), Problema("correcoes", "invalido")):
            self.assertTrue(resumo(problema).itens[0]["sem_campo"])
        self.assertEqual(len(resumo(Problema("correcoes", "invalido")).gerais), 1)
        self.assertEqual(resumo(Problema("parcelas", "parcela_soma")).gerais, [])

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

    def test_cartao_de_atencao_diz_quantas_pendencias_e_o_motivo_junto_do_campo(self):
        atencao = re.search(r'<section class="cartao cartao--pend".*?</section>', self.html, re.S).group(0)
        self.assertIn('<span class="st st--erro">1 pendência</span>', atencao)
        self.assertIn("Existem pendências na validação da nota", atencao)
        self.assertIn('<span class="onde">3. Dados da nota</span>', atencao)
        campo = re.search(r'<div class="campo campo--f campo--pendente">.*?</div>', atencao, re.S).group(0)
        self.assertIn('id="id_chave_acesso"', campo)
        self.assertIn("<strong>Pendente:</strong>", campo)

    def test_campos_de_identificacao_fiscal_ficam_juntos_no_cartao_de_atencao(self):
        atencao = re.search(r'<section class="cartao cartao--pend".*?</section>', self.html, re.S).group(0)
        for nome in ("numero_nota", "serie_nota", "modelo", "chave_acesso"):
            self.assertIn(f'id="id_{nome}"', atencao)
        # Os outros campos da seção 3 seguem no "Já conferido".
        self.assertNotIn('id="id_classificacao"', atencao)

    def test_ja_conferido_lista_as_quatro_secoes_com_editar_ou_aviso(self):
        conferido = re.search(r'<section class="cartao" aria-labelledby="titulo-conferido">.*?</section>', self.html, re.S).group(0)
        for secao in ("Fornecedor", "Faturado", "Dados da nota", "Parcelas"):
            self.assertIn(f'<span class="rot">{secao}</span>', conferido)
        self.assertEqual(conferido.count('<details class="editavel"'), 4)
        self.assertIn('<span class="editar__abrir">Editar</span>', conferido)
