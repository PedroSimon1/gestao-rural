from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

from usuarios.demo import demo_login_required

from .forms import DocumentoUploadForm

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


@demo_login_required
@require_GET
def documento_inicio(request):
    """Tela de envio da chave e do PDF; o envio vai para analise_criar (views_analises)."""
    return render(request, "documentos/inicio.html", {
        "form": DocumentoUploadForm(),
        "limite_upload_mb": settings.MAX_PDF_UPLOAD_SIZE_MB,
    })
