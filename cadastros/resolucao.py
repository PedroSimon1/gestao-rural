"""Resolução das pessoas da nota fiscal (GR-22, F-4).

Para cada parte da nota (fornecedor, faturado), decide qual Pessoa será usada
no lançamento: a existente, uma nova ou um cadastro incompleto regularizado.
Duas operações, com as mesmas regras (_planejar):

- avaliar_partes(partes): só leitura. Diz o que falta para cada parte, sem
  gravar e sem bloquear linhas; serve para a tela pedir as decisões.
- resolver_partes(partes): grava, numa transação (savepoint quando já houver
  uma, como na confirmação da F-5), só o que as decisões de cada parte
  autorizam. Qualquer recusa desfaz tudo o que a chamada gravou.

Regras aprovadas aplicadas:

- Pessoa identificada só pelo CPF/CNPJ normalizado, nunca pelo nome (DQ-08).
  O documento é o escolhido na conferência; o tipo não é deduzido pelo papel
  (D-03): qualquer papel aceita CPF ou CNPJ.
- Documento ausente ou inválido bloqueia: nada é inventado nem gravado (DQ-05).
- Criar pessoa, atribuir papel, reativar pessoa ou papel e regularizar
  cadastro incompleto exigem a decisão explícita correspondente (DQ-07, D-04).
  Decisão é autorização, não ordem: uma decisão desnecessária é ignorada.
- Cadastro incompleto só é usado se for selecionado e regularizado com o
  documento da nota, no mesmo registro (DQ-05, D-04); sem isso, a resolução
  recusa com pessoa_incompleta e nenhum lançamento pode usá-lo.
- Partes com o mesmo documento resolvem para a mesma pessoa, com um papel
  para cada parte, sem duplicar o cadastro.

Os códigos de "decisão ausente" são os mesmos de registrar_movimento()
(pessoa_inexistente, pessoa_inativa, papel_ausente, papel_inativo,
pessoa_incompleta). Nenhum movimento é criado e nenhuma análise é tocada.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from .models import Papel, PapelPessoa, Pessoa, Status
from .validators import normalizar_documento, validar_documento


class Decisao(StrEnum):
    # Ordem da declaração = ordem de exigência e de aplicação.
    REGULARIZAR = "REGULARIZAR"
    CRIAR_PESSOA = "CRIAR_PESSOA"
    REATIVAR_PESSOA = "REATIVAR_PESSOA"
    ATRIBUIR_PAPEL = "ATRIBUIR_PAPEL"
    REATIVAR_PAPEL = "REATIVAR_PAPEL"


# Código da recusa quando a decisão necessária não foi dada.
CODIGO_SEM_DECISAO = {
    Decisao.REGULARIZAR: "pessoa_incompleta",
    Decisao.CRIAR_PESSOA: "pessoa_inexistente",
    Decisao.REATIVAR_PESSOA: "pessoa_inativa",
    Decisao.ATRIBUIR_PAPEL: "papel_ausente",
    Decisao.REATIVAR_PAPEL: "papel_inativo",
}

# Bloqueios: nenhuma decisão resolve; é preciso corrigir a conferência.
DOCUMENTO_AUSENTE = "documento_ausente"
DOCUMENTO_INVALIDO = "documento_invalido"
NOME_AUSENTE = "nome_ausente"
NOME_INVALIDO = "nome_invalido"
NOMES_DIVERGENTES = "nomes_divergentes"
DOCUMENTO_EM_USO = "documento_em_uso"
SELECAO_INVALIDA = "selecao_invalida"
CADASTRO_CONCORRENTE = "cadastro_concorrente"

_MENSAGENS = {
    DOCUMENTO_AUSENTE: "informe o CPF ou o CNPJ.",
    DOCUMENTO_INVALIDO: "o CPF ou o CNPJ é inválido.",
    NOME_AUSENTE: "informe o nome ou a razão social para o novo cadastro.",
    NOME_INVALIDO: "o nome ou a razão social é longo demais.",
    NOMES_DIVERGENTES: "o mesmo documento aparece com nomes diferentes na nota.",
    DOCUMENTO_EM_USO: "o documento já pertence a outro cadastro.",
    SELECAO_INVALIDA: "o cadastro incompleto selecionado não está disponível.",
    "pessoa_incompleta": "confirme a regularização do cadastro incompleto.",
    "pessoa_inexistente": "confirme a criação do cadastro.",
    "pessoa_inativa": "o cadastro está inativo; confirme a reativação.",
    "papel_ausente": "confirme a atribuição do papel.",
    "papel_inativo": "o papel está inativo; confirme a reativação.",
}

_TAMANHO_DO_NOME = Pessoa._meta.get_field("razao_social").max_length


@dataclass(frozen=True)
class ParteNota:
    """Uma parte da nota, com os valores finais da conferência (F-3)."""

    papel: str
    documento: str | None
    nome: str | None = None
    decisoes: frozenset = frozenset()
    # Seleção manual de um cadastro incompleto existente (D-04).
    pessoa_incompleta_id: int | None = None


@dataclass(frozen=True)
class AvaliacaoParte:
    papel: str
    documento: str | None
    # Pessoa que será usada; None quando será criada ou houver bloqueio.
    pessoa_id: int | None
    decisoes_necessarias: frozenset
    decisoes_faltando: frozenset
    bloqueio: str | None

    @property
    def pronta(self):
        return self.bloqueio is None and not self.decisoes_faltando


@dataclass(frozen=True)
class PessoaResolvida:
    papel: str
    pessoa: Pessoa
    papel_pessoa: PapelPessoa
    # Decisões aplicadas a esta parte, na ordem de Decisao.
    acoes: tuple


@dataclass
class _Item:
    parte: ParteNota
    documento: str | None = None
    nome: str | None = None
    pessoa: Pessoa | None = None
    vinculo: PapelPessoa | None = None
    exigidas: set = field(default_factory=set)
    bloqueio: str | None = None
    regularizar: bool = False

    def faltando(self):
        return frozenset(self.exigidas - self.parte.decisoes)


class _Concorrencia(Exception):
    """Outra transação gravou o mesmo documento entre o planejamento e a gravação."""


_NOVA = object()


def _texto(valor, campo):
    if valor is not None and not isinstance(valor, str):
        raise TypeError(f"{campo} deve ser texto ou None.")
    return " ".join((valor or "").split()) or None


def _entrada(partes):
    if isinstance(partes, ParteNota):
        raise TypeError("Informe as partes em uma lista.")
    partes = tuple(partes)
    normalizadas = []
    for parte in partes:
        if not isinstance(parte, ParteNota):
            raise TypeError("Cada parte deve ser uma ParteNota.")
        if parte.papel not in Papel.values:
            raise ValueError(f"Papel desconhecido: {parte.papel!r}.")
        selecionada = parte.pessoa_incompleta_id
        if selecionada is not None and (type(selecionada) is not int or selecionada < 1):
            raise TypeError("pessoa_incompleta_id deve ser um inteiro positivo ou None.")
        normalizadas.append(ParteNota(
            papel=parte.papel,
            documento=normalizar_documento(_texto(parte.documento, "documento")) or None,
            nome=_texto(parte.nome, "nome"),
            # ValueError para uma decisão desconhecida.
            decisoes=frozenset(Decisao(decisao) for decisao in parte.decisoes),
            pessoa_incompleta_id=selecionada,
        ))
    return tuple(normalizadas)


def _documento_valido(documento):
    try:
        validar_documento(documento)
    except ValidationError:
        return False
    return True


def _carregar(partes, bloquear):
    """Pessoas dos documentos válidos e dos incompletos selecionados, com os papéis."""
    documentos = {p.documento for p in partes if p.documento and _documento_valido(p.documento)}
    ids = {p.pessoa_incompleta_id for p in partes if p.pessoa_incompleta_id is not None}
    if not documentos and not ids:
        return {}, {}, {}
    # Mesma normalização de Pessoa.objects.por_documento; uma consulta por pk
    # para bloquear sempre na mesma ordem (sem deadlock entre resoluções).
    pessoas = Pessoa.objects.filter(Q(documento__in=documentos) | Q(pk__in=ids)).order_by("pk")
    if bloquear:
        # FOR NO KEY UPDATE, como em registrar_movimento: não conflita com as
        # FKs dos movimentos e barra inativação ou regularização concorrente.
        pessoas = pessoas.select_for_update(no_key=True)
    pessoas = list(pessoas)
    papeis = PapelPessoa.objects.filter(pessoa_id__in=[p.pk for p in pessoas]).order_by("pk")
    if bloquear:
        papeis = papeis.select_for_update(no_key=True)
    por_documento = {p.documento: p for p in pessoas if p.documento}
    por_id = {p.pk: p for p in pessoas}
    papeis = {(v.pessoa_id, v.papel): v for v in papeis}
    return por_documento, por_id, papeis


def _planejar(partes, por_documento, por_id, papeis):
    pessoas = dict(por_documento)  # documento → Pessoa existente ou _NOVA
    regularizadas = {}  # pk do incompleto → documento que receberá
    novas = {}  # documento → itens que pedem a criação
    itens = []
    for parte in partes:
        item = _Item(parte, documento=parte.documento, nome=parte.nome)
        itens.append(item)
        documento = parte.documento
        if documento is None:
            item.bloqueio = DOCUMENTO_AUSENTE
            continue
        if not _documento_valido(documento):
            item.bloqueio = DOCUMENTO_INVALIDO
            continue

        if parte.pessoa_incompleta_id is not None:
            pessoa = por_id.get(parte.pessoa_incompleta_id)
            if pessoa is None or pessoa.documentacao_completa:
                item.bloqueio = SELECAO_INVALIDA
                continue
            destino = regularizadas.get(pessoa.pk)
            if destino is None:
                if documento in pessoas:
                    item.bloqueio = DOCUMENTO_EM_USO
                    continue
                regularizadas[pessoa.pk] = documento
                pessoas[documento] = pessoa
                item.regularizar = True
            elif destino != documento:
                item.bloqueio = SELECAO_INVALIDA
                continue
            # Cada parte que usa o incompleto consente com a regularização.
            item.exigidas.add(Decisao.REGULARIZAR)
        else:
            pessoa = pessoas.get(documento)
            if pessoa is None or pessoa is _NOVA:
                # Pessoa nova: o papel é atribuído na criação, com o consentimento
                # de cada parte que a usa.
                item.exigidas.add(Decisao.CRIAR_PESSOA)
                pessoas[documento] = _NOVA
                novas.setdefault(documento, []).append(item)
                continue
        item.pessoa = pessoa
        if pessoa.status != Status.ATIVO:
            item.exigidas.add(Decisao.REATIVAR_PESSOA)
        item.vinculo = vinculo = papeis.get((pessoa.pk, parte.papel))
        if vinculo is None:
            item.exigidas.add(Decisao.ATRIBUIR_PAPEL)
        elif vinculo.status != Status.ATIVO:
            item.exigidas.add(Decisao.REATIVAR_PAPEL)

    for grupo in novas.values():
        nomes = list(dict.fromkeys(item.nome for item in grupo if item.nome))
        if not nomes:
            bloqueio, nome = NOME_AUSENTE, None
        elif len(nomes) > 1:
            bloqueio, nome = NOMES_DIVERGENTES, None
        elif len(nomes[0]) > _TAMANHO_DO_NOME:
            bloqueio, nome = NOME_INVALIDO, None
        else:
            bloqueio, nome = None, nomes[0]
        for item in grupo:
            item.bloqueio, item.nome = bloqueio, nome
    return itens


def avaliar_partes(partes):
    """Só leitura: o que cada parte exige antes de resolver_partes()."""
    partes = _entrada(partes)
    itens = _planejar(partes, *_carregar(partes, bloquear=False))
    return tuple(
        AvaliacaoParte(
            papel=item.parte.papel,
            documento=item.documento,
            pessoa_id=item.pessoa.pk if item.pessoa is not None and not item.bloqueio else None,
            decisoes_necessarias=frozenset(item.exigidas),
            decisoes_faltando=item.faltando(),
            bloqueio=item.bloqueio,
        )
        for item in itens
    )


def _recusa(item, codigo):
    rotulo = Papel(item.parte.papel).label
    return ValidationError(
        f"{rotulo}: {_MENSAGENS[codigo]}", code=codigo, params={"papel": item.parte.papel}
    )


def _exigir(itens):
    for item in itens:
        if item.bloqueio:
            raise _recusa(item, item.bloqueio)
        for decisao in Decisao:
            if decisao in item.faltando():
                raise _recusa(item, CODIGO_SEM_DECISAO[decisao])


def _regularizar(pessoa, documento):
    try:
        pessoa.regularizar(documento)
    except ValidationError as erro:
        codigos = {e.code for erros in getattr(erro, "error_dict", {}).values() for e in erros}
        if "unique" in codigos:
            raise _Concorrencia from erro
        raise


def _criar(documento, nome):
    try:
        with transaction.atomic():
            return Pessoa.objects.create(documento=documento, razao_social=nome)
    except IntegrityError as erro:
        # Índice único: outra transação criou o mesmo documento e fez COMMIT.
        raise _Concorrencia from erro


def _gravar(partes):
    itens = _planejar(partes, *_carregar(partes, bloquear=True))
    _exigir(itens)
    criadas = {}
    resolvidas = []
    for item in itens:
        papel = item.parte.papel
        if item.regularizar:
            _regularizar(item.pessoa, item.documento)
        if Decisao.CRIAR_PESSOA in item.exigidas:
            if item.documento not in criadas:
                criadas[item.documento] = _criar(item.documento, item.nome)
            pessoa = criadas[item.documento]
            vinculo, _ = pessoa.atribuir_papel(papel)
        else:
            pessoa = item.pessoa
            if Decisao.REATIVAR_PESSOA in item.exigidas:
                pessoa.reativar()
            if Decisao.ATRIBUIR_PAPEL in item.exigidas:
                vinculo, _ = pessoa.atribuir_papel(papel)
            else:
                vinculo = item.vinculo
                if Decisao.REATIVAR_PAPEL in item.exigidas:
                    vinculo.reativar()
        resolvidas.append(PessoaResolvida(
            papel=papel, pessoa=pessoa, papel_pessoa=vinculo,
            acoes=tuple(decisao for decisao in Decisao if decisao in item.exigidas),
        ))
    return tuple(resolvidas)


def resolver_partes(partes):
    """Pessoa e papel de cada parte, gravando só o que as decisões autorizam.

    Devolve uma PessoaResolvida por parte, na mesma ordem. Recusa com
    ValidationError (code em CODIGO_SEM_DECISAO ou nos bloqueios deste módulo,
    params={"papel": ...}) sem deixar nada gravado. Dentro de uma transação
    externa, os bloqueios das pessoas valem até o COMMIT dela.
    """
    partes = _entrada(partes)
    for tentativa in range(2):
        try:
            with transaction.atomic():
                return _gravar(partes)
        except _Concorrencia:
            # Uma nova tentativa relê o banco: o cadastro criado pela outra
            # transação passa a ser o existente, sujeito às mesmas decisões.
            if tentativa:
                raise ValidationError(
                    "Os cadastros mudaram durante a confirmação; confira e tente novamente.",
                    code=CADASTRO_CONCORRENTE,
                ) from None
