"""Registro de movimentos financeiros (GR-37) e suas parcelas (GR-38).

registrar_movimento() grava o movimento, as classificações e as parcelas em
uma única transação, depois de validar as regras entre entidades:

- APAGAR exige contraparte com papel FORNECEDOR vigente e faturado com papel
  FATURADO vigente; ARECEBER exige contraparte com papel CLIENTE vigente.
- Pessoas incompletas (C-02) e pessoas, papéis ou classificações inativos são
  recusados; nada é reativado automaticamente (T-05).
- APAGAR usa classificações DESPESA; ARECEBER, RECEITA. Pelo menos uma, sem
  repetição e com exatamente uma principal.
- Pelo menos uma parcela, numeradas 1..n, com vencimento e valor; a soma das
  parcelas é exatamente o valor_total. O gatilho diferido da migration 0002
  confere a mesma regra no COMMIT.
- Com analise_origem_id, repetir a chamada com os mesmos dados devolve o
  movimento já gravado, sem duplicar; com dados diferentes, recusa.

Os registros são relidos com select_for_update dentro da transação: uma
inativação concorrente não passa entre a validação e a gravação, e uma
instância desatualizada em memória não engana a validação.

A integração com o Extrator e a conferência da tela ficam para a GR-51; o
pagamento e o cancelamento das parcelas ainda não têm contrato aprovado.
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from cadastros.models import (
    Classificacao, Papel, PapelPessoa, Pessoa, SituacaoDocumental, Status, TipoClassificacao,
)

from .models import (
    LIMITE_VALOR, MovimentoClassificacao, MovimentoConta, OrigemMovimento, ParcelaConta,
    StatusMovimento, StatusParcela, TipoMovimento,
)

PAPEL_DA_CONTRAPARTE = {
    TipoMovimento.APAGAR: Papel.FORNECEDOR,
    TipoMovimento.ARECEBER: Papel.CLIENTE,
}
TIPO_DA_CLASSIFICACAO = {
    TipoMovimento.APAGAR: TipoClassificacao.DESPESA,
    TipoMovimento.ARECEBER: TipoClassificacao.RECEITA,
}
CENTAVO = Decimal("0.01")
# Dez anos de parcelas mensais (decisão de 26/10/2026). Também evita estourar o
# smallint de ParcelaConta.numero e o custo do gatilho no COMMIT.
MAXIMO_DE_PARCELAS = 120


@dataclass(frozen=True)
class ItemClassificacao:
    classificacao: Classificacao
    principal: bool = False


@dataclass(frozen=True)
class ItemParcela:
    numero: int
    data_vencimento: date
    valor: Decimal


@dataclass(frozen=True)
class DadosMovimento:
    tipo: str
    origem: str
    contraparte: Pessoa
    valor_total: Decimal
    classificacoes: tuple[ItemClassificacao, ...] = field(default_factory=tuple)
    faturado: Pessoa | None = None
    analise_origem_id: UUID | None = None
    parcelas: tuple[ItemParcela, ...] = field(default_factory=tuple)


def registrar_movimento(dados):
    """Grava movimento, classificações e parcelas; devolve (movimento, criado)."""
    # Uma só leitura: um gerador consumido na validação chegaria vazio à
    # gravação, e o movimento ficaria sem classificação ou sem parcela.
    try:
        itens = tuple(dados.classificacoes)
    except TypeError:
        raise _erro("Informe as classificações em uma lista.", "classificacao") from None
    try:
        parcelas = tuple(dados.parcelas)
    except TypeError:
        raise _erro("Informe as parcelas em uma lista.", "parcela") from None
    dados = replace(dados, classificacoes=itens, parcelas=parcelas)
    _validar_dados(dados)

    if dados.analise_origem_id is not None:
        existente = MovimentoConta.objects.filter(
            analise_origem_id=dados.analise_origem_id
        ).first()
        if existente is not None:
            return _mesma_analise(existente, dados), False

    try:
        with transaction.atomic():
            _validar_no_banco(dados)
            movimento = MovimentoConta.objects.create(
                tipo=dados.tipo,
                origem=dados.origem,
                contraparte_id=dados.contraparte.pk,
                faturado_id=dados.faturado.pk if dados.faturado else None,
                valor_total=dados.valor_total,
                analise_origem_id=dados.analise_origem_id,
            )
            MovimentoClassificacao.objects.bulk_create([
                MovimentoClassificacao(
                    movimento=movimento,
                    classificacao_id=item.classificacao.pk,
                    principal=item.principal,
                )
                for item in dados.classificacoes
            ])
            ParcelaConta.objects.bulk_create([
                ParcelaConta(
                    movimento=movimento,
                    numero=parcela.numero,
                    data_vencimento=parcela.data_vencimento,
                    valor=parcela.valor,
                )
                for parcela in dados.parcelas
            ])
    except IntegrityError:
        # Outra requisição gravou a mesma análise entre a busca e a gravação.
        if dados.analise_origem_id is None:
            raise
        existente = MovimentoConta.objects.filter(
            analise_origem_id=dados.analise_origem_id
        ).first()
        if existente is None:
            raise
        return _mesma_analise(existente, dados), False
    return movimento, True


def _erro(mensagem, codigo):
    return ValidationError(mensagem, code=codigo)


def _valor_valido(valor):
    """Decimal finito, positivo, abaixo do teto e com até 2 casas; ou o código do erro."""
    # Decimal, nunca float: valores financeiros não podem perder centavos.
    if not isinstance(valor, Decimal) or not valor.is_finite():
        return "valor_tipo"
    if valor <= 0 or valor >= LIMITE_VALOR:
        return "valor"
    if valor != valor.quantize(CENTAVO):
        return "valor_centavos"
    return None


MENSAGENS_DE_VALOR = {
    "valor_tipo": "deve ser um Decimal",
    "valor": "deve ser maior que zero e menor que o limite",
    "valor_centavos": "deve ter no máximo duas casas decimais",
}


def _validar_dados(dados):
    """Regras que não dependem do banco."""
    if dados.tipo not in TipoMovimento.values:
        raise _erro("Tipo de movimento inválido.", "tipo")
    if dados.origem not in OrigemMovimento.values:
        raise _erro("Origem do movimento inválida.", "origem")

    codigo = _valor_valido(dados.valor_total)
    if codigo:
        raise _erro(f"O valor total {MENSAGENS_DE_VALOR[codigo]}.", codigo)

    # isinstance, e não só a pk: um objeto de outro model com a mesma pk
    # lançaria o movimento para outro registro.
    if not _gravado(dados.contraparte, Pessoa):
        raise _erro("Informe a contraparte já cadastrada.", "contraparte")
    if dados.faturado is not None and not _gravado(dados.faturado, Pessoa):
        raise _erro("Informe o faturado já cadastrado.", "faturado")
    if dados.tipo == TipoMovimento.APAGAR and dados.faturado is None:
        raise _erro("Conta a pagar exige o faturado já cadastrado.", "faturado")
    if dados.analise_origem_id is not None and not isinstance(dados.analise_origem_id, UUID):
        raise _erro("O identificador da análise de origem é inválido.", "analise_origem")

    itens = dados.classificacoes
    if not itens:
        raise _erro("Informe pelo menos uma classificação.", "sem_classificacao")
    if any(
        not isinstance(item, ItemClassificacao) or not _gravado(item.classificacao, Classificacao)
        for item in itens
    ):
        raise _erro("Use classificações já cadastradas.", "classificacao")
    # bool, e não "verdadeiro": "False" contaria como principal aqui, mas o
    # BooleanField gravaria False, e o movimento ficaria sem principal.
    if any(not isinstance(item.principal, bool) for item in itens):
        raise _erro("Indique a classificação principal com verdadeiro ou falso.", "principal_tipo")
    ids = [item.classificacao.pk for item in itens]
    if len(ids) != len(set(ids)):
        raise _erro("A mesma classificação foi informada mais de uma vez.", "classificacao_repetida")
    principais = sum(1 for item in itens if item.principal)
    if principais != 1:
        raise _erro("Indique exatamente uma classificação principal.", "principal")

    _validar_parcelas(dados)


def _validar_parcelas(dados):
    """Pelo menos uma, numeradas 1..n, e a soma igual ao valor total (GR-38)."""
    parcelas = dados.parcelas
    if not parcelas:
        raise _erro("Informe pelo menos uma parcela.", "sem_parcela")
    if len(parcelas) > MAXIMO_DE_PARCELAS:
        raise _erro(f"Informe no máximo {MAXIMO_DE_PARCELAS} parcelas.", "parcela_quantidade")
    if any(not isinstance(parcela, ItemParcela) for parcela in parcelas):
        raise _erro("Informe as parcelas com número, vencimento e valor.", "parcela")
    for parcela in parcelas:
        # bool é subclasse de int; datetime, de date.
        if type(parcela.numero) is not int or parcela.numero < 1:
            raise _erro("O número da parcela deve ser um inteiro maior que zero.",
                        "parcela_numero")
        if not isinstance(parcela.data_vencimento, date) or isinstance(
            parcela.data_vencimento, datetime
        ):
            raise _erro(f"Informe a data de vencimento da parcela {parcela.numero}.",
                        "parcela_vencimento")
        codigo = _valor_valido(parcela.valor)
        if codigo:
            raise _erro(f"O valor da parcela {parcela.numero} {MENSAGENS_DE_VALOR[codigo]}.",
                        f"parcela_{codigo}")
    numeros = sorted(parcela.numero for parcela in parcelas)
    if len(numeros) != len(set(numeros)):
        raise _erro("O mesmo número de parcela foi informado mais de uma vez.",
                    "parcela_repetida")
    if numeros != list(range(1, len(numeros) + 1)):
        raise _erro("As parcelas devem ser numeradas de 1 a n, sem lacunas.",
                    "parcela_numeracao")
    soma = sum(parcela.valor for parcela in parcelas)
    if soma != dados.valor_total:
        raise _erro(
            f"A soma das parcelas (R$ {soma}) difere do valor total (R$ {dados.valor_total}).",
            "parcela_soma",
        )


def _gravado(objeto, model):
    return isinstance(objeto, model) and objeto.pk is not None


def _bloquear_pessoas(dados):
    """Bloqueia contraparte e faturado em uma consulta ordenada por pk.

    A ordem fixa evita deadlock entre lançamentos com papéis cruzados (A paga
    a B e B paga a A). FOR NO KEY UPDATE barra uma inativação concorrente sem
    conflitar com as FKs que apontam para a pessoa.
    """
    ids = {dados.contraparte.pk} | ({dados.faturado.pk} if dados.faturado else set())
    pessoas = Pessoa.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk")
    pessoas = {pessoa.pk: pessoa for pessoa in pessoas}
    # list(): o QuerySet é preguiçoso; sem avaliar, o bloqueio não acontece.
    list(PapelPessoa.objects.select_for_update(no_key=True).filter(pessoa_id__in=ids).order_by("pk"))
    return pessoas


def _validar_pessoa(pessoas, pessoa_id, papel, rotulo):
    pessoa = pessoas.get(pessoa_id)
    if pessoa is None:
        raise _erro(f"{rotulo} não encontrado.", "pessoa_inexistente")
    if pessoa.status != Status.ATIVO:
        raise _erro(f"{rotulo} está inativo; reative o cadastro antes do lançamento.",
                    "pessoa_inativa")
    if pessoa.situacao_documental != SituacaoDocumental.COMPLETO:
        raise _erro(f"{rotulo} tem cadastro incompleto; regularize o documento antes.",
                    "pessoa_incompleta")
    vinculo = PapelPessoa.objects.filter(pessoa=pessoa, papel=papel).first()
    if vinculo is None:
        raise _erro(f"{rotulo} não tem o papel {papel}.", "papel_ausente")
    if vinculo.status != Status.ATIVO:
        raise _erro(f"O papel {papel} do {rotulo.lower()} está inativo; reative-o antes.",
                    "papel_inativo")


def _validar_no_banco(dados):
    """Regras relidas do banco, com bloqueio, dentro da transação."""
    pessoas = _bloquear_pessoas(dados)
    _validar_pessoa(pessoas, dados.contraparte.pk, PAPEL_DA_CONTRAPARTE[dados.tipo], "Contraparte")
    if dados.faturado is not None:
        _validar_pessoa(pessoas, dados.faturado.pk, Papel.FATURADO, "Faturado")

    ids = [item.classificacao.pk for item in dados.classificacoes]
    classificacoes = {
        c.pk: c for c in
        Classificacao.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk")
    }
    tipo_esperado = TIPO_DA_CLASSIFICACAO[dados.tipo]
    for pk in ids:
        classificacao = classificacoes.get(pk)
        if classificacao is None:
            raise _erro("Classificação não encontrada.", "classificacao_inexistente")
        if classificacao.status != Status.ATIVO:
            raise _erro(f"A classificação {classificacao.codigo} está inativa.",
                        "classificacao_inativa")
        if classificacao.tipo != tipo_esperado:
            raise _erro(
                f"A classificação {classificacao.codigo} é {classificacao.tipo}; "
                f"este movimento exige {tipo_esperado}.",
                "classificacao_incompativel",
            )


def _mesma_analise(movimento, dados):
    """A mesma análise só pode corresponder ao mesmo lançamento."""
    principal = movimento.classificacoes.filter(principal=True).values_list(
        "classificacao_id", flat=True
    ).first()
    # O status entra na comparação: uma análise de movimento cancelado não é
    # devolvida como se fosse o mesmo lançamento.
    gravado = (
        movimento.status,
        movimento.tipo, movimento.origem, movimento.contraparte_id, movimento.faturado_id,
        movimento.valor_total,
        set(movimento.classificacoes.values_list("classificacao_id", flat=True)), principal,
        set(movimento.parcelas.filter(status=StatusParcela.ATIVA).values_list(
            "numero", "data_vencimento", "valor"
        )),
    )
    pedido = (
        StatusMovimento.CONFIRMADO,
        dados.tipo, dados.origem, dados.contraparte.pk,
        dados.faturado.pk if dados.faturado else None, dados.valor_total,
        {item.classificacao.pk for item in dados.classificacoes},
        next(item.classificacao.pk for item in dados.classificacoes if item.principal),
        {(p.numero, p.data_vencimento, p.valor) for p in dados.parcelas},
    )
    if gravado != pedido:
        raise _erro("Esta análise já foi lançada com outros dados.", "analise_ja_lancada")
    return movimento
