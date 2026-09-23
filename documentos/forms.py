from django import forms

from .validators import validar_pdf


class DocumentoUploadForm(forms.Form):
    arquivo = forms.FileField(
        error_messages={"required": "Selecione um arquivo PDF."}
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        return validar_pdf(arquivo)