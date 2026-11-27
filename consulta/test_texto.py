"""Texto completo, índice estável e carregamento sem N+1 no banco local."""

from datetime import date

from django.test import TestCase

from financeiro.identidade_fiscal import identificar_nota, registrar_identidade_fiscal
from financeiro.itens_nota import registrar_itens_nota
from financeiro.models import ParcelaConta
from financeiro.servicos import registrar_movimento
from financeiro.test_servicos import DadosDeServico

from .texto import carregar_movimentos, montar_contexto, texto_contexto, texto_indexacao


class DadosConsulta(DadosDeServico):
    def criar_nota(self, numero=123, descricao="Ração bovina", **alteracoes):
        movimento, _ = registrar_movimento(self.apagar(**alteracoes))
        nota, _ = registrar_identidade_fiscal(movimento, identificar_nota(
            emitente_cnpj=self.fornecedor.documento, modelo="55", serie=1, numero=numero,
        ), data_emissao=date(2026, 10, 1))
        registrar_itens_nota(nota, [{
            "descricao": descricao, "quantidade": "2", "valor_unitario": "625.20",
            "valor_total": "1250.40",
        }])
        return movimento


class TextoTests(DadosConsulta, TestCase):
    def test_carrega_ordem_ignora_inexistentes_e_nao_faz_n_mais_um(self):
        primeiro = self.criar_nota()
        segundo = self.criar_nota(numero=124)
        with self.assertNumQueries(4):
            movimentos = carregar_movimentos([segundo.pk, 99999999, primeiro.pk])
        self.assertEqual([m.pk for m in movimentos], [segundo.pk, primeiro.pk])
        with self.assertNumQueries(0):
            for movimento in movimentos:
                texto_contexto(movimento)
                texto_indexacao(movimento)
            montar_contexto(movimentos)
        with self.assertNumQueries(0):
            self.assertEqual(carregar_movimentos([]), [])

    def test_contexto_completo_sem_documentos_pessoais(self):
        movimento = self.criar_nota()
        ParcelaConta.objects.filter(movimento=movimento).update(pago_em=date(2026, 11, 27))
        movimento = carregar_movimentos([movimento.pk])[0]
        texto = texto_contexto(movimento)
        for trecho in (
            "Contraparte: Fornecedor Teste", "Faturado: Faturado Teste",
            "MANUTENCAO_E_OPERACAO", "Ração bovina", "quantidade 2.000000",
            "valor unitário 625.20", "valor total 1250.40", "número 123",
            "emissão 2026-10-01", "Status: Confirmado", "Parcela 1",
            "vencimento 2026-11-30", "valor R$ 1250.40", "status Ativa",
            "pago em: 2026-11-27",
        ):
            self.assertIn(trecho, texto)
        for proibido in (self.fornecedor.documento, self.faturado.documento, "CPF", "CNPJ"):
            self.assertNotIn(proibido, texto)
            self.assertNotIn(proibido, texto_indexacao(movimento))

    def test_indice_nao_muda_com_pagamento_nem_status(self):
        movimento = self.criar_nota()
        antes = texto_indexacao(carregar_movimentos([movimento.pk])[0])
        ParcelaConta.objects.filter(movimento=movimento).update(pago_em=date(2026, 11, 27))
        carregado = carregar_movimentos([movimento.pk])[0]
        carregado.status = "CANCELADO"
        self.assertEqual(texto_indexacao(carregado), antes)
        for proibido in ("Status:", "Parcela", "pago em", "criado_em", "atualizado_em"):
            self.assertNotIn(proibido, antes)
        self.assertIn("Cancelado", texto_contexto(carregado))

    def test_movimento_manual_sem_nota_nem_faturado(self):
        movimento, _ = registrar_movimento(self.areceber())
        with self.assertNumQueries(3):
            carregado = carregar_movimentos([movimento.pk])[0]
        with self.assertNumQueries(0):
            contexto = texto_contexto(carregado)
        self.assertIn("Cliente Teste", contexto)
        self.assertIn("em aberto", contexto)
        self.assertNotIn("Nota fiscal:", contexto)
        self.assertNotIn("Faturado:", contexto)

    def test_monta_blocos_identificados_na_ordem_recebida(self):
        primeiro = self.criar_nota()
        segundo = self.criar_nota(numero=124)
        movimentos = carregar_movimentos([segundo.pk, primeiro.pk])
        contexto = montar_contexto(movimentos)
        self.assertTrue(contexto.startswith(f"### MOVIMENTO #{segundo.pk}\n"))
        self.assertIn(f"\n\n### MOVIMENTO #{primeiro.pk}\n", contexto)
        self.assertEqual(montar_contexto([]), "")

    def test_valores_ausentes_nao_sao_inventados(self):
        outro, _ = registrar_movimento(self.apagar())
        nota, _ = registrar_identidade_fiscal(outro, identificar_nota(
            emitente_cnpj=self.fornecedor.documento, modelo="55", serie=1, numero=456,
        ))
        registrar_itens_nota(nota, [{"descricao": "Peça"}])
        texto = texto_indexacao(carregar_movimentos([outro.pk])[0])
        self.assertIn("emissão não informado", texto)
        self.assertIn("quantidade não informado", texto)
        self.assertIn("valor unitário não informado", texto)
