"""Carga fictícia e salvaguardas, exclusivamente no banco local de teste."""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from cadastros.models import Classificacao, PapelPessoa, Pessoa, Status
from comum.documentos_br import cnpj_dv_valido, cpf_dv_valido
from financeiro.models import (
    ItemNotaFiscal, MovimentoClassificacao, MovimentoConta, NotaFiscalLancada, ParcelaConta,
)

from . import demonstracao

COMANDO = "documentos.management.commands.carregar_demonstracao"


def contagens():
    return tuple(model.objects.count() for model in (
        Pessoa, PapelPessoa, MovimentoConta, MovimentoClassificacao, NotaFiscalLancada,
        ParcelaConta, ItemNotaFiscal, Classificacao,
    ))


class DemonstracaoTests(TestCase):
    def test_carga_oficial_coerente_variada_e_idempotente(self):
        classificacoes_antes = list(Classificacao.objects.values_list("pk", "codigo", "descricao"))
        with (
            mock.patch.object(demonstracao, "registrar_movimento", wraps=demonstracao.registrar_movimento) as movimentos,
            mock.patch.object(demonstracao, "registrar_identidade_fiscal", wraps=demonstracao.registrar_identidade_fiscal) as identidades,
            mock.patch.object(demonstracao, "registrar_itens_nota", wraps=demonstracao.registrar_itens_nota) as itens,
        ):
            self.assertEqual(demonstracao.carregar_demonstracao(), 24)
        self.assertEqual((movimentos.call_count, identidades.call_count, itens.call_count), (24, 24, 24))
        self.assertEqual(MovimentoConta.objects.count(), 24)
        self.assertEqual(NotaFiscalLancada.objects.count(), 24)
        self.assertEqual(ItemNotaFiscal.objects.count(), 24)
        self.assertEqual(MovimentoConta.objects.values("contraparte_id").distinct().count(), 12)
        notas = NotaFiscalLancada.objects.select_related("movimento").prefetch_related(
            "itens", "movimento__parcelas", "movimento__classificacoes__classificacao",
        )
        quantidades_parcelas = set()
        emissoes = []
        for nota in notas:
            with self.subTest(nota=nota.numero):
                movimento = nota.movimento
                self.assertEqual(movimento.origem, "NOTA_FISCAL")
                self.assertEqual(movimento.tipo, "APAGAR")
                self.assertTrue(cnpj_dv_valido(nota.emitente_cnpj))
                self.assertTrue(cpf_dv_valido(movimento.faturado.documento))
                self.assertIsNotNone(movimento.analise_origem_id)
                emissoes.append(nota.data_emissao)
                parcelas = list(movimento.parcelas.all())
                quantidades_parcelas.add(len(parcelas))
                self.assertEqual([p.numero for p in parcelas], list(range(1, len(parcelas) + 1)))
                self.assertTrue(all(p.data_vencimento > nota.data_emissao for p in parcelas))
                self.assertEqual(sum(p.valor for p in parcelas), movimento.valor_total)
                self.assertEqual(sum(i.valor_total for i in nota.itens.all()), movimento.valor_total)
                self.assertEqual(len(movimento.classificacoes.all()), 1)
        self.assertEqual(quantidades_parcelas, {1, 2, 3})
        self.assertGreater((max(emissoes) - min(emissoes)).days, 250)
        self.assertEqual(list(Classificacao.objects.values_list("pk", "codigo", "descricao")), classificacoes_antes)
        antes = contagens()
        self.assertEqual(demonstracao.carregar_demonstracao(), 0)
        self.assertEqual(contagens(), antes)

    def test_falha_reverte_carga_inteira(self):
        antes = contagens()
        with mock.patch.object(demonstracao, "registrar_itens_nota", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                demonstracao.carregar_demonstracao()
        self.assertEqual(contagens(), antes)

    def test_nao_cria_classificacao_nem_reativa_cadastro(self):
        Classificacao.objects.filter(codigo=demonstracao.MANUTENCAO).update(status=Status.INATIVO)
        antes = contagens()
        with self.assertRaises(ValidationError):
            demonstracao.carregar_demonstracao()
        self.assertEqual(contagens(), antes)
        self.assertEqual(Classificacao.objects.get(codigo=demonstracao.MANUTENCAO).status, Status.INATIVO)

    def test_documentos_ficticios_validos_e_identidades_deterministicas(self):
        documentos = [demonstracao.cnpj_ficticio(n) for n in range(1, 13)]
        self.assertEqual(len(set(documentos)), 12)
        self.assertTrue(all(cnpj_dv_valido(cnpj) for cnpj in documentos))
        self.assertTrue(cpf_dv_valido(demonstracao.CPF_FICTICIO))
        self.assertEqual(demonstracao.id_da_nota(1), demonstracao.id_da_nota(1))
        self.assertNotEqual(demonstracao.id_da_nota(1), demonstracao.id_da_nota(2))


class ComandoDemonstracaoTests(TestCase):
    def executar(self, host, *opcoes):
        self.saida = StringIO()
        banco = {"HOST": host, "NAME": "test_gr_itens", "USER": "usuario_sigilo", "PASSWORD": "senha_sigilo"}
        with mock.patch(f"{COMANDO}.connection", SimpleNamespace(settings_dict=banco)):
            call_command("carregar_demonstracao", *opcoes, stdout=self.saida)

    def test_exige_confirmacao_e_mostra_apenas_host_e_nome(self):
        with mock.patch(f"{COMANDO}.carregar_demonstracao") as carregar:
            with self.assertRaisesMessage(CommandError, "--confirmar"):
                self.executar("127.0.0.1")
            carregar.assert_not_called()
        self.assertIn("127.0.0.1", self.saida.getvalue())
        self.assertIn("test_gr_itens", self.saida.getvalue())
        self.assertNotIn("usuario_sigilo", self.saida.getvalue())
        self.assertNotIn("senha_sigilo", self.saida.getvalue())

    def test_recusa_remoto_inclusive_lista_de_hosts_sem_autorizacao(self):
        for host in ("192.0.2.1", "db.exemplo.invalid", "localhost,db.exemplo.invalid", "127.0.0.1.exemplo.invalid"):
            with self.subTest(host=host), mock.patch(f"{COMANDO}.carregar_demonstracao") as carregar:
                with self.assertRaisesMessage(CommandError, "--permitir-remoto"):
                    self.executar(host, "--confirmar")
                carregar.assert_not_called()

    def test_remoto_exige_as_duas_opcoes(self):
        with mock.patch(f"{COMANDO}.carregar_demonstracao", return_value=24) as carregar:
            with self.assertRaisesMessage(CommandError, "--confirmar"):
                self.executar("192.0.2.1", "--permitir-remoto")
            carregar.assert_not_called()
            self.executar("192.0.2.1", "--confirmar", "--permitir-remoto")
            carregar.assert_called_once_with()
        self.assertIn("Notas fictícias criadas: 24", self.saida.getvalue())

    def test_aceita_loopback_e_socket_so_com_confirmacao(self):
        for host in ("localhost", "127.0.0.1", "::1", "", "/var/run/postgresql"):
            with self.subTest(host=host), mock.patch(f"{COMANDO}.carregar_demonstracao", return_value=0) as carregar:
                self.executar(host, "--confirmar")
                carregar.assert_called_once_with()
                self.assertIn("Notas fictícias criadas: 0", self.saida.getvalue())
