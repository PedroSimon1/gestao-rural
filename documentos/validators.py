from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename


ALLOWED_PDF_CONTENT_TYPES = {"application/pdf"}


def validar_pdf(arquivo):
    nome_original = Path(arquivo.name.replace("\\", "/")).name

    if not nome_original.lower().endswith(".pdf"):
        raise ValidationError("Selecione um arquivo PDF.")

    if arquivo.size == 0:
        raise ValidationError("O arquivo PDF está vazio.")

    if arquivo.size > settings.MAX_PDF_UPLOAD_SIZE:
        raise ValidationError(
            f"O arquivo excede o limite de "
            f"{settings.MAX_PDF_UPLOAD_SIZE_MB} MB."
        )

    if arquivo.content_type not in ALLOWED_PDF_CONTENT_TYPES:
        raise ValidationError("O tipo do arquivo enviado não é PDF.")

    arquivo.seek(0)
    cabecalho = arquivo.read(5)
    arquivo.seek(0)

    if cabecalho != b"%PDF-":
        raise ValidationError("O arquivo enviado não é um PDF válido.")

    arquivo.name = get_valid_filename(nome_original)

    return arquivo
