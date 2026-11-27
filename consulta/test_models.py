"""Sanidade do índice derivado, proteção do vínculo e regravação permitida."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from financeiro.models import MovimentoConta

from .models import EmbeddingMovimento
from .test_indexacao import DadosIndice


class EmbeddingMovimentoTests(DadosIndice, TestCase):
    def test_um_embedding_por_movimento_e_modelo(self):
        movimento = self.criar_nota()
        self.criar_embedding(movimento)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.criar_embedding(movimento)
        self.criar_embedding(movimento, modelo="outro-modelo")
        self.assertEqual(movimento.embeddings.count(), 2)

    def test_constraints_de_sanidade(self):
        movimento = self.criar_nota()
        for alteracoes in ({"modelo": " "}, {"dimensao": 0}, {"hash_texto": "inválido"}):
            with self.subTest(alteracoes=alteracoes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.criar_embedding(movimento, **alteracoes)

    def test_validacao_do_vetor(self):
        movimento = self.criar_nota()
        for vetor in ([], {}, [1.0], [True] * 8, ["1"] * 8, [float("inf")] * 8):
            with self.subTest(vetor=vetor), self.assertRaises(ValidationError):
                EmbeddingMovimento(
                    movimento=movimento, modelo="modelo-teste", dimensao=8,
                    vetor=vetor, hash_texto="0" * 64,
                ).full_clean()
        embedding = EmbeddingMovimento(
            movimento=movimento, modelo="modelo-teste", dimensao=8,
            vetor=[1.0] + [0.0] * 7, hash_texto="0" * 64,
        )
        embedding.full_clean()

    def test_derivado_pode_ser_regravado_e_excluido(self):
        movimento = self.criar_nota()
        embedding = self.criar_embedding(movimento)
        embedding.vetor = [0.0, 1.0] + [0.0] * 6
        embedding.save()
        embedding.refresh_from_db()
        self.assertEqual(embedding.vetor, [0.0, 1.0] + [0.0] * 6)
        embedding.delete()
        self.assertTrue(MovimentoConta.objects.filter(pk=movimento.pk).exists())

    def test_fk_protect(self):
        campo = EmbeddingMovimento._meta.get_field("movimento")
        self.assertEqual(campo.remote_field.related_name, "embeddings")
        with self.assertRaises(ProtectedError):
            campo.remote_field.on_delete(None, campo, [self.criar_nota()], "default")
