"""Índice incremental, falhas atômicas e leituras limitadas no banco local."""

import hashlib
import math
import re
import unicodedata
from unittest import mock

from django.test import TestCase, override_settings

from agents.gemini_client import (
    GeminiAPIError,
    GeminiRespostaInvalidaError,
    TAREFA_DOCUMENTO,
)
from cadastros.models import Pessoa
from financeiro.servicos import registrar_movimento

from .indexacao import (
    ConfiguracaoDoIndiceError,
    SituacaoIndice,
    atualizar_indice,
    situacao_indice,
)
from .models import EmbeddingMovimento
from .test_texto import DadosConsulta
from .texto import carregar_movimentos, texto_indexacao


class ClienteEmbeddingFalso:
    """Bag-of-words normalizado, determinístico e sem rede, em oito dimensões."""

    termos = ("racao", "vacina", "diesel", "adubo", "semente", "arame", "trator")

    def __init__(self, *, erro=None, resposta=None):
        self.chamadas = []
        self.erro = erro
        self.resposta = resposta

    def gerar_embeddings(self, textos, *, tarefa):
        self.chamadas.append((list(textos), tarefa))
        if self.erro is not None:
            raise self.erro
        if self.resposta is not None:
            return self.resposta
        vetores = []
        for texto in textos:
            texto = unicodedata.normalize("NFKD", texto.lower())
            termos = re.findall(r"[a-z]+", texto.encode("ascii", "ignore").decode())
            vetor = [float(termos.count(termo)) for termo in self.termos] + [0.0]
            if not any(vetor):
                vetor[-1] = 1.0
            norma = math.hypot(*vetor)
            vetores.append([valor / norma for valor in vetor])
        return vetores


class DadosIndice(DadosConsulta):
    def criar_embedding(self, movimento, *, modelo="modelo-teste", dimensao=8,
                       vetor=None, hash_texto=None):
        texto = texto_indexacao(carregar_movimentos([movimento.pk])[0])
        return EmbeddingMovimento.objects.create(
            movimento=movimento, modelo=modelo, dimensao=dimensao,
            vetor=vetor if vetor is not None else [1.0] + [0.0] * (dimensao - 1),
            hash_texto=hash_texto or hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        )


@override_settings(GEMINI_MODELO_EMBEDDING="modelo-teste", GEMINI_DIMENSAO_EMBEDDING="8")
class IndexacaoTests(DadosIndice, TestCase):
    def test_indice_vazio_nao_chama_cliente(self):
        cliente = ClienteEmbeddingFalso()
        self.assertEqual(situacao_indice(), SituacaoIndice(0, 0, 0, 0))
        self.assertEqual(atualizar_indice(cliente, 5), SituacaoIndice(0, 0, 0, 0))
        self.assertEqual(cliente.chamadas, [])

    def test_lote_unico_limite_incremental_e_idempotencia(self):
        movimentos = [self.criar_nota(numero=numero) for numero in range(1, 4)]
        cliente = ClienteEmbeddingFalso()
        self.assertEqual(atualizar_indice(cliente, 2), SituacaoIndice(3, 2, 0, 1))
        self.assertEqual(len(cliente.chamadas), 1)
        self.assertEqual(len(cliente.chamadas[0][0]), 2)
        self.assertEqual(cliente.chamadas[0][1], TAREFA_DOCUMENTO)
        self.assertEqual(
            set(EmbeddingMovimento.objects.values_list("movimento_id", flat=True)),
            {movimentos[1].pk, movimentos[2].pk},
        )
        self.assertEqual(atualizar_indice(cliente, 2), SituacaoIndice(3, 3, 0, 0))
        self.assertEqual(len(cliente.chamadas[1][0]), 1)
        self.assertEqual(atualizar_indice(cliente, 2), SituacaoIndice(3, 3, 0, 0))
        self.assertEqual(len(cliente.chamadas), 2)
        for embedding in EmbeddingMovimento.objects.all():
            self.assertTrue(all(isinstance(valor, float) for valor in embedding.vetor))
            self.assertAlmostEqual(math.hypot(*embedding.vetor), 1.0)

    def test_limite_absoluto_de_cem(self):
        for _ in range(101):
            registrar_movimento(self.apagar())
        cliente = ClienteEmbeddingFalso()
        self.assertEqual(atualizar_indice(cliente, 500), SituacaoIndice(101, 100, 0, 1))
        self.assertEqual(len(cliente.chamadas), 1)
        self.assertEqual(len(cliente.chamadas[0][0]), 100)

    def test_reindexa_hash_modificado_sem_alterar_movimento(self):
        movimento = self.criar_nota()
        cliente = ClienteEmbeddingFalso()
        atualizar_indice(cliente, 5)
        anterior = EmbeddingMovimento.objects.get(movimento=movimento)
        Pessoa.objects.filter(pk=self.fornecedor.pk).update(razao_social="Diesel Rural Fictício")
        self.assertEqual(situacao_indice(), SituacaoIndice(1, 0, 1, 0))
        self.assertEqual(atualizar_indice(cliente, 5), SituacaoIndice(1, 1, 0, 0))
        atual = EmbeddingMovimento.objects.get(movimento=movimento)
        self.assertEqual(atual.pk, anterior.pk)
        self.assertEqual(atual.criado_em, anterior.criado_em)
        self.assertGreaterEqual(atual.atualizado_em, anterior.atualizado_em)
        self.assertNotEqual(atual.hash_texto, anterior.hash_texto)
        self.assertIn("Diesel Rural Fictício", cliente.chamadas[1][0][0])
        movimento.refresh_from_db()
        self.assertEqual(movimento.valor_total, self.apagar().valor_total)

    def test_pendente_tem_prioridade_sobre_desatualizado_mais_recente(self):
        pendente = self.criar_nota(numero=1)
        antigo = self.criar_nota(numero=2)
        self.criar_embedding(antigo, hash_texto="0" * 64)
        self.assertEqual(atualizar_indice(ClienteEmbeddingFalso(), 1), SituacaoIndice(2, 1, 1, 0))
        self.assertTrue(EmbeddingMovimento.objects.filter(movimento=pendente).exists())

    def test_modelo_ou_dimensao_antigos_contam_como_pendentes(self):
        primeiro = self.criar_nota(numero=1)
        segundo = self.criar_nota(numero=2)
        self.criar_embedding(primeiro, modelo="modelo-antigo")
        self.criar_embedding(segundo, dimensao=4)
        self.assertEqual(situacao_indice(), SituacaoIndice(2, 0, 0, 2))
        self.assertEqual(atualizar_indice(ClienteEmbeddingFalso(), 5), SituacaoIndice(2, 2, 0, 0))
        self.assertEqual(EmbeddingMovimento.objects.count(), 3)
        self.assertEqual(EmbeddingMovimento.objects.get(movimento=segundo).dimensao, 8)

    def test_falha_do_cliente_nao_grava_nada(self):
        self.criar_nota()
        with self.assertRaises(GeminiAPIError):
            atualizar_indice(ClienteEmbeddingFalso(erro=GeminiAPIError("Falha simulada")), 5)
        self.assertFalse(EmbeddingMovimento.objects.exists())

    def test_resposta_invalida_nao_grava_nem_parte_do_lote(self):
        self.criar_nota(numero=1)
        self.criar_nota(numero=2)
        respostas = [[], [[1.0] * 8], [[1.0] * 8, [1.0] * 4],
                     [[1.0] * 8, [float("nan")] * 8], [[1.0] * 8, [0.0] * 8]]
        for resposta in respostas:
            with self.subTest(resposta=resposta):
                with self.assertRaises(GeminiRespostaInvalidaError):
                    atualizar_indice(ClienteEmbeddingFalso(resposta=resposta), 5)
                self.assertFalse(EmbeddingMovimento.objects.exists())

    def test_falha_preserva_embedding_existente(self):
        movimento = self.criar_nota()
        anterior = self.criar_embedding(movimento, hash_texto="0" * 64)
        with self.assertRaises(GeminiRespostaInvalidaError):
            atualizar_indice(ClienteEmbeddingFalso(resposta=[]), 5)
        anterior.refresh_from_db()
        self.assertEqual(anterior.hash_texto, "0" * 64)

    def test_limite_invalido(self):
        for limite in (0, -1):
            with self.subTest(limite=limite), self.assertRaises(ValueError):
                atualizar_indice(ClienteEmbeddingFalso(), limite)

    def test_configuracao_invalida(self):
        for dimensao in (None, "", "abc", "1.5", 0, -1, 1.5, True):
            with self.subTest(dimensao=dimensao), override_settings(GEMINI_DIMENSAO_EMBEDDING=dimensao):
                with self.assertRaises(ConfiguracaoDoIndiceError):
                    situacao_indice()
                with self.assertRaises(ConfiguracaoDoIndiceError):
                    atualizar_indice(ClienteEmbeddingFalso(), 1)
        for modelo in (None, "", " ", "m" * 101):
            with self.subTest(modelo=modelo), override_settings(GEMINI_MODELO_EMBEDDING=modelo):
                with self.assertRaises(ConfiguracaoDoIndiceError):
                    situacao_indice()

    def test_consultas_nao_crescem_por_movimento(self):
        self.criar_nota(numero=1)
        with self.assertNumQueries(5):
            self.assertEqual(situacao_indice(), SituacaoIndice(1, 0, 0, 1))
        for numero in range(2, 12):
            self.criar_nota(numero=numero)
        with self.assertNumQueries(5):
            self.assertEqual(situacao_indice(), SituacaoIndice(11, 0, 0, 11))

    def test_calcula_hashes_em_blocos_sem_carregar_tudo(self):
        for numero in range(1, 6):
            self.criar_nota(numero=numero)
        with mock.patch("consulta.indexacao.TAMANHO_BLOCO", 2), mock.patch(
            "consulta.indexacao.carregar_movimentos", wraps=carregar_movimentos,
        ) as carregar:
            with self.assertNumQueries(13):
                self.assertEqual(situacao_indice(), SituacaoIndice(5, 0, 0, 5))
            self.assertEqual([len(chamada.args[0]) for chamada in carregar.call_args_list], [2, 2, 1])
