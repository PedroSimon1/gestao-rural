"""Cosseno em Python sobre os vetores normalizados do índice atual."""

from heapq import nlargest

from agents.gemini_client import TAREFA_CONSULTA

from .fontes import Fonte
from .indexacao import TAMANHO_BLOCO, configuracao_indice, validar_vetores
from .models import EmbeddingMovimento


def recuperar(pergunta: str, cliente, limite: int) -> list[Fonte]:
    if not pergunta or not pergunta.strip():
        raise ValueError("Informe uma pergunta para a consulta semântica.")
    modelo, dimensao = configuracao_indice()
    if limite < 1:
        return []
    consulta = validar_vetores(
        cliente.gerar_embeddings([pergunta.strip()], tarefa=TAREFA_CONSULTA),
        1, dimensao,
    )[0]
    vetores = EmbeddingMovimento.objects.filter(
        modelo=modelo, dimensao=dimensao,
    ).order_by("-movimento__criado_em", "-movimento_id").values_list(
        "movimento_id", "vetor",
    ).iterator(chunk_size=TAMANHO_BLOCO)
    resultados = (
        (pk, sum(a * b for a, b in zip(consulta, vetor, strict=True)))
        for pk, vetor in vetores
        if len(vetor) == len(consulta)
    )
    return [
        Fonte(
            movimento_id=pk,
            pontuacao=float(round(pontuacao, 4)),
            motivo=f"similaridade {pontuacao:.2f}".replace(".", ","),
        )
        for pk, pontuacao in nlargest(limite, resultados, key=lambda resultado: resultado[1])
    ]
