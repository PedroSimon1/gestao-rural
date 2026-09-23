import copy
import json
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase
from pydantic import ValidationError

from .schemas import (
    VERSAO_SCHEMA,
    NotaFiscalExtraida,
    cnpj_dv_valido,
    cpf_dv_valido,
)

# Documentos fictícios com dígitos verificadores válidos.
CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_ALFANUMERICO_VALIDO = "12.ABC.345/01DE-35"  # exemplo oficial da Receita
CPF_VALIDO = "529.982.247-25"
CPF_FICTICIO_DV_INVALIDO = "999.999.999-99"  # CPF fictício do PDF de teste


def nota_valida():
    return {
        "documento_e_nota_fiscal": True,
        "fornecedor": {
            "razao_social": "Agro Insumos Ltda",
            "nome_fantasia": "Agro Insumos",
            "cnpj": CNPJ_VALIDO,
        },
        "faturado": {"nome": "Produtor Teste", "cpf": CPF_VALIDO},
        "numero_nota": "000123",
        "data_emissao": "2026-09-20",
        "itens": [
            {
                "descricao": "Semente de milho",
                "quantidade": 10,
                "valor_unitario": 150,
                "valor_total": 1500,
            }
        ],
        "parcelas": [
            {"numero": 1, "data_vencimento": "2026-10-20", "valor": 750},
            {"numero": 2, "data_vencimento": "2026-11-20", "valor": 750},
        ],
        "valor_total": 1500,
    }


def validar(**alteracoes):
    dados = nota_valida()
    dados.update(alteracoes)
    return NotaFiscalExtraida.model_validate(dados)


def validar_bloco(bloco, **alteracoes):
    dados = nota_valida()
    dados[bloco] = {**dados[bloco], **alteracoes}
    return NotaFiscalExtraida.model_validate(dados)


class NotaFiscalValidaTests(SimpleTestCase):
    def test_versao_do_schema(self):
        self.assertEqual(VERSAO_SCHEMA, 1)

    def test_json_completo_valido(self):
        nota = validar()

        self.assertTrue(nota.documento_e_nota_fiscal)
        self.assertEqual(nota.fornecedor.razao_social, "Agro Insumos Ltda")
        self.assertEqual(nota.fornecedor.cnpj, "11222333000181")
        self.assertEqual(nota.faturado.cpf, "52998224725")
        self.assertEqual(nota.numero_nota, "000123")
        self.assertEqual(nota.data_emissao, date(2026, 9, 20))
        self.assertEqual(nota.valor_total, Decimal("1500.00"))
        self.assertEqual(nota.itens[0].quantidade, Decimal("10"))
        self.assertEqual(nota.parcelas[1].data_vencimento, date(2026, 11, 20))

    def test_dump_json_e_serializavel_e_usa_iso_e_centavos(self):
        dados = validar().model_dump(mode="json")

        json.dumps(dados)  # mesmo encoder padrão usado pelo JSONField
        self.assertEqual(dados["valor_total"], "1500.00")
        self.assertEqual(dados["data_emissao"], "2026-09-20")
        self.assertEqual(dados["itens"][0]["valor_unitario"], "150.00")
        self.assertEqual(
            dados["parcelas"][0],
            {"numero": 1, "data_vencimento": "2026-10-20", "valor": "750.00"},
        )

    def test_valores_monetarios_sao_quantizados_em_duas_casas(self):
        nota = validar(valor_total=1500.1)
        self.assertEqual(nota.valor_total, Decimal("1500.10"))
        self.assertEqual(str(nota.valor_total), "1500.10")

        nota = validar(valor_total="99.995")
        self.assertEqual(nota.valor_total, Decimal("100.00"))

    def test_float_nao_gera_artefato_de_precisao(self):
        nota = validar(valor_total=0.1 + 0.2)

        self.assertEqual(nota.valor_total, Decimal("0.30"))

    def test_quantidade_nao_e_limitada_a_duas_casas(self):
        dados = nota_valida()
        dados["itens"][0]["quantidade"] = 2.345

        nota = NotaFiscalExtraida.model_validate(dados)

        self.assertEqual(nota.itens[0].quantidade, Decimal("2.345"))

    def test_campos_extras_sao_ignorados(self):
        dados = nota_valida()
        dados["campo_desconhecido"] = "x"
        dados["fornecedor"]["inscricao_estadual"] = "123"

        dump = NotaFiscalExtraida.model_validate(dados).model_dump()

        self.assertNotIn("campo_desconhecido", dump)
        self.assertNotIn("inscricao_estadual", dump["fornecedor"])


class CamposOpcionaisTests(SimpleTestCase):
    def test_campos_opcionais_ausentes_viram_none(self):
        nota = NotaFiscalExtraida.model_validate(
            {
                "documento_e_nota_fiscal": True,
                "fornecedor": {},
                "faturado": {},
                "itens": [{"descricao": "Adubo"}],
                "parcelas": [{"valor": 100}],
                "valor_total": 100,
            }
        )

        self.assertIsNone(nota.fornecedor.razao_social)
        self.assertIsNone(nota.fornecedor.nome_fantasia)
        self.assertIsNone(nota.fornecedor.cnpj)
        self.assertIsNone(nota.faturado.nome)
        self.assertIsNone(nota.faturado.cpf)
        self.assertIsNone(nota.numero_nota)
        self.assertIsNone(nota.data_emissao)
        self.assertIsNone(nota.itens[0].quantidade)
        self.assertIsNone(nota.itens[0].valor_unitario)
        self.assertIsNone(nota.itens[0].valor_total)
        self.assertIsNone(nota.parcelas[0].data_vencimento)

    def test_campos_opcionais_null_viram_none(self):
        nota = validar(numero_nota=None, data_emissao=None)

        self.assertIsNone(nota.numero_nota)
        self.assertIsNone(nota.data_emissao)

    def test_strings_vazias_ou_so_com_espacos_viram_none(self):
        dados = nota_valida()
        dados["fornecedor"] = {"razao_social": "", "nome_fantasia": "   ", "cnpj": ""}
        dados["faturado"] = {"nome": " ", "cpf": ""}
        dados["numero_nota"] = "  "
        dados["data_emissao"] = ""

        nota = NotaFiscalExtraida.model_validate(dados)

        self.assertEqual(nota.fornecedor.model_dump(), {
            "razao_social": None, "nome_fantasia": None, "cnpj": None,
        })
        self.assertEqual(nota.faturado.model_dump(), {"nome": None, "cpf": None})
        self.assertIsNone(nota.numero_nota)
        self.assertIsNone(nota.data_emissao)

    def test_espacos_extras_sao_removidos(self):
        nota = validar_bloco(
            "fornecedor", razao_social="  Agro   Insumos\n Ltda  "
        )

        self.assertEqual(nota.fornecedor.razao_social, "Agro Insumos Ltda")

    def test_blocos_obrigatorios_ausentes_sao_rejeitados(self):
        for campo in ("documento_e_nota_fiscal", "fornecedor", "faturado",
                      "itens", "parcelas", "valor_total"):
            with self.subTest(campo=campo):
                dados = nota_valida()
                del dados[campo]

                with self.assertRaises(ValidationError):
                    NotaFiscalExtraida.model_validate(dados)


class DocumentosTests(SimpleTestCase):
    """Estrutura de CPF/CNPJ é exigida; DV inválido é preservado e sinalizado."""

    def test_cpf_formatado_e_normalizado(self):
        for cpf in ("529.982.247-25", "52998224725", " 529 982 247 25 "):
            with self.subTest(cpf=cpf):
                nota = validar_bloco("faturado", cpf=cpf)
                self.assertEqual(nota.faturado.cpf, "52998224725")

    def test_cpf_com_dv_invalido_e_preservado(self):
        casos = (
            (CPF_FICTICIO_DV_INVALIDO, "99999999999"),  # do PDF de teste
            ("529.982.247-24", "52998224724"),          # DV errado
            ("111.111.111-11", "11111111111"),          # sequência repetida
        )
        for cpf, esperado in casos:
            with self.subTest(cpf=cpf):
                nota = validar_bloco("faturado", cpf=cpf)
                self.assertEqual(nota.faturado.cpf, esperado)

    def test_cpf_com_estrutura_impossivel_e_rejeitado(self):
        for cpf in (
            "5299822472",      # 10 dígitos
            "529982247251",    # 12 dígitos
            "529.982.247-2X",  # letra
            "CPF 52998224725",
            12345678909,       # número em vez de texto
        ):
            with self.subTest(cpf=cpf):
                with self.assertRaises(ValidationError):
                    validar_bloco("faturado", cpf=cpf)

    def test_cnpj_formatado_e_normalizado(self):
        for cnpj in ("11.222.333/0001-81", "11222333000181"):
            with self.subTest(cnpj=cnpj):
                nota = validar_bloco("fornecedor", cnpj=cnpj)
                self.assertEqual(nota.fornecedor.cnpj, "11222333000181")

    def test_cnpj_alfanumerico_e_aceito_e_normalizado(self):
        for cnpj in (CNPJ_ALFANUMERICO_VALIDO, "12abc34501de35"):
            with self.subTest(cnpj=cnpj):
                nota = validar_bloco("fornecedor", cnpj=cnpj)
                self.assertEqual(nota.fornecedor.cnpj, "12ABC34501DE35")

    def test_cnpj_com_dv_invalido_e_preservado(self):
        casos = (
            ("11.222.333/0001-82", "11222333000182"),  # DV errado
            ("12.ABC.345/01DE-36", "12ABC34501DE36"),  # DV alfanumérico errado
            ("00.000.000/0000-00", "00000000000000"),  # sequência repetida
        )
        for cnpj, esperado in casos:
            with self.subTest(cnpj=cnpj):
                nota = validar_bloco("fornecedor", cnpj=cnpj)
                self.assertEqual(nota.fornecedor.cnpj, esperado)

    def test_cnpj_com_estrutura_impossivel_e_rejeitado(self):
        for cnpj in (
            "12.ABC.345/01DE-3A",   # DV precisa ser numérico
            "1122233300018",        # 13 caracteres
            "112223330001811",      # 15 caracteres
            "11.222.333/0001-8!",
            11222333000181,         # número em vez de texto
        ):
            with self.subTest(cnpj=cnpj):
                with self.assertRaises(ValidationError):
                    validar_bloco("fornecedor", cnpj=cnpj)


class DigitosVerificadoresTests(SimpleTestCase):
    def test_cpf_dv_valido(self):
        casos = {
            "52998224725": True,
            "529.982.247-25": True,
            "12345678909": True,
            "52998224724": False,
            CPF_FICTICIO_DV_INVALIDO: False,  # sequência repetida
            "00000000000": False,
            "5299822472": False,
            "": False,
        }
        for cpf, esperado in casos.items():
            with self.subTest(cpf=cpf):
                self.assertIs(cpf_dv_valido(cpf), esperado)

    def test_cnpj_dv_valido(self):
        casos = {
            "11222333000181": True,
            CNPJ_VALIDO: True,
            CNPJ_ALFANUMERICO_VALIDO: True,
            "12abc34501de35": True,
            "11222333000182": False,
            "12ABC34501DE36": False,
            "00000000000000": False,
            "1122233300018": False,
            "": False,
        }
        for cnpj, esperado in casos.items():
            with self.subTest(cnpj=cnpj):
                self.assertIs(cnpj_dv_valido(cnpj), esperado)

    def test_funcoes_nao_alteram_o_dado(self):
        nota = validar_bloco("faturado", cpf=CPF_FICTICIO_DV_INVALIDO)

        cpf_dv_valido(nota.faturado.cpf)
        nota.validacoes

        self.assertEqual(nota.faturado.cpf, "99999999999")


class ValidacoesTests(SimpleTestCase):
    def validacao(self, nota, campo):
        return nota.validacoes.model_dump()[campo]

    def test_cpf_valido(self):
        nota = validar()

        self.assertEqual(nota.faturado.cpf, "52998224725")
        self.assertEqual(
            self.validacao(nota, "faturado_cpf"), {"status": "valido", "motivo": None}
        )

    def test_cpf_ficticio_com_dv_invalido(self):
        nota = validar_bloco("faturado", cpf=CPF_FICTICIO_DV_INVALIDO)

        self.assertIsInstance(nota, NotaFiscalExtraida)
        self.assertEqual(nota.faturado.cpf, "99999999999")
        self.assertEqual(
            self.validacao(nota, "faturado_cpf"),
            {"status": "invalido", "motivo": "digitos_verificadores_invalidos"},
        )

    def test_cpf_ausente(self):
        for valor in (None, ""):
            with self.subTest(valor=valor):
                nota = validar_bloco("faturado", cpf=valor)

                self.assertIsNone(nota.faturado.cpf)
                self.assertEqual(
                    self.validacao(nota, "faturado_cpf"),
                    {"status": "ausente", "motivo": None},
                )

    def test_cnpj_valido(self):
        for cnpj in (CNPJ_VALIDO, CNPJ_ALFANUMERICO_VALIDO):
            with self.subTest(cnpj=cnpj):
                nota = validar_bloco("fornecedor", cnpj=cnpj)
                self.assertEqual(
                    self.validacao(nota, "fornecedor_cnpj"),
                    {"status": "valido", "motivo": None},
                )

    def test_cnpj_com_dv_invalido(self):
        nota = validar_bloco("fornecedor", cnpj="11.222.333/0001-82")

        self.assertEqual(nota.fornecedor.cnpj, "11222333000182")
        self.assertEqual(
            self.validacao(nota, "fornecedor_cnpj"),
            {"status": "invalido", "motivo": "digitos_verificadores_invalidos"},
        )

    def test_cnpj_ausente(self):
        nota = validar_bloco("fornecedor", cnpj=None)

        self.assertIsNone(nota.fornecedor.cnpj)
        self.assertEqual(
            self.validacao(nota, "fornecedor_cnpj"),
            {"status": "ausente", "motivo": None},
        )

    def test_validacoes_aparecem_no_dump_json_sem_os_numeros(self):
        nota = validar_bloco("faturado", cpf=CPF_FICTICIO_DV_INVALIDO)

        dados = nota.model_dump(mode="json")

        json.dumps(dados)
        self.assertEqual(
            dados["validacoes"],
            {
                "fornecedor_cnpj": {"status": "valido", "motivo": None},
                "faturado_cpf": {
                    "status": "invalido",
                    "motivo": "digitos_verificadores_invalidos",
                },
            },
        )
        texto = json.dumps(dados["validacoes"])
        self.assertNotIn("99999999999", texto)
        self.assertNotIn("11222333000181", texto)

    def test_validacoes_enviadas_pelo_gemini_sao_ignoradas(self):
        dados = nota_valida()
        dados["faturado"]["cpf"] = CPF_FICTICIO_DV_INVALIDO
        dados["validacoes"] = {
            "fornecedor_cnpj": {"status": "invalido"},
            "faturado_cpf": {"status": "valido"},
        }

        nota = NotaFiscalExtraida.model_validate(dados)

        self.assertEqual(nota.validacoes.faturado_cpf.status, "invalido")
        self.assertEqual(nota.validacoes.fornecedor_cnpj.status, "valido")


class DatasEValoresTests(SimpleTestCase):
    def test_data_invalida_e_rejeitada(self):
        for data in ("20/09/2026", "2026-02-30", "2026-9-20",
                     "2026-09-20T10:00:00", "ontem", 1758326400):
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    validar(data_emissao=data)

    def test_valor_total_zero_ou_negativo_e_rejeitado(self):
        for valor in (0, "0.00", 0.004, -10):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    validar(valor_total=valor)

    def test_valor_nao_numerico_e_rejeitado(self):
        for valor in ("R$ 1.500,00", "abc", True, "NaN", "Infinity", None):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    validar(valor_total=valor)

    def test_valor_acima_do_limite_e_rejeitado(self):
        for valor in ("10000000000", "1e30"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    validar(valor_total=valor)

    def test_valores_negativos_do_item_sao_rejeitados(self):
        for campo in ("quantidade", "valor_unitario", "valor_total"):
            with self.subTest(campo=campo):
                dados = nota_valida()
                dados["itens"][0][campo] = -1

                with self.assertRaises(ValidationError):
                    NotaFiscalExtraida.model_validate(dados)

    def test_parcela_com_valor_zero_ou_negativo_e_rejeitada(self):
        for valor in (0, -750):
            with self.subTest(valor=valor):
                dados = nota_valida()
                dados["parcelas"][0]["valor"] = valor

                with self.assertRaises(ValidationError):
                    NotaFiscalExtraida.model_validate(dados)


class ItensTests(SimpleTestCase):
    def test_item_sem_descricao_e_rejeitado(self):
        for item in ({}, {"descricao": ""}, {"descricao": "   "},
                     {"descricao": None, "valor_total": 10}):
            with self.subTest(item=item):
                with self.assertRaises(ValidationError):
                    validar(itens=[item])

    def test_multiplos_itens_preservam_ordem(self):
        descricoes = ["Semente", "Adubo", "Defensivo", "Frete"]

        nota = validar(itens=[{"descricao": d} for d in descricoes])

        self.assertEqual([item.descricao for item in nota.itens], descricoes)

    def test_lista_de_itens_vazia_e_aceita_pelo_schema(self):
        # A exigência de pelo menos 1 item é regra do AgentExtrator.
        self.assertEqual(validar(itens=[]).itens, [])


class ParcelasTests(SimpleTestCase):
    def test_multiplas_parcelas_preservam_ordem(self):
        parcelas = [
            {"numero": 3, "data_vencimento": "2026-12-20", "valor": 500},
            {"numero": 1, "data_vencimento": "2026-10-20", "valor": 500},
            {"numero": 2, "data_vencimento": "2026-11-20", "valor": 500},
        ]

        nota = validar(parcelas=parcelas)

        self.assertEqual([p.numero for p in nota.parcelas], [3, 1, 2])

    def test_parcelas_sem_numero_sao_numeradas_na_ordem(self):
        parcelas = [
            {"data_vencimento": "2026-10-20", "valor": 500},
            {"numero": None, "data_vencimento": "2026-11-20", "valor": 500},
            {"data_vencimento": "2026-12-20", "valor": 500},
        ]

        nota = validar(parcelas=parcelas)

        self.assertEqual([p.numero for p in nota.parcelas], [1, 2, 3])
        self.assertEqual(
            [p.data_vencimento.month for p in nota.parcelas], [10, 11, 12]
        )

    def test_numeracao_parcial_e_rejeitada(self):
        parcelas = [
            {"numero": 1, "valor": 500},
            {"valor": 500},
        ]

        with self.assertRaises(ValidationError):
            validar(parcelas=parcelas)

    def test_numero_duplicado_e_rejeitado(self):
        parcelas = [
            {"numero": 1, "valor": 500},
            {"numero": 1, "valor": 500},
        ]

        with self.assertRaises(ValidationError):
            validar(parcelas=parcelas)

    def test_numero_menor_que_um_e_rejeitado(self):
        for numero in (0, -1):
            with self.subTest(numero=numero):
                with self.assertRaises(ValidationError):
                    validar(parcelas=[{"numero": numero, "valor": 500}])

    def test_parcelas_vazia_e_valida(self):
        nota = validar(parcelas=[])

        self.assertEqual(nota.parcelas, [])


class SchemaParaGeminiTests(SimpleTestCase):
    """O schema JSON é enviado ao Gemini como response_schema."""

    def setUp(self):
        self.schema = NotaFiscalExtraida.model_json_schema()

    def percorrer(self, no, caminho="$"):
        if isinstance(no, dict):
            yield caminho, no
            for chave, valor in no.items():
                yield from self.percorrer(valor, f"{caminho}.{chave}")
        elif isinstance(no, list):
            for indice, valor in enumerate(no):
                yield from self.percorrer(valor, f"{caminho}[{indice}]")

    def propriedade(self, modelo, campo):
        if modelo is None:
            return self.schema["properties"][campo]
        return self.schema["$defs"][modelo]["properties"][campo]

    def tipos(self, propriedade):
        opcoes = propriedade.get("anyOf", [propriedade])
        return sorted(opcao["type"] for opcao in opcoes)

    def test_schema_nao_tem_pattern_nem_format(self):
        for caminho, no in self.percorrer(self.schema):
            with self.subTest(caminho=caminho):
                self.assertNotIn("pattern", no)
                self.assertNotIn("format", no)

    def test_any_of_so_aparece_para_tornar_campo_anulavel(self):
        for caminho, no in self.percorrer(self.schema):
            if "anyOf" in no:
                with self.subTest(caminho=caminho):
                    self.assertEqual(len(no["anyOf"]), 2)
                    self.assertIn({"type": "null"}, no["anyOf"])

    def test_campos_monetarios_e_quantidade_sao_number(self):
        casos = (
            (None, "valor_total", ["number"]),
            ("ParcelaExtraida", "valor", ["number"]),
            ("Item", "quantidade", ["null", "number"]),
            ("Item", "valor_unitario", ["null", "number"]),
            ("Item", "valor_total", ["null", "number"]),
        )
        for modelo, campo, esperado in casos:
            with self.subTest(modelo=modelo, campo=campo):
                self.assertEqual(self.tipos(self.propriedade(modelo, campo)), esperado)

    def test_datas_sao_string(self):
        for modelo, campo in ((None, "data_emissao"),
                              ("ParcelaExtraida", "data_vencimento")):
            with self.subTest(modelo=modelo, campo=campo):
                self.assertEqual(
                    self.tipos(self.propriedade(modelo, campo)), ["null", "string"]
                )

    def test_validacoes_nao_fazem_parte_do_schema_do_gemini(self):
        self.assertEqual(
            list(self.schema["properties"]),
            ["documento_e_nota_fiscal", "fornecedor", "faturado", "numero_nota",
             "data_emissao", "itens", "parcelas", "valor_total"],
        )
        self.assertNotIn("validacoes", json.dumps(self.schema))
        self.assertNotIn("Validacoes", self.schema.get("$defs", {}))
        # Só o schema de serialização (saída) conhece o campo calculado.
        self.assertIn(
            "validacoes",
            NotaFiscalExtraida.model_json_schema(mode="serialization")["properties"],
        )

    def test_estrutura_principal_e_obrigatoria(self):
        self.assertEqual(
            sorted(self.schema["required"]),
            sorted(["documento_e_nota_fiscal", "fornecedor", "faturado",
                    "itens", "parcelas", "valor_total"]),
        )

    def test_validacao_nao_altera_os_dados_de_entrada(self):
        dados = nota_valida()
        dados["parcelas"] = [{"valor": 100}, {"valor": 200}]
        original = copy.deepcopy(dados)

        NotaFiscalExtraida.model_validate(dados)

        self.assertEqual(dados, original)
