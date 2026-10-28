"""SHA do deploy fornecido pelo Render; não executa Git nem consulta serviços."""
import os
import re

from django import template

register = template.Library()


@register.simple_tag
def commit_publicado():
    sha = os.getenv('RENDER_GIT_COMMIT', '').strip()
    return sha.lower() if re.fullmatch(r'[0-9a-fA-F]{40}', sha) else ''
