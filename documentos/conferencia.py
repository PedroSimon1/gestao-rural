"""Combinação e revalidação dos dados extraídos com as correções (GR-22, F-3).

conferir_nota(dados, correcoes) monta a nota que será lançada: para cada campo
da lista fechada de documentos/correcoes.py, vale a correção, se houver, ou o
valor extraído do JSON final (versão 1). Tudo é revalidado no servidor com as
regras que já existem, sem confiar no que a tela validou:

- cada campo: os mesmos validadores das correções (F-2), aplicados também ao
  valor extraído;
- documentos e papéis: consultar_pessoa (GR-40);
- classificação: consultar_classificacao (GR-40);
- parcelas e valor total: validar_parcelas (GR-38);
- identidade fiscal e duplicidade: identificar_nota e nota_lancada (F-1).

Só leitura: nada é criado, alterado, reativado ou atribuído (F-4 e F-5). O
resultado traz os problemas por campo (códigos, nunca valores) e as consultas,
para a tela (GR-45) e para a confirmação (F-5). Pessoa ou classificação
INATIVA e papel AUSENTE não são problemas de dado: aparecem nas consultas e
pedem decisão explícita na F-4 (DQ-07).

D-03: se o extraído trouxer CPF e CNPJ para a mesma parte, sem correção,
nenhum dos dois é escolhido automaticamente (problema escolha_necessaria).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from cadastros.consultas import (
    ConsultaClassificacao, ConsultaPessoa, Situacao, consultar_classificacao, consultar_pessoa,
)
from cadastros.models import Papel
from financeiro.identidade_fiscal import IdentidadeFiscal, identificar_nota, nota_lancada
from financeiro.servicos import ItemParcela, validar_parcelas

from .correcoes import CAMPOS_CORRIGIVEIS, CampoInvalido, validar_correcoes

AUSENTE = "ausente"
INVALIDO = "invalido"
ESCOLHA_NECESSARIA = "escolha_necessaria"
# Extraído que só é problema se for usado: o nome só é exigido quando a pessoa
# ainda não existe; a data de emissão não é gravada no movimento. Uma correção
# inválida desses campos continua sendo problema.
_SO_SE_USADO = {"fornecedor.razao_social", "faturado.nome", "data_emissao"}
# Série e número ausentes entram na identidade fiscal, que acusa a falta.
_AUSENCIA_NA_IDENTIDADE = {"serie", "numero_nota"}


@dataclass(frozen=True)
class Problema:
    campo: str
    codigo: str


@dataclass(frozen=True)
class ParteConferida:
    papel: str
    documento: str | None
    nome: str | None
    consulta: ConsultaPessoa


@dataclass(frozen=True)
class NotaConferida:
    fornecedor: ParteConferida
    faturado: ParteConferida
    classificacao: ConsultaClassificacao
    numero_nota: int | None
    serie: int | None
    data_emissao: date | None
    valor_total: Decimal | None
    parcelas: tuple[ItemParcela, ...]
    identidade_fiscal: IdentidadeFiscal | None
    # Campos cujo valor final difere do extraído (informativo; P-11 aberta).
    campos_alterados: tuple[str, ...]
    problemas: tuple[Problema, ...]

    @property
    def sem_problemas(self):
        """Dados prontos para a F-4/F-5 (as decisões da F-4 ainda podem faltar)."""
        return not self.problemas


class _Escolha:
    """Marca: CPF e CNPJ extraídos para a mesma parte (D-03)."""


_ESCOLHA = _Escolha()


def _bloco(dados, chave):
    bloco = dados.get(chave) if isinstance(dados, dict) else None
    return bloco if isinstance(bloco, dict) else {}


def _documento_extraido(bloco):
    documentos = [bloco.get(chave) for chave in ("cnpj", "cpf") if bloco.get(chave)]
    if len(documentos) > 1:
        return _ESCOLHA
    return documentos[0] if documentos else None


_CAMPOS_DA_PARCELA = ("numero", "data_vencimento", "valor")


def _parcelas_extraidas(valor):
    # Só os três campos da versão 1: um campo novo da versão 2 não invalida a lista.
    if not isinstance(valor, list):
        return valor
    return [
        {campo: item.get(campo) for campo in _CAMPOS_DA_PARCELA} if isinstance(item, dict) else item
        for item in valor
    ]


def _extraidos(dados):
    """Valores do JSON final (versão 1) com os nomes da lista de correções."""
    fornecedor, faturado = _bloco(dados, "fornecedor"), _bloco(dados, "faturado")
    obter = dados.get if isinstance(dados, dict) else (lambda chave: None)
    return {
        "fornecedor.documento": _documento_extraido(fornecedor),
        "fornecedor.razao_social": fornecedor.get("razao_social"),
        "faturado.documento": _documento_extraido(faturado),
        "faturado.nome": faturado.get("nome"),
        "tipo_despesa": obter("tipo_despesa"),
        "numero_nota": obter("numero_nota"),
        # A versão 1 não tem série: só por correção.
        "serie": None,
        "data_emissao": obter("data_emissao"),
        "valor_total": obter("valor_total"),
        "parcelas": _parcelas_extraidas(obter("parcelas")),
    }


def _normalizado(campo, valor):
    """(valor normalizado, código do problema ou None)."""
    if valor is _ESCOLHA:
        return None, ESCOLHA_NECESSARIA
    if valor is None or valor == "" or valor == []:
        return None, AUSENTE
    try:
        return CAMPOS_CORRIGIVEIS[campo](valor), None
    except CampoInvalido:
        return None, INVALIDO


@dataclass
class _Combinacao:
    finais: dict
    alterados: tuple
    problemas: list
    extraidos: dict
    # Código do problema de cada valor extraído (ausente, invalido...).
    codigos_extraidos: dict
    correcoes: dict
    correcoes_invalidas: set


def _combinar(dados, correcoes):
    problemas = []
    if correcoes is None:
        correcoes = {}
    if not isinstance(correcoes, dict):
        correcoes, problemas = {}, [Problema("correcoes", INVALIDO)]
    validas, invalidos = validar_correcoes(correcoes)
    problemas += [Problema(campo, INVALIDO) for campo in invalidos]

    extraidos = _extraidos(dados)
    finais, alterados, codigos = {}, [], {}
    for campo in CAMPOS_CORRIGIVEIS:
        extraido, codigos[campo] = _normalizado(campo, extraidos[campo])
        if campo in validas:
            finais[campo] = validas[campo]
            if validas[campo] != extraido:
                alterados.append(campo)
        elif campo in invalidos:
            finais[campo] = None
        else:
            finais[campo] = extraido
            codigo = codigos[campo]
            if not codigo or campo in _SO_SE_USADO:
                continue
            if codigo == AUSENTE and campo in _AUSENCIA_NA_IDENTIDADE:
                continue
            problemas.append(Problema(campo, codigo))
    return _Combinacao(
        finais, tuple(alterados), problemas, extraidos, codigos, correcoes, set(invalidos),
    )


def _parte(papel, documento_campo, nome_campo, combinacao):
    finais = combinacao.finais
    documento, nome = finais[documento_campo], finais[nome_campo]
    if documento is not None:
        bruto = documento
    elif documento_campo in combinacao.correcoes_invalidas:
        bruto = combinacao.correcoes.get(documento_campo)
    else:
        bruto = combinacao.extraidos[documento_campo]
    # Ausente ou inválido: consultar_pessoa devolve a situação sem consultar o
    # banco (DOCUMENTO_INVALIDO para um texto inválido, inclusive corrigido).
    consulta = consultar_pessoa(bruto if isinstance(bruto, str) else None, papel, nome=nome)
    if (
        nome is None
        and nome_campo not in combinacao.correcoes_invalidas
        and consulta.situacao != Situacao.EXISTE
    ):
        # Pessoa a cadastrar (ou sem documento): o nome é obrigatório.
        codigo = combinacao.codigos_extraidos[nome_campo] or AUSENTE
        combinacao.problemas.append(Problema(nome_campo, codigo))
    return ParteConferida(papel=papel, documento=documento, nome=nome, consulta=consulta)


def _parcelas(finais):
    return tuple(
        ItemParcela(
            numero=parcela["numero"],
            data_vencimento=date.fromisoformat(parcela["data_vencimento"]),
            valor=Decimal(parcela["valor"]),
        )
        for parcela in finais["parcelas"] or ()
    )


def _identidade(finais, problemas):
    try:
        identidade = identificar_nota(
            emitente_cnpj=finais["fornecedor.documento"], modelo=None,
            serie=finais["serie"], numero=finais["numero_nota"],
        )
    except ValidationError as erro:
        problemas.append(Problema("identidade_fiscal", erro.code))
        return None
    if nota_lancada(identidade) is not None:
        problemas.append(Problema("identidade_fiscal", "nota_ja_lancada"))
    return identidade


def conferir_nota(dados, correcoes=None):
    """NotaConferida a partir dos dados extraídos e das correções; só leitura.

    `dados`: AnalisePendente.dados (JSON final, versão 1). `correcoes`:
    AnalisePendente.correcoes ou correcoes_da_confirmacao() (None ou dict).
    """
    combinacao = _combinar(dados, correcoes)
    finais, problemas = combinacao.finais, combinacao.problemas

    fornecedor = _parte(
        Papel.FORNECEDOR, "fornecedor.documento", "fornecedor.razao_social", combinacao
    )
    faturado = _parte(Papel.FATURADO, "faturado.documento", "faturado.nome", combinacao)

    classificacao = consultar_classificacao(finais["tipo_despesa"])
    if classificacao.situacao == Situacao.NAO_EXISTE:
        # Criar classificação a partir do Classificador depende da Q-05.
        problemas.append(Problema("tipo_despesa", "classificacao_inexistente"))

    valor_total = Decimal(finais["valor_total"]) if finais["valor_total"] else None
    parcelas = _parcelas(finais)
    if valor_total is not None and finais["parcelas"]:
        try:
            validar_parcelas(valor_total, parcelas)
        except ValidationError as erro:
            # O código, nunca a mensagem (que traz valores).
            problemas.append(Problema("parcelas", erro.code))

    identidade = _identidade(finais, problemas)

    return NotaConferida(
        fornecedor=fornecedor,
        faturado=faturado,
        classificacao=classificacao,
        numero_nota=finais["numero_nota"],
        serie=finais["serie"],
        data_emissao=date.fromisoformat(finais["data_emissao"]) if finais["data_emissao"] else None,
        valor_total=valor_total,
        parcelas=parcelas,
        identidade_fiscal=identidade,
        campos_alterados=combinacao.alterados,
        problemas=tuple(problemas),
    )
