"""Dependências entre apps: `financeiro` e `cadastros` não importam `documentos` (nem `agents`).

`documentos` orquestra a nota fiscal e usa `financeiro` e `cadastros`; a volta criaria um ciclo.
O que os dois lados dividem (CPF/CNPJ, código da sessão) fica em `comum/`.
"""
import ast
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
PROIBIDOS = {"financeiro": {"documentos", "agents"}, "cadastros": {"documentos", "agents", "financeiro"}}


def importados(arquivo):
    arvore = ast.parse(arquivo.read_text())
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            yield from (alias.name.split(".")[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            yield no.module.split(".")[0]


class DependenciasEntreAppsTests(SimpleTestCase):
    def test_codigo_de_producao_nao_importa_o_app_que_o_usa(self):
        for app, proibidos in PROIBIDOS.items():
            arquivos = [a for a in (RAIZ / app).rglob("*.py") if not a.name.startswith("test_") and "migrations" not in a.parts]
            self.assertTrue(arquivos, app)
            for arquivo in arquivos:
                with self.subTest(arquivo=str(arquivo.relative_to(RAIZ))):
                    self.assertEqual(set(importados(arquivo)) & proibidos, set())
