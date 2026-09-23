from django.contrib.admin.views.decorators import staff_member_required
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .forms import DocumentoUploadForm
from .models import Documento


@staff_member_required
@require_POST
def upload_documento(request):
    form = DocumentoUploadForm(request.POST, request.FILES)

    if not form.is_valid():
        mensagem = form.errors.get("arquivo", ["Arquivo inválido."])[0]
        return JsonResponse({"erro": str(mensagem)}, status=400)

    arquivo = form.cleaned_data["arquivo"]
    documento = Documento(
        arquivo=arquivo,
        nome_original=arquivo.name,
    )

    try:
        documento.save()
    except (DatabaseError, OSError):
        # Se o arquivo foi gravado antes da falha no banco, remova-o.
        if documento.arquivo._committed:
            try:
                documento.arquivo.delete(save=False)
            except OSError:
                pass
        return JsonResponse(
            {"erro": "Não foi possível salvar o documento."},
            status=500,
        )

    return JsonResponse(
        {
            "id": documento.pk,
            "nome_original": documento.nome_original,
            "status": documento.status,
        },
        status=201,
    )
