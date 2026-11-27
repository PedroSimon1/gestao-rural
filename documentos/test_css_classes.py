"""Toda classe fixa usada nos templates tem regra na folha de estilo (evita classe órfã, como `.mono` já foi)."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "documentos" / "static" / "documentos" / "documentos.css"

# Classes que existem só como gancho (script, teste ou marcação) e propositalmente não têm estilo.
SEM_ESTILO = set()


def classes_do_css():
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)
    return set(re.findall(r"\.([a-zA-Z_][\w-]*)", re.sub(r"\{[^}]*\}", "{}", css)))


def classes_dos_templates():
    usadas = {}
    for arquivo in Path(settings.BASE_DIR).glob("*/templates/**/*.html"):
        texto = arquivo.read_text()
        for valor in re.findall(r'class="([^"]*)"', texto):
            valor = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", " ", valor)
            for classe in valor.split():
                if re.fullmatch(r"[a-zA-Z_][\w-]*[a-zA-Z0-9_]", classe):
                    usadas.setdefault(classe, set()).add(arquivo.name)
    return usadas


class ClassesDosTemplatesTests(SimpleTestCase):
    def test_toda_classe_fixa_dos_templates_tem_regra_no_css(self):
        definidas = classes_do_css() | SEM_ESTILO
        orfas = {c: sorted(a) for c, a in classes_dos_templates().items() if c not in definidas}
        self.assertEqual(orfas, {})
