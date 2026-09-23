"""Orquestração do processamento de um Documento (GR-12).

Fluxo: Documento → AgentExtrator → AgentClassificador → JSON final,
com o estado e o resultado gravados no próprio Documento.
"""

import logging

from django.db import transaction
from django.utils import timezone

from agents.classificador.agent import AgentClassificador, ClassificadorError
from agents.classificador.schemas import VERSAO_SCHEMA as VERSAO_SCHEMA_CLASSIFICACAO
from agents.extrator.agent import AgentExtrator, ExtratorError
from agents.extrator.schemas import VERSAO_SCHEMA as VERSAO_SCHEMA_EXTRACAO

from .models import Documento

logger = logging.getLogger(__name__)

VERSAO_RESULTADO = 1

MENSAGEM_ERRO_INTERNO = "Erro inesperado ao processar o documento."


class ProcessamentoError(Exception):
    """Erro base do processamento. A mensagem é segura para exibir."""

    codigo = "erro_processamento"
    mensagem_padrao = "Não foi possível processar o documento."

    def __init__(self, mensagem=None):
        super().__init__(mensagem or self.mensagem_padrao)


class DocumentoEmProcessamentoError(ProcessamentoError):
    codigo = "documento_em_processamento"
    mensagem_padrao = "O documento já está sendo processado."


def _reservar(documento_id):
    """Passa o Documento para PROCESSANDO numa transação curta.

    O lock (select_for_update) só dura a leitura, a checagem e o save:
    as chamadas ao Gemini acontecem depois, fora da transação. Uma
    execução concorrente espera o lock e então encontra PROCESSANDO.

    Retorna (documento, reservado):
    - PENDENTE ou ERRO → (documento em PROCESSANDO, True);
    - CONCLUIDO        → (documento inalterado, False).
    Lança DocumentoEmProcessamentoError se já estiver PROCESSANDO e
    Documento.DoesNotExist se não existir.
    """
    with transaction.atomic():
        documento = Documento.objects.select_for_update().get(pk=documento_id)

        if documento.status == Documento.Status.PROCESSANDO:
            raise DocumentoEmProcessamentoError()
        if documento.status == Documento.Status.CONCLUIDO:
            return documento, False

        metadados = dict(documento.metadados)
        metadados.pop("erro", None)
        metadados["processamento"] = {
            "versao_resultado": VERSAO_RESULTADO,
            "iniciado_em": timezone.now().isoformat(),
        }

        documento.metadados = metadados
        documento.status = Documento.Status.PROCESSANDO
        documento.save(update_fields=["status", "metadados"])

    return documento, True


def _montar_resultado(nota, classificacao):
    """Monta o JSON final da atividade (resultado_estruturado).

    Parte do dump JSON da extração (dinheiro como string, datas ISO,
    validacoes incluído) e acrescenta quantidade_parcelas e tipo_despesa.
    documento_e_nota_fiscal fica de fora: é sempre true quando se chega aqui.
    """
    extracao = nota.model_dump(mode="json")
    parcelas = extracao["parcelas"]

    return {
        "fornecedor": extracao["fornecedor"],
        "faturado": extracao["faturado"],
        "numero_nota": extracao["numero_nota"],
        "data_emissao": extracao["data_emissao"],
        "itens": extracao["itens"],
        "quantidade_parcelas": len(parcelas),
        "parcelas": parcelas,
        "valor_total": extracao["valor_total"],
        "tipo_despesa": classificacao.model_dump(mode="json")["tipo_despesa"],
        "validacoes": extracao["validacoes"],
    }


def _erro_seguro(documento, etapa, exc):
    # Só o código e a mensagem fixa da exceção; nunca __cause__ ou traceback,
    # que podem conter dados da nota ou detalhes da API.
    logger.warning(
        "Processamento do documento %s falhou (%s/%s).",
        documento.pk,
        etapa,
        exc.codigo,
    )
    return {"etapa": etapa, "codigo": exc.codigo, "mensagem": str(exc)}


def _registrar_sucesso(documento, resultado, processamento):
    metadados = dict(documento.metadados)
    metadados.pop("erro", None)
    metadados["processamento"] = {
        **metadados.get("processamento", {}),
        **processamento,
        "finalizado_em": timezone.now().isoformat(),
    }

    documento.status = Documento.Status.CONCLUIDO
    documento.resultado_estruturado = resultado
    documento.metadados = metadados
    documento.save(update_fields=["status", "resultado_estruturado", "metadados"])


def _registrar_erro(documento, erro):
    metadados = dict(documento.metadados)
    metadados["erro"] = erro
    # Reconstruído do zero: se o save de sucesso falhou, dados das etapas
    # (extracao, classificacao, justificativa) já estariam em memória.
    metadados["processamento"] = {
        "versao_resultado": VERSAO_RESULTADO,
        "iniciado_em": metadados.get("processamento", {}).get("iniciado_em"),
        "finalizado_em": timezone.now().isoformat(),
    }

    documento.status = Documento.Status.ERRO
    documento.resultado_estruturado = {}
    documento.metadados = metadados
    documento.save(update_fields=["status", "resultado_estruturado", "metadados"])


def _executar(documento, extrator, classificador):
    """Roda Extrator e Classificador e grava o sucesso.

    Retorna o erro seguro de uma falha esperada, ou None no sucesso.
    """
    if extrator is None:
        extrator = AgentExtrator()
    if classificador is None:
        classificador = AgentClassificador()

    try:
        nota = extrator.extrair_documento(documento)
    except ExtratorError as exc:
        return _erro_seguro(documento, "extracao", exc)

    try:
        classificacao = classificador.classificar(nota)
    except ClassificadorError as exc:
        return _erro_seguro(documento, "classificacao", exc)

    resultado = _montar_resultado(nota, classificacao)
    _registrar_sucesso(
        documento,
        resultado,
        {
            # modelo só é conhecido depois da chamada (cliente preguiçoso).
            "extracao": {
                "versao_schema": VERSAO_SCHEMA_EXTRACAO,
                "modelo": extrator.modelo,
            },
            "classificacao": {
                "versao_schema": VERSAO_SCHEMA_CLASSIFICACAO,
                "modelo": classificador.modelo,
                "justificativa": classificacao.justificativa,
            },
        },
    )
    return None


def processar_documento(documento_id, *, extrator=None, classificador=None):
    """Processa o PDF de um Documento e grava o resultado nele.

    - PENDENTE ou ERRO → processa; termina em CONCLUIDO ou ERRO.
    - CONCLUIDO        → devolve o documento sem chamar os Agents.
    - PROCESSANDO      → DocumentoEmProcessamentoError (nada é alterado).
    - inexistente      → Documento.DoesNotExist.

    Falhas de extração, classificação ou inesperadas não são relançadas:
    ficam registradas no Documento (status ERRO + metadados["erro"]).
    Nenhuma transação fica aberta durante as chamadas aos Agents.
    """
    documento, reservado = _reservar(documento_id)
    if not reservado:
        return documento

    try:
        erro = _executar(documento, extrator, classificador)
    except Exception:
        logger.exception("Erro inesperado ao processar o documento %s.", documento.pk)
        erro = {
            "etapa": "processamento",
            "codigo": "erro_interno",
            "mensagem": MENSAGEM_ERRO_INTERNO,
        }

    if erro is not None:
        # Se esta gravação falhar, a exceção sobe.
        _registrar_erro(documento, erro)

    return documento
