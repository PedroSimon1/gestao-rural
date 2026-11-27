"""Onde cada pendência da conferência aparece na tela: seção, campo e âncora.

Só apresentação: junta os problemas da nota (códigos da F-3, nunca valores) e os erros do formulário enviado
para a tela mostrar, por seção e por campo, o que impede a confirmação.
"""
from types import SimpleNamespace

from .views_confirmacao import ROTULOS_CAMPO, mensagem_validacao

SECOES = (
    (1, "Fornecedor", "secao-fornecedor"),
    (2, "Faturado", "secao-faturado"),
    (3, "Dados da nota", "secao-nota"),
    (4, "Parcelas", "secao-parcelas"),
)
_SECAO_POR_NUMERO = {numero: (rotulo, ancora) for numero, rotulo, ancora in SECOES}

# Campo do problema da nota -> (seção, campos do formulário; o primeiro é o alvo do link).
_DESTINOS = {
    "fornecedor.razao_social": (1, ("fornecedor_nome",)),
    "fornecedor.documento": (1, ("fornecedor_documento",)),
    "faturado.nome": (2, ("faturado_nome",)),
    "identidade_fiscal": (3, ("chave_acesso", "modelo", "serie_nota", "numero_nota")),
    "chave_acesso": (3, ("chave_acesso",)),
    "modelo": (3, ("modelo",)),
    "serie": (3, ("serie_nota",)),
    "numero_nota": (3, ("numero_nota",)),
    "data_emissao": (3, ("data_emissao",)),
    "valor_total": (3, ("valor_total",)),
    "tipo_despesa": (3, ("classificacao",)),
    "parcelas": (4, ()),
}

# Campo do formulário -> seção (para os erros de validação do que foi enviado).
_SECAO_DO_CAMPO = {
    "fornecedor_nome": 1, "fornecedor_documento": 1,
    "faturado_nome": 2, "faturado_cpf": 2, "faturado_cnpj": 2, "documento_faturado": 2,
    "numero_nota": 3, "serie_nota": 3, "chave_acesso": 3, "modelo": 3, "data_emissao": 3,
    "classificacao": 3, "valor_total": 3,
}

_COMPLEMENTO_FISCAL = "Faz parte da identificação fiscal (veja a chave de acesso)."


def _destino(problema, form):
    """(seção, campos) do problema; o documento do faturado aponta para o campo preenchido."""
    if problema.campo == "faturado.documento":
        if problema.codigo == "escolha_necessaria":
            return 2, ("documento_faturado",)
        preenchido = [c for c in ("faturado_cnpj", "faturado_cpf") if form[c].value()]
        return 2, tuple(preenchido[:1]) or ("faturado_cnpj",)
    return _DESTINOS.get(problema.campo, (None, ()))


def _item(secao, rotulo, mensagem, ancora):
    nome_secao = _SECAO_POR_NUMERO[secao][0] if secao else None
    # Sem campo próprio para carregar o motivo: o painel precisa mostrar a mensagem junto do item.
    sem_campo = ancora is None or ancora.startswith("secao-")
    return {"secao": secao, "secao_rotulo": nome_secao, "rotulo": rotulo, "mensagem": mensagem,
            "ancora": ancora, "sem_campo": sem_campo}


def resumir_pendencias(nota, form, parcelas):
    """Itens ordenados por seção, contagem por seção e o motivo de cada campo pendente.

    `campos` mapeia o nome do campo do formulário ao motivo (só problemas da nota; os erros do formulário
    já aparecem sob o próprio campo).
    """
    itens, campos = [], {}
    for problema in nota.problemas:
        secao, nomes = _destino(problema, form)
        mensagem = mensagem_validacao(problema.codigo)
        rotulo = ROTULOS_CAMPO.get(problema.campo, "Dados da nota")
        if nomes:
            ancora = form[nomes[0]].id_for_label
            for posicao, nome in enumerate(nomes):
                campos.setdefault(nome, mensagem if posicao == 0 else _COMPLEMENTO_FISCAL)
        else:
            ancora = _SECAO_POR_NUMERO[secao][1] if secao else None
        itens.append(_item(secao, rotulo, mensagem, ancora))

    for nome, erros in form.errors.items():
        if nome == "__all__" or nome not in _SECAO_DO_CAMPO:
            itens.append(_item(None, "Dados da nota", erros[0], None))
            continue
        itens.append(_item(_SECAO_DO_CAMPO[nome], form.fields[nome].label, erros[0], form[nome].id_for_label))

    for posicao, linha in enumerate(parcelas.forms, 1):
        for nome, erros in linha.errors.items():
            ancora = linha[nome].id_for_label if nome in linha.fields else _SECAO_POR_NUMERO[4][1]
            rotulo = f"Parcela {posicao}" + (f" — {linha.fields[nome].label}" if nome in linha.fields else "")
            itens.append(_item(4, rotulo, erros[0], ancora))
    for erro in parcelas.non_form_errors():
        itens.append(_item(4, "Parcelas", erro, _SECAO_POR_NUMERO[4][1]))

    itens.sort(key=lambda item: (item["secao"] is None, item["secao"] or 0))
    secoes = [
        {"numero": numero, "rotulo": rotulo, "ancora": ancora,
         "itens": [i for i in itens if i["secao"] == numero]}
        for numero, rotulo, ancora in SECOES
    ]
    for secao in secoes:
        secao["total"] = len(secao["itens"])
    gerais = [i for i in itens if i["secao"] is None]
    return SimpleNamespace(total=len(itens), itens=itens, secoes=secoes, gerais=gerais, campos=campos)
