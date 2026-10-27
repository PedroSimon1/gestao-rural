"""AnalisePendente e o serviço de análise temporária (GR-43) no PostgreSQL local.

TestCase e TransactionTestCase: rodam só com as variáveis DB_TEST_*
(config/banco_de_teste.py). Documentos fictícios, com DV calculado; nenhum
dado real. Os TransactionTestCase usam serialized_rollback=True para que o
flush ao terminar não apague as categorias iniciais.
"""

import copy
import io
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from cadastros.models import Classificacao, Papel, Pessoa
from financeiro.models import MovimentoConta, ParcelaConta
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

from .analises import (
    CHAVE_DA_SESSAO, CHAVES_DOS_DADOS, LIMITE_DOS_DADOS, VALIDADE, VERSAO_DADOS, AnaliseError,
    cancelar_analise, confirmar_analise, criar_analise, descartar_analises, expirar_analises,
    garantir_dono, obter_analise,
)
from .models import AnalisePendente, StatusAnalise
from .testing import CNPJ, CPF, nova_sessao, resultado_da_nota

TEMPO_LIMITE = 20


def vencer(analise):
    """Leva a análise para depois do prazo, mantendo expira_em > criado_em."""
    agora = timezone.now()
    AnalisePendente.objects.filter(pk=analise.pk).update(
        criado_em=agora - VALIDADE - timedelta(minutes=2), expira_em=agora - timedelta(minutes=1)
    )


def assert_erro(teste, codigo, funcao, *args):
    with teste.assertRaises(AnaliseError) as contexto:
        funcao(*args)
    teste.assertEqual(contexto.exception.codigo, codigo)
    return contexto.exception


def gravar_movimento(dados, analise_id):
    """Mapeamento mínimo nota → movimento, só para os testes (a real é da GR-51)."""
    valor = Decimal(dados["valor_total"])
    movimento, _ = registrar_movimento(DadosMovimento(
        tipo="APAGAR", origem="NOTA_FISCAL",
        contraparte=Pessoa.objects.get(documento=dados["fornecedor"]["cnpj"]),
        faturado=Pessoa.objects.get(documento=dados["faturado"]["cpf"]),
        valor_total=valor,
        classificacoes=(ItemClassificacao(
            Classificacao.objects.get(tipo="DESPESA", codigo=dados["tipo_despesa"]), principal=True
        ),),
        analise_origem_id=analise_id,
        parcelas=tuple(
            ItemParcela(p["numero"], date.fromisoformat(p["data_vencimento"]), Decimal(p["valor"]))
            for p in dados["parcelas"]
        ),
    ))
    return movimento


def cadastrar_pessoas():
    fornecedor = Pessoa.objects.create(documento=CNPJ, razao_social="Fornecedor Teste Ltda")
    fornecedor.atribuir_papel(Papel.FORNECEDOR)
    faturado = Pessoa.objects.create(documento=CPF, razao_social="Produtor Teste")
    faturado.atribuir_papel(Papel.FATURADO)


class CriacaoTests(TestCase):
    def test_guarda_os_dados_no_servidor_com_validade_de_30_minutos(self):
        sessao = nova_sessao()
        resultado = resultado_da_nota()

        analise = criar_analise(sessao, resultado)
        analise.refresh_from_db()

        self.assertIsInstance(analise.id, UUID)
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)
        self.assertEqual(analise.versao_dados, VERSAO_DADOS)
        self.assertEqual(analise.dados, resultado)
        self.assertEqual(analise.expira_em - analise.criado_em, VALIDADE)
        self.assertIsNone(analise.finalizado_em)

    def test_sessao_sem_codigo_nao_cria_analise(self):
        # Cookie anterior à GR-43: o código nasce só no login.
        for sessao in ({}, {"demo_autenticado": True}, {CHAVE_DA_SESSAO: ""}, {CHAVE_DA_SESSAO: 1}):
            with self.subTest(sessao=sessao):
                antes = dict(sessao)
                assert_erro(self, "sessao_sem_codigo", criar_analise, sessao, resultado_da_nota())
                self.assertEqual(sessao, antes)
        self.assertEqual(AnalisePendente.objects.count(), 0)

    def test_cookie_guarda_so_o_codigo_da_sessao(self):
        sessao = nova_sessao()

        analise = criar_analise(sessao, resultado_da_nota())

        self.assertEqual(list(sessao), [CHAVE_DA_SESSAO])
        codigo = sessao[CHAVE_DA_SESSAO]
        self.assertGreaterEqual(len(codigo), 40)
        # No banco fica só o hash; o código não é recuperável a partir dele.
        self.assertRegex(analise.dono_hash, r"^[0-9a-f]{64}$")
        self.assertNotIn(codigo, analise.dono_hash)
        for dado in (CPF, CNPJ, "Produtor Teste", str(analise.id)):
            self.assertNotIn(dado, str(sessao))

    def test_mesma_sessao_reusa_o_codigo(self):
        sessao = nova_sessao()
        primeira = criar_analise(sessao, resultado_da_nota())
        codigo = sessao[CHAVE_DA_SESSAO]

        segunda = criar_analise(sessao, resultado_da_nota())

        self.assertEqual(sessao[CHAVE_DA_SESSAO], codigo)
        self.assertEqual(primeira.dono_hash, segunda.dono_hash)
        self.assertNotEqual(primeira.id, segunda.id)

    def test_sessoes_diferentes_tem_donos_diferentes(self):
        self.assertNotEqual(
            criar_analise(nova_sessao(), resultado_da_nota()).dono_hash,
            criar_analise(nova_sessao(), resultado_da_nota()).dono_hash,
        )

    def test_copia_os_dados(self):
        resultado = resultado_da_nota()
        analise = criar_analise(nova_sessao(), resultado)

        resultado["valor_total"] = "999.00"
        analise.refresh_from_db()

        self.assertEqual(analise.dados["valor_total"], "150.00")

    def test_nao_cria_cadastros_nem_lancamentos(self):
        antes = (Pessoa.objects.count(), MovimentoConta.objects.count(), ParcelaConta.objects.count())

        criar_analise(nova_sessao(), resultado_da_nota())

        self.assertEqual(
            (Pessoa.objects.count(), MovimentoConta.objects.count(), ParcelaConta.objects.count()),
            antes,
        )

    def test_dados_fora_do_contrato_sao_recusados_sem_gravar(self):
        com_chave = resultado_da_nota() | {"gemini_api_key": "x"}
        sem_itens = resultado_da_nota()
        del sem_itens["itens"]
        com_decimal = resultado_da_nota() | {"valor_total": Decimal("150.00")}
        com_nan = resultado_da_nota() | {"quantidade_parcelas": float("nan")}
        com_bytes = resultado_da_nota() | {"itens": [b"%PDF-1.7"]}
        grande = resultado_da_nota() | {"itens": [{"descricao": "x" * LIMITE_DOS_DADOS}]}

        for dados in (None, [], "{}", com_chave, sem_itens, com_decimal, com_nan, com_bytes, grande):
            with self.subTest(dados=str(dados)[:40]):
                sessao = nova_sessao()
                antes = dict(sessao)
                assert_erro(self, "dados_invalidos", criar_analise, sessao, dados)
                self.assertEqual(sessao, antes)
        self.assertEqual(AnalisePendente.objects.count(), 0)

    def test_codigo_do_login_e_reusado_pelas_analises(self):
        sessao = nova_sessao()
        garantir_dono(sessao)
        codigo = sessao[CHAVE_DA_SESSAO]

        criar_analise(sessao, resultado_da_nota())

        self.assertEqual(sessao, {CHAVE_DA_SESSAO: codigo})

    def test_novo_codigo_nao_ve_as_analises_do_anterior(self):
        # O cancelamento das anteriores é do login (usuarios/demo.py).
        sessao = nova_sessao()
        anterior = criar_analise(sessao, resultado_da_nota())
        codigo = sessao[CHAVE_DA_SESSAO]

        garantir_dono(sessao)

        self.assertNotEqual(sessao[CHAVE_DA_SESSAO], codigo)
        assert_erro(self, "analise_nao_encontrada", obter_analise, sessao, anterior.id)

    def test_criar_expira_as_vencidas_de_outras_sessoes(self):
        abandonada = criar_analise(nova_sessao(), resultado_da_nota())
        vencer(abandonada)

        criar_analise(nova_sessao(), resultado_da_nota())

        abandonada.refresh_from_db()
        self.assertEqual(abandonada.status, StatusAnalise.EXPIRADA)
        self.assertIsNone(abandonada.dados)

    def test_ordem_das_chaves_nao_importa(self):
        resultado = dict(reversed(list(resultado_da_nota().items())))

        self.assertEqual(set(criar_analise(nova_sessao(), resultado).dados), set(CHAVES_DOS_DADOS))


class RecuperacaoTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())

    def test_sessao_dona_recupera_pelo_uuid_ou_pelo_texto(self):
        for identificador in (self.analise.id, str(self.analise.id)):
            with self.subTest(identificador=type(identificador).__name__):
                analise = obter_analise(self.sessao, identificador)
                self.assertEqual(analise.pk, self.analise.pk)
                self.assertEqual(analise.dados, resultado_da_nota())

    def test_cookie_regravado_continua_valendo(self):
        # O cookie assinado volta ao servidor como uma cópia da sessão.
        sessao = copy.deepcopy(self.sessao)

        self.assertEqual(obter_analise(sessao, self.analise.id).pk, self.analise.pk)

    def test_outra_sessao_nao_ve_a_analise(self):
        outra = nova_sessao()
        criar_analise(outra, resultado_da_nota())

        for sessao in (outra, {}, {CHAVE_DA_SESSAO: "forjado"}, {CHAVE_DA_SESSAO: None}):
            with self.subTest(sessao=sessao):
                assert_erro(self, "analise_nao_encontrada", obter_analise, sessao, self.analise.id)

    def test_dono_hash_no_lugar_do_codigo_nao_autoriza(self):
        sessao = {CHAVE_DA_SESSAO: self.analise.dono_hash}

        assert_erro(self, "analise_nao_encontrada", obter_analise, sessao, self.analise.id)

    def test_identificador_inexistente_ou_invalido(self):
        for identificador in (uuid4(), "nao-e-uuid", "", None, 123):
            with self.subTest(identificador=identificador):
                assert_erro(self, "analise_nao_encontrada", obter_analise, self.sessao, identificador)

    def test_mensagens_seguras(self):
        erro = assert_erro(self, "analise_nao_encontrada", obter_analise, {}, self.analise.id)

        self.assertNotIn(str(self.analise.id), erro.mensagem)
        self.assertEqual(str(erro), erro.mensagem)


class ExpiracaoTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())

    def assert_expirada(self):
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.EXPIRADA)
        self.assertIsNone(self.analise.dados)
        self.assertIsNotNone(self.analise.finalizado_em)

    def test_vencida_expira_ao_ser_obtida(self):
        vencer(self.analise)

        assert_erro(self, "analise_expirada", obter_analise, self.sessao, self.analise.id)
        self.assert_expirada()
        assert_erro(self, "analise_expirada", obter_analise, self.sessao, self.analise.id)

    def test_vencida_nao_e_confirmada_e_a_expiracao_fica_gravada(self):
        vencer(self.analise)
        chamadas = []

        assert_erro(
            self, "analise_expirada", confirmar_analise, self.sessao, self.analise.id,
            lambda *args: chamadas.append(args),
        )

        self.assertEqual(chamadas, [])
        self.assert_expirada()

    def test_vencida_nao_e_cancelada(self):
        vencer(self.analise)

        assert_erro(self, "analise_expirada", cancelar_analise, self.sessao, self.analise.id)
        self.assert_expirada()

    def test_no_prazo_continua_pendente(self):
        AnalisePendente.objects.filter(pk=self.analise.pk).update(
            expira_em=timezone.now() + timedelta(seconds=30)
        )

        self.assertEqual(obter_analise(self.sessao, self.analise.id).status, StatusAnalise.PENDENTE)

    def test_limpeza_expira_so_as_pendentes_vencidas(self):
        # Todas criadas antes de vencer: criar_analise também expira as vencidas.
        no_prazo = criar_analise(nova_sessao(), resultado_da_nota())
        cancelada = criar_analise(nova_sessao(), resultado_da_nota())
        vencer(self.analise)
        vencer(cancelada)
        AnalisePendente.objects.filter(pk=cancelada.pk).update(
            status=StatusAnalise.CANCELADA, dados=None, finalizado_em=timezone.now()
        )

        self.assertEqual(expirar_analises(), 1)
        self.assertEqual(expirar_analises(), 0)

        self.assert_expirada()
        no_prazo.refresh_from_db()
        cancelada.refresh_from_db()
        self.assertEqual(no_prazo.status, StatusAnalise.PENDENTE)
        self.assertEqual(cancelada.status, StatusAnalise.CANCELADA)

    def test_comando_de_limpeza(self):
        vencer(self.analise)
        saida = io.StringIO()

        call_command("expirar_analises", stdout=saida)

        self.assertIn("Análises expiradas: 1.", saida.getvalue())
        self.assert_expirada()


class CancelamentoTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())

    def test_cancela_e_apaga_os_dados(self):
        cancelar_analise(self.sessao, self.analise.id)

        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.CANCELADA)
        self.assertIsNone(self.analise.dados)
        self.assertIsNotNone(self.analise.finalizado_em)

    def test_cancelar_de_novo_nao_tem_efeito(self):
        cancelar_analise(self.sessao, self.analise.id)
        self.analise.refresh_from_db()
        finalizado_em = self.analise.finalizado_em

        cancelar_analise(self.sessao, self.analise.id)

        self.analise.refresh_from_db()
        self.assertEqual(self.analise.finalizado_em, finalizado_em)

    def test_cancelada_nao_e_obtida_nem_confirmada(self):
        cancelar_analise(self.sessao, self.analise.id)

        assert_erro(self, "analise_cancelada", obter_analise, self.sessao, self.analise.id)
        assert_erro(
            self, "analise_cancelada", confirmar_analise, self.sessao, self.analise.id,
            lambda *args: self.fail("gravar não deveria ser chamado"),
        )

    def test_outra_sessao_nao_cancela(self):
        assert_erro(self, "analise_nao_encontrada", cancelar_analise, {}, self.analise.id)

        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)

    def test_descartar_no_logout_cancela_so_as_pendentes_da_sessao(self):
        confirmada = criar_analise(self.sessao, resultado_da_nota())
        confirmar_analise(self.sessao, confirmada.id, lambda *args: None)
        de_outra_sessao = criar_analise(nova_sessao(), resultado_da_nota())
        cookie_antigo = copy.deepcopy(self.sessao)

        self.assertEqual(descartar_analises(self.sessao), 1)
        self.assertEqual(descartar_analises({}), 0)

        assert_erro(self, "analise_cancelada", obter_analise, cookie_antigo, self.analise.id)
        self.analise.refresh_from_db()
        self.assertIsNone(self.analise.dados)
        confirmada.refresh_from_db()
        de_outra_sessao.refresh_from_db()
        self.assertEqual(confirmada.status, StatusAnalise.CONFIRMADA)
        self.assertEqual(de_outra_sessao.status, StatusAnalise.PENDENTE)

    def test_confirmada_nao_e_cancelada(self):
        confirmar_analise(self.sessao, self.analise.id, lambda *args: None)

        assert_erro(self, "analise_confirmada", cancelar_analise, self.sessao, self.analise.id)


class ConfirmacaoTests(TestCase):
    def setUp(self):
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())

    def test_gravar_recebe_os_dados_e_o_uuid(self):
        recebidos = []

        devolvido = confirmar_analise(
            self.sessao, str(self.analise.id),
            lambda dados, analise_id: recebidos.append((dados, analise_id)) or "ok",
        )

        self.assertEqual(devolvido, "ok")
        self.assertEqual(recebidos, [(resultado_da_nota(), self.analise.id)])
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.CONFIRMADA)
        self.assertIsNone(self.analise.dados)
        self.assertIsNotNone(self.analise.finalizado_em)

    def test_reutilizacao_e_recusada_sem_chamar_gravar(self):
        chamadas = []
        gravar = lambda *args: chamadas.append(args)  # noqa: E731
        confirmar_analise(self.sessao, self.analise.id, gravar)

        assert_erro(self, "analise_confirmada", confirmar_analise, self.sessao, self.analise.id, gravar)
        assert_erro(self, "analise_confirmada", obter_analise, self.sessao, self.analise.id)
        self.assertEqual(len(chamadas), 1)

    def test_outra_sessao_nao_confirma(self):
        assert_erro(
            self, "analise_nao_encontrada", confirmar_analise, {}, self.analise.id,
            lambda *args: self.fail("gravar não deveria ser chamado"),
        )

        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)

    def test_falha_em_gravar_mantem_a_analise_pendente(self):
        def falhar(dados, analise_id):
            raise RuntimeError("falha simulada")

        with self.assertRaises(RuntimeError):
            confirmar_analise(self.sessao, self.analise.id, falhar)

        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)
        self.assertEqual(self.analise.dados, resultado_da_nota())
        self.assertEqual(confirmar_analise(self.sessao, self.analise.id, lambda *args: 1), 1)


class TransacaoExternaTests(TestCase):
    def test_confirmar_dentro_de_outra_transacao_e_recusado(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())

        for funcao in (obter_analise, cancelar_analise):
            with self.subTest(funcao=funcao.__name__), self.assertRaises(RuntimeError):
                with transaction.atomic():
                    funcao(sessao, analise.id)
        with self.assertRaises(RuntimeError), transaction.atomic():
            confirmar_analise(sessao, analise.id, lambda *args: self.fail("não chamar"))

        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)


class ConfirmacaoComMovimentoTests(TestCase):
    """Integração com registrar_movimento() (GR-37/GR-38), sem antecipar a GR-51."""

    def setUp(self):
        cadastrar_pessoas()
        self.sessao = nova_sessao()
        self.analise = criar_analise(self.sessao, resultado_da_nota())

    def test_movimento_usa_o_uuid_da_analise(self):
        movimento = confirmar_analise(self.sessao, self.analise.id, gravar_movimento)

        self.assertEqual(movimento.analise_origem_id, self.analise.id)
        self.assertEqual(movimento.valor_total, Decimal("150.00"))
        self.assertEqual(movimento.parcelas.count(), 1)

    def test_falha_depois_de_gravar_nao_deixa_lancamento_parcial(self):
        def gravar_e_falhar(dados, analise_id):
            gravar_movimento(dados, analise_id)
            Pessoa.objects.create(documento="12ABC34501DE35", razao_social="Nova")
            raise RuntimeError("falha depois da gravação")

        with self.assertRaises(RuntimeError):
            confirmar_analise(self.sessao, self.analise.id, gravar_e_falhar)

        self.assertEqual(MovimentoConta.objects.count(), 0)
        self.assertEqual(ParcelaConta.objects.count(), 0)
        self.assertFalse(Pessoa.objects.filter(documento="12ABC34501DE35").exists())
        self.analise.refresh_from_db()
        self.assertEqual(self.analise.status, StatusAnalise.PENDENTE)

    def test_recusa_do_servico_financeiro_mantem_a_analise_pendente(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota() | {"tipo_despesa": "INEXISTENTE"})

        with self.assertRaises(Classificacao.DoesNotExist):
            confirmar_analise(sessao, analise.id, gravar_movimento)

        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.PENDENTE)
        self.assertEqual(MovimentoConta.objects.count(), 0)


class ConstraintsTests(TestCase):
    def criar(self, **campos):
        agora = timezone.now()
        valores = {
            "dono_hash": "a" * 64, "versao_dados": 1, "dados": {"x": 1},
            "criado_em": agora, "expira_em": agora + VALIDADE,
        } | campos
        with transaction.atomic():
            return AnalisePendente.objects.create(**valores)

    def test_banco_recusa_estados_incoerentes(self):
        agora = timezone.now()
        casos = {
            "pendente sem dados": {"dados": None},
            "pendente finalizada": {"finalizado_em": agora},
            "confirmada com dados": {"status": StatusAnalise.CONFIRMADA, "finalizado_em": agora},
            "cancelada sem data": {"status": StatusAnalise.CANCELADA, "dados": None},
            "status desconhecido": {"status": "RASCUNHO"},
            "hash inválido": {"dono_hash": "Z" * 64},
            "hash curto": {"dono_hash": "a" * 63},
            "expira antes de criar": {"expira_em": agora - timedelta(seconds=1), "criado_em": agora},
        }
        for nome, campos in casos.items():
            with self.subTest(nome), self.assertRaises(IntegrityError):
                self.criar(**campos)

    def test_banco_aceita_os_estados_validos(self):
        self.criar()
        for status in (StatusAnalise.CONFIRMADA, StatusAnalise.CANCELADA, StatusAnalise.EXPIRADA):
            self.criar(status=status, dados=None, finalizado_em=timezone.now())

        self.assertEqual(AnalisePendente.objects.count(), 4)


class ConcorrenciaTests(TransactionTestCase):
    """Conexões reais em paralelo: cada thread tem a própria conexão."""

    serialized_rollback = True

    def em_paralelo(self, *chamadas):
        barreira = threading.Barrier(len(chamadas))
        resultados = [None] * len(chamadas)
        erros = []

        def executar(indice, chamada):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                barreira.wait(timeout=TEMPO_LIMITE)
                resultados[indice] = chamada()
            except BaseException as erro:
                erros.append((indice, erro))
            finally:
                connection.close()

        threads = [
            threading.Thread(target=executar, args=(indice, chamada), daemon=True)
            for indice, chamada in enumerate(chamadas)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TEMPO_LIMITE)
        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        return resultados, erros

    def test_expiracao_preguicosa_fica_gravada_com_commit_real(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        vencer(analise)

        assert_erro(
            self, "analise_expirada", confirmar_analise, sessao, analise.id,
            lambda *args: self.fail("não chamar"),
        )

        # Lido por outra conexão: a marcação foi confirmada (COMMIT), não só liberada.
        resultados, erros = self.em_paralelo(
            lambda: AnalisePendente.objects.values_list("status", "dados").get(pk=analise.pk)
        )
        self.assertEqual(erros, [])
        self.assertEqual(resultados, [(StatusAnalise.EXPIRADA, None)])

    def test_confirmacoes_simultaneas_gravam_uma_vez(self):
        cadastrar_pessoas()
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        chamadas = []

        def gravar(dados, analise_id):
            chamadas.append(analise_id)
            time.sleep(0.2)  # mantém a primeira transação aberta durante a segunda
            return gravar_movimento(dados, analise_id)

        confirmar = lambda: confirmar_analise(dict(sessao), analise.id, gravar)  # noqa: E731
        resultados, erros = self.em_paralelo(confirmar, confirmar, confirmar)

        self.assertEqual(len(chamadas), 1)
        self.assertEqual(len([r for r in resultados if r is not None]), 1)
        self.assertEqual(len(erros), 2)
        for _, erro in erros:
            self.assertIsInstance(erro, AnaliseError)
            self.assertEqual(erro.codigo, "analise_confirmada")
        self.assertEqual(MovimentoConta.objects.filter(analise_origem_id=analise.id).count(), 1)
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.CONFIRMADA)

    def test_cancelamento_durante_a_confirmacao(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        gravando = threading.Event()

        def gravar(dados, analise_id):
            gravando.set()
            time.sleep(0.3)
            return "gravado"

        def cancelar():
            gravando.wait(TEMPO_LIMITE)
            cancelar_analise(dict(sessao), analise.id)

        resultados, erros = self.em_paralelo(
            lambda: confirmar_analise(dict(sessao), analise.id, gravar), cancelar
        )

        # O cancelamento espera a confirmação e encontra a análise já confirmada.
        self.assertEqual(resultados[0], "gravado")
        self.assertEqual([(i, e.codigo) for i, e in erros], [(1, "analise_confirmada")])
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.CONFIRMADA)

    def test_logout_durante_a_confirmacao(self):
        sessao = nova_sessao()
        confirmando = criar_analise(sessao, resultado_da_nota())
        outra_pendente = criar_analise(sessao, resultado_da_nota())
        gravando = threading.Event()

        def gravar(dados, analise_id):
            gravando.set()
            time.sleep(0.3)
            return "gravado"

        def descartar():
            gravando.wait(TEMPO_LIMITE)
            return descartar_analises(dict(sessao))

        resultados, erros = self.em_paralelo(
            lambda: confirmar_analise(dict(sessao), confirmando.id, gravar), descartar
        )

        # O descarte espera a confirmação, que prevalece; a outra é cancelada.
        self.assertEqual(erros, [])
        self.assertEqual(resultados, ["gravado", 1])
        confirmando.refresh_from_db()
        outra_pendente.refresh_from_db()
        self.assertEqual(confirmando.status, StatusAnalise.CONFIRMADA)
        self.assertEqual(outra_pendente.status, StatusAnalise.CANCELADA)

    def test_limpeza_durante_a_confirmacao_nao_desfaz_o_resultado(self):
        sessao = nova_sessao()
        analise = criar_analise(sessao, resultado_da_nota())
        gravando = threading.Event()

        def gravar(dados, analise_id):
            gravando.set()
            time.sleep(0.3)
            return "gravado"

        def limpar():
            gravando.wait(TEMPO_LIMITE)
            # Prazo já vencido do ponto de vista da limpeza.
            return expirar_analises(timezone.now() + VALIDADE * 2)

        resultados, erros = self.em_paralelo(
            lambda: confirmar_analise(dict(sessao), analise.id, gravar), limpar
        )

        self.assertEqual(erros, [])
        self.assertEqual(resultados, ["gravado", 0])
        analise.refresh_from_db()
        self.assertEqual(analise.status, StatusAnalise.CONFIRMADA)
