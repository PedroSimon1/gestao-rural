import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import DatabaseError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import DocumentoUploadForm
from .models import Documento
from .processamento import DocumentoEmProcessamentoError, processar_documento

logger = logging.getLogger(__name__)

LIMITE_DOCUMENTOS_RECENTES = 10
MENSAGEM_FALHA_AO_SALVAR = "Não foi possível salvar o documento."
MENSAGEM_PROCESSAMENTO_CONCLUIDO = "Processamento concluído."
MENSAGEM_PROCESSAMENTO_FALHOU = "O processamento falhou. Veja os detalhes abaixo."
MENSAGEM_FALHA_INESPERADA = (
    "Não foi possível processar o documento agora. Tente novamente mais tarde."
)

# Ordem do JSON final (contrato da GR-12). O jsonb do PostgreSQL não preserva
# a ordem das chaves, então a tela reordena.
CHAVES_RESULTADO = (
    "fornecedor",
    "faturado",
    "numero_nota",
    "data_emissao",
    "itens",
    "quantidade_parcelas",
    "parcelas",
    "valor_total",
    "tipo_despesa",
    "validacoes",
)

ROTULOS_TIPO_DESPESA = {
    "MANUTENCAO_E_OPERACAO": "Manutenção e operação",
    "INFRAESTRUTURA_E_UTILIDADES": "Infraestrutura e utilidades",
}

AVISOS_VALIDACAO = (
    ("fornecedor_cnpj", "CNPJ do fornecedor com dígitos verificadores inválidos."),
    ("faturado_cpf", "CPF do faturado com dígitos verificadores inválidos."),
)

MENSAGEM_ERRO_PADRAO = "Não foi possível processar o documento."
SUGESTAO_ERRO_PADRAO = "Tente novamente. Se o problema persistir, avise a equipe."
SUGESTOES_ERRO = {
    "documento_ilegivel": "Envie o arquivo PDF novamente.",
    "servico_indisponivel": "Tente novamente mais tarde.",
    "resposta_invalida": "Confira se o arquivo enviado é uma nota fiscal válida.",
    "classificacao_invalida": "Tente novamente.",
    "classificacao_inconclusiva": (
        "Os itens da nota não se encaixaram nas categorias de despesa "
        "disponíveis no MVP (Manutenção e operação; Infraestrutura e utilidades)."
    ),
    "erro_interno": SUGESTAO_ERRO_PADRAO,
}


def _salvar_documento(arquivo):
    """Cria o Documento (status PENDENTE) com um arquivo já validado.

    Se o save falhar depois que o arquivo foi gravado no storage, o
    arquivo é removido e a exceção é relançada para a view tratar.
    """
    documento = Documento(
        arquivo=arquivo,
        nome_original=arquivo.name,
    )

    try:
        documento.save()
    except Exception:
        # Se o arquivo foi gravado antes da falha no banco, remova-o.
        if documento.arquivo._committed:
            try:
                documento.arquivo.delete(save=False)
            except OSError:
                pass
        raise

    return documento


@staff_member_required
@require_POST
def upload_documento(request):
    form = DocumentoUploadForm(request.POST, request.FILES)

    if not form.is_valid():
        mensagem = form.errors.get("arquivo", ["Arquivo inválido."])[0]
        return JsonResponse({"erro": str(mensagem)}, status=400)

    try:
        documento = _salvar_documento(form.cleaned_data["arquivo"])
    except (DatabaseError, OSError):
        return JsonResponse({"erro": MENSAGEM_FALHA_AO_SALVAR}, status=500)

    return JsonResponse(
        {
            "id": documento.pk,
            "nome_original": documento.nome_original,
            "status": documento.status,
        },
        status=201,
    )


@staff_member_required
@require_http_methods(["GET", "POST"])
def documento_inicio(request):
    """Tela inicial: envio de PDF (validação da GR-8) e documentos recentes."""
    if request.method == "POST":
        form = DocumentoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                documento = _salvar_documento(form.cleaned_data["arquivo"])
            except (DatabaseError, OSError):
                form.add_error(None, MENSAGEM_FALHA_AO_SALVAR)
            else:
                messages.success(
                    request, f"Documento “{documento.nome_original}” enviado."
                )
                return redirect("documento_detalhe", pk=documento.pk)
    else:
        form = DocumentoUploadForm()

    documentos = Documento.objects.only(
        "nome_original", "enviado_em", "status"
    ).order_by("-enviado_em")[:LIMITE_DOCUMENTOS_RECENTES]

    return render(
        request,
        "documentos/inicio.html",
        {
            "form": form,
            "documentos": documentos,
            "limite_upload_mb": settings.MAX_PDF_UPLOAD_SIZE_MB,
        },
    )


def _dicionario(valor):
    # JSONField aceita qualquer JSON; a tela só confia em objetos.
    return valor if isinstance(valor, dict) else {}


def _json_ordenado(resultado):
    ordenado = {chave: resultado[chave] for chave in CHAVES_RESULTADO if chave in resultado}
    ordenado.update(
        (chave, valor) for chave, valor in resultado.items() if chave not in ordenado
    )
    return json.dumps(ordenado, ensure_ascii=False, indent=2)


def _rotulo_tipo_despesa(valor):
    # Valor desconhecido aparece como veio (o template escapa).
    return ROTULOS_TIPO_DESPESA.get(valor, valor)


def _formatar_moeda(valor):
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return valor
    texto = f"{numero:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def _formatar_data(valor):
    try:
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return valor


def _resumo(resultado):
    fornecedor = _dicionario(resultado.get("fornecedor"))
    return {
        "tipo_despesa": _rotulo_tipo_despesa(resultado.get("tipo_despesa")),
        "valor_total": _formatar_moeda(resultado.get("valor_total")),
        "quantidade_parcelas": resultado.get("quantidade_parcelas"),
        "fornecedor": fornecedor.get("razao_social") or fornecedor.get("nome_fantasia"),
        "numero_nota": resultado.get("numero_nota"),
        "data_emissao": _formatar_data(resultado.get("data_emissao")),
    }


def _avisos_validacao(resultado):
    validacoes = _dicionario(resultado.get("validacoes"))
    return [
        aviso
        for chave, aviso in AVISOS_VALIDACAO
        if _dicionario(validacoes.get(chave)).get("status") == "invalido"
    ]


def _justificativa(metadados):
    processamento = _dicionario(metadados.get("processamento"))
    return _dicionario(processamento.get("classificacao")).get("justificativa")


def _erro_para_exibir(metadados):
    # Só a mensagem segura gravada pela GR-12 e uma orientação pelo código.
    erro = _dicionario(metadados.get("erro"))
    return {
        "mensagem": erro.get("mensagem") or MENSAGEM_ERRO_PADRAO,
        "sugestao": SUGESTOES_ERRO.get(erro.get("codigo"), SUGESTAO_ERRO_PADRAO),
    }


@staff_member_required
@require_GET
def documento_detalhe(request, pk):
    """Estado do Documento e, quando houver, o resultado ou o erro seguro."""
    documento = get_object_or_404(Documento, pk=pk)
    contexto = {"documento": documento}

    if documento.status == Documento.Status.CONCLUIDO:
        resultado = _dicionario(documento.resultado_estruturado)
        metadados = _dicionario(documento.metadados)
        contexto.update(
            resumo=_resumo(resultado),
            avisos=_avisos_validacao(resultado),
            justificativa=_justificativa(metadados),
            json_resultado=_json_ordenado(resultado),
        )
    elif documento.status == Documento.Status.ERRO:
        contexto["erro"] = _erro_para_exibir(_dicionario(documento.metadados))

    return render(request, "documentos/detalhe.html", contexto)


@staff_member_required
@require_POST
def documento_processar(request, pk):
    """Dispara o processamento (GR-12) e volta para a página do documento.

    Falhas de extração/classificação já chegam aqui como Documento em ERRO;
    a view só traduz o resultado em mensagem.
    """
    try:
        documento = processar_documento(pk)
    except Documento.DoesNotExist:
        raise Http404("Documento não encontrado.")
    except DocumentoEmProcessamentoError as exc:
        messages.info(request, str(exc))
    except Exception:
        # Só falhas excepcionais escapam do serviço (ex.: banco indisponível).
        logger.exception("Falha inesperada ao processar o documento %s pela interface.", pk)
        messages.error(request, MENSAGEM_FALHA_INESPERADA)
    else:
        if documento.status == Documento.Status.CONCLUIDO:
            messages.success(request, MENSAGEM_PROCESSAMENTO_CONCLUIDO)
        elif documento.status == Documento.Status.ERRO:
            messages.error(request, MENSAGEM_PROCESSAMENTO_FALHOU)

    return redirect("documento_detalhe", pk=pk)
