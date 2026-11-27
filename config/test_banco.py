"""Mensagem única de banco indisponível e checagem prévia do banco."""
from unittest import mock

from django.db import Error, OperationalError
from django.test import SimpleTestCase, TestCase

from .erros_banco import mensagem_de_banco, verificar_banco


class MensagemDeBancoTests(SimpleTestCase):
    def test_diz_o_que_falhou_que_o_banco_nao_responde_e_o_que_fazer(self):
        texto = mensagem_de_banco("acessar os cadastros")

        self.assertTrue(texto.startswith("Não foi possível acessar os cadastros agora"))
        self.assertIn("o banco de dados não está respondendo", texto)
        self.assertIn("Tente novamente em instantes.", texto)
        self.assertIn("avise o responsável", texto)

    def test_orientacao_propria_substitui_a_padrao(self):
        texto = mensagem_de_banco("concluir o registro", "Reenvie esta mesma solicitação.")

        self.assertIn("Reenvie esta mesma solicitação.", texto)
        self.assertNotIn("Tente novamente em instantes.", texto)


class VerificarBancoTests(TestCase):
    def test_banco_respondendo_nao_levanta_erro(self):
        verificar_banco()

    def test_banco_fora_do_ar_levanta_erro_de_banco(self):
        with mock.patch("config.erros_banco.connection.cursor", side_effect=OperationalError("sem conexao")):
            with self.assertRaises(Error):
                verificar_banco()
