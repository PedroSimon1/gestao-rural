"""Contas manuais (financeiro/manual.py, P08) no PostgreSQL local de teste.

TestCase e TransactionTestCase: rodam só com as variáveis DB_TEST_*
(config/banco_de_teste.py). Documentos fictícios; as classificações DESPESA vêm
da carga inicial e a de RECEITA é criada no setUp (DadosDeServico).
"""

import threading
import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from cadastros.models import Classificacao, Papel, Pessoa, SituacaoDocumental

from .manual import (
    ClassificacaoManual, ContaManual, DetalheMovimento, ParcelaManual, consultar_movimento,
    listar_movimentos, registrar_conta_manual,
)
from .models import AlteracaoNaoPermitida, MovimentoClassificacao, MovimentoConta, ParcelaConta
from .servicos import registrar_movimento
from .test_servicos import DadosDeServico

TEMPO_LIMITE = 30
VENCIMENTOS = (date(2026, 11, 30), date(2026, 12, 30), date(2027, 1, 30))


def parcelas(*valores):
    return tuple(ParcelaManual(VENCIMENTOS[i], Decimal(v)) for i, v in enumerate(valores))


def contagens():
    return (MovimentoConta.objects.count(), MovimentoClassificacao.objects.count(),
            ParcelaConta.objects.count())


class ContaManualBase(DadosDeServico):
    def pagar(self, **campos):
        dados = dict(
            tipo="APAGAR", contraparte_id=self.fornecedor.pk, faturado_id=self.faturado.pk,
            valor_total=Decimal("1000.00"),
            classificacoes=(ClassificacaoManual(self.manutencao.pk, principal=True),),
            parcelas=parcelas("1000.00"), chave_idempotencia=uuid.uuid4(),
        )
        return ContaManual(**{**dados, **campos})

    def receber(self, **campos):
        dados = dict(
            tipo="ARECEBER", contraparte_id=self.cliente.pk, valor_total=Decimal("900.00"),
            classificacoes=(ClassificacaoManual(self.venda.pk, principal=True),),
            parcelas=parcelas("900.00"), chave_idempotencia=uuid.uuid4(),
        )
        return ContaManual(**{**dados, **campos})

    def assert_recusado(self, conta, codigo):
        antes = contagens()
        with self.assertRaises(ValidationError) as contexto:
            registrar_conta_manual(conta)
        self.assertEqual(contexto.exception.code, codigo)
        self.assertEqual(contagens(), antes)


class RegistroManualTests(ContaManualBase, TestCase):
    def test_conta_a_pagar(self):
        detalhe = registrar_conta_manual(self.pagar())

        self.assertIsInstance(detalhe, DetalheMovimento)
        self.assertEqual(
            (detalhe.tipo, detalhe.origem, detalhe.status, detalhe.valor_total),
            ("APAGAR", "MANUAL", "CONFIRMADO", Decimal("1000.00")),
        )
        self.assertEqual((detalhe.contraparte_id, detalhe.contraparte_nome),
                         (self.fornecedor.pk, "Fornecedor Teste"))
        self.assertEqual((detalhe.faturado_id, detalhe.faturado_nome),
                         (self.faturado.pk, "Faturado Teste"))
        movimento = MovimentoConta.objects.get()
        self.assertIsNone(movimento.analise_origem_id)
        self.assertEqual(movimento.origem, "MANUAL")

    def test_conta_a_receber_sem_e_com_faturado(self):
        sem = registrar_conta_manual(self.receber())
        com = registrar_conta_manual(self.receber(faturado_id=self.faturado.pk))

        self.assertEqual((sem.tipo, sem.faturado_id, sem.faturado_nome), ("ARECEBER", None, None))
        self.assertEqual(com.faturado_id, self.faturado.pk)
        self.assertEqual(sem.classificacoes[0].codigo, "VENDA_PRODUCAO")

    def test_varias_classificacoes_e_parcelas_numeradas_pela_ordem(self):
        detalhe = registrar_conta_manual(self.pagar(
            classificacoes=(
                ClassificacaoManual(self.manutencao.pk),
                ClassificacaoManual(self.infraestrutura.pk, principal=True),
            ),
            parcelas=parcelas("300.00", "300.00", "400.00"),
        ))

        self.assertEqual(
            [(c.codigo, c.principal) for c in detalhe.classificacoes],
            [("INFRAESTRUTURA_E_UTILIDADES", True), ("MANUTENCAO_E_OPERACAO", False)],
        )
        self.assertEqual(
            [(p.numero, p.data_vencimento, p.valor, p.status) for p in detalhe.parcelas],
            [(1, VENCIMENTOS[0], Decimal("300.00"), "ATIVA"),
             (2, VENCIMENTOS[1], Decimal("300.00"), "ATIVA"),
             (3, VENCIMENTOS[2], Decimal("400.00"), "ATIVA")],
        )

    def test_mesma_pessoa_fornecedora_e_faturada(self):
        self.fornecedor.atribuir_papel(Papel.FATURADO)
        detalhe = registrar_conta_manual(self.pagar(faturado_id=self.fornecedor.pk))
        self.assertEqual(detalhe.contraparte_id, detalhe.faturado_id)

    def test_aceita_listas_e_geradores(self):
        detalhe = registrar_conta_manual(self.pagar(
            classificacoes=[ClassificacaoManual(self.manutencao.pk, principal=True)],
            parcelas=(p for p in parcelas("500.00", "500.00")),
        ))
        self.assertEqual(len(detalhe.parcelas), 2)


class ClassificacoesManuaisTests(ContaManualBase, TestCase):
    def test_tipo_incompativel(self):
        self.assert_recusado(
            self.pagar(classificacoes=(ClassificacaoManual(self.venda.pk, principal=True),)),
            "classificacao_incompativel",
        )
        self.assert_recusado(
            self.receber(classificacoes=(ClassificacaoManual(self.manutencao.pk, principal=True),)),
            "classificacao_incompativel",
        )

    def test_principal_e_repeticao(self):
        casos = {
            "principal": (ClassificacaoManual(self.manutencao.pk),),
            "classificacao_repetida": (
                ClassificacaoManual(self.manutencao.pk, principal=True),
                ClassificacaoManual(self.manutencao.pk),
            ),
            "sem_classificacao": (),
            "principal_tipo": (ClassificacaoManual(self.manutencao.pk, principal="True"),),
        }
        for codigo, itens in casos.items():
            with self.subTest(codigo):
                self.assert_recusado(self.pagar(classificacoes=itens), codigo)

    def test_inexistente_ou_inativa_nao_e_criada_nem_reativada(self):
        self.assert_recusado(
            self.pagar(classificacoes=(ClassificacaoManual(999_999, principal=True),)),
            "classificacao_inexistente",
        )
        self.manutencao.inativar()
        self.assert_recusado(self.pagar(), "classificacao_inativa")
        self.manutencao.refresh_from_db()
        self.assertFalse(self.manutencao.ativo)
        self.assertEqual(Classificacao.objects.filter(pk=999_999).count(), 0)


class PessoasManuaisTests(ContaManualBase, TestCase):
    def test_papel_errado_ou_ausente(self):
        self.assert_recusado(self.pagar(contraparte_id=self.cliente.pk), "papel_ausente")
        self.assert_recusado(self.receber(contraparte_id=self.fornecedor.pk), "papel_ausente")
        self.assert_recusado(self.pagar(faturado_id=self.fornecedor.pk), "papel_ausente")
        self.assert_recusado(self.receber(faturado_id=self.cliente.pk), "papel_ausente")

    def test_apagar_exige_faturado(self):
        self.assert_recusado(self.pagar(faturado_id=None), "faturado")

    def test_pessoa_inexistente(self):
        self.assert_recusado(self.pagar(contraparte_id=999_999), "pessoa_inexistente")
        self.assert_recusado(self.pagar(faturado_id=999_999), "pessoa_inexistente")

    def test_pessoa_e_papel_inativos_nao_sao_reativados(self):
        self.fornecedor.inativar()
        self.assert_recusado(self.pagar(), "pessoa_inativa")
        self.fornecedor.reativar()
        self.faturado.papeis.get(papel=Papel.FATURADO).inativar()
        self.assert_recusado(self.pagar(), "papel_inativo")
        self.cliente.papeis.get(papel=Papel.CLIENTE).inativar()
        self.assert_recusado(self.receber(), "papel_inativo")
        self.assertFalse(self.faturado.papeis.get(papel=Papel.FATURADO).ativo)

    def test_cadastro_incompleto(self):
        pendente = Pessoa.objects.create(
            razao_social="Fornecedor Pendente", situacao_documental=SituacaoDocumental.INCOMPLETO
        )
        pendente.atribuir_papel(Papel.FORNECEDOR)
        self.assert_recusado(self.pagar(contraparte_id=pendente.pk), "pessoa_incompleta")

    def test_nenhuma_pessoa_ou_papel_criado(self):
        pessoas, papeis = Pessoa.objects.count(), self.cliente.papeis.count()
        self.assert_recusado(self.pagar(contraparte_id=self.cliente.pk), "papel_ausente")
        self.assertEqual((Pessoa.objects.count(), self.cliente.papeis.count()), (pessoas, papeis))


class ValoresManuaisTests(ContaManualBase, TestCase):
    def test_soma_das_parcelas(self):
        self.assert_recusado(self.pagar(parcelas=parcelas("400.00", "500.00")), "parcela_soma")
        self.assert_recusado(self.pagar(parcelas=()), "sem_parcela")

    def test_valores_invalidos(self):
        casos = {
            "valor_tipo": self.pagar(valor_total=1000.0),
            "valor": self.pagar(valor_total=Decimal("0"), parcelas=parcelas("0")),
            "valor_centavos": self.pagar(valor_total=Decimal("1.001")),
            "parcela_valor_centavos": self.pagar(
                valor_total=Decimal("1.00"), parcelas=parcelas("0.995", "0.005")
            ),
            "parcela_vencimento": self.pagar(
                parcelas=(ParcelaManual("2026-11-30", Decimal("1000.00")),)
            ),
            "tipo": self.pagar(tipo="PAGAR"),
        }
        for codigo, conta in casos.items():
            with self.subTest(codigo):
                self.assert_recusado(conta, codigo)

    def test_entrada_mal_formada(self):
        self.assert_recusado(self.pagar(parcelas=(("2026-11-30", "1000.00"),)), "parcela")
        self.assert_recusado(self.pagar(parcelas=None), "parcela")
        self.assert_recusado(self.pagar(classificacoes=(self.manutencao.pk,)), "classificacao")
        for conta in (
            self.pagar(contraparte_id=str(self.fornecedor.pk)),
            self.pagar(contraparte_id=True),
            self.pagar(faturado_id=self.faturado),
            self.pagar(classificacoes=(ClassificacaoManual(None, principal=True),)),
        ):
            with self.subTest(conta=conta), self.assertRaises(TypeError):
                registrar_conta_manual(conta)
        with self.assertRaises(TypeError):
            registrar_conta_manual({"tipo": "APAGAR"})
        with self.assertRaises(TypeError):
            # A chave é obrigatória e só nomeada.
            ContaManual("APAGAR", self.fornecedor.pk, Decimal("1.00"), (), ())
        self.assertEqual(contagens(), (0, 0, 0))


class AtomicidadeManualTests(ContaManualBase, TestCase):
    def test_falha_nas_parcelas_desfaz_tudo(self):
        with mock.patch.object(
            ParcelaConta.objects, "bulk_create", side_effect=IntegrityError("falha")
        ), self.assertRaises(IntegrityError):
            registrar_conta_manual(self.pagar(parcelas=parcelas("500.00", "500.00")))
        self.assertEqual(contagens(), (0, 0, 0))


class ConsultaTests(ContaManualBase, TestCase):
    def setUp(self):
        super().setUp()
        self.p1 = registrar_conta_manual(self.pagar(parcelas=parcelas("600.00", "400.00")))
        self.r1 = registrar_conta_manual(self.receber())
        self.p2 = registrar_conta_manual(self.pagar(
            valor_total=Decimal("50.00"), parcelas=parcelas("50.00"),
            classificacoes=(ClassificacaoManual(self.infraestrutura.pk, principal=True),),
        ))

    def ids(self, pagina):
        return [item.id for item in pagina.itens]

    def test_consultar(self):
        detalhe = consultar_movimento(self.p1.id)
        self.assertEqual(detalhe, self.p1)
        self.assertEqual(len(detalhe.parcelas), 2)

    def test_consultar_inexistente(self):
        with self.assertRaises(ValidationError) as contexto:
            consultar_movimento(999_999)
        self.assertEqual(contexto.exception.code, "movimento_inexistente")
        with self.assertRaises(TypeError):
            consultar_movimento("1")

    def test_listar_mais_recentes_primeiro_com_resumo(self):
        pagina = listar_movimentos()
        self.assertEqual(self.ids(pagina), [self.p2.id, self.r1.id, self.p1.id])
        self.assertEqual((pagina.pagina, pagina.total_paginas, pagina.total), (1, 1, 3))
        resumo = pagina.itens[2]
        self.assertEqual((resumo.quantidade_parcelas, resumo.proximo_vencimento),
                         (2, VENCIMENTOS[0]))
        self.assertEqual((resumo.contraparte_nome, resumo.faturado_nome),
                         ("Fornecedor Teste", "Faturado Teste"))

    def test_filtros(self):
        casos = (
            ({"tipo": "APAGAR"}, [self.p2.id, self.p1.id]),
            ({"tipo": "ARECEBER"}, [self.r1.id]),
            ({"origem": "NOTA_FISCAL"}, []),
            ({"origem": "MANUAL", "status": "CONFIRMADO"}, [self.p2.id, self.r1.id, self.p1.id]),
            ({"status": "CANCELADO"}, []),
            ({"contraparte_id": self.cliente.pk}, [self.r1.id]),
            ({"classificacao_id": self.manutencao.pk}, [self.p1.id]),
            ({"tipo": "APAGAR", "classificacao_id": self.venda.pk}, []),
        )
        for filtros, esperado in casos:
            with self.subTest(filtros=filtros):
                self.assertEqual(self.ids(listar_movimentos(**filtros)), esperado)

    def test_resumo_conta_so_parcelas_ativas(self):
        # Ainda não há operação de cancelamento: o estado é montado por SQL,
        # como em test_parcelas.py (o gatilho aceita parcela cancelada em
        # movimento CANCELADO).
        with connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s",
                           [self.p1.id])
            cursor.execute(
                "UPDATE parcelas_contas SET status = 'CANCELADA' WHERE movimento_id = %s "
                "AND numero = 1", [self.p1.id],
            )

        resumo = listar_movimentos(status="CANCELADO").itens[0]
        detalhe = consultar_movimento(self.p1.id)

        self.assertEqual((resumo.id, resumo.quantidade_parcelas, resumo.proximo_vencimento),
                         (self.p1.id, 1, VENCIMENTOS[1]))
        self.assertEqual([p.status for p in detalhe.parcelas], ["CANCELADA", "ATIVA"])

    def test_paginacao(self):
        primeira = listar_movimentos(por_pagina=2)
        segunda = listar_movimentos(por_pagina=2, pagina=2)
        alem = listar_movimentos(por_pagina=2, pagina=99)
        self.assertEqual((self.ids(primeira), primeira.total_paginas), ([self.p2.id, self.r1.id], 2))
        self.assertEqual(self.ids(segunda), [self.p1.id])
        self.assertEqual(alem.pagina, 2)

    def test_filtros_invalidos(self):
        for filtros in ({"tipo": "PAGAR"}, {"origem": "X"}, {"status": "ABERTO"},
                        {"por_pagina": 0}, {"por_pagina": 101}):
            with self.subTest(filtros=filtros), self.assertRaises(ValueError):
                listar_movimentos(**filtros)
        with self.assertRaises(TypeError):
            listar_movimentos(contraparte_id="1")

    def test_consultas_constantes(self):
        for _ in range(5):
            registrar_conta_manual(self.pagar(parcelas=parcelas("500.00", "500.00")))
        with CaptureQueriesContext(connection) as consultas:
            listar_movimentos()
        # Uma contagem e uma página, para qualquer quantidade de movimentos.
        self.assertEqual(len(consultas), 2)

    def test_listagem_nao_grava(self):
        antes = contagens()
        with CaptureQueriesContext(connection) as consultas:
            listar_movimentos(tipo="APAGAR")
            consultar_movimento(self.p1.id)
        self.assertFalse(any(
            c["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            for c in consultas.captured_queries
        ))
        self.assertEqual(contagens(), antes)


class RepeticaoTests(ContaManualBase, TestCase):
    """Idempotência pela chave da solicitação (seção 15.1.20)."""

    def test_mesma_chave_e_mesmos_dados_devolve_o_existente(self):
        conta = self.pagar(parcelas=parcelas("500.00", "500.00"))
        primeiro = registrar_conta_manual(conta)
        segundo = registrar_conta_manual(conta)

        self.assertEqual(primeiro, segundo)
        self.assertEqual(contagens(), (1, 1, 2))
        self.assertEqual(MovimentoConta.objects.get().chave_idempotencia, conta.chave_idempotencia)

    def test_mesma_chave_com_outros_dados_e_conflito(self):
        conta = self.pagar(parcelas=parcelas("500.00", "500.00"))
        registrar_conta_manual(conta)
        self.cliente.atribuir_papel(Papel.FORNECEDOR)
        alteracoes = {
            "valor e parcelas": dict(valor_total=Decimal("900.00"), parcelas=parcelas("900.00")),
            "parcelas": dict(parcelas=parcelas("400.00", "600.00")),
            "vencimento": dict(parcelas=(ParcelaManual(VENCIMENTOS[2], Decimal("500.00")),
                                         ParcelaManual(VENCIMENTOS[1], Decimal("500.00")))),
            "contraparte": dict(contraparte_id=self.cliente.pk),
            "classificacao": dict(classificacoes=(
                ClassificacaoManual(self.infraestrutura.pk, principal=True),)),
            "principal": dict(classificacoes=(
                ClassificacaoManual(self.manutencao.pk),
                ClassificacaoManual(self.infraestrutura.pk, principal=True),
            )),
        }
        for nome, campos in alteracoes.items():
            with self.subTest(nome):
                self.assert_recusado(replace(conta, **campos), "solicitacao_ja_registrada")
        outro_tipo = self.receber(chave_idempotencia=conta.chave_idempotencia)
        self.assert_recusado(outro_tipo, "solicitacao_ja_registrada")
        self.assertEqual(contagens(), (1, 1, 2))

    def test_chaves_diferentes_com_dados_identicos_gravam_duas_contas(self):
        primeiro = registrar_conta_manual(self.pagar())
        segundo = registrar_conta_manual(self.pagar())

        self.assertNotEqual(primeiro.id, segundo.id)
        self.assertEqual(
            (primeiro.contraparte_id, primeiro.valor_total, primeiro.parcelas),
            (segundo.contraparte_id, segundo.valor_total, segundo.parcelas),
        )
        self.assertEqual(contagens(), (2, 2, 2))

    def test_chave_ausente_ou_invalida(self):
        for chave in (None, str(uuid.uuid4()), uuid.uuid4().int):
            with self.subTest(chave=chave):
                self.assert_recusado(self.pagar(chave_idempotencia=chave), "chave_idempotencia")

    def test_recusa_nao_consome_a_chave(self):
        conta = self.pagar(contraparte_id=self.cliente.pk)
        self.assert_recusado(conta, "papel_ausente")

        detalhe = registrar_conta_manual(replace(conta, contraparte_id=self.fornecedor.pk))

        self.assertEqual(MovimentoConta.objects.get(pk=detalhe.id).chave_idempotencia,
                         conta.chave_idempotencia)

    def test_chave_independente_da_analise_de_origem(self):
        # Mesmo UUID numa nota e numa conta manual: colunas e significados distintos.
        valor = uuid.uuid4()
        nota, _ = registrar_movimento(self.apagar(analise_origem_id=valor))
        manual = registrar_conta_manual(self.pagar(chave_idempotencia=valor))

        self.assertNotEqual(nota.pk, manual.id)
        nota.refresh_from_db()
        self.assertEqual((nota.analise_origem_id, nota.chave_idempotencia), (valor, None))
        gravado = MovimentoConta.objects.get(pk=manual.id)
        self.assertEqual((gravado.analise_origem_id, gravado.chave_idempotencia), (None, valor))

    def test_movimento_cancelado_nao_e_devolvido(self):
        conta = self.pagar()
        detalhe = registrar_conta_manual(conta)
        with connection.cursor() as cursor:
            # Parcelas continuam ATIVAS: só o status do movimento difere.
            cursor.execute("UPDATE movimentos_contas SET status = 'CANCELADO' WHERE id = %s",
                           [detalhe.id])

        self.assert_recusado(conta, "solicitacao_ja_registrada")


class ChaveNoServicoTests(ContaManualBase, TestCase):
    """registrar_movimento(): a chave é opcional e só vale para a origem MANUAL."""

    def test_nota_fiscal_continua_sem_chave(self):
        movimento, criado = registrar_movimento(self.apagar(analise_origem_id=uuid.uuid4()))
        self.assertTrue(criado)
        self.assertIsNone(movimento.chave_idempotencia)

    def test_manual_sem_chave_continua_aceito_no_servico(self):
        movimento, _ = registrar_movimento(self.areceber())
        self.assertEqual((movimento.origem, movimento.chave_idempotencia), ("MANUAL", None))

    def test_chave_recusada_fora_do_manual_ou_com_analise(self):
        chave = uuid.uuid4()
        casos = (
            self.apagar(chave_idempotencia=chave),
            self.areceber(chave_idempotencia=chave, analise_origem_id=uuid.uuid4()),
            self.areceber(chave_idempotencia=str(chave)),
        )
        for dados in casos:
            with self.subTest(dados=dados), self.assertRaises(ValidationError) as contexto:
                registrar_movimento(dados)
            self.assertEqual(contexto.exception.code, "chave_idempotencia")
        self.assertEqual(contagens(), (0, 0, 0))

    def test_chave_imutavel(self):
        detalhe = registrar_conta_manual(self.pagar())
        movimento = MovimentoConta.objects.get(pk=detalhe.id)
        movimento.chave_idempotencia = uuid.uuid4()
        with self.assertRaises(AlteracaoNaoPermitida):
            movimento.save()
        with self.assertRaises(AlteracaoNaoPermitida):
            MovimentoConta.objects.filter(pk=detalhe.id).update(chave_idempotencia=None)

    def test_banco_recusa_chave_em_nota_fiscal(self):
        movimento, _ = registrar_movimento(self.apagar())
        with self.assertRaises(IntegrityError) as contexto, transaction.atomic(), \
                connection.cursor() as cursor:
            cursor.execute("UPDATE movimentos_contas SET chave_idempotencia = %s WHERE id = %s",
                           [uuid.uuid4(), movimento.pk])
        self.assertIn("movimento_chave_idempotencia_so_manual", str(contexto.exception))


class MigrationDaChaveTests(TestCase):
    def test_coluna_nula_com_indice_unico_e_check(self):
        with connection.cursor() as cursor:
            colunas = {c.name: c for c in connection.introspection.get_table_description(
                cursor, "movimentos_contas")}
            constraints = connection.introspection.get_constraints(cursor, "movimentos_contas")

        self.assertTrue(colunas["chave_idempotencia"].null_ok)
        self.assertTrue(any(c["unique"] and c["columns"] == ["chave_idempotencia"]
                            for c in constraints.values()))
        self.assertTrue(constraints["movimento_chave_idempotencia_so_manual"]["check"])


class ConcorrenciaManualTests(ContaManualBase, TransactionTestCase):
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
            threading.Thread(target=executar, args=(i, chamada), daemon=True)
            for i, chamada in enumerate(chamadas)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TEMPO_LIMITE)
        self.assertEqual([t.name for t in threads if t.is_alive()], [], "Thread travada.")
        return resultados, erros

    def test_papeis_cruzados_sem_deadlock(self):
        # A paga a B e B paga a A ao mesmo tempo: o bloqueio ordenado evita deadlock.
        self.fornecedor.atribuir_papel(Papel.FATURADO)
        self.faturado.atribuir_papel(Papel.FORNECEDOR)
        ida = self.pagar()
        volta = self.pagar(contraparte_id=self.faturado.pk, faturado_id=self.fornecedor.pk)

        # Uma chave por solicitação: são seis contas, não repetições.
        contas = [replace(conta, chave_idempotencia=uuid.uuid4()) for conta in (ida, volta) * 3]

        resultados, erros = self.em_paralelo(
            *[lambda conta=conta: registrar_conta_manual(conta) for conta in contas]
        )

        self.assertEqual(erros, [])
        self.assertEqual(len({r.id for r in resultados}), 6)
        self.assertEqual(contagens(), (6, 6, 6))

    def test_mesma_chave_ao_mesmo_tempo_grava_uma_vez(self):
        conta = self.pagar(parcelas=parcelas("300.00", "300.00", "400.00"))

        resultados, erros = self.em_paralelo(*[lambda: registrar_conta_manual(conta)] * 4)

        self.assertEqual(erros, [])
        self.assertEqual(len({r.id for r in resultados}), 1)
        self.assertEqual(contagens(), (1, 1, 3))

    def test_mesma_chave_com_dados_diferentes_ao_mesmo_tempo_grava_so_um(self):
        conta = self.pagar(parcelas=parcelas("500.00", "500.00"))
        pedidos = (conta, replace(conta, parcelas=parcelas("400.00", "600.00")))

        resultados, erros = self.em_paralelo(
            *[lambda pedido=pedido: registrar_conta_manual(pedido) for pedido in pedidos]
        )

        self.assertEqual(len([r for r in resultados if r is not None]), 1)
        self.assertEqual([e.code for _, e in erros], ["solicitacao_ja_registrada"])
        self.assertEqual(contagens(), (1, 1, 2))

    def test_chaves_diferentes_ao_mesmo_tempo_gravam_todas(self):
        contas = [self.pagar() for _ in range(4)]

        resultados, erros = self.em_paralelo(
            *[lambda conta=conta: registrar_conta_manual(conta) for conta in contas]
        )

        self.assertEqual(erros, [])
        self.assertEqual(len({r.id for r in resultados}), 4)
        self.assertEqual(contagens(), (4, 4, 4))

    def test_inativacao_concorrente_nao_deixa_movimento_com_papel_inativo(self):
        papel = self.fornecedor.papeis.get(papel=Papel.FORNECEDOR)

        def inativar():
            papel.inativar()

        resultados, erros = self.em_paralelo(lambda: registrar_conta_manual(self.pagar()), inativar)

        papel.refresh_from_db()
        self.assertFalse(papel.ativo)
        if resultados[0] is not None:
            # O lançamento bloqueou o papel primeiro: gravou com o papel ainda ativo.
            self.assertEqual(erros, [])
            self.assertEqual(contagens()[0], 1)
        else:
            self.assertEqual([(i, e.code) for i, e in erros], [(0, "papel_inativo")])
            self.assertEqual(contagens(), (0, 0, 0))
