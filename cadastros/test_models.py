"""Pessoa e PapelPessoa (GR-35) no PostgreSQL local de teste.

TestCase: rodam só com as variáveis DB_TEST_* (config/banco_de_teste.py).
Documentos fictícios, com DV calculado; nenhum dado real.
"""

import json
from unittest import mock

from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from .models import (
    ExclusaoNaoPermitida, Papel, PapelPessoa, Pessoa, PessoaQuerySet, SituacaoDocumental,
    Status,
)

CPF = "12345678909"
CPF_FORMATADO = "123.456.789-09"
CNPJ = "11222333000181"
CNPJ_FORMATADO = "11.222.333/0001-81"
# Exemplo de CNPJ alfanumérico da Receita Federal (IN RFB 2.229/2024).
CNPJ_ALFANUMERICO = "12ABC34501DE35"
CPF_DV_INVALIDO = "12345678900"
CNPJ_DV_INVALIDO = "11222333000182"


def criar_pessoa(documento=CPF, razao_social="Pessoa Teste"):
    return Pessoa.objects.create(documento=documento, razao_social=razao_social)


def criar_incompleta(razao_social="Pessoa Sem Documento"):
    return Pessoa.objects.create(
        razao_social=razao_social, situacao_documental=SituacaoDocumental.INCOMPLETO
    )


class NormalizacaoTests(TestCase):
    def test_cpf_formatado_e_normalizado(self):
        pessoa = criar_pessoa(CPF_FORMATADO, "  Maria   da  Silva ")
        pessoa.refresh_from_db()

        self.assertEqual(pessoa.documento, CPF)
        self.assertEqual(pessoa.tipo_documento, "CPF")
        self.assertEqual(pessoa.razao_social, "Maria da Silva")
        self.assertEqual(pessoa.status, Status.ATIVO)

    def test_cnpj_numerico_formatado_e_normalizado(self):
        pessoa = criar_pessoa(CNPJ_FORMATADO, "Empresa Teste Ltda")
        pessoa.refresh_from_db()

        self.assertEqual(pessoa.documento, CNPJ)
        self.assertEqual(pessoa.tipo_documento, "CNPJ")

    def test_cnpj_alfanumerico_em_minusculas_e_normalizado(self):
        pessoa = criar_pessoa("12.abc.345/01de-35", "Empresa Alfanumérica")
        pessoa.refresh_from_db()

        self.assertEqual(pessoa.documento, CNPJ_ALFANUMERICO)
        self.assertEqual(pessoa.tipo_documento, "CNPJ")

    def test_full_clean_aceita_documento_formatado(self):
        pessoa = Pessoa(documento=CNPJ_FORMATADO, razao_social="Empresa Teste")

        pessoa.full_clean()

        self.assertEqual(pessoa.documento, CNPJ)

    def test_busca_por_documento_formatado(self):
        pessoa = criar_pessoa(CNPJ)

        self.assertEqual(list(Pessoa.objects.por_documento(CNPJ_FORMATADO)), [pessoa])
        self.assertEqual(list(Pessoa.objects.por_documento("12.abc.345/01de-35")), [])


class DocumentoInvalidoTests(TestCase):
    def test_documentos_invalidos_sao_recusados_e_nada_e_gravado(self):
        for documento in (
            CPF_DV_INVALIDO, CNPJ_DV_INVALIDO, "11111111111", "00000000000000",
            "1234567890", "123456789012345", "12ABC34501DE3X", "123.456.789_09", "",
        ):
            with self.subTest(documento=documento):
                with self.assertRaises(ValidationError) as contexto:
                    criar_pessoa(documento)
                self.assertIn("documento", contexto.exception.message_dict)
        self.assertEqual(Pessoa.objects.count(), 0)

    def test_full_clean_informa_o_erro_no_documento(self):
        pessoa = Pessoa(documento=CPF_DV_INVALIDO, razao_social="Pessoa Teste")

        with self.assertRaises(ValidationError) as contexto:
            pessoa.full_clean()

        self.assertEqual(contexto.exception.message_dict["documento"], ["CPF inválido."])

    def test_razao_social_em_branco_recusada(self):
        with self.assertRaises(ValidationError) as contexto:
            Pessoa(documento=CPF, razao_social="   ").full_clean()
        self.assertIn("razao_social", contexto.exception.message_dict)

        pessoa = criar_pessoa()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pessoa.objects.filter(pk=pessoa.pk).update(razao_social=" ")

    def test_banco_recusa_documento_fora_do_formato(self):
        pessoa = criar_pessoa()

        for alteracao in ({"documento": CPF_FORMATADO}, {"documento": "12345678901234"},
                          {"tipo_documento": "CNPJ"}, {"documento": "12abc34501de35"},
                          {"documento": "12ÇBC34501DE35"}):
            with self.subTest(**alteracao):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Pessoa.objects.filter(pk=pessoa.pk).update(**alteracao)


class AtualizacaoDoDocumentoTests(TestCase):
    def test_trocar_cpf_por_cnpj_atualiza_o_tipo(self):
        pessoa = criar_pessoa(CPF)
        pessoa.documento = CNPJ_FORMATADO

        pessoa.save(update_fields=["documento"])

        pessoa.refresh_from_db()
        self.assertEqual((pessoa.documento, pessoa.tipo_documento), (CNPJ, "CNPJ"))

    def test_str_mascara_o_cpf_e_mostra_o_cnpj(self):
        self.assertEqual(str(criar_pessoa(CPF, "Maria")), "Maria (CPF *******8909)")
        self.assertEqual(str(criar_pessoa(CNPJ, "Empresa")), f"Empresa (CNPJ {CNPJ})")


class UnicidadeTests(TestCase):
    def test_mesmo_cpf_com_outra_formatacao_e_recusado(self):
        criar_pessoa(CPF)

        with self.assertRaises(IntegrityError), transaction.atomic():
            criar_pessoa(CPF_FORMATADO, "Outra Pessoa")
        self.assertEqual(Pessoa.objects.count(), 1)

    def test_mesmo_cnpj_alfanumerico_em_minusculas_e_recusado(self):
        criar_pessoa(CNPJ_ALFANUMERICO)

        with self.assertRaises(IntegrityError), transaction.atomic():
            criar_pessoa("12abc34501de35", "Outra Empresa")

    def test_full_clean_informa_documento_ja_cadastrado(self):
        criar_pessoa(CNPJ)

        with self.assertRaises(ValidationError) as contexto:
            Pessoa(documento=CNPJ_FORMATADO, razao_social="Outra").full_clean()

        self.assertIn("documento", contexto.exception.message_dict)


class PapeisTests(TestCase):
    def test_uma_pessoa_com_varios_papeis_sem_duplicar_a_pessoa(self):
        pessoa = criar_pessoa(CNPJ)

        for papel in (Papel.FORNECEDOR, Papel.FATURADO, Papel.CLIENTE):
            _, criado = pessoa.atribuir_papel(papel)
            self.assertTrue(criado)

        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(
            sorted(pessoa.papeis.values_list("papel", flat=True)),
            ["CLIENTE", "FATURADO", "FORNECEDOR"],
        )

    def test_atribuir_papel_existente_nao_duplica_nem_muda_o_status(self):
        pessoa = criar_pessoa()
        papel, _ = pessoa.atribuir_papel(Papel.FORNECEDOR)
        papel.inativar()

        mesmo, criado = pessoa.atribuir_papel(Papel.FORNECEDOR)

        self.assertFalse(criado)
        self.assertEqual(mesmo.pk, papel.pk)
        self.assertEqual(mesmo.status, Status.INATIVO)
        self.assertEqual(pessoa.papeis.count(), 1)

    def test_banco_recusa_papel_duplicado_na_mesma_pessoa(self):
        pessoa = criar_pessoa()
        PapelPessoa.objects.create(pessoa=pessoa, papel=Papel.FATURADO)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PapelPessoa.objects.create(pessoa=pessoa, papel=Papel.FATURADO)

    def test_full_clean_informa_papel_duplicado(self):
        pessoa = criar_pessoa()
        pessoa.atribuir_papel(Papel.CLIENTE)

        with self.assertRaisesMessage(ValidationError, "Esta pessoa já possui este papel."):
            PapelPessoa(pessoa=pessoa, papel=Papel.CLIENTE).full_clean()

    def test_mesmo_papel_em_pessoas_diferentes(self):
        criar_pessoa(CPF).atribuir_papel(Papel.FATURADO)
        criar_pessoa(CNPJ).atribuir_papel(Papel.FATURADO)

        self.assertEqual(PapelPessoa.objects.filter(papel=Papel.FATURADO).count(), 2)

    def test_banco_recusa_papel_e_status_desconhecidos(self):
        pessoa = criar_pessoa()

        # Valores que cabem na coluna, para chegar à CHECK (e não ao limite de tamanho).
        for campos in ({"papel": "SOCIO"}, {"papel": Papel.CLIENTE, "status": "PAUSADO"}):
            with self.subTest(**campos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    PapelPessoa.objects.create(pessoa=pessoa, **campos)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pessoa.objects.filter(pk=pessoa.pk).update(status="PAUSADO")


class InativacaoTests(TestCase):
    def setUp(self):
        self.pessoa = criar_pessoa(CNPJ)
        self.fornecedor, _ = self.pessoa.atribuir_papel(Papel.FORNECEDOR)
        self.faturado, _ = self.pessoa.atribuir_papel(Papel.FATURADO)

    def recarregar(self):
        for registro in (self.pessoa, self.fornecedor, self.faturado):
            registro.refresh_from_db()

    def test_inativar_e_reativar_pessoa_sem_mudar_os_papeis(self):
        self.pessoa.inativar()
        self.recarregar()

        self.assertEqual(self.pessoa.status, Status.INATIVO)
        self.assertEqual({self.fornecedor.status, self.faturado.status}, {Status.ATIVO})
        self.assertEqual(list(PapelPessoa.objects.vigentes()), [])
        self.assertEqual(list(Pessoa.objects.ativos()), [])

        self.pessoa.reativar()
        self.recarregar()

        self.assertTrue(self.pessoa.ativo)
        self.assertEqual(PapelPessoa.objects.vigentes().count(), 2)

    def test_inativar_e_reativar_papel_sem_mudar_a_pessoa_nem_outros_papeis(self):
        self.fornecedor.inativar()
        self.recarregar()

        self.assertTrue(self.pessoa.ativo)
        self.assertEqual(self.fornecedor.status, Status.INATIVO)
        self.assertTrue(self.faturado.ativo)
        self.assertEqual(list(PapelPessoa.objects.vigentes()), [self.faturado])

        self.fornecedor.reativar()
        self.recarregar()

        self.assertTrue(self.fornecedor.ativo)
        self.assertEqual(PapelPessoa.objects.vigentes().count(), 2)

    def test_inativacao_preserva_o_registro_e_os_vinculos(self):
        ids = (self.pessoa.pk, self.fornecedor.pk, self.faturado.pk)

        self.fornecedor.inativar()
        self.pessoa.inativar()
        self.pessoa.reativar()
        self.fornecedor.reativar()

        self.assertEqual(Pessoa.objects.get(pk=ids[0]).documento, CNPJ)
        self.assertEqual(
            set(PapelPessoa.objects.filter(pessoa_id=ids[0]).values_list("pk", flat=True)),
            set(ids[1:]),
        )

    def test_inativar_duas_vezes_nao_falha(self):
        self.pessoa.inativar()
        self.pessoa.inativar()

        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.status, Status.INATIVO)


class ExclusaoTests(TestCase):
    def test_pessoa_e_papel_nao_podem_ser_excluidos(self):
        pessoa = criar_pessoa()
        papel, _ = pessoa.atribuir_papel(Papel.CLIENTE)

        for operacao in (pessoa.delete, papel.delete, Pessoa.objects.all().delete,
                         PapelPessoa.objects.all().delete):
            with self.subTest(operacao=operacao):
                with self.assertRaises(ExclusaoNaoPermitida):
                    operacao()
        self.assertEqual((Pessoa.objects.count(), PapelPessoa.objects.count()), (1, 1))

    def test_banco_impede_excluir_pessoa_com_papeis(self):
        pessoa = criar_pessoa()
        pessoa.atribuir_papel(Papel.FORNECEDOR)

        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM pessoas WHERE id = %s", [pessoa.pk])
            # A FK é DEFERRABLE INITIALLY DEFERRED: a checagem vem no commit.
            connection.check_constraints()

    def test_banco_recusa_papel_sem_pessoa(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PapelPessoa.objects.create(pessoa_id=999999, papel=Papel.CLIENTE)
            connection.check_constraints()


class FixturesDeTesteTests(TestCase):
    """Documentos com DV inválido entram só por fixtures controladas (loaddata)."""

    def carregar(self, documento):
        dados = [{"model": "cadastros.pessoa", "pk": 1, "fields": {
            "tipo_documento": "CPF", "documento": documento, "razao_social": "Pessoa de QA",
            "status": "ATIVO", "criado_em": "2026-10-26T00:00:00Z",
            "atualizado_em": "2026-10-26T00:00:00Z",
        }}]
        for objeto in serializers.deserialize("json", json.dumps(dados)):
            objeto.save()
        return Pessoa.objects.get(pk=1)

    def test_fixture_aceita_dv_invalido_mas_o_save_normal_recusa(self):
        pessoa = self.carregar(CPF_DV_INVALIDO)

        self.assertEqual(pessoa.documento, CPF_DV_INVALIDO)
        # Inativar e reativar não revalidam o documento.
        pessoa.inativar()
        pessoa.reativar()
        with self.assertRaises(ValidationError):
            pessoa.save()

    def test_fixture_nao_contorna_o_formato_exigido_pelo_banco(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.carregar(CPF_FORMATADO)


class CadastroIncompletoTests(TestCase):
    """C-02: sem CPF/CNPJ válido, cadastro incompleto explícito, regularizado depois."""

    def test_cadastro_incompleto_explicito_sem_documento(self):
        pessoa = criar_incompleta()
        pessoa.refresh_from_db()

        self.assertIsNone(pessoa.documento)
        self.assertIsNone(pessoa.tipo_documento)
        self.assertFalse(pessoa.documentacao_completa)
        # Situação documental e status cadastral são independentes.
        self.assertEqual(pessoa.status, Status.ATIVO)
        self.assertEqual(list(Pessoa.objects.incompletas()), [pessoa])

    def test_sem_documento_e_sem_marcacao_explicita_e_recusado(self):
        for documento in (None, "", "   "):
            with self.subTest(documento=documento):
                with self.assertRaises(ValidationError) as contexto:
                    criar_pessoa(documento)
                self.assertIn("documento", contexto.exception.message_dict)
        self.assertEqual(Pessoa.objects.count(), 0)

    def test_incompleto_nao_guarda_documento_invalido_nem_valido(self):
        for documento in (CPF_DV_INVALIDO, CNPJ):
            with self.subTest(documento=documento):
                with self.assertRaises(ValidationError):
                    Pessoa.objects.create(
                        documento=documento, razao_social="Pessoa Teste",
                        situacao_documental=SituacaoDocumental.INCOMPLETO,
                    )
        self.assertEqual(Pessoa.objects.count(), 0)

    def test_varios_incompletos_coexistem_sem_violar_a_unicidade(self):
        criar_incompleta("Primeira")
        criar_incompleta("Segunda")

        self.assertEqual(Pessoa.objects.incompletas().count(), 2)
        self.assertEqual(list(Pessoa.objects.por_documento("")), [])

    def test_full_clean_do_incompleto_e_do_completo_sem_documento(self):
        Pessoa(razao_social="Sem Documento",
               situacao_documental=SituacaoDocumental.INCOMPLETO).full_clean()

        with self.assertRaises(ValidationError) as contexto:
            Pessoa(razao_social="Sem Documento").full_clean()
        self.assertIn("documento", contexto.exception.message_dict)

    def test_regularizar_preserva_o_registro_e_os_vinculos(self):
        pessoa = criar_incompleta()
        papel, _ = pessoa.atribuir_papel(Papel.FORNECEDOR)

        pessoa.regularizar(CNPJ_FORMATADO)
        pessoa.refresh_from_db()

        self.assertEqual((pessoa.documento, pessoa.tipo_documento), (CNPJ, "CNPJ"))
        self.assertTrue(pessoa.documentacao_completa)
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(list(pessoa.papeis.all()), [papel])
        self.assertEqual(list(Pessoa.objects.incompletas()), [])

    def test_regularizar_com_cnpj_alfanumerico(self):
        pessoa = criar_incompleta()

        pessoa.regularizar("12.abc.345/01de-35")

        pessoa.refresh_from_db()
        self.assertEqual(pessoa.documento, CNPJ_ALFANUMERICO)

    def assert_nada_mudou(self, pessoa):
        self.assertIsNone(pessoa.documento)
        self.assertFalse(pessoa.documentacao_completa)
        pessoa.refresh_from_db()
        self.assertIsNone(pessoa.documento)
        self.assertEqual(pessoa.situacao_documental, SituacaoDocumental.INCOMPLETO)

    def test_regularizar_com_documento_invalido_nao_muda_nada(self):
        pessoa = criar_incompleta()

        for documento in (CPF_DV_INVALIDO, "", "123"):
            with self.subTest(documento=documento):
                with self.assertRaises(ValidationError) as contexto:
                    pessoa.regularizar(documento)
                self.assertIn("documento", contexto.exception.message_dict)
                self.assert_nada_mudou(pessoa)

    def test_regularizar_com_documento_de_outra_pessoa_e_recusado(self):
        criar_pessoa(CPF, "Dono do CPF")
        pessoa = criar_incompleta()

        with self.assertRaisesMessage(ValidationError, "Já existe uma pessoa com este documento."):
            pessoa.regularizar(CPF_FORMATADO)
        self.assert_nada_mudou(pessoa)

    def test_regularizar_em_concorrencia_e_decidido_pelo_indice_unico(self):
        criar_pessoa(CPF, "Cadastro concorrente")
        pessoa = criar_incompleta()

        # Simula o outro cadastro chegando entre a verificação e a gravação.
        with mock.patch.object(PessoaQuerySet, "exists", return_value=False):
            with self.assertRaisesMessage(ValidationError, "Já existe uma pessoa com este documento."):
                pessoa.regularizar(CPF)
        self.assert_nada_mudou(pessoa)

    def test_regularizar_restaura_a_memoria_em_qualquer_falha(self):
        pessoa = criar_incompleta()
        atualizado_em = pessoa.atualizado_em

        with mock.patch.object(Pessoa, "save_base", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                pessoa.regularizar(CPF)

        self.assertEqual(pessoa.atualizado_em, atualizado_em)
        self.assert_nada_mudou(pessoa)

    def test_regularizar_exige_pessoa_salva(self):
        with self.assertRaises(ValueError):
            Pessoa(razao_social="Nova",
                   situacao_documental=SituacaoDocumental.INCOMPLETO).regularizar(CPF)

    def test_update_fields_parcial_grava_documento_e_situacao_juntos(self):
        pessoa = criar_incompleta()
        pessoa.documento = CNPJ
        pessoa.situacao_documental = SituacaoDocumental.COMPLETO

        pessoa.save(update_fields=["situacao_documental"])

        pessoa.refresh_from_db()
        self.assertEqual((pessoa.documento, pessoa.tipo_documento, pessoa.situacao_documental),
                         (CNPJ, "CNPJ", SituacaoDocumental.COMPLETO))

    def test_regularizar_cadastro_completo_e_recusado(self):
        pessoa = criar_pessoa(CPF)

        with self.assertRaises(ValidationError):
            pessoa.regularizar(CNPJ)
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.documento, CPF)

    def test_banco_exige_coerencia_entre_documento_e_situacao(self):
        completa = criar_pessoa(CPF)
        incompleta = criar_incompleta()

        for pk, campos in (
            (completa.pk, {"documento": None, "tipo_documento": None}),
            (completa.pk, {"documento": None}),
            (completa.pk, {"situacao_documental": SituacaoDocumental.INCOMPLETO}),
            (incompleta.pk, {"documento": CNPJ, "tipo_documento": "CNPJ"}),
            (incompleta.pk, {"situacao_documental": SituacaoDocumental.COMPLETO}),
            (incompleta.pk, {"situacao_documental": "PARCIAL"}),
        ):
            with self.subTest(pk=pk, **campos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Pessoa.objects.filter(pk=pk).update(**campos)

    def test_incompleto_tem_papeis_e_status_independentes(self):
        pessoa = criar_incompleta()
        pessoa.atribuir_papel(Papel.FORNECEDOR)
        pessoa.atribuir_papel(Papel.CLIENTE)

        pessoa.inativar()
        pessoa.refresh_from_db()

        self.assertEqual(pessoa.situacao_documental, SituacaoDocumental.INCOMPLETO)
        self.assertEqual(pessoa.status, Status.INATIVO)
        self.assertEqual(pessoa.papeis.count(), 2)

    def test_str_do_incompleto(self):
        self.assertEqual(str(criar_incompleta("Maria")), "Maria (documento pendente)")


class ReativacaoExplicitaTests(TestCase):
    """T-05: o inativo é identificado e só volta a ATIVO por reativar()."""

    def setUp(self):
        self.pessoa = criar_pessoa(CNPJ)
        self.fornecedor, _ = self.pessoa.atribuir_papel(Papel.FORNECEDOR)
        self.fornecedor.inativar()
        self.pessoa.inativar()

    def test_busca_encontra_e_identifica_o_inativo(self):
        encontrada = Pessoa.objects.por_documento(CNPJ_FORMATADO).get()

        self.assertEqual(encontrada.pk, self.pessoa.pk)
        self.assertEqual(encontrada.status, Status.INATIVO)
        self.assertEqual(encontrada.papeis.get().status, Status.INATIVO)

    def test_nenhuma_operacao_comum_reativa_automaticamente(self):
        self.pessoa.atribuir_papel(Papel.FORNECEDOR)
        novo, criado = self.pessoa.atribuir_papel(Papel.FATURADO)
        self.pessoa.razao_social = "Nome Corrigido"
        self.pessoa.save()

        self.pessoa.refresh_from_db()
        self.fornecedor.refresh_from_db()
        self.assertEqual(self.pessoa.status, Status.INATIVO)
        self.assertEqual(self.fornecedor.status, Status.INATIVO)
        self.assertTrue(criado)
        self.assertEqual(novo.pessoa.status, Status.INATIVO)
        self.assertEqual(PapelPessoa.objects.vigentes().count(), 0)

    def test_regularizar_nao_reativa(self):
        incompleta = criar_incompleta()
        incompleta.inativar()

        incompleta.regularizar(CPF)

        incompleta.refresh_from_db()
        self.assertEqual(incompleta.status, Status.INATIVO)

    def test_reativacao_explicita_preserva_o_mesmo_registro(self):
        ids = (self.pessoa.pk, self.fornecedor.pk)

        self.pessoa.reativar()
        self.fornecedor.reativar()

        self.assertEqual((Pessoa.objects.get().pk, PapelPessoa.objects.get().pk), ids)
        self.assertEqual(list(PapelPessoa.objects.vigentes()), [self.fornecedor])

    def test_documento_unico_impede_duplicar_para_contornar_a_inativacao(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            criar_pessoa(CNPJ_FORMATADO, "Mesma Empresa")


class MigrationTests(TestCase):
    def test_tabelas_e_constraints_criadas_pela_migration(self):
        with connection.cursor() as cursor:
            tabelas = connection.introspection.table_names(cursor)
            pessoas = connection.introspection.get_constraints(cursor, "pessoas")
            papeis = connection.introspection.get_constraints(cursor, "papeis_pessoa")

        self.assertIn("pessoas", tabelas)
        self.assertIn("papeis_pessoa", tabelas)
        for nome in ("pessoa_documento_coerente_com_situacao", "pessoa_razao_social_preenchida",
                     "pessoa_status_valido"):
            self.assertIn(nome, pessoas)
        self.assertTrue(any(c["unique"] and c["columns"] == ["documento"]
                            for c in pessoas.values()))
        self.assertTrue(papeis["papel_pessoa_unico"]["unique"])
        self.assertEqual(papeis["papel_pessoa_unico"]["columns"], ["pessoa_id", "papel"])
        self.assertTrue(any(c["foreign_key"] == ("pessoas", "id") for c in papeis.values()))
