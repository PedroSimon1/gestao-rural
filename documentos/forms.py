from django import forms


class DocumentoUploadForm(forms.Form):
    arquivo = forms.FileField(
        error_messages={"required": "Selecione um arquivo PDF."}
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]

        if not arquivo.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Selecione um arquivo PDF.")

        arquivo.seek(0)
        cabecalho = arquivo.read(5)
        arquivo.seek(0)

        if cabecalho != b"%PDF-":
            raise forms.ValidationError("O arquivo enviado não é um PDF válido.")

        return arquivo
