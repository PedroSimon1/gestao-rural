"""Textos determinísticos para consulta e índice, sem documentos pessoais."""

from django.db.models import Prefetch

from financeiro.models import MovimentoClassificacao, MovimentoConta


def carregar_movimentos(ids) -> list[MovimentoConta]:
    """Carrega o grafo em quatro consultas, independentemente do número de IDs."""
    ids = list(ids)
    if not ids:
        return []
    movimentos = MovimentoConta.objects.filter(pk__in=ids).select_related(
        "contraparte", "faturado", "nota_fiscal",
    ).prefetch_related(
        Prefetch("classificacoes", queryset=MovimentoClassificacao.objects.select_related(
            "classificacao",
        )),
        "parcelas", "nota_fiscal__itens",
    )
    por_id = {movimento.pk: movimento for movimento in movimentos}
    return [por_id[pk] for pk in ids if pk in por_id]


def _valor(valor):
    return "não informado" if valor is None else str(valor)


def texto_indexacao(movimento) -> str:
    """Somente dados de negócio: nunca status, baixa, parcelas ou timestamps."""
    linhas = [
        f"Tipo: {movimento.get_tipo_display()}",
        f"Contraparte: {movimento.contraparte.razao_social}",
        f"Valor total: R$ {movimento.valor_total}",
    ]
    for vinculo in movimento.classificacoes.all():
        classificacao = vinculo.classificacao
        principal = " (principal)" if vinculo.principal else ""
        linhas.append(f"Classificação: {classificacao.codigo} — {classificacao.descricao}{principal}")
    nota = getattr(movimento, "nota_fiscal", None)
    if nota is not None:
        linhas.append(f"Nota fiscal: número {nota.numero}; série {nota.serie}; emissão {_valor(nota.data_emissao)}")
        for item in nota.itens.all():
            linhas.append(
                f"Item {item.ordem}: {item.descricao}; quantidade {_valor(item.quantidade)}; "
                f"valor unitário {_valor(item.valor_unitario)}; valor total {_valor(item.valor_total)}"
            )
    return "\n".join(linhas)


def texto_contexto(movimento) -> str:
    linhas = [texto_indexacao(movimento), f"Status: {movimento.get_status_display()}"]
    if movimento.faturado is not None:
        linhas.append(f"Faturado: {movimento.faturado.razao_social}")
    for parcela in movimento.parcelas.all():
        pagamento = str(parcela.pago_em) if parcela.pago_em else "em aberto"
        linhas.append(
            f"Parcela {parcela.numero}: vencimento {parcela.data_vencimento}; "
            f"valor R$ {parcela.valor}; status {parcela.get_status_display()}; "
            f"pago em: {pagamento}"
        )
    return "\n".join(linhas)


def montar_contexto(movimentos) -> str:
    return "\n\n".join(
        f"### MOVIMENTO #{movimento.pk}\n{texto_contexto(movimento)}"
        for movimento in movimentos
    )
