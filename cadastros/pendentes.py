"""Cadastro pendente: salvar, listar e regularizar pessoas incompletas (GR-22, F-6).

Regras aprovadas aplicadas (DQ-05, D-04/DQ-13):

- Cadastro incompleto só para quem não tem CPF/CNPJ válido na nota: com
  documento válido, a pessoa é cadastrada completa (F-4). Nenhum documento
  fictício ou inválido é guardado.
- "Salvar cadastro pendente" é uma ação separada da confirmação financeira,
  com consentimento explícito: não toca a análise nem cria movimento. O papel é
  o escolhido pelo usuário para a parte da nota, nunca deduzido.
- Lançamento bloqueado até a regularização: registrar_movimento() e a F-4 já
  recusam com pessoa_incompleta; nada aqui muda isso.
- Seleção manual de um incompleto existente: listar_incompletos() devolve a
  lista, sem busca nem filtro por nome (nada é identificado pelo nome). A
  seleção para o lançamento é a da F-4 (pessoa_incompleta_id + REGULARIZAR).
- Regularização no mesmo registro, preservando os vínculos (Pessoa.regularizar).

O destino da análise depois de salvar o cadastro pendente (T-05) não é
decidido aqui: estes serviços nunca leem nem alteram AnalisePendente.
"""

import unicodedata
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Papel, Pessoa, SituacaoDocumental
from .resolucao import (
    DOCUMENTO_AUSENTE, DOCUMENTO_EM_USO, DOCUMENTO_INVALIDO, NOME_AUSENTE, NOME_INVALIDO,
    SELECAO_INVALIDA,
)
from .validators import normalizar_documento, validar_documento

CONSENTIMENTO_AUSENTE = "consentimento_ausente"
# A nota tem CPF/CNPJ válido: a pessoa deve ser cadastrada completa (F-4).
DOCUMENTO_VALIDO = "documento_valido"

_MENSAGENS = {
    CONSENTIMENTO_AUSENTE: "Confirme que deseja salvar o cadastro como pendente.",
    DOCUMENTO_VALIDO: "O documento informado é válido: cadastre a pessoa com ele.",
    NOME_AUSENTE: "Informe o nome ou a razão social.",
    NOME_INVALIDO: "O nome ou a razão social é inválido ou longo demais.",
    DOCUMENTO_AUSENTE: "Informe o CPF ou o CNPJ para regularizar o cadastro.",
    DOCUMENTO_INVALIDO: "O CPF ou o CNPJ é inválido.",
    DOCUMENTO_EM_USO: "O documento já pertence a outro cadastro.",
    SELECAO_INVALIDA: "O cadastro pendente selecionado não está disponível.",
}

_TAMANHO_DO_NOME = Pessoa._meta.get_field("razao_social").max_length
# Caracteres de controle (o PostgreSQL recusa NUL) e surrogates isolados.
_CATEGORIAS_PROIBIDAS = {"Cc", "Cs"}


@dataclass(frozen=True)
class CadastroPendente:
    id: int
    razao_social: str
    status: str
    # (papel, status) de cada papel, na ordem do papel.
    papeis: tuple


def _erro(codigo):
    return ValidationError(_MENSAGENS[codigo], code=codigo)


def _papel(papel):
    if papel not in Papel.values:
        raise ValueError(f"Papel desconhecido: {papel!r}.")
    return papel


def _nome(razao_social):
    if razao_social is not None and not isinstance(razao_social, str):
        raise TypeError("razao_social deve ser texto ou None.")
    nome = " ".join((razao_social or "").split())
    if not nome:
        raise _erro(NOME_AUSENTE)
    if len(nome) > _TAMANHO_DO_NOME or any(
        unicodedata.category(caractere) in _CATEGORIAS_PROIBIDAS for caractere in nome
    ):
        raise _erro(NOME_INVALIDO)
    return nome


def _documento(documento):
    """Documento normalizado e validado; ValidationError com o código estável."""
    if documento is not None and not isinstance(documento, str):
        raise TypeError("documento deve ser texto ou None.")
    normalizado = normalizar_documento(documento)
    if not normalizado:
        raise _erro(DOCUMENTO_AUSENTE)
    try:
        validar_documento(normalizado)
    except ValidationError:
        raise _erro(DOCUMENTO_INVALIDO) from None
    return normalizado


def _cadastro(pessoa):
    # all(): aproveita o prefetch da listagem (uma consulta para todos).
    papeis = tuple(sorted((vinculo.papel, vinculo.status) for vinculo in pessoa.papeis.all()))
    return CadastroPendente(pessoa.pk, pessoa.razao_social, pessoa.status, papeis)


def salvar_cadastro_pendente(razao_social, papel, *, consentimento, documento_extraido=None):
    """Cria uma Pessoa INCOMPLETA com o papel escolhido; devolve CadastroPendente.

    `consentimento`: precisa ser exatamente True (a confirmação do usuário).
    `documento_extraido`: o CPF/CNPJ que a nota trouxe para a parte, como veio
    (ou None); válido → documento_valido (cadastrar completa pela F-4).
    Inválido ou ausente nunca é guardado. Pessoa e papel são gravados juntos.
    """
    papel = _papel(papel)
    if consentimento is not True:
        raise _erro(CONSENTIMENTO_AUSENTE)
    nome = _nome(razao_social)
    try:
        _documento(documento_extraido)
    except ValidationError:
        pass
    else:
        raise _erro(DOCUMENTO_VALIDO)

    with transaction.atomic():
        pessoa = Pessoa.objects.create(
            razao_social=nome, situacao_documental=SituacaoDocumental.INCOMPLETO
        )
        pessoa.atribuir_papel(papel)
    return _cadastro(pessoa)


def listar_incompletos(papel=None):
    """Cadastros incompletos para seleção manual, em ordem de nome e id.

    Com `papel`, só os que têm esse papel (em qualquer status). Pessoas e
    papéis inativos aparecem com o status: usar um deles exige a decisão de
    reativar (F-4). Sem busca nem filtro por nome.
    """
    pessoas = Pessoa.objects.incompletas().order_by("razao_social", "id")
    if papel is not None:
        pessoas = pessoas.filter(papeis__papel=_papel(papel)).distinct()
    return tuple(_cadastro(pessoa) for pessoa in pessoas.prefetch_related("papeis"))


def regularizar_cadastro_pendente(pessoa_id, documento):
    """Completa o cadastro pendente com o CPF/CNPJ, no mesmo registro.

    Ação avulsa (fora do lançamento). Devolve a Pessoa completa. Erros
    (ValidationError, code): documento_ausente, documento_invalido,
    documento_em_uso, selecao_invalida (inexistente ou já completo).
    """
    if isinstance(pessoa_id, bool) or not isinstance(pessoa_id, int):
        raise TypeError("pessoa_id deve ser um inteiro.")
    documento = _documento(documento)
    with transaction.atomic():
        # Bloqueio: duas regularizações do mesmo cadastro não se cruzam.
        pessoa = Pessoa.objects.select_for_update().filter(pk=pessoa_id).first()
        if pessoa is None or pessoa.documentacao_completa:
            raise _erro(SELECAO_INVALIDA)
        try:
            pessoa.regularizar(documento)
        except ValidationError as erro:
            codigos = {e.code for erros in getattr(erro, "error_dict", {}).values() for e in erros}
            if "unique" in codigos:
                raise _erro(DOCUMENTO_EM_USO) from None
            raise
    return pessoa
