"""Identidade fiscal da nota (D-01, GR-22, F-1) no PostgreSQL local de teste.

TestCase e TransactionTestCase: rodam só com as variáveis DB_TEST_*
(config/banco_de_teste.py). CNPJs e chaves fictícios, com DV calculado; nenhum
dado real. O DV da chave é recalculado aqui de forma independente da
implementação (dv_da_chave), pela regra da NT Conjunta 2025.001.
"""

import threading
import time
import uuid
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from .identidade_fiscal import (
    IdentidadeFiscal, identificar_nota, nota_lancada, registrar_identidade_fiscal,
    validar_chave_acesso,
)
from .models import (
    AlteracaoNaoPermitida, ExclusaoDeMovimentoNaoPermitida, MovimentoConta, NotaFiscalLancada,
)
from .servicos import registrar_movimento
from .test_servicos import DadosDeServico, ServicoTestBase

CNPJ = "11222333000181"
# Exemplo de CNPJ alfanumérico da Receita Federal (IN RFB 2.229/2024).
CNPJ_ALFANUMERICO = "12ABC34501DE35"
CNPJ_DV_INVALIDO = "11222333000182"
TEMPO_LIMITE = 30


def dv_da_chave(base):
    """Módulo 11 com ASCII − 48 e pesos 2 a 9 da direita para a esquerda."""
    soma, peso = 0, 2
    for caractere in reversed(base):
        soma += (ord(caractere) - 48) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def chave(cnpj=CNPJ, modelo="55", serie=1, numero=123, cuf="52", aamm="2610", tp_emis="1",
          codigo="12345678"):
    base = f"{cuf}{aamm}{cnpj}{modelo}{serie:03d}{numero:09d}{tp_emis}{codigo}"
    assert len(base) == 43
    return base + dv_da_chave(base)


def outro_dv(valor):
    return valor[:-1] + str((int(valor[-1]) + 1) % 10)


def assert_codigo(teste, codigo, funcao, *args, **kwargs):
    with teste.assertRaises(ValidationError) as contexto:
        funcao(*args, **kwargs)
    teste.assertEqual(contexto.exception.code, codigo)


class ChaveDeAcessoTests(SimpleTestCase):
    def test_vetor_conhecido(self):
        # Calculado à mão pela regra da NT: 52 2610 11222333000181 55 001
        # 000000123 1 12345678; soma ponderada 480, resto 7, DV 11 − 7 = 4.
        esperado = "52261011222333000181550010000001231123456784"
        self.assertEqual(chave(), esperado)
        self.assertEqual(validar_chave_acesso(esperado), esperado)

    def test_cnpj_alfanumerico(self):
        valida = chave(cnpj=CNPJ_ALFANUMERICO)

        self.assertEqual(validar_chave_acesso(valida), valida)

    def test_normaliza_espacos_e_minusculas(self):
        valida = chave(cnpj=CNPJ_ALFANUMERICO)
        impressa = " ".join(valida[i:i + 4] for i in range(0, 44, 4)).lower()

        self.assertEqual(validar_chave_acesso(impressa), valida)

    def test_recusa_dv_e_formato_invalidos(self):
        valida = chave()
        casos = {
            "dv errado": outro_dv(valida),
            "43 posições": valida[:-1],
            "45 posições": valida + "0",
            "letra fora do CNPJ (UF)": "A" + valida[1:],
            "letra no DV do CNPJ": valida[:18] + "A" + valida[19:],
            "letra no número": valida[:30] + "A" + valida[31:],
            "símbolo": valida[:10] + "#" + valida[11:],
            "vazia": "",
        }
        for nome, valor in casos.items():
            with self.subTest(nome):
                assert_codigo(self, "chave_acesso_invalida", validar_chave_acesso, valor)
        assert_codigo(self, "chave_acesso_invalida", validar_chave_acesso, 123)

    def test_dv_com_letras_usa_ascii_menos_48(self):
        # Trocar uma letra do CNPJ por outra muda o DV (A=17, B=18).
        com_a = chave(cnpj=CNPJ_ALFANUMERICO)
        base_b = com_a[:8] + "B" + com_a[9:43]
        self.assertNotEqual(com_a[-1], dv_da_chave(base_b))
        assert_codigo(self, "chave_acesso_invalida", validar_chave_acesso, base_b + com_a[-1])


class IdentificarNotaTests(SimpleTestCase):
    def test_pela_chave(self):
        valida = chave(cnpj=CNPJ_ALFANUMERICO, modelo="65", serie=7, numero=999_999_999)

        self.assertEqual(identificar_nota(chave_acesso=valida), IdentidadeFiscal(
            emitente_cnpj=CNPJ_ALFANUMERICO, modelo="65", serie=7, numero=999_999_999,
            chave_acesso=valida,
        ))

    def test_chave_com_campos_iguais(self):
        identidade = identificar_nota(
            chave_acesso=chave(), emitente_cnpj="11.222.333/0001-81", modelo=55, serie="001",
            numero="123",
        )

        self.assertEqual((identidade.serie, identidade.numero), (1, 123))

    def test_chave_divergente_bloqueia(self):
        # T-04: a chave não prevalece sobre dados divergentes.
        for campo, valor in {
            "emitente_cnpj": CNPJ_ALFANUMERICO, "modelo": "65", "serie": 2, "numero": 124,
        }.items():
            with self.subTest(campo):
                assert_codigo(
                    self, "identidade_fiscal_divergente", identificar_nota,
                    chave_acesso=chave(), **{campo: valor},
                )

    def test_divergencia_com_valor_invalido_ou_nao_suportado(self):
        # T-04: com chave válida, o código é sempre o da divergência.
        for campo, valor in {
            "modelo": "57", "emitente_cnpj": "12345678909", "serie": "abc", "numero": 0,
            "emitente_cnpj ": "./-",
        }.items():
            with self.subTest(campo=campo, valor=valor):
                assert_codigo(
                    self, "identidade_fiscal_divergente", identificar_nota,
                    chave_acesso=chave(), **{campo.strip(): valor},
                )

    def test_chave_invalida_bloqueia_mesmo_com_os_campos(self):
        # T-04: chave inválida não é ignorada em favor da combinação.
        assert_codigo(
            self, "chave_acesso_invalida", identificar_nota,
            chave_acesso=outro_dv(chave()), emitente_cnpj=CNPJ, modelo="55", serie=1, numero=123,
        )

    def test_sem_chave_pela_combinacao(self):
        self.assertEqual(
            identificar_nota(chave_acesso="  ", emitente_cnpj=CNPJ, modelo="55", serie=0, numero=1),
            IdentidadeFiscal(emitente_cnpj=CNPJ, modelo="55", serie=0, numero=1),
        )

    def test_dados_insuficientes_bloqueiam(self):
        completos = {"emitente_cnpj": CNPJ, "modelo": "55", "serie": 1, "numero": 123}
        for campo in completos:
            for vazio in (None, ""):
                with self.subTest(campo=campo, vazio=vazio):
                    assert_codigo(
                        self, "identidade_fiscal_insuficiente", identificar_nota,
                        **(completos | {campo: vazio}),
                    )
        assert_codigo(self, "identidade_fiscal_insuficiente", identificar_nota)

    def test_emitente_so_com_separadores_e_insuficiente(self):
        assert_codigo(
            self, "identidade_fiscal_insuficiente", identificar_nota,
            emitente_cnpj="./-", modelo="55", serie=1, numero=1,
        )

    def test_documentos_nao_suportados(self):
        # T-06: só NF-e e NFC-e, emitente com CNPJ.
        base = {"emitente_cnpj": CNPJ, "modelo": "55", "serie": 1, "numero": 123}
        for nome, campos in {
            "emitente com CPF": {"emitente_cnpj": "12345678909"},
            "CT-e (57)": {"modelo": "57"},
            "modelo vazio de sentido": {"modelo": "XX"},
        }.items():
            with self.subTest(nome):
                assert_codigo(
                    self, "identidade_fiscal_nao_suportada", identificar_nota, **(base | campos)
                )
        assert_codigo(
            self, "identidade_fiscal_nao_suportada", identificar_nota,
            chave_acesso=chave(modelo="57"),
        )

    def test_chave_valida_com_emitente_sem_cnpj_valido(self):
        # Ex.: emitente pessoa física na chave (zeros + CPF): não suportado (T-06).
        assert_codigo(
            self, "identidade_fiscal_nao_suportada", identificar_nota,
            chave_acesso=chave(cnpj="00012345678909"),
        )

    def test_valores_invalidos(self):
        base = {"emitente_cnpj": CNPJ, "modelo": "55", "serie": 1, "numero": 123}
        casos = [
            ("emitente_invalido", {"emitente_cnpj": CNPJ_DV_INVALIDO}),
            ("serie_invalida", {"serie": 1000}),
            ("serie_invalida", {"serie": -1}),
            ("serie_invalida", {"serie": True}),
            ("serie_invalida", {"serie": "1A"}),
            ("numero_invalido", {"numero": 0}),
            ("numero_invalido", {"numero": 1_000_000_000}),
            ("numero_invalido", {"numero": 1.5}),
            ("serie_invalida", {"serie": "²"}),
            ("numero_invalido", {"numero": "①"}),
        ]
        for codigo, campos in casos:
            with self.subTest(campos=campos):
                assert_codigo(self, codigo, identificar_nota, **(base | campos))

    def test_numero_zero_na_chave(self):
        assert_codigo(
            self, "chave_acesso_invalida", identificar_nota, chave_acesso=chave(numero=0)
        )


class IdentidadeTestBase(ServicoTestBase):
    def movimento(self, **alteracoes):
        dados = self.apagar(analise_origem_id=uuid.uuid4(), **alteracoes)
        return registrar_movimento(dados)[0]


class RegistrarIdentidadeTests(IdentidadeTestBase):
    def test_grava_com_chave(self):
        movimento = self.movimento()
        identidade = identificar_nota(chave_acesso=chave())

        nota, criada = registrar_identidade_fiscal(movimento, identidade)

        nota.refresh_from_db()
        self.assertTrue(criada)
        self.assertEqual(
            (nota.movimento_id, nota.chave_acesso, nota.emitente_cnpj, nota.modelo, nota.serie,
             nota.numero),
            (movimento.pk, chave(), CNPJ, "55", 1, 123),
        )
        self.assertEqual(movimento.nota_fiscal, nota)
        self.assertEqual(nota_lancada(identidade), nota)

    def test_grava_sem_chave(self):
        identidade = identificar_nota(emitente_cnpj=CNPJ, modelo="55", serie=1, numero=123)

        nota, _ = registrar_identidade_fiscal(self.movimento(), identidade)

        self.assertIsNone(nota.chave_acesso)

    def test_mesma_nota_em_outro_movimento(self):
        registrar_identidade_fiscal(self.movimento(), identificar_nota(chave_acesso=chave()))
        segundo = self.movimento()

        assert_codigo(
            self, "nota_ja_lancada", registrar_identidade_fiscal, segundo,
            identificar_nota(chave_acesso=chave()),
        )
        self.assertFalse(NotaFiscalLancada.objects.filter(movimento=segundo).exists())

    def test_mesma_nota_com_e_sem_chave_colide(self):
        registrar_identidade_fiscal(self.movimento(), identificar_nota(chave_acesso=chave()))

        assert_codigo(
            self, "nota_ja_lancada", registrar_identidade_fiscal, self.movimento(),
            identificar_nota(emitente_cnpj=CNPJ, modelo="55", serie=1, numero=123),
        )

    def test_mesma_combinacao_com_chave_diferente_colide(self):
        # Outro tpEmis/cNF gera outra chave para a mesma nota (ex.: contingência).
        registrar_identidade_fiscal(self.movimento(), identificar_nota(chave_acesso=chave()))

        assert_codigo(
            self, "nota_ja_lancada", registrar_identidade_fiscal, self.movimento(),
            identificar_nota(chave_acesso=chave(tp_emis="9", codigo="87654321")),
        )

    def test_notas_diferentes_do_mesmo_emitente(self):
        for numero, modelo, serie in ((123, "55", 1), (124, "55", 1), (123, "65", 1), (123, "55", 2)):
            with self.subTest(numero=numero, modelo=modelo, serie=serie):
                _, criada = registrar_identidade_fiscal(
                    self.movimento(),
                    identificar_nota(chave_acesso=chave(modelo=modelo, serie=serie, numero=numero)),
                )
                self.assertTrue(criada)

    def test_repetir_no_mesmo_movimento_e_idempotente(self):
        movimento = self.movimento()
        identidade = identificar_nota(chave_acesso=chave())
        primeira, _ = registrar_identidade_fiscal(movimento, identidade)

        segunda, criada = registrar_identidade_fiscal(movimento, identidade)

        self.assertFalse(criada)
        self.assertEqual(segunda, primeira)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)

    def test_outra_nota_no_mesmo_movimento(self):
        movimento = self.movimento()
        registrar_identidade_fiscal(movimento, identificar_nota(chave_acesso=chave()))

        assert_codigo(
            self, "movimento_ja_identificado", registrar_identidade_fiscal, movimento,
            identificar_nota(chave_acesso=chave(numero=124)),
        )

    def test_mesma_nota_sem_chave_no_movimento_identificado_com_chave(self):
        # Repetir só é idempotente com a mesma identidade, inclusive a chave.
        movimento = self.movimento()
        registrar_identidade_fiscal(movimento, identificar_nota(chave_acesso=chave()))

        assert_codigo(
            self, "movimento_ja_identificado", registrar_identidade_fiscal, movimento,
            identificar_nota(emitente_cnpj=CNPJ, modelo="55", serie=1, numero=123),
        )

    def test_identidade_montada_a_mao_e_revalidada(self):
        movimento = self.movimento()
        casos = {
            "emitente_invalido": IdentidadeFiscal(
                emitente_cnpj="11222333000182", modelo="55", serie=1, numero=123
            ),
            "chave_acesso_invalida": IdentidadeFiscal(
                emitente_cnpj=CNPJ, modelo="55", serie=1, numero=123, chave_acesso=outro_dv(chave())
            ),
            "identidade_fiscal_divergente": IdentidadeFiscal(
                emitente_cnpj=CNPJ, modelo="55", serie=1, numero=999, chave_acesso=chave()
            ),
        }
        for codigo, identidade in casos.items():
            with self.subTest(codigo):
                assert_codigo(self, codigo, registrar_identidade_fiscal, movimento, identidade)
        self.assertEqual(NotaFiscalLancada.objects.count(), 0)

    def test_entradas_recusadas(self):
        identidade = identificar_nota(chave_acesso=chave())
        manual = registrar_movimento(self.apagar(origem="MANUAL"))[0]
        nao_gravado = MovimentoConta(tipo="APAGAR", origem="NOTA_FISCAL")

        assert_codigo(self, "origem_incompativel", registrar_identidade_fiscal, manual, identidade)
        assert_codigo(self, "movimento", registrar_identidade_fiscal, nao_gravado, identidade)
        assert_codigo(self, "movimento", registrar_identidade_fiscal, None, identidade)
        assert_codigo(
            self, "identidade_fiscal", registrar_identidade_fiscal, self.movimento(), {"chave": chave()}
        )
        self.assertEqual(NotaFiscalLancada.objects.count(), 0)

    def test_falha_desfaz_o_lancamento_inteiro(self):
        # Como no serviço de lançamento: movimento + identidade na mesma transação.
        registrar_identidade_fiscal(self.movimento(), identificar_nota(chave_acesso=chave()))
        antes = MovimentoConta.objects.count()

        with self.assertRaises(ValidationError), transaction.atomic():
            movimento = self.movimento()
            registrar_identidade_fiscal(movimento, identificar_nota(chave_acesso=chave()))

        self.assertEqual(MovimentoConta.objects.count(), antes)

    def test_erro_mantem_a_transacao_utilizavel(self):
        registrar_identidade_fiscal(self.movimento(), identificar_nota(chave_acesso=chave()))

        with transaction.atomic():
            with self.assertRaises(ValidationError):
                registrar_identidade_fiscal(self.movimento(), identificar_nota(chave_acesso=chave()))
            self.assertEqual(NotaFiscalLancada.objects.count(), 1)

    def test_corrida_entre_busca_e_insert(self):
        # Simula a outra transação gravando entre nota_lancada() e o INSERT.
        movimento, outro = self.movimento(), self.movimento()
        identidade = identificar_nota(chave_acesso=chave())
        with mock.patch("financeiro.identidade_fiscal.nota_lancada", side_effect=[
            None,
            NotaFiscalLancada.objects.create(
                movimento=outro, chave_acesso=chave(), emitente_cnpj=CNPJ, modelo="55",
                serie=1, numero=123,
            ),
        ]):
            assert_codigo(self, "nota_ja_lancada", registrar_identidade_fiscal, movimento, identidade)
        self.assertFalse(NotaFiscalLancada.objects.filter(movimento=movimento).exists())


class ModelTests(IdentidadeTestBase):
    def criar(self, movimento=None, **campos):
        valores = {
            "chave_acesso": chave(), "emitente_cnpj": CNPJ, "modelo": "55", "serie": 1,
            "numero": 123,
        } | campos
        with transaction.atomic():
            return NotaFiscalLancada.objects.create(movimento=movimento or self.movimento(), **valores)

    def test_banco_recusa_identidades_incoerentes(self):
        casos = {
            "chave de outro emitente": {"emitente_cnpj": CNPJ_ALFANUMERICO},
            "chave de outro modelo": {"modelo": "65"},
            "chave de outra série": {"serie": 2},
            "chave de outro número": {"numero": 124},
            "modelo fora da lista": {"chave_acesso": None, "modelo": "57"},
            "CNPJ mal formado": {"chave_acesso": None, "emitente_cnpj": "123"},
            "série acima de 999": {"chave_acesso": None, "serie": 1000},
            "número zero": {"chave_acesso": None, "numero": 0},
        }
        for nome, campos in casos.items():
            with self.subTest(nome), self.assertRaises(IntegrityError):
                self.criar(**campos)

    def test_banco_recusa_chave_mal_formada(self):
        # Sempre violação de CHECK (IntegrityError), mesmo com letra numa
        # posição numérica: a constraint compara texto, sem CAST da chave.
        for valor in ("1" * 43, "A" + chave()[1:], chave()[:30] + "A" + chave()[31:],
                      chave()[:23] + "A" + chave()[24:]):
            with self.subTest(valor=valor), self.assertRaises(IntegrityError):
                self.criar(chave_acesso=valor)

    def test_banco_garante_unicidade(self):
        self.criar()
        for nome, campos in {
            "mesma combinação sem chave": {"chave_acesso": None},
            "mesma chave": {},
        }.items():
            with self.subTest(nome), self.assertRaises(IntegrityError):
                self.criar(**campos)
        movimento = self.movimento()
        self.criar(movimento, chave_acesso=chave(numero=200), numero=200)
        with self.assertRaises(IntegrityError):
            self.criar(movimento, chave_acesso=chave(numero=201), numero=201)

    def test_imutavel_e_sem_exclusao(self):
        nota = self.criar()
        nota.numero = 999

        with self.assertRaises(AlteracaoNaoPermitida):
            nota.save()
        with self.assertRaises(AlteracaoNaoPermitida):
            NotaFiscalLancada.objects.filter(pk=nota.pk).update(serie=9)
        with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
            NotaFiscalLancada.objects.get(pk=nota.pk).delete()
        with self.assertRaises(ExclusaoDeMovimentoNaoPermitida):
            NotaFiscalLancada.objects.all().delete()

    def test_movimento_cancelado_nao_libera_a_identidade(self):
        # T-07: sem operação de cancelamento; o status muda só por SQL aqui.
        nota = self.criar()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s", [nota.movimento_id]
            )

        assert_codigo(
            self, "nota_ja_lancada", registrar_identidade_fiscal, self.movimento(),
            identificar_nota(chave_acesso=chave()),
        )


class ConcorrenciaTests(DadosDeServico, TransactionTestCase):
    """Conexões reais em paralelo: cada thread tem a própria conexão."""

    serialized_rollback = True

    def lancar(self, gravado=None, segurar=0):
        """Movimento + identidade na mesma transação, como no serviço de lançamento."""
        with transaction.atomic():
            movimento, _ = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))
            nota, _ = registrar_identidade_fiscal(movimento, identificar_nota(chave_acesso=chave()))
            if gravado is not None:
                gravado.set()
            time.sleep(segurar)
        return nota

    def em_paralelo(self, *chamadas):
        resultados = [None] * len(chamadas)
        erros = []

        def executar(indice, chamada):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                resultados[indice] = chamada()
            except BaseException as erro:
                erros.append((indice, erro))
            finally:
                connection.close()

        threads = [
            threading.Thread(target=executar, args=(i, c), daemon=True) for i, c in enumerate(chamadas)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TEMPO_LIMITE)
        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        return resultados, erros

    def test_mesma_nota_em_duas_transacoes_simultaneas(self):
        gravado = threading.Event()

        def segunda():
            gravado.wait(TEMPO_LIMITE)
            # registrar_movimento() espera o bloqueio das pessoas até o COMMIT
            # da primeira; depois a busca prévia acha a nota.
            return self.lancar()

        resultados, erros = self.em_paralelo(
            lambda: self.lancar(gravado=gravado, segurar=0.5), segunda
        )

        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, e.code) for i, e in erros if isinstance(e, ValidationError)],
                         [(1, "nota_ja_lancada")])
        self.assertEqual(len(erros), 1)
        # A segunda transação foi desfeita inteira: um só movimento e uma só nota.
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)

    def test_servico_sob_corrida_trata_o_indice_unico(self):
        # Movimentos já gravados: as duas buscas prévias não acham nada (a
        # primeira ainda não fez COMMIT), o INSERT da segunda espera o índice
        # único e o except do serviço devolve nota_ja_lancada.
        primeiro, _ = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))
        segundo, _ = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))
        gravado = threading.Event()

        def registrar(movimento, segurar=0, esperar=None):
            if esperar is not None:
                esperar.wait(TEMPO_LIMITE)
            with transaction.atomic():
                nota, _ = registrar_identidade_fiscal(movimento, identificar_nota(chave_acesso=chave()))
                gravado.set()
                time.sleep(segurar)
            return nota

        resultados, erros = self.em_paralelo(
            lambda: registrar(primeiro, segurar=0.5), lambda: registrar(segundo, esperar=gravado)
        )

        self.assertEqual(resultados[0].movimento_id, primeiro.pk)
        self.assertEqual([(i, getattr(e, "code", e)) for i, e in erros], [(1, "nota_ja_lancada")])
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)

    def test_exige_transacao_aberta(self):
        movimento, _ = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))

        with self.assertRaises(RuntimeError):
            registrar_identidade_fiscal(movimento, identificar_nota(chave_acesso=chave()))
        self.assertEqual(NotaFiscalLancada.objects.count(), 0)

    def test_indice_unico_sob_corrida_sem_a_verificacao_previa(self):
        # Sem os bloqueios de registrar_movimento nem a busca prévia: só o
        # índice único decide. A segunda espera o COMMIT da primeira e falha.
        primeiro, _ = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))
        segundo, _ = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))
        gravado = threading.Event()
        campos = {"chave_acesso": None, "emitente_cnpj": CNPJ, "modelo": "55", "serie": 1, "numero": 123}

        def inserir(movimento, segurar=0, esperar=None):
            if esperar is not None:
                esperar.wait(TEMPO_LIMITE)
            with transaction.atomic():
                nota = NotaFiscalLancada.objects.create(movimento=movimento, **campos)
                gravado.set()
                time.sleep(segurar)
            return nota

        resultados, erros = self.em_paralelo(
            lambda: inserir(primeiro, segurar=0.5), lambda: inserir(segundo, esperar=gravado)
        )

        self.assertIsNotNone(resultados[0])
        self.assertEqual([(i, type(e)) for i, e in erros], [(1, IntegrityError)])
        self.assertEqual(list(NotaFiscalLancada.objects.values_list("movimento_id", flat=True)),
                         [primeiro.pk])

    def test_varias_simultaneas_gravam_uma(self):
        barreira = threading.Barrier(4)

        def lancar():
            barreira.wait(TEMPO_LIMITE)
            return self.lancar()

        resultados, erros = self.em_paralelo(*[lancar] * 4)

        self.assertEqual(len([r for r in resultados if r is not None]), 1)
        self.assertEqual(sorted(e.code for _, e in erros), ["nota_ja_lancada"] * 3)
        self.assertEqual(MovimentoConta.objects.count(), 1)
        self.assertEqual(NotaFiscalLancada.objects.count(), 1)
