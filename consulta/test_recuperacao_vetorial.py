"""Cosseno, top-k e filtros do índice atual, sem serviços externos."""

from django.test import TestCase, override_settings

from agents.gemini_client import GeminiAPIError, GeminiRespostaInvalidaError, TAREFA_CONSULTA

from .indexacao import ConfiguracaoDoIndiceError, atualizar_indice
from .models import EmbeddingMovimento
from .recuperacao_vetorial import recuperar
from .test_indexacao import ClienteEmbeddingFalso, DadosIndice


@override_settings(GEMINI_MODELO_EMBEDDING="modelo-teste", GEMINI_DIMENSAO_EMBEDDING="8")
class RecuperacaoVetorialTests(DadosIndice, TestCase):
    def test_ordena_por_cosseno_e_limita_top_k(self):
        mais_similar = self.criar_nota(numero=1, descricao="Ração")
        intermediario = self.criar_nota(numero=2, descricao="Ração diesel")
        self.criar_nota(numero=3, descricao="Vacina")
        cliente = ClienteEmbeddingFalso()
        atualizar_indice(cliente, 5)
        with self.assertNumQueries(1):
            fontes = recuperar("ração", cliente, 2)
        self.assertEqual([fonte.movimento_id for fonte in fontes],
                         [mais_similar.pk, intermediario.pk])
        self.assertEqual([fonte.pontuacao for fonte in fontes], [1.0, 0.7071])
        self.assertEqual([fonte.motivo for fonte in fontes],
                         ["similaridade 1,00", "similaridade 0,71"])
        self.assertTrue(all(isinstance(fonte.pontuacao, float) for fonte in fontes))
        self.assertEqual(cliente.chamadas[-1], (["ração"], TAREFA_CONSULTA))

    def test_indice_vazio(self):
        self.criar_nota()
        cliente = ClienteEmbeddingFalso()
        with self.assertNumQueries(1):
            self.assertEqual(recuperar("ração", cliente, 5), [])
        self.assertEqual(cliente.chamadas, [(["ração"], TAREFA_CONSULTA)])

    def test_ignora_modelo_dimensao_e_tamanho_de_vetor_diferentes(self):
        movimentos = [self.criar_nota(numero=numero) for numero in range(1, 5)]
        self.criar_embedding(movimentos[0], modelo="modelo-antigo")
        self.criar_embedding(movimentos[1], dimensao=4)
        self.criar_embedding(movimentos[2], vetor=[1.0, 0.0])
        self.criar_embedding(movimentos[3])
        fontes = recuperar("ração", ClienteEmbeddingFalso(), 5)
        self.assertEqual([fonte.movimento_id for fonte in fontes], [movimentos[3].pk])

    def test_empate_preserva_mais_recentes(self):
        self.criar_nota(numero=1)
        recente = self.criar_nota(numero=2)
        cliente = ClienteEmbeddingFalso()
        atualizar_indice(cliente, 5)
        fontes = recuperar("ração", cliente, 1)
        self.assertEqual([fonte.movimento_id for fonte in fontes], [recente.pk])

    def test_preserva_pontuacao_negativa(self):
        movimento = self.criar_nota()
        self.criar_embedding(movimento, vetor=[-1.0] + [0.0] * 7)
        fontes = recuperar("ração", ClienteEmbeddingFalso(), 5)
        self.assertEqual(fontes[0].pontuacao, -1.0)
        self.assertEqual(fontes[0].motivo, "similaridade -1,00")

    def test_pergunta_vazia_e_limite_nao_positivo(self):
        cliente = ClienteEmbeddingFalso()
        for pergunta in ("", " \n\t"):
            with self.subTest(pergunta=pergunta), self.assertRaises(ValueError):
                recuperar(pergunta, cliente, 5)
        self.assertEqual(recuperar("ração", cliente, 0), [])
        self.assertEqual(recuperar("ração", cliente, -1), [])
        self.assertEqual(cliente.chamadas, [])

    def test_erro_do_cliente_propaga_sem_modificar_indice(self):
        movimento = self.criar_nota()
        self.criar_embedding(movimento)
        with self.assertRaises(GeminiAPIError):
            recuperar("ração", ClienteEmbeddingFalso(erro=GeminiAPIError("Falha simulada")), 5)
        self.assertEqual(EmbeddingMovimento.objects.count(), 1)

    def test_resposta_invalida_da_consulta(self):
        for resposta in ([], [[1.0] * 4], [[0.0] * 8], [[1.0] * 8, [1.0] * 8]):
            with self.subTest(resposta=resposta), self.assertRaises(GeminiRespostaInvalidaError):
                recuperar("ração", ClienteEmbeddingFalso(resposta=resposta), 5)

    def test_configuracao_invalida_antes_de_chamar_cliente(self):
        cliente = ClienteEmbeddingFalso()
        with override_settings(GEMINI_DIMENSAO_EMBEDDING="inválida"):
            with self.assertRaises(ConfiguracaoDoIndiceError):
                recuperar("ração", cliente, 5)
        self.assertEqual(cliente.chamadas, [])

    def test_uma_consulta_independentemente_do_numero_de_vetores(self):
        primeiro = self.criar_nota(numero=1)
        self.criar_embedding(primeiro)
        cliente = ClienteEmbeddingFalso()
        with self.assertNumQueries(1):
            self.assertEqual(len(recuperar("ração", cliente, 3)), 1)
        for numero in range(2, 12):
            self.criar_embedding(self.criar_nota(numero=numero))
        with self.assertNumQueries(1):
            self.assertEqual(len(recuperar("ração", cliente, 3)), 3)
