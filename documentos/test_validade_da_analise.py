"""D2: salvar as correções renova a validade da análise, com teto desde a criação."""
from datetime import timedelta
from unittest import mock

from django.test import TestCase

from .analises import LIMITE_TOTAL, VALIDADE, AnaliseError, criar_analise, obter_analise, registrar_correcoes
from .models import AnalisePendente
from .testing import nova_sessao, resultado_da_nota


class RenovacaoDaValidadeTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())
        self.criado = self.analise.criado_em

    def em(self, depois):
        """Congela o relógio do módulo `depois` da criação."""
        return mock.patch("documentos.analises.timezone.now", return_value=self.criado + depois)

    def salvar(self, depois, versao):
        with self.em(depois):
            return registrar_correcoes(self.sessao, self.analise.id, {"serie": versao + 1}, versao)

    def test_prazo_inicial_continua_sendo_de_30_minutos(self):
        self.assertEqual(self.analise.expira_em - self.criado, VALIDADE)

    def test_salvar_renova_30_minutos_a_partir_de_agora(self):
        analise = self.salvar(timedelta(minutes=20), 0)

        self.assertEqual(analise.expira_em - self.criado, timedelta(minutes=50))
        analise.refresh_from_db()
        self.assertEqual(analise.expira_em - self.criado, timedelta(minutes=50))

    def test_salvar_varias_vezes_permite_conferir_por_mais_de_30_minutos(self):
        for minutos, versao in ((20, 0), (45, 1), (70, 2)):
            self.salvar(timedelta(minutes=minutos), versao)

        with self.em(timedelta(minutes=95)):  # 95 min > 30 min do prazo original
            self.assertEqual(obter_analise(self.sessao, self.analise.id).id, self.analise.id)

    def salvar_ate_perto_do_teto(self):
        """Um salvamento a cada 25 minutos (sempre dentro do prazo) até 175 min; devolve a próxima versão."""
        versao = 0
        for minutos in range(25, 176, 25):
            self.salvar(timedelta(minutes=minutos), versao)
            versao += 1
        return versao

    def test_renovacao_nunca_passa_do_teto_desde_a_criacao(self):
        self.salvar_ate_perto_do_teto()

        analise = AnalisePendente.objects.get(pk=self.analise.pk)

        self.assertEqual(analise.expira_em - self.criado, LIMITE_TOTAL)  # 175 min + 30 min seria 205 min
        with self.em(LIMITE_TOTAL + timedelta(seconds=1)), self.assertRaises(AnaliseError) as contexto:
            obter_analise(self.sessao, self.analise.id)
        self.assertEqual(contexto.exception.codigo, "analise_expirada")

    def test_salvar_perto_do_teto_nao_encurta_o_prazo_ja_dado(self):
        versao = self.salvar_ate_perto_do_teto()

        analise = self.salvar(timedelta(minutes=178), versao)

        self.assertEqual(analise.expira_em - self.criado, LIMITE_TOTAL)

    def test_analise_vencida_nao_e_renovada(self):
        with self.em(VALIDADE + timedelta(minutes=1)), self.assertRaises(AnaliseError) as contexto:
            registrar_correcoes(self.sessao, self.analise.id, {"serie": 1}, 0)

        self.assertEqual(contexto.exception.codigo, "analise_expirada")
        self.assertEqual(AnalisePendente.objects.get(pk=self.analise.pk).status, "EXPIRADA")

    def test_correcao_recusada_nao_renova(self):
        antes = AnalisePendente.objects.get(pk=self.analise.pk).expira_em

        with self.em(timedelta(minutes=10)):
            for chamada in (
                lambda: registrar_correcoes(self.sessao, self.analise.id, {"serie": 1}, 7),  # versão desatualizada
                lambda: registrar_correcoes(self.sessao, self.analise.id, {"serie": "x"}, 0),  # valor inválido
            ):
                with self.assertRaises(AnaliseError):
                    chamada()

        self.assertEqual(AnalisePendente.objects.get(pk=self.analise.pk).expira_em, antes)

    def test_apenas_ler_a_analise_nao_renova(self):
        with self.em(timedelta(minutes=10)):
            obter_analise(self.sessao, self.analise.id)

        self.assertEqual(AnalisePendente.objects.get(pk=self.analise.pk).expira_em - self.criado, VALIDADE)
