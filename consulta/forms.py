from copy import deepcopy

from django import forms

from documentos.forms import DocumentoUploadForm

from .servico import MODO_SIMPLES, MODOS

TAMANHO_MAXIMO_PERGUNTA = 500


def _campo_da_chave(ajuda):
    # Mesmo tratamento do envio de nota (PasswordInput sem render_value, autocomplete desligado, limite de tamanho).
    campo = deepcopy(DocumentoUploadForm.base_fields["gemini_api_key"])
    campo.help_text = ajuda
    return campo


class RadioComDescricao(forms.RadioSelect):
    """Rádio em que cada opção leva um texto curto de explicação (`radio.data.descricao` no template)."""

    def __init__(self, *args, descricoes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.descricoes = descricoes or {}

    def create_option(self, name, value, *args, **kwargs):
        opcao = super().create_option(name, value, *args, **kwargs)
        opcao["descricao"] = self.descricoes.get(value, "")
        if opcao["descricao"]:
            opcao["attrs"]["aria-describedby"] = f'{opcao["attrs"]["id"]}_descricao'
        return opcao


class ConsultaForm(forms.Form):
    pergunta = forms.CharField(
        label="Pergunta",
        max_length=TAMANHO_MAXIMO_PERGUNTA,
        strip=True,
        help_text=f"Até {TAMANHO_MAXIMO_PERGUNTA} caracteres. Ex.: quanto gastei com ração neste ano?",
        widget=forms.Textarea(attrs={"class": "formulario__campo", "rows": 4}),
        error_messages={
            "required": "Digite a pergunta.",
            "max_length": f"A pergunta deve ter no máximo {TAMANHO_MAXIMO_PERGUNTA} caracteres.",
        },
    )
    modo = forms.ChoiceField(
        label="Forma de busca",
        choices=[(codigo, modo.rotulo) for codigo, modo in MODOS.items()],
        initial=MODO_SIMPLES,
        widget=RadioComDescricao(descricoes={codigo: modo.descricao for codigo, modo in MODOS.items()}),
        error_messages={
            "required": "Escolha uma forma de busca.",
            "invalid_choice": "Escolha uma forma de busca válida.",
        },
    )
    gemini_api_key = _campo_da_chave("A chave é utilizada somente nesta consulta e não é armazenada.")


class IndiceForm(forms.Form):
    """Só a chave: "Atualizar índice" não recebe mais nada da tela."""

    gemini_api_key = _campo_da_chave("A chave é utilizada somente para atualizar o índice e não é armazenada.")

    def __init__(self, *args, **kwargs):
        # Outro formulário da mesma página já usa o campo gemini_api_key: ids próprios evitam duplicidade.
        kwargs.setdefault("auto_id", "id_indice_%s")
        super().__init__(*args, **kwargs)
