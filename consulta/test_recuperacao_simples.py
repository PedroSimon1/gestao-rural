"""Recuperação literal com acentos, relevância, limite e fallback determinístico."""

from django.test import TestCase

from financeiro.models import ItemNotaFiscal
from financeiro.servicos import ItemClassificacao, registrar_movimento

from .recuperacao_simples import recuperar
from .test_texto import DadosConsulta


class RecuperacaoSimplesTests(DadosConsulta, TestCase):
    def test_itens_com_acentos_caixa_e_termos_repetidos(self):
        classificacoes = (ItemClassificacao(self.infraestrutura, principal=True),)
        movimento = self.criar_nota(descricao="RAÇÃO e Óleo", classificacoes=classificacoes)
        self.criar_nota(numero=124, descricao="Arame", classificacoes=classificacoes)
        for pergunta in ("ração óleo", "RACAO OLEO", "Ração ração óleo"):
            with self.subTest(pergunta=pergunta):
                fontes = recuperar(pergunta, 5)
                self.assertEqual([f.movimento_id for f in fontes], [movimento.pk])
                self.assertEqual(fontes[0].pontuacao, 4.0)
                self.assertIn("racao (itens)", fontes[0].motivo)
                self.assertIn("oleo (itens)", fontes[0].motivo)

    def test_contraparte_sem_acentos_compara_nome_acentuado(self):
        self.fornecedor.razao_social = "Agro São José"
        self.fornecedor.save()
        movimento = self.criar_nota(descricao="Arame")
        fontes = recuperar("AGRO SAO JOSE", 5)
        self.assertEqual([f.movimento_id for f in fontes], [movimento.pk])
        self.assertEqual(fontes[0].pontuacao, 4.0)
        self.assertIn("fornecedor", fontes[0].motivo)

    def test_classificacao_por_codigo_e_descricao(self):
        movimento = self.criar_nota(descricao="Arame")
        for pergunta in ("MANUTENCAO_E_OPERACAO", "manutenção"):
            with self.subTest(pergunta=pergunta):
                fontes = recuperar(pergunta, 5)
                self.assertEqual(fontes[0].movimento_id, movimento.pk)
                self.assertEqual(fontes[0].pontuacao, 1.0)
                self.assertIn("classificação", fontes[0].motivo)

    def test_numero_da_nota(self):
        movimento = self.criar_nota(numero=987654)
        self.criar_nota(numero=123456)
        fontes = recuperar("nota 987654", 5)
        self.assertEqual([f.movimento_id for f in fontes], [movimento.pk])
        self.assertEqual(fontes[0].pontuacao, 1.0)
        self.assertIn("987654 (nota)", fontes[0].motivo)

    def test_itens_e_fornecedor_pesam_mais_que_classificacao(self):
        item = self.criar_nota(descricao="Manutenção trator")
        self.criar_nota(numero=124, descricao="Arame")
        fontes = recuperar("manutenção", 5)
        self.assertEqual(fontes[0].movimento_id, item.pk)
        self.assertEqual([f.pontuacao for f in fontes], [2.0, 1.0])
        self.assertIn("itens", fontes[0].motivo)
        self.assertIn("classificação", fontes[0].motivo)

    def test_conta_termo_distinto_uma_vez_sem_duplicar_movimento(self):
        movimento = self.criar_nota(descricao="Fornecedor Fornecedor")
        fontes = recuperar("fornecedor fornecedor", 5)
        self.assertEqual(len(fontes), 1)
        self.assertEqual(fontes[0].movimento_id, movimento.pk)
        self.assertEqual(fontes[0].pontuacao, 2.0)
        self.assertIn("fornecedor (fornecedor, itens)", fontes[0].motivo)

    def test_varios_itens_nao_duplicam_fontes_ou_pontos(self):
        movimento = self.criar_nota(descricao="Ração")
        ItemNotaFiscal.objects.create(
            nota_fiscal=movimento.nota_fiscal, ordem=2, descricao="Ração suplementar",
        )
        fontes = recuperar("ração", 5)
        self.assertEqual(len(fontes), 1)
        self.assertEqual(fontes[0].pontuacao, 2.0)

    def test_desempata_por_recencia_e_respeita_limite_sem_n_mais_um(self):
        self.criar_nota()
        segundo = self.criar_nota(numero=124)
        terceiro = self.criar_nota(numero=125)
        with self.assertNumQueries(5):
            fontes = recuperar("ração", 2)
        self.assertEqual([f.movimento_id for f in fontes], [terceiro.pk, segundo.pk])

    def test_sem_termos_ou_sem_correspondencia_devolve_recentes(self):
        self.criar_nota()
        ultimo = self.criar_nota(numero=124)
        for pergunta in ("", "e de a os um para", "xy", "abacaxizeiro"):
            with self.subTest(pergunta=pergunta):
                fontes = recuperar(pergunta, 1)
                self.assertEqual([f.movimento_id for f in fontes], [ultimo.pk])
                self.assertEqual(fontes[0].motivo, "mais recentes")
                self.assertEqual(fontes[0].pontuacao, 0.0)

    def test_sem_movimentos_e_limite_nao_positivo(self):
        self.assertEqual(recuperar("ração", 5), [])
        with self.assertNumQueries(0):
            self.assertEqual(recuperar("ração", 0), [])
            self.assertEqual(recuperar("ração", -1), [])

    def test_busca_tambem_movimentos_manuais_sem_nota(self):
        movimento, _ = registrar_movimento(self.areceber())
        fontes = recuperar("cliente", 5)
        self.assertEqual([f.movimento_id for f in fontes], [movimento.pk])
        self.assertIn("fornecedor", fontes[0].motivo)

    def test_documentos_pessoais_nao_sao_campos_de_busca(self):
        self.criar_nota()
        for documento in (self.fornecedor.documento, self.faturado.documento):
            self.assertEqual(recuperar(documento, 5)[0].motivo, "mais recentes")
