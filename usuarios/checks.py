"""Verificações de implantação do login compartilhado (auditoria M-01)."""
from django.conf import settings
from django.core.checks import Tags, Warning, register

TAMANHO_MINIMO_DA_SENHA = 12


@register(Tags.security, deploy=True)
def senha_da_demonstracao_curta(app_configs, **kwargs):
    senha = getattr(settings, "DEMO_PASSWORD", None)
    if isinstance(senha, str) and senha.strip() and len(senha) < TAMANHO_MINIMO_DA_SENHA:
        return [Warning(
            f"DEMO_PASSWORD tem menos de {TAMANHO_MINIMO_DA_SENHA} caracteres.",
            hint="O sistema inteiro fica atrás desta senha única: use uma senha longa e aleatória.",
            id="usuarios.W001",
        )]
    return []
