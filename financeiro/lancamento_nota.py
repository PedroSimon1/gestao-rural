"""Lançamento da nota fiscal a partir da análise conferida (GR-22, F-5).

lancar_nota(session, analise_id, solicitacao) é o único ponto de entrada: a
view chama depois do clique explícito em "Confirmar" (DQ-02). Tudo acontece
dentro de confirmar_analise() (GR-43), que bloqueia a análise, confere a
versão das correções e faz o COMMIT único (transaction.atomic(durable=True)):

1. conferir_nota(dados, correcoes_da_confirmacao(analise_id)) (F-3): qualquer
   problema recusa o lançamento;
2. resolver_partes() (F-4) com as decisões da solicitação: pessoas e papéis;
3. registrar_movimento() (GR-37/GR-38): movimento, classificação e parcelas,
   com analise_origem_id = id da análise;
4. registrar_identidade_fiscal() (F-1): a nota não pode ser lançada duas vezes.

Qualquer exceção desfaz cadastros, papéis, movimento, parcelas e identidade,
e a análise continua PENDENTE. O resultado só é devolvido depois do COMMIT.

As decisões da F-4 chegam na solicitação, separadas dos dados extraídos e das
correções fiscais: nada é persistido na análise e nada é decidido aqui.

Com o JSON v1, sem modelo nem chave de acesso, conferir_nota() sempre acusa
identidade_fiscal_insuficiente; o lançamento só passa quando a origem desses
campos existir (G-01 nas correções ou JSON fiscal v2 na análise).
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError

from cadastros.models import Classificacao
from cadastros.resolucao import Decisao, ParteNota, PessoaResolvida, resolver_partes
from documentos.analises import confirmar_analise, correcoes_da_confirmacao
from documentos.conferencia import conferir_nota

from .identidade_fiscal import registrar_identidade_fiscal
from .models import MovimentoConta, NotaFiscalLancada, OrigemMovimento, TipoMovimento
from .servicos import DadosMovimento, ItemClassificacao, registrar_movimento

CONFERENCIA_PENDENTE = "conferencia_pendente"


@dataclass(frozen=True)
class DecisoesDaParte:
    """Decisões explícitas do usuário para uma parte da nota (F-4)."""

    decisoes: frozenset = frozenset()
    # Cadastro incompleto selecionado manualmente (D-04).
    pessoa_incompleta_id: int | None = None


@dataclass(frozen=True)
class SolicitacaoLancamento:
    # versao_correcoes que o usuário conferiu: outra janela mudou → recusa.
    versao_correcoes: int
    fornecedor: DecisoesDaParte = DecisoesDaParte()
    faturado: DecisoesDaParte = DecisoesDaParte()


@dataclass(frozen=True)
class LancamentoNota:
    movimento: MovimentoConta
    nota_fiscal: NotaFiscalLancada
    fornecedor: PessoaResolvida
    faturado: PessoaResolvida


def _validar_solicitacao(solicitacao):
    if not isinstance(solicitacao, SolicitacaoLancamento):
        raise TypeError("Informe uma SolicitacaoLancamento.")
    versao = solicitacao.versao_correcoes
    if isinstance(versao, bool) or not isinstance(versao, int):
        raise TypeError("A versão das correções deve ser um inteiro.")
    for parte in (solicitacao.fornecedor, solicitacao.faturado):
        if not isinstance(parte, DecisoesDaParte):
            raise TypeError("Informe as decisões de cada parte em DecisoesDaParte.")
        if isinstance(parte.decisoes, str):
            raise TypeError("Informe as decisões em um conjunto.")
        # ValueError para uma decisão desconhecida, antes de abrir a transação.
        frozenset(Decisao(decisao) for decisao in parte.decisoes)
        selecionada = parte.pessoa_incompleta_id
        if selecionada is not None and (type(selecionada) is not int or selecionada < 1):
            raise TypeError("pessoa_incompleta_id deve ser um inteiro positivo ou None.")


def _recusar_problemas(nota):
    """Um ValidationError com um item por problema da F-3 (só campo e código)."""
    if nota.problemas:
        raise ValidationError([
            ValidationError(
                "Revise a conferência: %(campo)s (%(codigo)s).",
                code=problema.codigo,
                params={"campo": problema.campo, "codigo": problema.codigo},
            )
            for problema in nota.problemas
        ])
    # Defesa: sem problemas, a F-3 sempre preenche estes campos.
    if nota.identidade_fiscal is None or nota.valor_total is None or nota.classificacao.id is None:
        raise ValidationError("A conferência está incompleta.", code=CONFERENCIA_PENDENTE)


def _parte(conferida, decisoes):
    return ParteNota(
        papel=conferida.papel,
        documento=conferida.documento,
        nome=conferida.nome,
        decisoes=frozenset(decisoes.decisoes),
        pessoa_incompleta_id=decisoes.pessoa_incompleta_id,
    )


def _gravador(solicitacao):
    def gravar(dados, analise_id):
        nota = conferir_nota(dados, correcoes_da_confirmacao(analise_id))
        _recusar_problemas(nota)

        fornecedor, faturado = resolver_partes([
            _parte(nota.fornecedor, solicitacao.fornecedor),
            _parte(nota.faturado, solicitacao.faturado),
        ])

        # Status e tipo são revalidados com bloqueio por registrar_movimento
        # (classificacao_inativa, classificacao_incompativel); nada é reativado.
        classificacao = Classificacao.objects.get(pk=nota.classificacao.id)
        movimento, _ = registrar_movimento(DadosMovimento(
            tipo=TipoMovimento.APAGAR,
            origem=OrigemMovimento.NOTA_FISCAL,
            contraparte=fornecedor.pessoa,
            faturado=faturado.pessoa,
            valor_total=nota.valor_total,
            classificacoes=(ItemClassificacao(classificacao, principal=True),),
            analise_origem_id=analise_id,
            parcelas=nota.parcelas,
        ))
        nota_fiscal, _ = registrar_identidade_fiscal(movimento, nota.identidade_fiscal)
        return LancamentoNota(movimento, nota_fiscal, fornecedor, faturado)

    return gravar


def lancar_nota(session, analise_id, solicitacao):
    """Lança a nota da análise e devolve LancamentoNota, depois do COMMIT.

    Erros (nada gravado; a análise continua PENDENTE, salvo os estados finais):
    - AnaliseError (GR-43): analise_nao_encontrada, analise_expirada,
      analise_cancelada, analise_confirmada (inclusive a segunda de duas
      confirmações simultâneas), correcoes_desatualizadas;
    - ValidationError: problemas da conferência (F-3) em error_list, um por
      problema, com code e params {"campo", "codigo"}; códigos da F-4
      (params {"papel"}); de registrar_movimento e da identidade fiscal
      (nota_ja_lancada, também quando outra análise lança a mesma nota ao
      mesmo tempo). Ler sempre erro.error_list;
    - TypeError/ValueError: solicitação mal formada (erro de programação).

    Não pode ser chamada dentro de outra transação (RuntimeError da GR-43).
    """
    _validar_solicitacao(solicitacao)
    return confirmar_analise(
        session, analise_id, _gravador(solicitacao),
        versao_correcoes=solicitacao.versao_correcoes,
    )
