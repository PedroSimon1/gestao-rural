"""Contas a pagar e a receber lançadas à mão (FUN-06, FUN-07; P08).

Fachada para a interface: recebe identificadores de pessoas e classificações
já cadastradas, monta o DadosMovimento oficial com origem MANUAL e delega a
gravação a registrar_movimento() (GR-37/GR-38), que relê tudo com bloqueio e
aplica as regras: fornecedor e faturado vigentes no APAGAR, cliente vigente no
ARECEBER (faturado opcional, mas com o papel vigente se informado),
classificações ativas do tipo do movimento, exatamente uma principal, parcelas
numeradas cuja soma é o valor total. Nada é criado, reativado ou deduzido:
pessoa, papel ou classificação que falte é recusado com o código estável.

As parcelas são numeradas pela ordem em que chegam (1..n). A listagem e a
consulta valem para qualquer origem e só leem o banco.

Repetição (seção 15.1.20): cada solicitação traz uma chave_idempotencia
(UUID gerado pela tela ao abrir o formulário). A mesma chave com os mesmos
dados devolve o movimento já gravado; com outros dados, recusa
(solicitacao_ja_registrada). O índice único decide envios simultâneos. Chaves
diferentes gravam contas diferentes, mesmo com dados idênticos.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Min, Q

from cadastros.models import Classificacao, Pessoa

from .models import MovimentoConta, OrigemMovimento, StatusMovimento, StatusParcela, TipoMovimento
from .servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

MOVIMENTO_INEXISTENTE = "movimento_inexistente"
POR_PAGINA = 30
MAXIMO_POR_PAGINA = 100


@dataclass(frozen=True)
class ClassificacaoManual:
    classificacao_id: int
    principal: bool = False


@dataclass(frozen=True)
class ParcelaManual:
    data_vencimento: date
    valor: Decimal


@dataclass(frozen=True)
class ContaManual:
    tipo: str
    contraparte_id: int
    valor_total: Decimal
    classificacoes: tuple[ClassificacaoManual, ...]
    parcelas: tuple[ParcelaManual, ...]
    faturado_id: int | None = None
    # Obrigatória e nomeada: uma por formulário aberto, nunca reaproveitada.
    chave_idempotencia: UUID = field(kw_only=True)


@dataclass(frozen=True)
class ClassificacaoDoMovimento:
    id: int
    codigo: str
    descricao: str
    principal: bool


@dataclass(frozen=True)
class ParcelaDoMovimento:
    numero: int
    data_vencimento: date
    valor: Decimal
    status: str


@dataclass(frozen=True)
class ResumoMovimento:
    id: int
    tipo: str
    origem: str
    status: str
    contraparte_id: int
    contraparte_nome: str
    faturado_id: int | None
    faturado_nome: str | None
    valor_total: Decimal
    criado_em: datetime
    quantidade_parcelas: int
    proximo_vencimento: date | None


@dataclass(frozen=True)
class DetalheMovimento:
    id: int
    tipo: str
    origem: str
    status: str
    contraparte_id: int
    contraparte_nome: str
    faturado_id: int | None
    faturado_nome: str | None
    valor_total: Decimal
    criado_em: datetime
    classificacoes: tuple[ClassificacaoDoMovimento, ...]
    parcelas: tuple[ParcelaDoMovimento, ...]


@dataclass(frozen=True)
class PaginaDeMovimentos:
    itens: tuple[ResumoMovimento, ...]
    pagina: int
    total_paginas: int
    total: int


def _erro(mensagem, codigo):
    return ValidationError(mensagem, code=codigo)


def _identificador(valor, nome, opcional=False):
    if opcional and valor is None:
        return None
    # bool é subclasse de int: True não é o cadastro 1.
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser um inteiro.")
    return valor


def _escolha(valor, opcoes, nome):
    if valor is not None and valor not in opcoes:
        raise ValueError(f"{nome} desconhecido: {valor!r}.")
    return valor


def _sequencia(valores, tipo, mensagem, codigo):
    # Uma só leitura, como em registrar_movimento(): um gerador chegaria vazio.
    try:
        valores = tuple(valores)
    except TypeError:
        raise _erro(mensagem, codigo) from None
    if any(not isinstance(valor, tipo) for valor in valores):
        raise _erro(mensagem, codigo)
    return valores


def _pessoa(pessoas, pessoa_id):
    pessoa = pessoas.get(pessoa_id)
    if pessoa is None:
        raise _erro("Pessoa não encontrada; selecione um cadastro existente.", "pessoa_inexistente")
    return pessoa


def _dados(conta):
    """ContaManual → DadosMovimento oficial, sem gravar nada."""
    if not isinstance(conta, ContaManual):
        raise TypeError("Informe uma ContaManual.")
    if not isinstance(conta.chave_idempotencia, UUID):
        raise _erro("A solicitação expirou; recarregue o formulário.", "chave_idempotencia")
    contraparte_id = _identificador(conta.contraparte_id, "contraparte_id")
    faturado_id = _identificador(conta.faturado_id, "faturado_id", opcional=True)
    itens = _sequencia(conta.classificacoes, ClassificacaoManual,
                       "Informe as classificações em uma lista.", "classificacao")
    parcelas = _sequencia(conta.parcelas, ParcelaManual,
                          "Informe as parcelas com vencimento e valor.", "parcela")
    for item in itens:
        _identificador(item.classificacao_id, "classificacao_id")

    # Leitura simples: registrar_movimento() relê com bloqueio e revalida.
    pessoas = Pessoa.objects.in_bulk({contraparte_id, faturado_id} - {None})
    classificacoes = Classificacao.objects.in_bulk({item.classificacao_id for item in itens})
    if any(item.classificacao_id not in classificacoes for item in itens):
        raise _erro("Classificação não encontrada.", "classificacao_inexistente")

    return DadosMovimento(
        tipo=conta.tipo,
        origem=OrigemMovimento.MANUAL,
        contraparte=_pessoa(pessoas, contraparte_id),
        faturado=_pessoa(pessoas, faturado_id) if faturado_id is not None else None,
        valor_total=conta.valor_total,
        classificacoes=tuple(
            ItemClassificacao(classificacoes[item.classificacao_id], principal=item.principal)
            for item in itens
        ),
        parcelas=tuple(
            ItemParcela(numero, parcela.data_vencimento, parcela.valor)
            for numero, parcela in enumerate(parcelas, start=1)
        ),
        chave_idempotencia=conta.chave_idempotencia,
    )


def registrar_conta_manual(conta):
    """Grava a conta a pagar ou a receber; devolve o DetalheMovimento.

    Repetida com a mesma chave e os mesmos dados, devolve o mesmo movimento.
    ValidationError (code) com os códigos de registrar_movimento(), mais
    chave_idempotencia e solicitacao_ja_registrada; nada é gravado em caso de
    erro. TypeError para identificadores que não são int.
    """
    movimento, _ = registrar_movimento(_dados(conta))
    return consultar_movimento(movimento.pk)


def _movimentos():
    return MovimentoConta.objects.select_related("contraparte", "faturado")


def _comum(movimento):
    faturado = movimento.faturado
    return dict(
        id=movimento.pk, tipo=movimento.tipo, origem=movimento.origem, status=movimento.status,
        contraparte_id=movimento.contraparte_id,
        contraparte_nome=movimento.contraparte.razao_social,
        faturado_id=movimento.faturado_id,
        faturado_nome=faturado.razao_social if faturado else None,
        valor_total=movimento.valor_total, criado_em=movimento.criado_em,
    )


def listar_movimentos(
    *, tipo=None, origem=None, status=None, contraparte_id=None, classificacao_id=None,
    pagina=1, por_pagina=POR_PAGINA,
):
    """Movimentos do mais recente ao mais antigo, paginados; só leitura.

    Filtros opcionais e combináveis. Valor fora das opções → ValueError; a
    tela valida as escolhas antes. Página fora do intervalo → a mais próxima.
    O vencimento e a quantidade contam só parcelas ATIVAS.
    """
    _escolha(tipo, TipoMovimento.values, "tipo")
    _escolha(origem, OrigemMovimento.values, "origem")
    _escolha(status, StatusMovimento.values, "status")
    _identificador(contraparte_id, "contraparte_id", opcional=True)
    _identificador(classificacao_id, "classificacao_id", opcional=True)
    _identificador(pagina, "pagina")
    _identificador(por_pagina, "por_pagina")
    if not 1 <= por_pagina <= MAXIMO_POR_PAGINA:
        raise ValueError(f"por_pagina deve estar entre 1 e {MAXIMO_POR_PAGINA}.")

    filtros = {
        "tipo": tipo, "origem": origem, "status": status, "contraparte_id": contraparte_id,
        "classificacoes__classificacao_id": classificacao_id,
    }
    movimentos = _movimentos().filter(**{c: v for c, v in filtros.items() if v is not None})
    ativas = Q(parcelas__status=StatusParcela.ATIVA)
    movimentos = movimentos.annotate(
        quantidade_parcelas=Count("parcelas", filter=ativas, distinct=True),
        proximo_vencimento=Min("parcelas__data_vencimento", filter=ativas),
    ).order_by("-criado_em", "-id")

    folha = Paginator(movimentos, por_pagina).get_page(pagina)
    itens = tuple(
        ResumoMovimento(
            **_comum(movimento),
            quantidade_parcelas=movimento.quantidade_parcelas,
            proximo_vencimento=movimento.proximo_vencimento,
        )
        for movimento in folha
    )
    return PaginaDeMovimentos(itens, folha.number, folha.paginator.num_pages, folha.paginator.count)


def consultar_movimento(movimento_id):
    """Movimento com classificações (principal primeiro) e todas as parcelas."""
    _identificador(movimento_id, "movimento_id")
    movimento = _movimentos().filter(pk=movimento_id).first()
    if movimento is None:
        raise _erro("Movimento não encontrado.", MOVIMENTO_INEXISTENTE)
    vinculos = movimento.classificacoes.select_related("classificacao").order_by("-principal", "id")
    return DetalheMovimento(
        **_comum(movimento),
        classificacoes=tuple(
            ClassificacaoDoMovimento(
                vinculo.classificacao_id, vinculo.classificacao.codigo,
                vinculo.classificacao.descricao, vinculo.principal,
            )
            for vinculo in vinculos
        ),
        parcelas=tuple(
            ParcelaDoMovimento(p.numero, p.data_vencimento, p.valor, p.status)
            for p in movimento.parcelas.order_by("numero")
        ),
    )
