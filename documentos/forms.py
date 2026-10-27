from django import forms
from django.conf import settings

from .validators import validar_pdf

TAMANHO_MAXIMO_GEMINI_API_KEY = 256


class DocumentoUploadForm(forms.Form):
    def __init__(self, *args, upload_interrompido=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.upload_interrompido = upload_interrompido

    def clean(self):
        dados = super().clean()
        if self.upload_interrompido:
            # O parser descartou o arquivo: informar o limite, não pedir que
            # selecione um PDF como se nenhum tivesse sido enviado.
            self.errors.pop("arquivo", None)
            self.add_error("arquivo", f"O arquivo excede o limite de {settings.MAX_PDF_UPLOAD_SIZE_MB} MB.")
        return dados

    # A chave só é usada na requisição atual. PasswordInput sem render_value:
    # o valor enviado nunca volta no HTML. O formato não é validado aqui;
    # quem valida a chave é a própria API do Gemini.
    gemini_api_key = forms.CharField(
        label="Gemini API Key",
        max_length=TAMANHO_MAXIMO_GEMINI_API_KEY,
        strip=True,
        help_text="A chave é utilizada somente durante este processamento e não é armazenada.",
        widget=forms.PasswordInput(
            attrs={
                "class": "formulario__campo",
                "autocomplete": "off",
                "autocapitalize": "off",
                "spellcheck": "false",
            }
        ),
        error_messages={
            "required": "Informe a Gemini API Key.",
            "max_length": (
                f"A Gemini API Key deve ter no máximo "
                f"{TAMANHO_MAXIMO_GEMINI_API_KEY} caracteres."
            ),
        },
    )
    arquivo = forms.FileField(
        error_messages={
            "required": "Selecione um arquivo PDF.",
            "empty": "O arquivo PDF está vazio.",
        }
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        return validar_pdf(arquivo)
