import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from usuarios.demo import demo_login_required

from .forms import DocumentoUploadForm
from .processamento import ProcessamentoError, processar_pdf

ROTULOS_TIPO_DESPESA = {
    "MANUTENCAO_E_OPERACAO": "Manutenção e operação",
    "INFRAESTRUTURA_E_UTILIDADES": "Infraestrutura e utilidades",
}

AVISOS_VALIDACAO = (
    ("fornecedor_cnpj", "CNPJ do fornecedor com dígitos verificadores inválidos."),
    ("faturado_cpf", "CPF do faturado com dígitos verificadores inválidos."),
)

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
        if validacoes[chave]["status"] == "invalido"
    ]


def _processar(arquivo):
    """Processa o PDF validado e devolve o contexto do resultado ou do erro."""
    try:
        processamento = processar_pdf(arquivo.read())
    except ProcessamentoError as exc:
        return {
            "erro": {
                "mensagem": exc.mensagem,
                "sugestao": SUGESTOES_ERRO.get(exc.codigo, SUGESTAO_ERRO_PADRAO),
            }
        }

    resultado = processamento.resultado
    return {
        "resumo": _resumo(resultado),
        "avisos": _avisos_validacao(resultado),
        "justificativa": processamento.justificativa,
        # Ordem do contrato: a de montar_resultado (dict preserva a inserção).
        "json_resultado": json.dumps(resultado, ensure_ascii=False, indent=2),
    }


@demo_login_required
@require_http_methods(["GET", "POST"])
def documento_inicio(request):
    """Tela única: envio do PDF, processamento e resultado na mesma resposta.

    Nada é gravado: o PDF é lido em memória e o resultado só é renderizado.
    """
    contexto = {"limite_upload_mb": settings.MAX_PDF_UPLOAD_SIZE_MB}

    if request.method == "POST":
        form = DocumentoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = form.cleaned_data["arquivo"]
            contexto["nome_arquivo"] = arquivo.name
            contexto.update(_processar(arquivo))
    else:
        form = DocumentoUploadForm()

    contexto["form"] = form
    return render(request, "documentos/inicio.html", contexto)
