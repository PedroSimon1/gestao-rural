"""Busca literal: cada termo distinto vale 2 em itens/contraparte e 1 no resto.

Um termo presente em vários campos conta uma vez, com o maior peso. O
TRANSLATE nativo do PostgreSQL remove acentos portugueses antes do iregex;
o casamento começa em uma palavra e aceita o singular retirando um «s» final.
Não depende de unaccent ou extensão. Só os 200 candidatos mais recentes são
carregados para pontuação; um movimento antigo pode ficar fora desse recorte.
"""

import re

from django.db.models import CharField, F, Func, Q, Value
from django.db.models.functions import Cast, Lower

from financeiro.models import MovimentoConta

from .fontes import Fonte
from .texto import carregar_movimentos

MAXIMO_CANDIDATOS = 200

_ACENTOS = "áàâãäéèêëíìîïóòôõöúùûüç"
_SEM_ACENTOS = "aaaaaeeeeiiiiooooouuuuc"
_TRADUCAO = str.maketrans(_ACENTOS, _SEM_ACENTOS)
_STOPWORDS = frozenset("""
a ao aos aquela aquelas aquele aqueles aqui as ate com como da das de dela
 delas dele deles depois do dos e ela elas ele eles em entre era eram essa
 essas esse esses esta estao estas este estes eu foi foram ha isso isto ja
 lhe lhes mais mas me mesmo meu meus minha minhas muito na nao nas nem no nos
 nossa nossas nosso nossos num numa o os ou para pela pelas pelo pelos por
 qual quais quando que quem quero quanto quantos sao se sem ser seu seus sua
 suas sobre so tambem tem tenho ter todos toda todas todo tu um uma umas uns
 voce voces onde gostaria saber mostrar mostre quais houve foram esta estão
""".split())
_CAMPOS = (
    ("fornecedor", "contraparte__razao_social", 2),
    ("classificação", "classificacoes__classificacao__descricao", 1),
    ("código da classificação", "classificacoes__classificacao__codigo", 1),
    ("itens", "nota_fiscal__itens__descricao", 2),
    ("nota", "nota_fiscal__numero", 1),
)


def _normalizar(texto):
    return texto.lower().translate(_TRADUCAO)


def _termos(pergunta):
    return sorted({
        termo for termo in re.findall(r"\w+", _normalizar(pergunta))
        if len(termo) >= 3 and termo not in _STOPWORDS
    })


def _radical(termo):
    if len(termo) >= 4 and termo.isalpha() and termo.endswith("s"):
        return termo[:-1]
    return termo


def _recentes(limite):
    return [Fonte(pk, 0.0, "mais recentes") for pk in (
        MovimentoConta.objects.order_by("-criado_em", "-pk")
        .values_list("pk", flat=True)[:limite]
    )]


def recuperar(pergunta: str, limite: int) -> list[Fonte]:
    if limite <= 0:
        return []
    termos = _termos(pergunta)
    if not termos:
        return _recentes(limite)
    padroes = [(termo, re.escape(_radical(termo))) for termo in termos]
    expressoes = {}
    filtro = Q()
    for indice, (_, campo, _) in enumerate(_CAMPOS):
        alias = f"busca_{indice}"
        expressoes[alias] = Func(
            Lower(Cast(F(campo), CharField())), Value(_ACENTOS), Value(_SEM_ACENTOS),
            function="TRANSLATE", output_field=CharField(),
        )
        for _, padrao in padroes:
            filtro |= Q(**{f"{alias}__iregex": r"\m" + padrao})
    ids = list(MovimentoConta.objects.alias(**expressoes).filter(filtro)
               .order_by("-criado_em", "-pk").values_list("pk", flat=True)
               .distinct()[:MAXIMO_CANDIDATOS])
    if not ids:
        return _recentes(limite)
    fontes = []
    for movimento in carregar_movimentos(ids):
        nota = getattr(movimento, "nota_fiscal", None)
        vinculos = list(movimento.classificacoes.all())
        textos = (
            movimento.contraparte.razao_social,
            " ".join(v.classificacao.descricao for v in vinculos),
            " ".join(v.classificacao.codigo for v in vinculos),
            " ".join(item.descricao for item in nota.itens.all()) if nota else "",
            str(nota.numero) if nota else "",
        )
        textos = [_normalizar(texto) for texto in textos]
        pontuacao = 0
        motivos = []
        for termo, padrao in padroes:
            casados = [(nome, peso) for (nome, _, peso), texto in zip(_CAMPOS, textos)
                       if re.search(r"\b" + padrao, texto)]
            if casados:
                pontuacao += max(peso for _, peso in casados)
                motivos.append(f"{termo} ({', '.join(nome for nome, _ in casados)})")
        fontes.append(Fonte(movimento.pk, float(pontuacao), "casou: " + "; ".join(motivos)))
    # O carregamento mantém a ordem de recência dos IDs; sort estável desempata.
    fontes.sort(key=lambda fonte: fonte.pontuacao, reverse=True)
    return fontes[:limite]
