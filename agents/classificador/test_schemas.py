from django.test import SimpleTestCase
from pydantic import ValidationError

from .schemas import (
    VERSAO_SCHEMA,
    ClassificacaoDespesa,
    TipoDespesa,
)


class TipoDespesaTests(SimpleTestCase):
    def test_versao_do_schema(self):
        self.assertEqual(VERSAO_SCHEMA, 1)

    def test_categorias_do_mvp(self):
        self.assertEqual(
            [categoria.value for categoria in TipoDespesa],
            [
                "MANUTENCAO_E_OPERACAO",
                "INFRAESTRUTURA_E_UTILIDADES",
            ],
        )


class ClassificacaoDespesaTests(SimpleTestCase):
    def test_manutencao_e_operacao_valida(self):
        classificacao = ClassificacaoDespesa.model_validate(
            {
                "tipo_despesa": "MANUTENCAO_E_OPERACAO",
                "justificativa": "A nota contém óleo diesel.",
            }
        )

        self.assertEqual(
            classificacao.tipo_despesa,
            TipoDespesa.MANUTENCAO_E_OPERACAO,
        )

    def test_infraestrutura_e_utilidades_valida(self):
        classificacao = ClassificacaoDespesa.model_validate(
            {
                "tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES",
                "justificativa": "A nota contém material hidráulico.",
            }
        )

        self.assertEqual(
            classificacao.tipo_despesa,
            TipoDespesa.INFRAESTRUTURA_E_UTILIDADES,
        )

    def test_categoria_desconhecida_e_rejeitada(self):
        with self.assertRaises(ValidationError):
            ClassificacaoDespesa.model_validate(
                {
                    "tipo_despesa": "COMBUSTIVEL",
                    "justificativa": "Categoria não permitida.",
                }
            )

    def test_classificacao_pode_ser_inconclusiva(self):
        classificacao = ClassificacaoDespesa.model_validate(
            {
                "tipo_despesa": None,
                "justificativa": (
                    "Os itens não pertencem às categorias disponíveis no MVP."
                ),
            }
        )

        self.assertIsNone(classificacao.tipo_despesa)

    def test_justificativa_vazia_e_rejeitada(self):
        with self.assertRaises(ValidationError):
            ClassificacaoDespesa.model_validate(
                {
                    "tipo_despesa": "MANUTENCAO_E_OPERACAO",
                    "justificativa": "",
                }
            )

    def test_justificativa_tem_espacos_normalizados(self):
        classificacao = ClassificacaoDespesa.model_validate(
            {
                "tipo_despesa": "MANUTENCAO_E_OPERACAO",
                "justificativa": "  Óleo   diesel\npara máquinas.  ",
            }
        )

        self.assertEqual(
            classificacao.justificativa,
            "Óleo diesel para máquinas.",
        )

    def test_campos_extras_sao_ignorados(self):
        classificacao = ClassificacaoDespesa.model_validate(
            {
                "tipo_despesa": "MANUTENCAO_E_OPERACAO",
                "justificativa": "Compra relacionada à operação.",
                "categoria_inventada": "X",
            }
        )

        self.assertNotIn(
            "categoria_inventada",
            classificacao.model_dump(),
        )
    def test_tipo_despesa_omitido_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            ClassificacaoDespesa.model_validate(
                {
                    "justificativa": "Classificação sem tipo de despesa."
                }
            )


class SchemaGeminiTests(SimpleTestCase):
    def test_schema_contem_somente_as_duas_categorias(self):
        schema = ClassificacaoDespesa.model_json_schema()

        self.assertEqual(
            schema["$defs"]["TipoDespesa"]["enum"],
            [
                "MANUTENCAO_E_OPERACAO",
                "INFRAESTRUTURA_E_UTILIDADES",
            ],
        )