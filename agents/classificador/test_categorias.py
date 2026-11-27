"""Classificador com as categorias de despesa informadas por quem chama (Q-05)."""
from .agent import (
    ClassificacaoInconclusivaError,
    ClassificacaoInvalidaError,
    montar_instrucao,
)
from .schemas import CategoriaDespesa, classificacao_para
from .test_agent import AgentClassificadorTestBase, nota_valida

PECAS = CategoriaDespesa("PECAS_E_IMPLEMENTOS", "Peças e implementos")
MANUTENCAO = CategoriaDespesa("MANUTENCAO_E_OPERACAO", "Manutenção e operação")
CATEGORIAS = (MANUTENCAO, PECAS)


class MontarInstrucaoTests(AgentClassificadorTestBase):
    def test_lista_codigo_e_descricao_de_cada_categoria(self):
        instrucao = montar_instrucao(CATEGORIAS)

        self.assertIn("1. MANUTENCAO_E_OPERACAO — Manutenção e operação", instrucao)
        self.assertIn("2. PECAS_E_IMPLEMENTOS — Peças e implementos", instrucao)

    def test_categoria_conhecida_ganha_orientacao_e_a_nova_so_a_descricao(self):
        linhas = montar_instrucao(CATEGORIAS).splitlines()

        self.assertIn("óleo diesel", linhas[linhas.index("1. MANUTENCAO_E_OPERACAO — Manutenção e operação") + 1])
        indice = linhas.index("2. PECAS_E_IMPLEMENTOS — Peças e implementos")
        self.assertEqual(linhas[indice + 1], "")

    def test_categoria_fora_da_lista_nao_aparece(self):
        self.assertNotIn("INFRAESTRUTURA_E_UTILIDADES", montar_instrucao((PECAS,)))


class SchemaDinamicoTests(AgentClassificadorTestBase):
    def test_schema_de_resposta_so_oferece_os_codigos_informados(self):
        propriedade = classificacao_para(CATEGORIAS).model_json_schema()["properties"]["tipo_despesa"]

        enum = [opcao["enum"] for opcao in propriedade["anyOf"] if "enum" in opcao]
        self.assertEqual(enum, [["MANUTENCAO_E_OPERACAO", "PECAS_E_IMPLEMENTOS"]])
        self.assertIn({"type": "null"}, propriedade["anyOf"])


class ClassificarComCategoriasTests(AgentClassificadorTestBase):
    def test_codigo_cadastrado_alem_do_mvp_e_aceito(self):
        self.cliente.gerar_json.return_value = {"tipo_despesa": "PECAS_E_IMPLEMENTOS", "justificativa": "Peça."}

        resultado = self.agent.classificar(nota_valida("Peça"), categorias=CATEGORIAS)

        self.assertEqual(resultado.tipo_despesa, "PECAS_E_IMPLEMENTOS")

    def test_gemini_recebe_instrucao_e_schema_das_categorias(self):
        self.agent.classificar(nota_valida(), categorias=CATEGORIAS)

        argumentos = self.cliente.gerar_json.call_args.kwargs
        self.assertEqual(argumentos["instrucao_sistema"], montar_instrucao(CATEGORIAS))
        self.assertIs(argumentos["schema_resposta"], classificacao_para(CATEGORIAS))

    def test_codigo_fora_da_lista_e_recusado_mesmo_que_exista_no_mvp(self):
        self.cliente.gerar_json.return_value = {"tipo_despesa": "INFRAESTRUTURA_E_UTILIDADES", "justificativa": "x"}

        with self.assertRaises(ClassificacaoInvalidaError):
            self.agent.classificar(nota_valida(), categorias=CATEGORIAS)

    def test_null_continua_inconclusivo(self):
        self.cliente.gerar_json.return_value = {"tipo_despesa": None, "justificativa": "Sem categoria."}

        with self.assertRaises(ClassificacaoInconclusivaError) as contexto:
            self.agent.classificar(nota_valida(), categorias=CATEGORIAS)

        self.assertIsNone(contexto.exception.classificacao.tipo_despesa)

    def test_sem_categoria_ativa_e_inconclusivo_sem_chamar_o_gemini(self):
        with self.assertRaises(ClassificacaoInconclusivaError) as contexto:
            self.agent.classificar(nota_valida(), categorias=())

        self.assertIsNone(contexto.exception.classificacao.tipo_despesa)
        self.cliente.gerar_json.assert_not_called()
