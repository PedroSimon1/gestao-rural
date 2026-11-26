"""Peças de interface reutilizáveis nos templates."""
from django import template
from django.utils.html import format_html

register = template.Library()

# Texto exibido -> tom visual. Desconhecido fica neutro.
TONS = {
    "ativo": "ok", "ativa": "ok", "confirmado": "ok", "a receber": "ok",
    "a pagar": "pagar", "pendente": "atencao",
    "inativo": "neutro", "inativa": "neutro", "cancelado": "neutro", "cancelada": "neutro",
}


@register.simple_tag
def situacao(texto, tom=None):
    """Situação em texto com contorno (a cor só reforça o texto): `{% situacao pessoa.get_status_display %}`."""
    tom = tom or TONS.get(str(texto).strip().lower(), "neutro")
    return format_html('<span class="sit sit--{}">{}</span>', tom, texto)
