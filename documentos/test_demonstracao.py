"""Carga fictícia e salvaguardas, exclusivamente no banco local de teste."""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from time import perf_counter
from types import SimpleNamespace
from unittest import mock
from uuid import NAMESPACE_URL, uuid5

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

# Retrato independente do catálogo anterior: descrição, quantidade, preço unitário.
LEGADO = (
    ("Ração bovina 25 kg", "20", "89.50"),
    ("Sal mineral 30 kg", "10", "112.00"),
    ("Vacina contra clostridioses 50 doses", "4", "92.50"),
    ("Vermífugo bovino 500 ml", "3", "165.00"),
    ("Adubo NPK 04-14-08 50 kg", "30", "148.00"),
    ("Calcário agrícola tonelada", "8", "155.00"),
    ("Defensivo agrícola herbicida 5 L", "4", "275.00"),
    ("Inseticida biológico 1 L", "6", "98.00"),
    ("Diesel S10 litro", "180.5", "6.20"),
    ("Óleo lubrificante para trator 20 L", "2", "385.00"),
    ("Filtro de óleo do trator", "3", "78.00"),
    ("Correia do alternador do trator", "2", "125.00"),
    ("Sementes de milho saco 20 kg", "10", "420.00"),
    ("Sementes de braquiária saco 10 kg", "8", "230.00"),
    ("Arame farpado rolo 500 m", "4", "395.00"),
    ("Mourão tratado para cerca", "60", "42.00"),
    ("Energia elétrica rural kWh", "850", "0.92"),
    ("Instalação de padrão elétrico rural", "1", "1250.00"),
    ("Tubo PVC de irrigação 50 mm", "25", "64.00"),
    ("Aspersor para irrigação", "12", "58.50"),
    ("Lona para silagem 8 x 50 m", "2", "690.00"),
    ("Inoculante para silagem", "5", "95.00"),
    ("Telha galvanizada para galpão", "20", "132.00"),
    ("Cimento saco 50 kg", "25", "39.90"),
)


def contagens():
    return tuple(model.objects.count() for model in (
        Pessoa, PapelPessoa, MovimentoConta, MovimentoClassificacao, NotaFiscalLancada,
        ParcelaConta, ItemNotaFiscal, Classificacao,
    ))


class DemonstracaoTests(TestCase):
    def setUp(self):
        relogio = mock.patch("django.utils.timezone.localdate", return_value=date(2026, 11, 27))
        relogio.start()
        self.addCleanup(relogio.stop)

    def test_carga_oficial_coerente_variada_e_idempotente(self):
        classificacoes_antes = list(Classificacao.objects.values_list("pk", "codigo", "descricao"))
        with (
            mock.patch.object(demonstracao, "registrar_movimento", wraps=demonstracao.registrar_movimento) as movimentos,
            mock.patch.object(demonstracao, "registrar_identidade_fiscal", wraps=demonstracao.registrar_identidade_fiscal) as identidades,
            mock.patch.object(demonstracao, "registrar_itens_nota", wraps=demonstracao.registrar_itens_nota) as itens,
            mock.patch.object(Pessoa.objects, "get_or_create", wraps=Pessoa.objects.get_or_create) as pessoas,
        ):
            inicio = perf_counter()
            self.assertEqual(demonstracao.carregar_demonstracao(), 200)
            duracao = perf_counter() - inicio
        self.assertEqual((movimentos.call_count, identidades.call_count, itens.call_count), (200, 200, 200))
        self.assertEqual(pessoas.call_count, 37)
        self.assertEqual(MovimentoConta.objects.count(), 200)
        self.assertEqual(NotaFiscalLancada.objects.count(), 200)
        self.assertGreaterEqual(MovimentoConta.objects.values("contraparte_id").distinct().count(), 30)
        self.assertEqual(NotaFiscalLancada.objects.values("emitente_cnpj", "modelo", "serie", "numero").distinct().count(), 200)
        notas = NotaFiscalLancada.objects.select_related("movimento__faturado").prefetch_related(
            "itens", "movimento__parcelas", "movimento__classificacoes__classificacao",
        )
        quantidades_parcelas, quantidades_itens = set(), set()
        emissoes, elegiveis, pagas = [], 0, 0
        for nota in notas:
            with self.subTest(nota=nota.numero):
                movimento = nota.movimento
                indice = nota.numero - 900000
                self.assertEqual(movimento.origem, "NOTA_FISCAL")
                self.assertEqual(movimento.tipo, "APAGAR")
                self.assertTrue(cnpj_dv_valido(nota.emitente_cnpj))
                self.assertTrue(cpf_dv_valido(movimento.faturado.documento))
                self.assertEqual(movimento.analise_origem_id, demonstracao.id_da_nota(indice))
                self.assertEqual((nota.modelo, nota.serie), ("55", 901))
                self.assertLessEqual(date(2026, 1, 5), nota.data_emissao)
                self.assertLessEqual(nota.data_emissao, date(2026, 11, 25))
                emissoes.append(nota.data_emissao)
                parcelas = list(movimento.parcelas.all())
                quantidades_parcelas.add(len(parcelas))
                self.assertEqual([p.numero for p in parcelas], list(range(1, len(parcelas) + 1)))
                self.assertEqual(sum(p.valor for p in parcelas), movimento.valor_total)
                itens_nota = list(nota.itens.all())
                self.assertGreaterEqual(len(itens_nota), 1)
                self.assertEqual(sum(i.valor_total for i in itens_nota), movimento.valor_total)
                self.assertEqual(len(movimento.classificacoes.all()), 1)
                self.assertIn(movimento.classificacoes.all()[0].classificacao.codigo, (
                    demonstracao.MANUTENCAO, demonstracao.INFRAESTRUTURA,
                ))
                if indice > 24:
                    quantidades_itens.add(len(itens_nota))
                    fornecedor = (indice - 25) % len(demonstracao.FORNECEDORES)
                    ramo = demonstracao.RAMOS_PRODUTOS[demonstracao.RAMOS_FORNECEDORES[fornecedor]]
                    self.assertTrue(all(i.descricao in {demonstracao.PRODUTOS[n][0] for n in ramo} for i in itens_nota))
                    for item in itens_nota:
                        self.assertEqual(item.valor_total, (item.quantidade * item.valor_unitario).quantize(Decimal("0.01")))
                for parcela in parcelas:
                    self.assertEqual(parcela.data_vencimento, nota.data_emissao + timedelta(days=30 * parcela.numero))
                    elegivel = indice > 24 and parcela.data_vencimento <= date(2026, 11, 15)
                    elegiveis += elegivel
                    if parcela.pago_em is not None:
                        pagas += 1
                        self.assertTrue(elegivel)
                        self.assertEqual(parcela.pago_em, parcela.data_vencimento)
        self.assertEqual(quantidades_parcelas, {1, 2, 3, 4, 5, 6})
        self.assertEqual(quantidades_itens, {1, 2, 3, 4})
        self.assertGreater((max(emissoes) - min(emissoes)).days, 250)
        self.assertGreater(pagas / elegiveis, 0.60)
        self.assertLess(pagas / elegiveis, 0.80)
        print(f"\nCarga local: 200 notas em {duracao:.3f}s; baixas: {pagas}/{elegiveis} elegíveis.")
        self.assertEqual(list(Classificacao.objects.values_list("pk", "codigo", "descricao")), classificacoes_antes)
        self.assertEqual(demonstracao.contar_faltantes(), 0)
        antes = contagens()
        baixas = list(ParcelaConta.objects.values_list("pk", "pago_em"))
        with mock.patch.object(demonstracao, "registrar_pagamento") as pagar:
            self.assertEqual(demonstracao.carregar_demonstracao(), 0)
            pagar.assert_not_called()
        self.assertEqual(contagens(), antes)
        self.assertEqual(list(ParcelaConta.objects.values_list("pk", "pago_em")), baixas)

    def test_legado_exato_e_completar_de_24_para_200(self):
        self.assertEqual(demonstracao.contar_faltantes(), 200)
        self.assertEqual(demonstracao.carregar_demonstracao(24), 24)
        retrato = []
        for indice, (descricao, quantidade, unitario) in enumerate(LEGADO, 1):
            codigo = demonstracao.INFRAESTRUTURA if 15 <= indice <= 20 or indice >= 23 else demonstracao.MANUTENCAO
            self.assertEqual(demonstracao.PRODUTOS[indice - 1], (descricao, quantidade, unitario, codigo))
            nota = NotaFiscalLancada.objects.select_related("movimento__contraparte").get(numero=900000 + indice)
            movimento = nota.movimento
            emissao = date(2026, 1, 5) + timedelta(days=(indice - 1) * 12)
            valor = (Decimal(quantidade) * Decimal(unitario)).quantize(Decimal("0.01"))
            self.assertEqual(movimento.analise_origem_id, uuid5(NAMESPACE_URL, f"gestao-rural:demonstracao:nota:{indice}"))
            self.assertEqual((nota.modelo, nota.serie, nota.data_emissao), ("55", 901, emissao))
            self.assertEqual(movimento.contraparte.documento, demonstracao.cnpj_ficticio((indice - 1) // 2 + 1))
            self.assertEqual(movimento.contraparte.razao_social, demonstracao.FORNECEDORES[(indice - 1) // 2])
            self.assertEqual(movimento.valor_total, valor)
            self.assertEqual(movimento.classificacoes.get().classificacao.codigo, codigo)
            item = nota.itens.get()
            self.assertEqual((item.descricao, item.quantidade, item.valor_unitario, item.valor_total),
                             (descricao, Decimal(quantidade), Decimal(unitario), valor))
            numero_parcelas = 1 + indice % 3
            parcela = (valor / numero_parcelas).quantize(Decimal("0.01"))
            esperado = [
                (n, emissao + timedelta(days=30 * n),
                 parcela if n < numero_parcelas else valor - parcela * (n - 1), None)
                for n in range(1, numero_parcelas + 1)
            ]
            self.assertEqual(list(movimento.parcelas.values_list("numero", "data_vencimento", "valor", "pago_em")), esperado)
            retrato.append((nota.pk, movimento.pk, item.pk, esperado))
        antes = contagens()
        self.assertEqual(demonstracao.contar_faltantes(), 176)
        self.assertEqual(demonstracao.contar_faltantes(24), 0)
        self.assertEqual(contagens(), antes)
        self.assertEqual(demonstracao.carregar_demonstracao(), 176)
        for nota_id, movimento_id, item_id, parcelas in retrato:
            self.assertTrue(ItemNotaFiscal.objects.filter(pk=item_id, nota_fiscal_id=nota_id).exists())
            self.assertEqual(list(ParcelaConta.objects.filter(movimento_id=movimento_id).values_list(
                "numero", "data_vencimento", "valor", "pago_em",
            )), parcelas)
        self.assertEqual((MovimentoConta.objects.count(), NotaFiscalLancada.objects.count()), (200, 200))

    def test_falha_reverte_somente_nota_atual_e_permite_retomada(self):
        registrar = demonstracao.registrar_itens_nota

        def falhar_na_terceira(nota, itens):
            registrar(nota, itens)
            if nota.numero == 900003:
                raise RuntimeError("Falha simulada de conexão")

        with mock.patch.object(demonstracao, "registrar_itens_nota", side_effect=falhar_na_terceira):
            with self.assertRaises(RuntimeError):
                demonstracao.carregar_demonstracao(4)
        self.assertEqual((MovimentoConta.objects.count(), NotaFiscalLancada.objects.count(), ItemNotaFiscal.objects.count()), (2, 2, 2))
        self.assertFalse(Pessoa.objects.filter(documento=demonstracao.cnpj_ficticio(2)).exists())
        self.assertFalse(MovimentoConta.objects.filter(analise_origem_id=demonstracao.id_da_nota(3)).exists())
        self.assertEqual(demonstracao.contar_faltantes(4), 2)
        self.assertEqual(demonstracao.carregar_demonstracao(4), 2)
        self.assertEqual(NotaFiscalLancada.objects.count(), 4)

    def test_falha_na_baixa_reverte_nota_inteira(self):
        demonstracao.carregar_demonstracao(24)
        antes = contagens()
        with mock.patch.object(demonstracao, "registrar_pagamento", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                demonstracao.carregar_demonstracao(25)
        self.assertEqual(contagens(), antes)
        self.assertFalse(NotaFiscalLancada.objects.filter(numero=900025).exists())

    def test_nao_cria_classificacao_nem_reativa_cadastro(self):
        Classificacao.objects.filter(codigo=demonstracao.MANUTENCAO).update(status=Status.INATIVO)
        antes = contagens()
        with self.assertRaises(ValidationError):
            demonstracao.carregar_demonstracao()
        self.assertEqual(contagens(), antes)
        self.assertEqual(Classificacao.objects.get(codigo=demonstracao.MANUTENCAO).status, Status.INATIVO)

    def test_documentos_ficticios_validos_e_identidades_deterministicas(self):
        documentos = [demonstracao.cnpj_ficticio(n) for n in range(1, len(demonstracao.FORNECEDORES) + 1)]
        self.assertGreaterEqual(len(demonstracao.PRODUTOS), 80)
        self.assertEqual(len(set(documentos)), 36)
        self.assertTrue(all(cnpj_dv_valido(cnpj) for cnpj in documentos))
        self.assertTrue(all(nome.endswith("Fictícia") for nome in demonstracao.FORNECEDORES))
        self.assertTrue(cpf_dv_valido(demonstracao.CPF_FICTICIO))
        self.assertEqual(demonstracao.id_da_nota(1), demonstracao.id_da_nota(1))
        self.assertNotEqual(demonstracao.id_da_nota(1), demonstracao.id_da_nota(2))
        for indice in (25, 200, 500):
            self.assertEqual(demonstracao._dados_da_nota(indice), demonstracao._dados_da_nota(indice))

    def test_servicos_validam_quantidade_sem_gravar(self):
        antes = contagens()
        for quantidade in (0, 501, -1, True, "200", 1.5):
            for servico in (demonstracao.carregar_demonstracao, demonstracao.contar_faltantes):
                with self.subTest(quantidade=quantidade, servico=servico), self.assertRaises(ValueError):
                    servico(quantidade)
        self.assertEqual(contagens(), antes)
        self.assertEqual(demonstracao.contar_faltantes(1), 1)
        self.assertEqual(demonstracao.contar_faltantes(500), 500)

    def test_nao_aplica_baixa_futura(self):
        with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 1, 10)):
            self.assertEqual(demonstracao.carregar_demonstracao(25), 25)
        self.assertFalse(ParcelaConta.objects.filter(pago_em__isnull=False).exists())


class ComandoDemonstracaoTests(TestCase):
    def executar(self, host, *opcoes):
        self.saida = StringIO()
        banco = {"HOST": host, "NAME": "test_gr_demo200", "USER": "usuario_sigilo", "PASSWORD": "senha_sigilo"}
        with mock.patch(f"{COMANDO}.connection", SimpleNamespace(settings_dict=banco)):
            call_command("carregar_demonstracao", *opcoes, stdout=self.saida)

    def test_exige_confirmacao_e_mostra_apenas_host_e_nome(self):
        with mock.patch(f"{COMANDO}.carregar_demonstracao") as carregar:
            with self.assertRaisesMessage(CommandError, "--confirmar"):
                self.executar("127.0.0.1")
            carregar.assert_not_called()
        self.assertIn("127.0.0.1", self.saida.getvalue())
        self.assertIn("test_gr_demo200", self.saida.getvalue())
        self.assertNotIn("usuario_sigilo", self.saida.getvalue())
        self.assertNotIn("senha_sigilo", self.saida.getvalue())

    def test_recusa_remoto_inclusive_lista_de_hosts_sem_autorizacao(self):
        for host in ("192.0.2.1", "db.exemplo.invalid", "localhost,db.exemplo.invalid", "127.0.0.1.exemplo.invalid"):
            with self.subTest(host=host), mock.patch(f"{COMANDO}.carregar_demonstracao") as carregar:
                with self.assertRaisesMessage(CommandError, "--permitir-remoto"):
                    self.executar(host, "--confirmar")
                carregar.assert_not_called()

    def test_remoto_exige_as_duas_opcoes(self):
        with (
            mock.patch(f"{COMANDO}.carregar_demonstracao", return_value=200) as carregar,
            mock.patch(f"{COMANDO}.contar_faltantes", return_value=0),
        ):
            with self.assertRaisesMessage(CommandError, "--confirmar"):
                self.executar("192.0.2.1", "--permitir-remoto")
            carregar.assert_not_called()
            self.executar("192.0.2.1", "--confirmar", "--permitir-remoto")
            carregar.assert_called_once_with(200)
        self.assertIn("Notas fictícias criadas: 200 (catálogo de 200 notas; existentes agora: 200).", self.saida.getvalue())

    def test_aceita_loopback_e_socket_so_com_confirmacao(self):
        for host in ("localhost", "127.0.0.1", "::1", "", "/var/run/postgresql"):
            with self.subTest(host=host), mock.patch(f"{COMANDO}.carregar_demonstracao", return_value=0) as carregar:
                self.executar(host, "--confirmar")
                carregar.assert_called_once_with(200)
                self.assertIn("Notas fictícias criadas: 0", self.saida.getvalue())

    def test_simulacao_remota_sem_confirmacao_nao_grava(self):
        antes = contagens()
        with mock.patch(f"{COMANDO}.carregar_demonstracao") as carregar:
            self.executar("192.0.2.1", "--simular")
            carregar.assert_not_called()
        self.assertEqual(contagens(), antes)
        self.assertIn("existentes: 0; seriam criadas: 200", self.saida.getvalue())
        demonstracao.carregar_demonstracao(2)
        antes = contagens()
        self.executar("localhost", "--simular", "--quantidade", "5")
        self.assertIn("existentes: 2; seriam criadas: 3", self.saida.getvalue())
        self.assertEqual(contagens(), antes)

    def test_quantidade_valida_e_saida_real(self):
        self.executar("localhost", "--confirmar", "--quantidade", "1")
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
        self.assertIn("Notas fictícias criadas: 1 (catálogo de 1 notas; existentes agora: 1).", self.saida.getvalue())

    def test_valida_quantidade_antes_de_carregar(self):
        for quantidade in ("0", "-1", "501", "abc", "1.5"):
            with self.subTest(quantidade=quantidade), mock.patch(f"{COMANDO}.carregar_demonstracao") as carregar:
                with self.assertRaises(CommandError):
                    self.executar("localhost", "--confirmar", "--quantidade", quantidade)
                carregar.assert_not_called()
        self.assertEqual(NotaFiscalLancada.objects.count(), 0)
