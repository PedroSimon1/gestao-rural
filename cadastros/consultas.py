"""Consultas de existência do fluxo da nota fiscal (GR-40, FLU-01 a FLU-03).

Respondem se o fornecedor, o faturado e a classificação da despesa já estão
cadastrados, com o ID quando estiverem. São só leitura: nada é criado,
atribuído ou reativado aqui (a gravação é da GR-51, depois da confirmação).

Regras aprovadas por Pedro Simon em 27/10/2026:

- Pessoa é identificada só pelo CPF/CNPJ normalizado (Q-03); não há busca
  pela razão social.
- Documento ausente ou inválido (estrutura ou DV) não é consultado: pelo
  caminho normal, documento inválido nunca é guardado (C-02).
- Pessoa encontrada é EXISTE em qualquer status. O resultado informa o status
  da pessoa e o do papel pedido (ATIVO, INATIVO ou AUSENTE), sem reativar ou
  atribuir nada (T-05).
- Classificação é buscada pelo código do Enum do Classificador (Q-05,
  parcial), em qualquer status.

O documento é revalidado aqui, sem confiar no bloco validacoes do JSON:
os dados podem voltar de fora do servidor antes da confirmação.
"""

from dataclasses import dataclass
from enum import StrEnum

from django.core.exceptions import ValidationError

from .models import Classificacao, Papel, PapelPessoa, Pessoa, TipoClassificacao
from .validators import normalizar_documento, tipo_do_documento, validar_documento


class Situacao(StrEnum):
    EXISTE = "EXISTE"
    NAO_EXISTE = "NAO_EXISTE"
    # Não consultados: sem dado suficiente para buscar no banco.
    DOCUMENTO_AUSENTE = "DOCUMENTO_AUSENTE"
    DOCUMENTO_INVALIDO = "DOCUMENTO_INVALIDO"
    CLASSIFICACAO_AUSENTE = "CLASSIFICACAO_AUSENTE"


# Situação do papel pedido numa pessoa existente, além de ATIVO e INATIVO.
PAPEL_AUSENTE = "AUSENTE"


@dataclass(frozen=True)
class ConsultaPessoa:
    papel: str
    situacao: Situacao
    # Como veio da nota, para exibição; o documento já normalizado.
    nome: str | None
    documento: str | None
    tipo_documento: str | None
    # Preenchidos só quando EXISTE.
    id: int | None = None
    razao_social: str | None = None
    status: str | None = None
    status_papel: str | None = None

    @property
    def existe(self):
        return self.situacao == Situacao.EXISTE


@dataclass(frozen=True)
class ConsultaClassificacao:
    tipo: str
    situacao: Situacao
    codigo: str | None
    # Preenchidos só quando EXISTE.
    id: int | None = None
    descricao: str | None = None
    status: str | None = None

    @property
    def existe(self):
        return self.situacao == Situacao.EXISTE


@dataclass(frozen=True)
class ResultadoConsultas:
    fornecedor: ConsultaPessoa
    faturado: ConsultaPessoa
    classificacao: ConsultaClassificacao


def _texto(valor, campo):
    if valor is not None and not isinstance(valor, str):
        raise TypeError(f"{campo} deve ser texto ou None.")
    return " ".join((valor or "").split()) or None


def consultar_pessoa(documento, papel, nome=None):
    """Consulta a pessoa pelo CPF/CNPJ e informa a situação do papel pedido."""
    if papel not in Papel.values:
        raise ValueError(f"Papel desconhecido: {papel!r}.")
    nome = _texto(nome, "nome")
    documento = normalizar_documento(_texto(documento, "documento")) or None
    tipo = tipo_do_documento(documento) if documento else None
    consulta = dict(papel=papel, nome=nome, documento=documento, tipo_documento=tipo)

    if documento is None:
        return ConsultaPessoa(situacao=Situacao.DOCUMENTO_AUSENTE, **consulta)
    try:
        validar_documento(documento)
    except ValidationError:
        return ConsultaPessoa(situacao=Situacao.DOCUMENTO_INVALIDO, **consulta)

    pessoa = (
        Pessoa.objects.por_documento(documento)
        .values("id", "razao_social", "status").first()
    )
    if pessoa is None:
        return ConsultaPessoa(situacao=Situacao.NAO_EXISTE, **consulta)

    status_papel = (
        PapelPessoa.objects.filter(pessoa_id=pessoa["id"], papel=papel)
        .values_list("status", flat=True).first()
    )
    return ConsultaPessoa(
        situacao=Situacao.EXISTE,
        id=pessoa["id"],
        razao_social=pessoa["razao_social"],
        status=pessoa["status"],
        status_papel=status_papel or PAPEL_AUSENTE,
        **consulta,
    )


def consultar_classificacao(codigo, tipo=TipoClassificacao.DESPESA):
    """Consulta a classificação pelo tipo e pelo código, em qualquer status."""
    if tipo not in TipoClassificacao.values:
        raise ValueError(f"Tipo de classificação desconhecido: {tipo!r}.")
    # Normalizado também aqui (além de por_codigo) para devolver o código buscado.
    codigo = (_texto(codigo, "codigo") or "").upper() or None
    if codigo is None:
        return ConsultaClassificacao(
            tipo=tipo, situacao=Situacao.CLASSIFICACAO_AUSENTE, codigo=None
        )

    classificacao = (
        Classificacao.objects.por_codigo(tipo, codigo)
        .values("id", "descricao", "status").first()
    )
    if classificacao is None:
        return ConsultaClassificacao(
            tipo=tipo, situacao=Situacao.NAO_EXISTE, codigo=codigo
        )
    return ConsultaClassificacao(
        tipo=tipo, situacao=Situacao.EXISTE, codigo=codigo, **classificacao
    )


def _bloco(resultado, campo):
    bloco = resultado.get(campo)
    if bloco is None:
        return {}
    if not isinstance(bloco, dict):
        raise TypeError(f"{campo} deve ser um dicionário ou None.")
    return bloco


def consultar_nota(resultado):
    """Consulta fornecedor, faturado e classificação a partir do JSON final do
    processamento (montar_resultado, ContextoProjeto 17.3)."""
    if not isinstance(resultado, dict):
        raise TypeError("resultado deve ser um dicionário.")
    fornecedor = _bloco(resultado, "fornecedor")
    faturado = _bloco(resultado, "faturado")
    return ResultadoConsultas(
        fornecedor=consultar_pessoa(
            fornecedor.get("cnpj"), Papel.FORNECEDOR, nome=fornecedor.get("razao_social")
        ),
        faturado=consultar_pessoa(faturado.get("cpf"), Papel.FATURADO, nome=faturado.get("nome")),
        classificacao=consultar_classificacao(resultado.get("tipo_despesa")),
    )
