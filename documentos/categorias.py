"""Categorias de despesa que o Classificador pode escolher: as classificações ativas do cadastro (Q-05)."""
from agents.classificador.schemas import CategoriaDespesa
from cadastros.models import Classificacao, TipoClassificacao


def categorias_de_despesa():
    """Classificações de DESPESA ativas, por descrição. Inativas nunca são oferecidas à IA."""
    return tuple(
        CategoriaDespesa(codigo=codigo, descricao=descricao)
        for codigo, descricao in Classificacao.objects.ativos()
        .filter(tipo=TipoClassificacao.DESPESA)
        .order_by("descricao", "id")
        .values_list("codigo", "descricao")
    )
