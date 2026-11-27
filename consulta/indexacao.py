"""Indexação explícita, incremental e em lotes dos textos estáveis."""

import hashlib
import math
from dataclasses import dataclass
from itertools import islice

from django.conf import settings
from django.db import transaction
from django.db.models import OuterRef, Subquery

from agents.gemini_client import GeminiRespostaInvalidaError, TAREFA_DOCUMENTO
from financeiro.models import MovimentoConta

from .models import EmbeddingMovimento
from .texto import carregar_movimentos, texto_indexacao

TAMANHO_BLOCO = 200
LIMITE_MAXIMO_INDEXACAO = 100


class ConfiguracaoDoIndiceError(ValueError):
    """Modelo ou dimensão do índice ausente ou inválido."""


@dataclass(frozen=True)
class SituacaoIndice:
    """Estados disjuntos relativos ao modelo E dimensão configurados.

    Pendente: não há vetor nessa configuração, mesmo havendo vetor antigo.
    Desatualizado: há vetor nessa configuração, mas o hash do texto mudou.
    Assim, total = indexados + desatualizados + pendentes.
    """

    total: int
    indexados: int
    desatualizados: int
    pendentes: int


def configuracao_indice() -> tuple[str, int]:
    modelo = getattr(settings, "GEMINI_MODELO_EMBEDDING", None)
    dimensao = getattr(settings, "GEMINI_DIMENSAO_EMBEDDING", None)
    if not isinstance(modelo, str) or not modelo.strip() or len(modelo.strip()) > 100:
        raise ConfiguracaoDoIndiceError("GEMINI_MODELO_EMBEDDING deve informar um modelo válido.")
    if isinstance(dimensao, bool) or not isinstance(dimensao, (int, str)):
        raise ConfiguracaoDoIndiceError("GEMINI_DIMENSAO_EMBEDDING deve ser um inteiro positivo.")
    try:
        dimensao = int(dimensao)
    except (TypeError, ValueError) as exc:
        raise ConfiguracaoDoIndiceError(
            "GEMINI_DIMENSAO_EMBEDDING deve ser um inteiro positivo."
        ) from exc
    if dimensao < 1:
        raise ConfiguracaoDoIndiceError("GEMINI_DIMENSAO_EMBEDDING deve ser um inteiro positivo.")
    return modelo.strip(), dimensao


def validar_vetores(vetores, quantidade, dimensao):
    """Confere todo o lote antes de qualquer escrita, inclusive clientes injetados."""
    if not isinstance(vetores, (list, tuple)) or len(vetores) != quantidade:
        raise GeminiRespostaInvalidaError("Quantidade de embeddings diferente da solicitada.")
    resultado = []
    for vetor in vetores:
        if (
            not isinstance(vetor, (list, tuple)) or len(vetor) != dimensao
            or any(
                isinstance(valor, bool) or not isinstance(valor, (int, float))
                or not math.isfinite(valor)
                for valor in vetor
            )
            or not any(vetor)
        ):
            raise GeminiRespostaInvalidaError("Embedding inválido ou com dimensão inesperada.")
        resultado.append([float(valor) for valor in vetor])
    return resultado


def _percorrer_indice(modelo, dimensao):
    atuais = EmbeddingMovimento.objects.filter(
        movimento_id=OuterRef("pk"), modelo=modelo, dimensao=dimensao,
    )
    linhas = MovimentoConta.objects.annotate(
        hash_indice=Subquery(atuais.values("hash_texto")[:1]),
    ).order_by("-criado_em", "-pk").values_list("pk", "hash_indice").iterator(
        chunk_size=TAMANHO_BLOCO,
    )
    while bloco := list(islice(linhas, TAMANHO_BLOCO)):
        hashes = dict(bloco)
        for movimento in carregar_movimentos(hashes):
            texto = texto_indexacao(movimento)
            hash_atual = hashlib.sha256(texto.encode("utf-8")).hexdigest()
            hash_anterior = hashes[movimento.pk]
            estado = (
                "pendentes" if hash_anterior is None
                else "indexados" if hash_anterior == hash_atual
                else "desatualizados"
            )
            yield movimento.pk, texto, hash_atual, estado


def situacao_indice() -> SituacaoIndice:
    modelo, dimensao = configuracao_indice()
    contagens = {"indexados": 0, "desatualizados": 0, "pendentes": 0}
    for _, _, _, estado in _percorrer_indice(modelo, dimensao):
        contagens[estado] += 1
    return SituacaoIndice(total=sum(contagens.values()), **contagens)


def atualizar_indice(cliente, limite: int) -> SituacaoIndice:
    if limite < 1:
        raise ValueError("O limite de indexação deve ser maior que zero.")
    modelo, dimensao = configuracao_indice()
    limite = min(limite, LIMITE_MAXIMO_INDEXACAO)
    pendentes, desatualizados = [], []
    for pk, texto, hash_atual, estado in _percorrer_indice(modelo, dimensao):
        if estado == "pendentes":
            pendentes.append((pk, texto, hash_atual))
            if len(pendentes) == limite:
                break
        elif estado == "desatualizados" and len(desatualizados) < limite:
            desatualizados.append((pk, texto, hash_atual))
    lote = (pendentes + desatualizados)[:limite]
    if not lote:
        return situacao_indice()
    vetores = validar_vetores(
        cliente.gerar_embeddings([texto for _, texto, _ in lote], tarefa=TAREFA_DOCUMENTO),
        len(lote), dimensao,
    )
    with transaction.atomic():
        EmbeddingMovimento.objects.bulk_create(
            [
                EmbeddingMovimento(
                    movimento_id=pk, modelo=modelo, dimensao=dimensao,
                    vetor=vetor, hash_texto=hash_atual,
                )
                for (pk, _, hash_atual), vetor in zip(lote, vetores, strict=True)
            ],
            update_conflicts=True,
            unique_fields=["movimento", "modelo"],
            update_fields=["dimensao", "vetor", "hash_texto", "atualizado_em"],
        )
    return situacao_indice()
