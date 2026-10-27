import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required

from .forms import DocumentoUploadForm
from .consultas import consultar_resultado
from .processamento import ProcessamentoError, processar_pdf

ROTULOS_TIPO_DESPESA = {
    "MANUTENCAO_E_OPERACAO": "Manutenção e operação",
    "INFRAESTRUTURA_E_UTILIDADES": "Infraestrutura e utilidades",
}

AVISOS_VALIDACAO = (
    ("fornecedor_cpf", "CPF do fornecedor com dígitos verificadores inválidos."),
    ("chave_acesso", "Chave de acesso inválida. Confira o documento antes da confirmação."),
    ("fornecedor_cnpj", "CNPJ do fornecedor com dígitos verificadores inválidos."),
    ("faturado_cpf", "CPF do faturado com dígitos verificadores inválidos."),
    ("faturado_cnpj", "CNPJ do faturado com dígitos verificadores inválidos."),
)

SUGESTAO_ERRO_PADRAO = "Tente novamente. Se o problema persistir, avise a equipe."
SUGESTOES_ERRO = {
    "documento_ilegivel": "Envie o arquivo PDF novamente.",
    "servico_indisponivel": (
        "Confira se a Gemini API Key informada é válida. Tente novamente mais tarde."
    ),
    "resposta_invalida": "Confira se o arquivo enviado é uma nota fiscal válida.",
    "classificacao_invalida": "Tente novamente.",
    "classificacao_inconclusiva": (
        "Os itens da nota não se encaixaram nas categorias de despesa "
        "disponíveis no MVP (Manutenção e operação; Infraestrutura e utilidades)."
    ),
    "erro_interno": SUGESTAO_ERRO_PADRAO,
}


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
    fornecedor = resultado["fornecedor"]
    tipo = resultado["tipo_despesa"]
    return {
        "tipo_despesa": ROTULOS_TIPO_DESPESA.get(tipo, tipo),
        "valor_total": _formatar_moeda(resultado["valor_total"]),
        "quantidade_parcelas": resultado["quantidade_parcelas"],
        "fornecedor": fornecedor["razao_social"] or fornecedor["nome_fantasia"],
        "numero_nota": resultado["numero_nota"],
        "data_emissao": _formatar_data(resultado["data_emissao"]),
    }


def _avisos_validacao(resultado):
    validacoes = resultado["validacoes"]
    return [
        aviso
        for chave, aviso in AVISOS_VALIDACAO
        if validacoes.get(chave, {}).get("status") == "invalido"
    ]


def _linhas_consultas(consultas):
    rotulos = {
        "EXISTE": "EXISTE", "NAO_EXISTE": "NÃO EXISTE",
        "DOCUMENTO_AUSENTE": "DOCUMENTO AUSENTE", "DOCUMENTO_INVALIDO": "DOCUMENTO INVÁLIDO",
        "CLASSIFICACAO_AUSENTE": "AGUARDANDO CLASSIFICAÇÃO",
    }
    linhas = []
    for rotulo, consulta in (
        ("Fornecedor", consultas.fornecedor), ("Faturado", consultas.faturado),
        ("Classificação", consultas.classificacao),
    ):
        linhas.append({
            "rotulo": rotulo, "situacao": rotulos[consulta.situacao], "id": consulta.id,
            "nome": (getattr(consulta, "razao_social", None) or getattr(consulta, "nome", None)
                     or getattr(consulta, "descricao", None) or getattr(consulta, "codigo", None)),
            "status": consulta.status, "status_papel": getattr(consulta, "status_papel", None),
        })
    return linhas


@sensitive_variables("gemini_api_key")
def _processar(arquivo, gemini_api_key):
    """Processa o PDF validado e devolve o contexto do resultado ou do erro.

    A chave só é repassada; não entra no contexto do template.
    """
    try:
        processamento = processar_pdf(arquivo.read(), gemini_api_key)
    except ProcessamentoError as exc:
        return {
            "erro": {
                "mensagem": exc.mensagem,
                "sugestao": SUGESTOES_ERRO.get(exc.codigo, SUGESTAO_ERRO_PADRAO),
            }
        }

    resultado = processamento.resultado
    contexto = {
        "resumo": _resumo(resultado),
        "aguardando_classificacao": processamento.situacao == "AGUARDANDO_CLASSIFICACAO",
        "avisos": _avisos_validacao(resultado),
        "justificativa": processamento.justificativa,
        # Ordem do contrato: a de montar_resultado (dict preserva a inserção).
        "json_resultado": json.dumps(resultado, ensure_ascii=False, indent=2),
    }
    try:
        contexto["consultas"] = _linhas_consultas(consultar_resultado(resultado))
    except (ValidationError, TypeError, ValueError):
        contexto["erro_consultas"] = (
            "Revise os dados extraídos antes da consulta. Se CPF e CNPJ estiverem "
            "preenchidos no faturado, a identificação precisa ser esclarecida."
        )
    except DatabaseError:
        contexto["erro_consultas"] = "Não foi possível consultar os cadastros agora. Os dados extraídos foram preservados."
    return contexto


@sensitive_post_parameters("gemini_api_key")
@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_variables("gemini_api_key")
def documento_inicio(request):
    """Tela única: envio da chave e do PDF, processamento e resultado na mesma resposta.

    Nada é gravado: o PDF é lido em memória, a Gemini API Key só é repassada
    ao processamento e o resultado só é renderizado.
    """
    contexto = {"limite_upload_mb": settings.MAX_PDF_UPLOAD_SIZE_MB}

    if request.method == "POST":
        form = DocumentoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = form.cleaned_data["arquivo"]
            gemini_api_key = form.cleaned_data["gemini_api_key"]
            contexto["nome_arquivo"] = arquivo.name
            contexto.update(_processar(arquivo, gemini_api_key))
            # Formulário novo e vazio: a próxima execução exige a chave de novo.
            form = DocumentoUploadForm()
    else:
        form = DocumentoUploadForm()

    contexto["form"] = form
    return render(request, "documentos/inicio.html", contexto)
