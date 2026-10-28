"""Identidade fiscal da nota e proteção contra lançamento duplicado (D-01, GR-22).

Regras aprovadas pela equipe em 27/10/2026:

- D-01: a chave de acesso válida identifica a nota; sem ela, CNPJ do emitente
  + modelo + série + número. Dados insuficientes bloqueiam o lançamento, e a
  identidade é única no banco, inclusive em transações concorrentes.
- T-01: a identidade fica em NotaFiscalLancada, 1:1 com o movimento.
- T-04: chave inválida (formato ou DV) ou divergente dos campos informados
  bloqueia o lançamento.
- T-06: só NF-e (55) e NFC-e (65) com emitente CNPJ; NFS-e, outros modelos e
  emitente com CPF ficam bloqueados até decisão própria.
- T-07: um movimento cancelado não libera a identidade.

Chave de acesso (NT Conjunta 2025.001): 44 posições; as 12 primeiras do CNPJ
do emitente (posições 7 a 18) aceitam letras maiúsculas. O DV é o módulo 11
com o valor de cada caractere = código ASCII − 48 e pesos 2 a 9 da direita
para a esquerda, a mesma regra do CNPJ alfanumérico.

Nada aqui cria movimento: registrar_identidade_fiscal() grava a identidade de
um movimento NOTA_FISCAL já gravado, dentro da transação de quem chamou (o
serviço de lançamento da GR-22 chamará registrar_movimento() e esta função na
mesma transação de confirmar_analise()).
"""

import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

# Mesmo módulo 11 (ASCII − 48) do CNPJ alfanumérico, já usado pelo Extrator e
# por cadastros/validators.py.
from agents.extrator.schemas import _digito_verificador, cnpj_dv_valido
from cadastros.validators import TIPO_CNPJ, normalizar_documento, tipo_do_documento

from .models import (
    FORMATO_CHAVE_ACESSO, NUMERO_MAXIMO, SERIE_MAXIMA, ModeloNota, MovimentoConta,
    NotaFiscalLancada, OrigemMovimento,
)

TAMANHO_CHAVE = 44
# Pesos 2 a 9 da direita para a esquerda sobre as 43 primeiras posições.
PESOS_DA_CHAVE = tuple(2 + (posicao % 8) for posicao in range(TAMANHO_CHAVE - 1))[::-1]
_SEPARADORES_DA_CHAVE = re.compile(r"[\s.\-/]")


@dataclass(frozen=True)
class IdentidadeFiscal:
    emitente_cnpj: str
    modelo: str
    serie: int
    numero: int
    chave_acesso: str | None = None


def _erro(mensagem, codigo):
    return ValidationError(mensagem, code=codigo)


def normalizar_chave(valor):
    """Remove espaços e separadores e põe as letras em maiúsculas."""
    return _SEPARADORES_DA_CHAVE.sub("", valor or "").upper()


def validar_chave_acesso(chave):
    """Chave normalizada, com formato e DV conferidos; ValidationError se inválida."""
    if not isinstance(chave, str):
        raise _erro("A chave de acesso deve ser texto.", "chave_acesso_invalida")
    chave = normalizar_chave(chave)
    if not re.fullmatch(FORMATO_CHAVE_ACESSO, chave):
        raise _erro("Chave de acesso com formato inválido.", "chave_acesso_invalida")
    if _digito_verificador(chave[:-1], PESOS_DA_CHAVE) != chave[-1]:
        raise _erro("Chave de acesso com dígito verificador inválido.", "chave_acesso_invalida")
    return chave


def _inteiro(valor, minimo, maximo, rotulo, codigo):
    # Texto com zeros à esquerda ("001") é aceito; bool não conta como número.
    # [0-9], e não isdigit(): "²" passaria e o int() levantaria ValueError.
    if isinstance(valor, str) and re.fullmatch(r"[0-9]+", valor.strip()):
        valor = int(valor.strip())
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        raise _erro(f"{rotulo} inválido.", codigo)
    return valor


def _emitente(documento):
    documento = normalizar_documento(documento) if isinstance(documento, str) else documento
    if not documento:
        # "./-" vira vazio depois de normalizado: dados insuficientes (D-01).
        raise _erro("Informe o CNPJ do emitente.", "identidade_fiscal_insuficiente")
    if not isinstance(documento, str) or tipo_do_documento(documento) != TIPO_CNPJ:
        raise _erro(
            "Só notas de emitente com CNPJ são aceitas.", "identidade_fiscal_nao_suportada"
        )
    if not cnpj_dv_valido(documento):
        raise _erro("CNPJ do emitente inválido.", "emitente_invalido")
    return documento


def _modelo(valor):
    modelo = None
    if isinstance(valor, (str, int)) and not isinstance(valor, bool):
        modelo = str(valor).strip()
    if modelo not in ModeloNota.values:
        raise _erro("Só NF-e (55) e NFC-e (65) são aceitas.", "identidade_fiscal_nao_suportada")
    return modelo


def _da_chave(chave):
    try:
        return IdentidadeFiscal(
            emitente_cnpj=_emitente(chave[6:20]),
            modelo=_modelo(chave[20:22]),
            serie=_inteiro(chave[22:25], 0, SERIE_MAXIMA, "Série", "chave_acesso_invalida"),
            numero=_inteiro(chave[25:34], 1, NUMERO_MAXIMO, "Número", "chave_acesso_invalida"),
            chave_acesso=chave,
        )
    except ValidationError as erro:
        if erro.code == "emitente_invalido":
            # DV da chave correto, mas o emitente não é um CNPJ válido
            # (ex.: emitente pessoa física): não suportado (T-06).
            raise _erro(
                "Só notas de emitente com CNPJ são aceitas.", "identidade_fiscal_nao_suportada"
            ) from None
        raise


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _diverge(valor, normalizar, esperado):
    # Com chave válida, qualquer valor informado diferente do da chave
    # diverge, inclusive um valor que nem seria válido sozinho (T-04).
    try:
        return normalizar(valor) != esperado
    except ValidationError:
        return True


def identificar_nota(
    *, chave_acesso=None, emitente_cnpj=None, modelo=None, serie=None, numero=None
):
    """IdentidadeFiscal da nota (D-01); só leitura, nada é gravado.

    Com chave: a chave é validada, os campos são derivados dela, e qualquer
    campo informado precisa ser igual ao da chave (T-04). Sem chave: os quatro
    campos são obrigatórios.

    Códigos de ValidationError: chave_acesso_invalida, identidade_fiscal_divergente,
    identidade_fiscal_insuficiente, identidade_fiscal_nao_suportada,
    emitente_invalido, serie_invalida, numero_invalido.
    """
    if not _vazio(chave_acesso):
        identidade = _da_chave(validar_chave_acesso(chave_acesso))
        informados = {
            "emitente_cnpj": (emitente_cnpj, _emitente),
            "modelo": (modelo, _modelo),
            "serie": (serie, lambda v: _inteiro(v, 0, SERIE_MAXIMA, "Série", "serie_invalida")),
            "numero": (numero, lambda v: _inteiro(v, 1, NUMERO_MAXIMO, "Número", "numero_invalido")),
        }
        for campo, (valor, normalizar) in informados.items():
            if _vazio(valor):
                continue
            if _diverge(valor, normalizar, getattr(identidade, campo)):
                raise _erro(
                    "A chave de acesso não corresponde aos dados informados da nota.",
                    "identidade_fiscal_divergente",
                )
        return identidade

    if any(_vazio(valor) for valor in (emitente_cnpj, modelo, serie, numero)):
        raise _erro(
            "Informe a chave de acesso ou o CNPJ do emitente, o modelo, a série e o número.",
            "identidade_fiscal_insuficiente",
        )
    return IdentidadeFiscal(
        emitente_cnpj=_emitente(emitente_cnpj),
        modelo=_modelo(modelo),
        serie=_inteiro(serie, 0, SERIE_MAXIMA, "Série", "serie_invalida"),
        numero=_inteiro(numero, 1, NUMERO_MAXIMO, "Número", "numero_invalido"),
    )


def _filtro(identidade):
    return {
        "emitente_cnpj": identidade.emitente_cnpj, "modelo": identidade.modelo,
        "serie": identidade.serie, "numero": identidade.numero,
    }


def nota_lancada(identidade):
    """NotaFiscalLancada com esta identidade, ou None (só leitura).

    Basta a combinação: a constraint de coerência garante que a mesma chave
    tem sempre os mesmos emitente, modelo, série e número.
    """
    return NotaFiscalLancada.objects.filter(**_filtro(identidade)).first()


def _mesma(nota, identidade):
    return (
        nota.emitente_cnpj, nota.modelo, nota.serie, nota.numero, nota.chave_acesso,
    ) == (
        identidade.emitente_cnpj, identidade.modelo, identidade.serie, identidade.numero,
        identidade.chave_acesso,
    )


def _duplicada():
    # Sem o id do movimento: quem chamou o obtém com nota_lancada(), se precisar.
    return _erro("Esta nota fiscal já foi lançada.", "nota_ja_lancada")


def _outra_nota_no_movimento():
    return _erro("Este movimento já tem outra nota fiscal.", "movimento_ja_identificado")


def registrar_identidade_fiscal(movimento, identidade):
    """Grava a identidade fiscal do movimento; devolve (NotaFiscalLancada, criada).

    Exige uma transação aberta (RuntimeError fora dela): a identidade é
    gravada na mesma transação do movimento, e um erro aqui precisa desfazer os
    dois. A identidade é revalidada (identificar_nota), mesmo montada à mão.

    Repetir com a mesma identidade para o mesmo movimento devolve a existente
    (acompanha a idempotência de registrar_movimento). A mesma nota em outro
    movimento → nota_ja_lancada, inclusive quando outra transação a grava ao
    mesmo tempo: a segunda espera o COMMIT da primeira no índice único e falha.
    A gravação usa um savepoint; o erro deve desfazer a transação de quem
    chamou (o movimento junto).
    """
    if not isinstance(movimento, MovimentoConta) or movimento.pk is None:
        raise _erro("Informe um movimento já gravado.", "movimento")
    if not isinstance(identidade, IdentidadeFiscal):
        raise _erro("Informe a identidade fiscal da nota.", "identidade_fiscal")
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "registrar_identidade_fiscal() deve rodar na transação que grava o movimento."
        )
    identidade = identificar_nota(
        chave_acesso=identidade.chave_acesso, emitente_cnpj=identidade.emitente_cnpj,
        modelo=identidade.modelo, serie=identidade.serie, numero=identidade.numero,
    )
    if movimento.origem != OrigemMovimento.NOTA_FISCAL:
        raise _erro("Só movimentos de nota fiscal têm identidade fiscal.", "origem_incompativel")

    existente = NotaFiscalLancada.objects.filter(movimento_id=movimento.pk).first()
    if existente is not None:
        if _mesma(existente, identidade):
            return existente, False
        raise _outra_nota_no_movimento()
    if nota_lancada(identidade) is not None:
        raise _duplicada()

    try:
        with transaction.atomic():
            nota = NotaFiscalLancada.objects.create(
                movimento=movimento, chave_acesso=identidade.chave_acesso, **_filtro(identidade)
            )
    except IntegrityError:
        # Outra transação gravou a mesma nota (ou este movimento) entre a
        # busca e o INSERT; o savepoint mantém a transação utilizável.
        existente = NotaFiscalLancada.objects.filter(movimento_id=movimento.pk).first()
        if existente is not None:
            if _mesma(existente, identidade):
                return existente, False
            raise _outra_nota_no_movimento() from None
        if nota_lancada(identidade) is not None:
            raise _duplicada() from None
        raise
    return nota, True
